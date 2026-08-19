/* ===========================================================================
   Heliocentric view: the asteroid's orbit against Earth's, with the encounter
   marked. This is where an eccentric, inclined orbit stops being six numbers
   and becomes an obviously Earth-crossing path.

   The backend works in the J2000 ecliptic frame (Z out of the ecliptic plane);
   Three.js wants Y up, so every incoming vector goes through `toScene`.
   =========================================================================== */

import * as THREE from 'three';
import { AU_UNITS } from './scene.js';

/** Ecliptic (x, y, z) in AU to scene coordinates. */
export function toScene(p) {
  return new THREE.Vector3(p[0] * AU_UNITS, p[2] * AU_UNITS, -p[1] * AU_UNITS);
}

function polyline(points, color, opacity = 1, width = 1) {
  const geo = new THREE.BufferGeometry().setFromPoints(points);
  return new THREE.Line(geo, new THREE.LineBasicMaterial({
    color: new THREE.Color(color), transparent: true, opacity,
    linewidth: width, depthWrite: false,
  }));
}

function glowSphere(radius, color, emissive = 1.6) {
  const m = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 24, 18),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(color) })
  );
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(radius * 2.6, 20, 14),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color(color), transparent: true, opacity: 0.22,
      depthWrite: false, blending: THREE.AdditiveBlending,
    })
  );
  m.add(halo);
  m.userData.emissive = emissive;
  return m;
}

export function createSystem(scene) {
  const root = new THREE.Group();
  scene.add(root);

  /* ---- ecliptic reference grid ---- */
  const grid = new THREE.PolarGridHelper(AU_UNITS * 3.2, 8, 6, 96,
                                         0x1b3a5c, 0x14293f);
  grid.material.transparent = true;
  grid.material.opacity = 0.3;
  grid.material.depthWrite = false;
  root.add(grid);

  let dynamic = new THREE.Group();
  root.add(dynamic);

  let anim = null;

  function clear() {
    root.remove(dynamic);
    dynamic.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        (Array.isArray(o.material) ? o.material : [o.material])
          .forEach(m => m.dispose());
      }
    });
    dynamic = new THREE.Group();
    root.add(dynamic);
    anim = null;
  }

  /**
   * @param orbitPath  [[x,y,z], ...] one revolution of the asteroid, AU
   * @param earthPath  [[x,y,z], ...] one year of Earth, AU
   * @param encounter  {index} optional position of the closest approach
   */
  function show(orbitPath, earthPath, opts = {}) {
    clear();
    if (!orbitPath || !orbitPath.length) return;

    const aPts = orbitPath.map(toScene);
    const ePts = earthPath && earthPath.length ? earthPath.map(toScene) : [];

    // Earth's orbit
    if (ePts.length) {
      const e = polyline([...ePts, ePts[0]], 0x4fd6ff, 0.55);
      dynamic.add(e);
    }

    // asteroid orbit, coloured by whether it is inside or outside 1 AU
    const closed = [...aPts, aPts[0]];
    const orbit = polyline(closed, opts.hazard ? 0xff5a3c : 0xffb347, 0.85);
    dynamic.add(orbit);

    // a faint ribbon dropping to the ecliptic shows the inclination
    const drops = [];
    for (let i = 0; i < aPts.length; i += 8) {
      drops.push(aPts[i].clone());
      drops.push(new THREE.Vector3(aPts[i].x, 0, aPts[i].z));
    }
    const dropGeo = new THREE.BufferGeometry().setFromPoints(drops);
    dynamic.add(new THREE.LineSegments(dropGeo, new THREE.LineBasicMaterial({
      color: 0xffb347, transparent: true, opacity: 0.12, depthWrite: false,
    })));

    // bodies
    const earth = glowSphere(1.5, 0x63b8ff);
    const asteroid = glowSphere(1.1, 0xff8c50);
    dynamic.add(earth);
    dynamic.add(asteroid);

    // marker at the closest approach, if the backend flagged one
    if (opts.encounterPoint) {
      const mk = glowSphere(2.0, 0xff3355);
      mk.position.copy(toScene(opts.encounterPoint));
      dynamic.add(mk);
    }

    anim = { aPts, ePts, earth, asteroid, t: 0 };
  }

  function update(dt) {
    if (!anim) return;
    anim.t += dt * 0.05;
    const f = anim.t % 1;
    if (anim.aPts.length) {
      const i = Math.floor(f * anim.aPts.length) % anim.aPts.length;
      anim.asteroid.position.copy(anim.aPts[i]);
    }
    if (anim.ePts.length) {
      // Earth runs on its own clock: one revolution per year of sim time
      const j = Math.floor((anim.t * 3.2 % 1) * anim.ePts.length) % anim.ePts.length;
      anim.earth.position.copy(anim.ePts[j]);
    }
  }

  return { root, show, clear, update };
}
