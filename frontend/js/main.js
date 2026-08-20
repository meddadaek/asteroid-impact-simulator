/* ===========================================================================
   Orbital Sentinel -- application entry point.

   Owns the render loop, the input wiring, and the flow from a form submission
   to a rendered impact.
   =========================================================================== */

import * as THREE from 'three';
import { api } from './api.js';
import { createEarth, loadTextures, latLonToVec3, vec3ToLatLon, EARTH_RADIUS }
  from './earth.js';
import { createStage, AU_UNITS } from './scene.js';
import { createOverlay } from './overlay.js';
import { createSystem, toScene } from './system.js';
import * as ui from './ui.js';
import { t, setLang, apply as applyI18n } from './i18n.js';

const $ = id => document.getElementById(id);

const state = {
  mode: 'simple',
  lat: 36.75,
  lon: 3.06,
  selectedNeo: null,
  busy: false,
  lastResult: null,
};

/* ======================================================== scene assembly */
const stage = createStage($('stage'));
const earthGroup = new THREE.Group();
stage.earthScene.add(earthGroup);

let earth = null;
let overlay = null;
const system = createSystem(stage.systemScene);

/* -------------------------------------------------------------- boot ---- */
async function boot() {
  const status = $('boot-status');

  status.textContent = t('boot.textures');
  const textures = await loadTextures((p, name) => {
    status.textContent = `${t('boot.textures')} ${Math.round(p * 100)}%`;
  });

  status.textContent = t('boot.globe');
  earth = createEarth(textures);
  earthGroup.add(earth.group);
  overlay = createOverlay(earthGroup);

  status.textContent = t('boot.service');
  try {
    const health = await api.health();
    if (!health.models_loaded) {
      ui.toast(t('err.noModels'), true);
    }
  } catch (e) {
    ui.toast(t('err.backend', { msg: e.message }));
  }

  loadNeoList('');
  updateTerrain();

  $('boot').classList.add('gone');
  animate();
}

/* ==================================================== the render loop === */
const clock = new THREE.Clock();

let paused = false;

function animate() {
  requestAnimationFrame(animate);
  // While paused the loop keeps draining the clock but advances nothing, so
  // manual stepping stays deterministic no matter how long a frame takes.
  const dt = Math.min(clock.getDelta(), 0.1);
  if (!paused) frame(dt);
}

/** One simulation + render step. Split out from the rAF loop so it can be
 *  driven manually -- browsers suspend requestAnimationFrame entirely while a
 *  tab is hidden, which otherwise freezes the scene mid-animation. */
function frame(dt) {
  if (earth) {
    earth.update(dt);
    earthGroup.rotation.y += dt * 0.014;
    // keep the terminator anchored in world space as the globe turns
    const sun = stage.sunLight.position.clone().normalize();
    earth.setSunDirection(sun);
  }
  if (overlay) overlay.update(dt);
  system.update(dt);

  stage.render(dt);
}

/* ================================================== picking on the globe */
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let dragged = false;

$('stage').addEventListener('pointerdown', () => { dragged = false; });
$('stage').addEventListener('pointermove', e => {
  dragged = true;
  if (stage.view !== 'earth' || !earth || state.mode !== 'simple') return;
  hover(e);
});
$('stage').addEventListener('pointerleave', () => {
  $('tooltip').classList.remove('on');
});
$('stage').addEventListener('pointerup', e => {
  if (dragged || stage.view !== 'earth' || !earth) return;
  if (state.mode !== 'simple') return;
  const hit = pick(e);
  if (hit) {
    setCoords(hit.lat, hit.lon);
    updateTerrain();
  }
});

function pick(event) {
  pointer.x = (event.clientX / innerWidth) * 2 - 1;
  pointer.y = -(event.clientY / innerHeight) * 2 + 1;
  raycaster.setFromCamera(pointer, stage.earthCam);
  const hits = raycaster.intersectObject(earth.surface, false);
  if (!hits.length) return null;
  // bring the hit back into the globe's own frame before reading coordinates
  const local = earthGroup.worldToLocal(hits[0].point.clone());
  return vec3ToLatLon(local);
}

function hover(event) {
  const tip = $('tooltip');
  const hit = pick(event);
  if (!hit) { tip.classList.remove('on'); return; }
  tip.textContent = `${hit.lat.toFixed(2)}°, ${hit.lon.toFixed(2)}°`;
  tip.style.left = `${event.clientX + 14}px`;
  tip.style.top = `${event.clientY + 14}px`;
  tip.style.transform = '';
  tip.classList.add('on');
}

/* ==================================================== input plumbing === */
function sliderPct(el) {
  const min = parseFloat(el.min), max = parseFloat(el.max);
  el.style.setProperty('--pct',
    `${((parseFloat(el.value) - min) / (max - min)) * 100}%`);
}

/* diameter slider is logarithmic: 10^0 = 1 m to 10^4.3 = 20 km */
function diameterValue() {
  return Math.pow(10, parseFloat($('in-diameter').value));
}
function setDiameter(metres) {
  $('in-diameter').value = Math.log10(
    Math.max(1, Math.min(20000, metres))).toFixed(3);
  syncDiameter();
}
function syncDiameter() {
  const d = diameterValue();
  $('v-diameter').textContent = d >= 1000
    ? `${(d / 1000).toFixed(2)} km` : `${d.toFixed(d < 10 ? 1 : 0)} m`;
  sliderPct($('in-diameter'));
}

$('in-diameter').addEventListener('input', syncDiameter);
$('in-velocity').addEventListener('input', e => {
  $('v-velocity').textContent = `${parseFloat(e.target.value).toFixed(1)} km/s`;
  sliderPct(e.target);
});
$('in-angle').addEventListener('input', e => {
  $('v-angle').textContent = `${e.target.value}°`;
  sliderPct(e.target);
});
$('in-clones').addEventListener('input', e => {
  $('v-clones').textContent = e.target.value;
  sliderPct(e.target);
});

['in-lat', 'in-lon'].forEach(id => $(id).addEventListener('change', () => {
  state.lat = parseFloat($('in-lat').value) || 0;
  state.lon = parseFloat($('in-lon').value) || 0;
  updateTerrain();
}));

function setCoords(lat, lon) {
  state.lat = lat; state.lon = lon;
  $('in-lat').value = lat.toFixed(3);
  $('in-lon').value = lon.toFixed(3);
}

let terrainTimer = null;
function updateTerrain() {
  clearTimeout(terrainTimer);
  terrainTimer = setTimeout(async () => {
    try {
      const info = await api.terrain(state.lat, state.lon);
      const near = info.nearest_cities[0];
      $('terrain-readout').innerHTML = `
        <div><span class="k">${t('ro.surface')}</span>
          <span class="v">${info.on_land ? t('ro.land') : t('ro.ocean')}</span></div>
        ${near ? `<div><span class="k">${t('ro.nearest')}</span>
          <span class="v">${near.name}, ${near.country}
          <bdi>${Math.round(near.distance_km)}</bdi> ${t('unit.km')}</span></div>` : ''}`;
    } catch { /* offline: leave the previous reading in place */ }
  }, 180);
}

/* ---- mode tabs ---- */
document.querySelectorAll('.mode-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.mode = b.dataset.mode;
    $('mode-simple').hidden = state.mode !== 'simple';
    $('mode-orbit').hidden = state.mode !== 'orbit';
    setView(state.mode === 'orbit' ? 'system' : 'earth');
  });
});

/* ---- view tabs ---- */
document.querySelectorAll('.view-btn').forEach(b => {
  b.addEventListener('click', () => setView(b.dataset.view));
});

function setView(v) {
  document.querySelectorAll('.view-btn')
    .forEach(x => x.classList.toggle('active', x.dataset.view === v));
  stage.setView(v);
}

$('close-right').addEventListener('click', () => ui.showResults(false));

/* ---- language ---- */
document.querySelectorAll('.lang-btn').forEach(b => {
  b.addEventListener('click', () => setLang(b.dataset.lang));
});

// Redraw what is already on screen in the new language. The payload is kept,
// so switching costs no network round trip and no re-simulation.
document.addEventListener('langchange', () => {
  loadNeoList($('neo-search').value);
  updateTerrain();
  if (state.lastResult && state.lastResult.physics) {
    presentImpact(state.lastResult, state.lastSourceKey || 'res.outcome',
                  { keepOrbit: !$('sec-orbit').hidden, textOnly: true });
  }
});

/* ---- historical presets ---- */
const PRESETS = {
  chelyabinsk: { d: 19, mat: 'stony', v: 19.2, ang: 18, lat: 55.15, lon: 61.4 },
  tunguska:    { d: 60, mat: 'carbonaceous', v: 20, ang: 45, lat: 60.9, lon: 101.9 },
  barringer:   { d: 50, mat: 'iron', v: 12.8, ang: 45, lat: 35.03, lon: -111.02 },
  chicxulub:   { d: 14000, mat: 'stony', v: 20, ang: 60, lat: 21.4, lon: -89.5 },
};

document.querySelectorAll('.chip').forEach(c => {
  c.addEventListener('click', () => {
    const p = PRESETS[c.dataset.preset];
    if (!p) return;
    setDiameter(p.d);
    $('in-material').value = p.mat;
    $('in-velocity').value = p.v;
    $('in-velocity').dispatchEvent(new Event('input'));
    $('in-angle').value = p.ang;
    $('in-angle').dispatchEvent(new Event('input'));
    setCoords(p.lat, p.lon);
    updateTerrain();
    // presets describe a strike, so force simple mode
    document.querySelector('.mode-btn[data-mode="simple"]').click();
    run();
  });
});

/* ---- NEO catalogue ---- */
let neoTimer = null;
$('neo-search').addEventListener('input', e => {
  clearTimeout(neoTimer);
  neoTimer = setTimeout(() => loadNeoList(e.target.value), 250);
});

async function loadNeoList(query) {
  try {
    const res = await api.neos(query, 60);
    const list = $('neo-list');
    if (!res.objects.length) {
      list.innerHTML = `<p class="note">${t('note.nothingMatches')}</p>`;
      return;
    }
    list.innerHTML = res.objects.map((o, i) => `
      <div class="neo-item" data-i="${i}">
        <div>
          <div class="neo-name">${o.name}</div>
          <div class="neo-meta">a ${o.a.toFixed(2)} · e ${o.e.toFixed(2)}
            · ${o.diameter_m ? Math.round(o.diameter_m) + ' m' : 'size unknown'}
            ${o.moid_au !== null ? ' · MOID ' + o.moid_au.toFixed(4) : ''}</div>
        </div>
        ${o.pha ? '<span class="neo-tag tag-pha">PHA</span>' : ''}
      </div>`).join('');

    list.querySelectorAll('.neo-item').forEach(el => {
      el.addEventListener('click', () => {
        list.querySelectorAll('.neo-item').forEach(x => x.classList.remove('sel'));
        el.classList.add('sel');
        applyNeo(res.objects[parseInt(el.dataset.i, 10)]);
      });
    });
  } catch (e) {
    $('neo-list').innerHTML = `<p class="note">${t('err.catalogue', { msg: e.message })}</p>`;
  }
}

function applyNeo(o) {
  state.selectedNeo = o;
  $('el-a').value = o.a.toFixed(6);
  $('el-e').value = o.e.toFixed(6);
  $('el-i').value = o.i.toFixed(4);
  $('el-om').value = o.om.toFixed(4);
  $('el-w').value = o.w.toFixed(4);
  $('el-ma').value = o.ma.toFixed(4);
  if (o.diameter_m) setDiameter(o.diameter_m);
}

/* ======================================================= run the model = */
$('run').addEventListener('click', run);

async function run() {
  if (state.busy) return;
  state.busy = true;
  const btn = $('run');
  btn.classList.add('busy');
  btn.disabled = true;
  const t0 = performance.now();

  try {
    if (state.mode === 'simple') await runSimple();
    else await runOrbit();
    ui.setTiming(Math.round(performance.now() - t0));
  } catch (e) {
    ui.toast(e.message || t('err.failed'));
  } finally {
    state.busy = false;
    btn.classList.remove('busy');
    btn.disabled = false;
  }
}

function impactorPayload() {
  return {
    diameter_m: diameterValue(),
    material: $('in-material').value,
  };
}

async function runSimple() {
  const res = await api.simulateSimple({
    ...impactorPayload(),
    velocity_kms: parseFloat($('in-velocity').value),
    angle_deg: parseFloat($('in-angle').value),
    latitude: state.lat,
    longitude: state.lon,
    azimuth_deg: 0,
  });
  presentImpact(res, 'res.simpleMode');
}

async function runOrbit() {
  const res = await api.simulateElements({
    ...impactorPayload(),
    a: parseFloat($('el-a').value),
    e: parseFloat($('el-e').value),
    i: parseFloat($('el-i').value),
    om: parseFloat($('el-om').value),
    w: parseFloat($('el-w').value),
    ma: parseFloat($('el-ma').value),
    uncertainty: $('in-uncertainty').value,
    n_clones: parseInt($('in-clones').value, 10),
    horizon_years: 30,
    force_impact: $('in-force').checked,
  });
  state.lastResult = res;

  system.show(res.orbit_path, res.earth_path, {
    hazard: (res.risk?.ml_risk_score || 0) > 0.15,
  });

  ui.showResults(true);
  ui.renderOrbit(res);
  ui.renderMonteCarlo(res.monte_carlo);

  if (res.impact) {
    presentImpact(res.impact, 'res.orbitSolution', { keepOrbit: true });
  } else {
    ui.setTitle(t('res.noImpact'), 'res.orbitSolution');
    $('severity').className = 'severity sev-negligible';
    $('severity').innerHTML =
      `<h3>${t('res.clear')}</h3><p>${t('res.clearBody')}</p>`;
    $('stat-grid').innerHTML = '';
    ['sec-location', 'sec-rings', 'sec-cities', 'sec-model']
      .forEach(id => { $(id).hidden = true; });
  }
}

function presentImpact(res, sourceKey, opts = {}) {
  state.lastResult = res;
  state.lastSourceKey = sourceKey;
  const p = res.physics;

  ['sec-location', 'sec-rings', 'sec-cities', 'sec-model']
    .forEach(id => { $(id).hidden = false; });
  if (!opts.keepOrbit) {
    $('sec-orbit').hidden = true;
    $('sec-mc').hidden = true;
  }

  ui.showResults(true);
  ui.setTitle(
    t(p.airburst ? 'res.airburst' : (p.crater ? 'res.cratering' : 'res.surface')),
    sourceKey);
  ui.renderSeverity(p.severity, res.hypothetical);
  ui.renderStats(p);
  ui.renderLocation(res.location, res.exposure);
  ui.renderRings(res.exposure.rings);
  ui.renderCities(res.exposure);
  ui.renderComparison(res.comparison);

  // draw it -- but a language switch only rewrites text, so leave the scene
  if (opts.textOnly) return;
  setView('earth');
  overlay.show(res.location.latitude, res.location.longitude,
               res.exposure.rings, res.location.azimuth_deg || 0,
               res.impactor.angle_deg);

  // swing the camera round to face the impact site
  const dir = latLonToVec3(res.location.latitude, res.location.longitude, 1)
    .normalize()
    .applyAxisAngle(new THREE.Vector3(0, 1, 0), earthGroup.rotation.y);
  // Frame the widest ring while keeping enough of the limb in shot that the
  // globe still reads as a globe -- flying right down onto the site loses all
  // sense of where on Earth it is.
  const widest = Math.max(...res.exposure.rings.map(r => r.radius_km), 200);
  const dist = THREE.MathUtils.clamp(2.6 + widest / 1500, 2.6, 8);
  stage.flyTo(dir.multiplyScalar(dist), new THREE.Vector3(0, 0, 0), 1.5);
}

/* -------------------------------------------------------------- kick off */
[$('in-diameter'), $('in-velocity'), $('in-angle'), $('in-clones')]
  .forEach(sliderPct);
syncDiameter();
applyI18n();

// Debug / capture handle. `step` advances the scene by a fixed timestep, which
// is how documentation stills are rendered without a visible tab.
window.__sentinel = {
  stage,
  step(dt = 1 / 60, count = 1) {
    for (let i = 0; i < count; i++) frame(dt);
  },
  pause(on = true) { paused = on; },
  get paused() { return paused; },
  get earth() { return earth; },
  get overlay() { return overlay; },
  get lastResult() { return state.lastResult; },
};

boot().catch(e => {
  $('boot-status').textContent = `failed: ${e.message}`;
  console.error(e);
});
