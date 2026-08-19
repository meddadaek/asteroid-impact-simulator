/* ===========================================================================
   Results rendering. Pure DOM work: takes an API payload, writes the panel.

   All user-facing wording goes through `t()`. The backend sends stable ids
   alongside its English labels, so nothing here depends on server wording.
   =========================================================================== */

import { t, isRTL } from './i18n.js';

const $ = id => document.getElementById(id);

/* ------------------------------------------------------------ formatting */
export function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 1e15) return v.toExponential(2);
  if (a < 1e-3) return v.toExponential(2);
  return v.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: a >= 100 ? 0 : digits,
  });
}

export function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Math.round(v).toLocaleString('en-US');
}

/** Human distance: metres below 1 km, kilometres above. */
export function fmtDist(km) {
  if (!km || km <= 0) return '—';
  if (km < 1) return `${fmtNum(km * 1000, 0)} ${t('unit.m')}`;
  return `${fmtNum(km, km < 10 ? 2 : 0)} ${t('unit.km')}`;
}

export function fmtEnergy(mt) {
  if (!mt || mt <= 0) return '—';
  if (mt < 1e-3) return `${fmtNum(mt * 1000, 2)} ${t('unit.kt')}`;
  if (mt >= 1e6) return `${fmtNum(mt / 1e6, 2)} ${t('unit.tt')}`;
  return `${fmtNum(mt, mt < 10 ? 2 : 0)} ${t('unit.mt')}`;
}

export function fmtPop(n) {
  if (!n) return '0';
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} ${t('unit.bn')}`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)} ${t('unit.M')}`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)} ${t('unit.k')}`;
  return String(n);
}

const HIROSHIMA_MT = 0.015;

/** Wrap a bare number so it stays left-to-right inside Arabic text. */
function num(s) {
  return isRTL() ? `<bdi>${s}</bdi>` : s;
}

/* --------------------------------------------------------------- panels */
export function renderSeverity(sev, hypothetical) {
  const el = $('severity');
  el.className = `severity sev-${sev.level}`;
  const nukes = fmtNum(sev.energy_mt / HIROSHIMA_MT, 0);
  el.innerHTML = `
    <h3>${t('sev.' + sev.level)}</h3>
    <p>${t('sevDesc.' + sev.level)}</p>
    <p style="margin-top:8px;color:var(--text-mute);font-size:11.5px">
      ${t('res.hiroshima', { n: num(nukes) })}
      ${hypothetical
        ? `<br><em style="color:var(--amber)">${t('res.hypothetical')}</em>`
        : ''}
    </p>`;
}

export function renderStats(physics) {
  const c = physics.crater;
  const stats = [
    { k: t('stat.energy'), v: fmtEnergy(physics.energy_deposited_mt), cls: 'hot' },
    physics.airburst
      ? { k: t('stat.burstAltitude'),
          v: `${fmtNum(physics.burst_altitude_km, 1)}<small>${t('unit.km')}</small>` }
      : { k: t('stat.impactSpeed'),
          v: `${fmtNum(physics.velocity_ground_kms, 1)}<small>${t('unit.kms')}</small>` },
    { k: t('stat.crater'),
      v: c ? fmtDist(c.final_diameter_m / 1000) : t('stat.none'),
      cls: c ? 'crit' : '' },
    { k: t('stat.seismic'), v: `M${fmtNum(physics.seismic.magnitude, 1)}` },
    { k: t('stat.fireball'), v: fmtDist(physics.thermal.fireball_radius_km) },
    { k: t('stat.mass'),
      v: `${fmtNum(physics.mass_kg, 2)}<small>${t('unit.kg')}</small>` },
  ];
  $('stat-grid').innerHTML = stats.map(s => `
    <div class="stat ${s.cls || ''}">
      <div class="k">${s.k}</div><div class="v">${num(s.v)}</div>
    </div>`).join('');
}

export function renderLocation(loc, exposure) {
  const near = exposure.nearest_cities?.[0];
  $('location-readout').innerHTML = `
    <div><span class="k">${t('ro.coordinates')}</span>
      <span class="v">${num(`${loc.latitude.toFixed(3)}°, ${loc.longitude.toFixed(3)}°`)}</span></div>
    <div><span class="k">${t('ro.terrain')}</span>
      <span class="v">${loc.on_land ? t('ro.land') : t('ro.ocean')}</span></div>
    <div><span class="k">${t('ro.bearing')}</span>
      <span class="v">${num(fmtNum(loc.azimuth_deg, 0) + '°')}</span></div>
    ${near ? `<div><span class="k">${t('ro.nearest')}</span>
      <span class="v">${near.name} · ${num(fmtNum(near.distance_km, 0) + ' ' + t('unit.km'))}</span></div>` : ''}`;
}

export function renderRings(rings) {
  if (!rings.length) {
    $('rings').innerHTML = `<p class="note">${t('note.noRings')}</p>`;
    return;
  }
  $('rings').innerHTML = rings.map(r => `
    <div class="ring-row">
      <span class="ring-dot" style="background:${r.colour};
        box-shadow:0 0 10px ${r.colour}"></span>
      <div>
        <div class="ring-label">${t('ring.' + r.id)}</div>
        <div class="ring-sub">${num(fmtNum(r.area_km2, 0))} km²
          · ${num(fmtPop(r.population))}</div>
      </div>
      <div class="ring-val">${num(fmtDist(r.radius_km))}</div>
    </div>`).join('');
}

export function renderCities(exposure) {
  const list = exposure.affected_cities || [];
  const total = exposure.total_population_affected || 0;
  if (!list.length) {
    $('cities').innerHTML = `<p class="note">${t('note.noCity')}
      ${exposure.on_land ? '' : t('note.atSea')}</p>`;
    return;
  }
  $('cities').innerHTML = `
    <div class="ring-row" style="border-bottom:1px solid var(--edge);padding-bottom:9px">
      <span></span>
      <div class="ring-label">${t('res.totalUrban')}</div>
      <div class="ring-val" style="color:var(--red)">${num(fmtPop(total))}</div>
    </div>
    ${list.slice(0, 12).map(c => `
      <div class="city-row">
        <span class="n">${c.name}<span style="color:var(--text-mute)">
          · ${c.country}</span></span>
        <span class="p">${num(fmtPop(c.population))} · ${num(fmtNum(c.distance_km, 0))}
          ${t('unit.km')}</span>
      </div>`).join('')}`;
}

export function renderComparison(rows) {
  const sec = $('sec-model');
  if (!rows || !rows.length) { sec.hidden = true; return; }
  sec.hidden = false;
  $('model-table').innerHTML = `
    <div class="mt">
      <div class="h">${t('mt.quantity')}</div><div class="h">${t('mt.physics')}</div>
      <div class="h">${t('mt.surrogate')}</div><div class="h">${t('mt.err')}</div>
      ${rows.map(r => {
        const cls = r.error_pct < 8 ? 'ok' : r.error_pct < 25 ? 'mid' : 'bad';
        return `<div class="lab">${t('cmp.' + r.id)}</div>
          <div class="num">${num(fmtNum(r.physics, 2))}</div>
          <div class="num">${num(fmtNum(r.surrogate, 2))}</div>
          <div class="err ${cls}">${num(r.error_pct.toFixed(1) + '%')}</div>`;
      }).join('')}
    </div>`;
}

export function renderOrbit(sim) {
  $('sec-orbit').hidden = false;
  const ca = sim.close_approaches?.[0];
  const risk = sim.risk || {};
  $('orbit-readout').innerHTML = `
    <div><span class="k">${t('ro.perihelion')}</span>
      <span class="v">${num(fmtNum(sim.orbit.perihelion_au, 3) + ' ' + t('unit.au'))}</span></div>
    <div><span class="k">${t('ro.aphelion')}</span>
      <span class="v">${num(fmtNum(sim.orbit.aphelion_au, 3) + ' ' + t('unit.au'))}</span></div>
    <div><span class="k">${t('ro.period')}</span>
      <span class="v">${num(fmtNum(sim.orbit.period_years, 2) + ' ' + t('unit.yr'))}</span></div>
    <div><span class="k">${t('ro.moid')}</span>
      <span class="v">${num(risk.moid_au !== undefined
        ? fmtNum(risk.moid_au, 5) + ' ' + t('unit.au') : '—')}</span></div>
    ${ca ? `
    <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--edge)">
      <div><span class="k">${t('ro.closestApproach')}</span>
        <span class="v">${num(fmtNum(ca.distance_km, 0) + ' ' + t('unit.km'))}</span></div>
      <div><span class="k">${t('ro.lunarDistances')}</span>
        <span class="v">${num(fmtNum(ca.distance_lunar, 2) + ' ' + t('unit.ld'))}</span></div>
      <div><span class="k">${t('ro.vInfinity')}</span>
        <span class="v">${num(fmtNum(ca.v_inf_kms, 2) + ' ' + t('unit.kms'))}</span></div>
      <div><span class="k">${t('ro.outcome')}</span>
        <span class="v" style="color:${ca.impact ? 'var(--red)' : 'var(--green)'}">
          ${ca.impact ? t('ro.impact') : t('ro.miss')}</span></div>
    </div>` : ''}
    <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--edge)">
      <div><span class="k">${t('ro.mlRisk')}</span>
        <span class="v">${num(risk.ml_risk_score !== undefined
          ? (risk.ml_risk_score * 100).toFixed(2) + '%' : '—')}</span></div>
    </div>`;
}

export function renderMonteCarlo(mc) {
  const sec = $('sec-mc');
  if (!mc) { sec.hidden = true; return; }
  sec.hidden = false;
  const pct = mc.probability * 100;
  const bar = Math.max(pct, mc.probability > 0 ? 1.5 : 0);
  $('mc-readout').innerHTML = `
    <div class="mc-big">${num((pct < 0.01 && pct > 0
      ? pct.toExponential(1) : pct.toFixed(2)) + '%')}</div>
    <div class="mc-bar"><i style="width:${Math.min(bar, 100)}%"></i></div>
    <div class="mc-sub">
      ${t('mc.struck', { k: num(fmtInt(mc.n_impacts)), n: num(fmtInt(mc.n_clones)),
                         y: num(fmtNum(mc.horizon_years, 0)) })}<br>
      ${t('mc.interval', { lo: num((mc.ci_low * 100).toFixed(3)),
                           hi: num((mc.ci_high * 100).toFixed(3)) })}<br>
      <span style="color:var(--text-dim)">${t('unc.' + mc.uncertainty)}.</span><br>
      ${t('mc.closest', { d: num(fmtNum(mc.closest_clone_km, 0)) })}
    </div>`;
}

export function setTitle(text, eyebrowKey) {
  $('res-title').textContent = text;
  const e = $('res-eyebrow');
  if (eyebrowKey) {
    e.dataset.i18n = eyebrowKey;
    e.textContent = t(eyebrowKey);
  }
}

export function showResults(on) {
  $('panel-right').hidden = !on;
}

export function setTiming(ms) {
  $('timing').textContent = ms === null ? '' : t('timing.roundTrip', { ms });
}

/* --------------------------------------------------------------- toasts */
export function toast(message, isError = true) {
  const el = $('tooltip');
  el.textContent = message;
  el.style.left = '50%';
  el.style.top = '24px';
  el.style.transform = 'translateX(-50%)';
  el.style.borderColor = isError ? 'var(--red)' : 'var(--edge-hot)';
  el.classList.add('on');
  clearTimeout(toast._h);
  toast._h = setTimeout(() => {
    el.classList.remove('on');
    el.style.transform = '';
  }, 3600);
}
