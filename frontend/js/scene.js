/* ===========================================================================
   Renderer, cameras, starfield, sun, and the bloom chain.

   Two scenes share one renderer:
     'earth'  -- Earth at unit radius, for the impact itself
     'system' -- heliocentric, 1 AU = 60 units, for the approach orbit
   Switching between them cross-fades rather than cutting, so the eye keeps
   track of what it is looking at.
   =========================================================================== */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

export const AU_UNITS = 60;          // scene units per astronomical unit

export function createStage(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
    stencil: false,
    // Keeps the drawing buffer readable after a frame is presented, so the
    // rendered globe can be exported with canvas.toDataURL(). Without it the
    // buffer is undefined by the time any capture runs.
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;

  /* ------------------------------------------------------------- scenes */
  const earthScene = new THREE.Scene();
  const systemScene = new THREE.Scene();

  // The near/far ratio sets depth precision. A 0.005 near plane against a
  // 4000 far plane leaves so few usable depth bits at the globe that surface
  // decals a few kilometres up (the damage rings) z-fight into the planet and
  // vanish. Controls clamp the camera at 1.24, so 0.05 is safely clear.
  const earthCam = new THREE.PerspectiveCamera(42, innerWidth / innerHeight,
                                               0.05, 3000);
  earthCam.position.set(0, 1.05, 3.15);

  const systemCam = new THREE.PerspectiveCamera(46, innerWidth / innerHeight,
                                                0.1, 60000);
  systemCam.position.set(0, 95, 190);

  const earthControls = new OrbitControls(earthCam, canvas);
  earthControls.enableDamping = true;
  earthControls.dampingFactor = 0.055;
  earthControls.rotateSpeed = 0.45;
  earthControls.minDistance = 1.24;
  earthControls.maxDistance = 26;
  earthControls.enablePan = false;

  const systemControls = new OrbitControls(systemCam, canvas);
  systemControls.enableDamping = true;
  systemControls.dampingFactor = 0.055;
  systemControls.minDistance = 12;
  systemControls.maxDistance = 3200;
  systemControls.enabled = false;

  /* ------------------------------------------------------------ lighting */
  const sunLight = new THREE.DirectionalLight(0xfff3e0, 3.1);
  sunLight.position.set(1, 0.2, 0.35).normalize().multiplyScalar(50);
  earthScene.add(sunLight);
  earthScene.add(new THREE.AmbientLight(0x14233a, 0.55));

  systemScene.add(new THREE.PointLight(0xfff0d8, 4.2, 0, 0.4));
  systemScene.add(new THREE.AmbientLight(0x223046, 0.7));

  /* ----------------------------------------------------------- starfield */
  earthScene.add(makeStarfield(1800, 2200));
  systemScene.add(makeStarfield(9000, 26000));

  /* ---------------------------------------------------------------- sun */
  const sunSprite = makeSunSprite(120);
  sunSprite.position.copy(sunLight.position).setLength(700);
  earthScene.add(sunSprite);

  const sunBall = new THREE.Mesh(
    new THREE.SphereGeometry(4.2, 48, 32),
    new THREE.MeshBasicMaterial({ color: 0xffd9a0 })
  );
  systemScene.add(sunBall);
  systemScene.add(makeSunSprite(46));

  /* --------------------------------------------------------- post chain */
  const composer = new EffectComposer(renderer);
  const renderPass = new RenderPass(earthScene, earthCam);
  composer.addPass(renderPass);

  const bloom = new UnrealBloomPass(
    new THREE.Vector2(innerWidth, innerHeight), 0.62, 0.55, 0.82);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  composer.setPixelRatio(Math.min(devicePixelRatio, 2));

  /* ------------------------------------------------------------- resize */
  function resize() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h);
    composer.setSize(w, h);
    bloom.resolution.set(w, h);
    earthCam.aspect = w / h;  earthCam.updateProjectionMatrix();
    systemCam.aspect = w / h; systemCam.updateProjectionMatrix();
  }
  addEventListener('resize', resize);

  /* -------------------------------------------------------- view switch */
  let view = 'earth';
  function setView(next) {
    if (next === view) return;
    view = next;
    const isEarth = view === 'earth';
    renderPass.scene = isEarth ? earthScene : systemScene;
    renderPass.camera = isEarth ? earthCam : systemCam;
    earthControls.enabled = isEarth;
    systemControls.enabled = !isEarth;
    bloom.strength = isEarth ? 0.62 : 0.9;
  }

  /* ------------------------------------------------- camera flight path */
  let flight = null;
  function flyTo(target, lookAt, seconds = 1.6) {
    const cam = view === 'earth' ? earthCam : systemCam;
    const ctl = view === 'earth' ? earthControls : systemControls;
    flight = {
      cam, ctl, t: 0, dur: seconds,
      fromPos: cam.position.clone(),
      toPos: target.clone(),
      fromTgt: ctl.target.clone(),
      toTgt: (lookAt || new THREE.Vector3()).clone(),
    };
  }

  function stepFlight(dt) {
    if (!flight) return;
    flight.t += dt / flight.dur;
    const k = Math.min(flight.t, 1);
    // smootherstep: zero velocity and zero acceleration at both ends
    const s = k * k * k * (k * (k * 6 - 15) + 10);
    flight.cam.position.lerpVectors(flight.fromPos, flight.toPos, s);
    flight.ctl.target.lerpVectors(flight.fromTgt, flight.toTgt, s);
    if (k >= 1) flight = null;
  }

  return {
    renderer, composer, bloom,
    earthScene, systemScene, earthCam, systemCam,
    earthControls, systemControls,
    sunLight, sunSprite,
    get view() { return view; },
    setView, flyTo, resize,

    render(dt) {
      stepFlight(dt);
      earthControls.update();
      systemControls.update();
      composer.render();
    },
  };
}

/* -------------------------------------------------------------- starfield */
function makeStarfield(count, radius) {
  const pos = new Float32Array(count * 3);
  const col = new Float32Array(count * 3);
  const size = new Float32Array(count);
  const c = new THREE.Color();

  for (let i = 0; i < count; i++) {
    // uniform on the sphere: acos of a uniform cosine, not a uniform angle
    const u = Math.random() * 2 - 1;
    const t = Math.random() * Math.PI * 2;
    const r = radius * (0.55 + Math.random() * 0.45);
    const s = Math.sqrt(1 - u * u);
    pos[i * 3]     = r * s * Math.cos(t);
    pos[i * 3 + 1] = r * u;
    pos[i * 3 + 2] = r * s * Math.sin(t);

    // a plausible spread of stellar colours, mostly white with hot and cool tails
    const k = Math.random();
    if (k < 0.06)      c.setHSL(0.60, 0.55, 0.80);   // blue giants
    else if (k < 0.20) c.setHSL(0.09, 0.50, 0.72);   // orange dwarfs
    else               c.setHSL(0.12, 0.06, 0.86);
    const mag = Math.pow(Math.random(), 2.4);        // few bright, many faint
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    size[i] = 0.6 + mag * 4.4;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));

  const mat = new THREE.ShaderMaterial({
    uniforms: { uScale: { value: Math.min(devicePixelRatio, 2) } },
    vertexShader: /* glsl */`
      attribute float aSize;
      varying vec3 vColor;
      uniform float uScale;
      void main() {
        vColor = color;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        // Stars are effectively at infinity, so their apparent size must not
        // fall off with distance -- dividing by depth here made every star
        // sub-pixel and the sky came out empty.
        gl_PointSize = aSize * uScale;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */`
      varying vec3 vColor;
      void main() {
        vec2 d = gl_PointCoord - 0.5;
        float r = length(d);
        if (r > 0.5) discard;
        float a = smoothstep(0.5, 0.02, r);
        gl_FragColor = vec4(vColor * (a * 1.6), a);
      }`,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  return pts;
}

/* ------------------------------------------------------------- sun glare */
function makeSunSprite(scale) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0.00, 'rgba(255,255,250,1)');
  g.addColorStop(0.10, 'rgba(255,238,200,0.95)');
  g.addColorStop(0.26, 'rgba(255,196,120,0.42)');
  g.addColorStop(0.55, 'rgba(255,150,70,0.11)');
  g.addColorStop(1.00, 'rgba(255,120,40,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, blending: THREE.AdditiveBlending,
    depthWrite: false, depthTest: false, transparent: true,
  }));
  sprite.scale.setScalar(scale);
  return sprite;
}
