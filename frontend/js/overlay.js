/* ===========================================================================
   Impact overlay: the marker, the damage rings drawn on the sphere, the
   incoming trajectory, and the detonation animation.

   Everything here is parented to the Earth group, so it rotates with the
   planet and stays locked to its ground coordinates.
   =========================================================================== */

import * as THREE from 'three';
import { EARTH_RADIUS, latLonToVec3 } from './earth.js';

const EARTH_KM = 6371.0;

/** Angular radius on the globe, in radians, for a ground range in km. */
function angularRadius(km) {
  return Math.min(km / EARTH_KM, Math.PI * 0.995);
}

/** An orthonormal pair tangent to the sphere at `c`. */
function tangentFrame(c) {
  const up = Math.abs(c.y) < 0.999 ? new THREE.Vector3(0, 1, 0)
                                   : new THREE.Vector3(1, 0, 0);
  const t1 = new THREE.Vector3().crossVectors(up, c).normalize();
  const t2 = new THREE.Vector3().crossVectors(c, t1).normalize();
  return [t1, t2];
}

/** Point at angular distance `alpha` from `c`, at bearing `theta`. */
function capPoint(c, t1, t2, alpha, theta, radius) {
  const sa = Math.sin(alpha), ca = Math.cos(alpha);
  return new THREE.Vector3()
    .addScaledVector(c, ca)
    .addScaledVector(t1, sa * Math.cos(theta))
    .addScaledVector(t2, sa * Math.sin(theta))
    .multiplyScalar(radius);
}

/* ----------------------------------------------------------- ring bands */
function makeBand(center, aIn, aOut, color, opacity, segments = 160) {
  const [t1, t2] = tangentFrame(center);
  const R = EARTH_RADIUS * 1.0015;
  const pos = [];
  const idx = [];

  for (let i = 0; i <= segments; i++) {
    const th = (i / segments) * Math.PI * 2;
    const pi = capPoint(center, t1, t2, aIn, th, R);
    const po = capPoint(center, t1, t2, aOut, th, R);
    pos.push(pi.x, pi.y, pi.z, po.x, po.y, po.z);
  }
  for (let i = 0; i < segments; i++) {
    const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
    idx.push(a, b, c, b, d, c);
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();

  return new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  }));
}

function makeOutline(center, alpha, color, segments = 220) {
  const [t1, t2] = tangentFrame(center);
  const R = EARTH_RADIUS * 1.003;
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    pts.push(capPoint(center, t1, t2, alpha, (i / segments) * Math.PI * 2, R));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  return new THREE.Line(geo, new THREE.LineBasicMaterial({
    color: new THREE.Color(color), transparent: true, opacity: 0.85,
    depthWrite: false, blending: THREE.AdditiveBlending,
  }));
}

/* --------------------------------------------------------------- marker */
function makeMarker(center) {
  const g = new THREE.Group();
  const dir = center.clone().normalize();

  const core = new THREE.Mesh(
    new THREE.SphereGeometry(0.011, 20, 16),
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );
  core.position.copy(dir).multiplyScalar(EARTH_RADIUS * 1.004);
  g.add(core);

  // a beam standing off the surface, so the site is findable from any angle
  const beamH = 0.42;
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0035, 0.014, beamH, 12, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0xff5a3c, transparent: true, opacity: 0.5,
      depthWrite: false, blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
    })
  );
  beam.position.copy(dir).multiplyScalar(EARTH_RADIUS + beamH / 2);
  beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  g.add(beam);

  return g;
}

/* ----------------------------------------------------------- trajectory */
function makeTrajectory(center, azimuthDeg, entryAngleDeg) {
  const dir = center.clone().normalize();
  const [t1, t2] = tangentFrame(dir);

  // local north/east so the azimuth means what it says
  const north = new THREE.Vector3(0, 1, 0)
    .addScaledVector(dir, -dir.y).normalize();
  const east = new THREE.Vector3().crossVectors(dir, north).normalize();
  const az = azimuthDeg * Math.PI / 180;
  // the track runs *toward* the site along this bearing, so come from behind it
  const horiz = north.clone().multiplyScalar(Math.cos(az))
    .addScaledVector(east, Math.sin(az)).negate();

  const gamma = Math.max(2, entryAngleDeg) * Math.PI / 180;
  const inbound = horiz.clone().multiplyScalar(Math.cos(gamma))
    .addScaledVector(dir, Math.sin(gamma)).normalize();

  const pts = [];
  const len = 2.9;
  for (let i = 0; i <= 80; i++) {
    const s = i / 80;
    // ease the tail upward a little so it reads as a descending arc
    const d = len * Math.pow(1 - s, 1.35);
    pts.push(dir.clone().multiplyScalar(EARTH_RADIUS)
      .addScaledVector(inbound, d));
  }

  const curve = new THREE.CatmullRomCurve3(pts);
  const geo = new THREE.TubeGeometry(curve, 90, 0.0075, 8, false);
  const mat = new THREE.MeshBasicMaterial({
    color: 0xffaa55, transparent: true, opacity: 0.72,
    depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const tube = new THREE.Mesh(geo, mat);

  const head = new THREE.Mesh(
    new THREE.SphereGeometry(0.022, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xfff0d0 })
  );

  return { tube, head, curve, inbound };
}

/* ============================================================== overlay */
export function createOverlay(parent) {
  const root = new THREE.Group();
  parent.add(root);

  let state = null;

  function clear() {
    while (root.children.length) {
      const c = root.children.pop();
      c.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) {
          (Array.isArray(o.material) ? o.material : [o.material])
            .forEach(m => m.dispose());
        }
      });
    }
    state = null;
  }

  /**
   * @param lat,lon      impact coordinates
   * @param rings        [{radius_km, colour, label}] from the API
   * @param azimuth,angle incoming track geometry
   */
  function show(lat, lon, rings, azimuth = 0, angle = 45) {
    clear();
    const center = latLonToVec3(lat, lon, 1).normalize();

    // draw widest first so the tight, bright rings sit on top
    const sorted = [...rings]
      .filter(r => r.radius_km > 0)
      .sort((a, b) => a.radius_km - b.radius_km);

    const bands = [];
    let prev = 0;
    for (const r of sorted) {
      const aOut = angularRadius(r.radius_km);
      const aIn = angularRadius(prev);
      if (aOut - aIn < 1e-5) { prev = r.radius_km; continue; }
      const band = makeBand(center, aIn, aOut, r.colour, 0.0);
      band.userData.targetOpacity = 0.2;
      band.visible = false;
      root.add(band);
      const line = makeOutline(center, aOut, r.colour);
      line.material.opacity = 0;
      line.visible = false;
      root.add(line);
      bands.push({ band, line, radius: r.radius_km });
      prev = r.radius_km;
    }

    const marker = makeMarker(center);
    root.add(marker);

    const traj = makeTrajectory(center, azimuth, angle);
    root.add(traj.tube);
    root.add(traj.head);

    // the flash: a shell that expands and fades once, on arrival
    const flash = new THREE.Mesh(
      new THREE.SphereGeometry(1, 32, 24),
      new THREE.MeshBasicMaterial({
        color: 0xfff2d0, transparent: true, opacity: 0,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    flash.position.copy(center).multiplyScalar(EARTH_RADIUS);
    flash.scale.setScalar(0.001);
    root.add(flash);

    state = {
      center, bands, marker, traj, flash,
      t: 0, phase: 'incoming', maxRadius: sorted.length
        ? angularRadius(sorted[sorted.length - 1].radius_km) : 0,
    };
    return state;
  }

  function update(dt) {
    if (!state) return;
    state.t += dt;

    if (state.phase === 'incoming') {
      // 1.15 s of approach, then detonate
      const k = Math.min(state.t / 1.15, 1);
      const s = k * k;                       // accelerating, as gravity implies
      const p = state.traj.curve.getPoint(s);
      state.traj.head.position.copy(p);
      state.traj.head.scale.setScalar(1 + (1 - k) * 1.4);
      state.traj.tube.material.opacity = 0.72 * (1 - k * 0.55);
      if (k >= 1) { state.phase = 'flash'; state.t = 0; }

    } else if (state.phase === 'flash') {
      const k = Math.min(state.t / 0.85, 1);
      state.traj.head.visible = false;
      state.flash.scale.setScalar(0.02 + k * Math.max(state.maxRadius, 0.06) * 1.5);
      state.flash.material.opacity = (1 - k) * 0.9;
      // rings bloom outward in sequence
      state.bands.forEach((b, i) => {
        const start = i * 0.075;
        const kk = THREE.MathUtils.clamp((k - start) / 0.35, 0, 1);
        if (kk > 0) {
          b.band.visible = true; b.line.visible = true;
          b.band.material.opacity = kk * b.band.userData.targetOpacity;
          b.line.material.opacity = kk * 0.85;
        }
      });
      if (k >= 1) { state.phase = 'settled'; state.t = 0; }

    } else {
      // gentle breathing so the site never looks like a static decal
      const pulse = 0.82 + Math.sin(state.t * 2.1) * 0.18;
      state.bands.forEach(b => {
        b.line.material.opacity = 0.55 + pulse * 0.3;
      });
      state.marker.scale.setScalar(0.94 + pulse * 0.1);
      state.flash.material.opacity = 0;
    }
  }

  return { root, show, clear, update, get state() { return state; } };
}
