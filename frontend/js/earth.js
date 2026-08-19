/* ===========================================================================
   Earth: a shaded globe with a real day/night terminator.

   Four layers, drawn outward:
     1. surface  -- day albedo, night city lights, ocean specular, relief
     2. clouds   -- an independently rotating shell that also shadows the ground
     3. haze     -- a thin forward-scattering shell hugging the limb
     4. corona   -- a back-facing shell giving the blue rim seen from orbit

   The surface shader does its own lighting rather than using a Three.js
   material, because the interesting part here is the terminator: city lights
   have to fade in exactly where the sunlight fades out, and the ocean specular
   has to survive right up to the day edge.
   =========================================================================== */

import * as THREE from 'three';

export const EARTH_RADIUS = 1.0;

/* --------------------------------------------------------------- helpers */

/** Geographic coordinates to a position on the globe. */
export function latLonToVec3(lat, lon, radius = EARTH_RADIUS) {
  const phi = (lon + 180) * Math.PI / 180;
  const theta = (90 - lat) * Math.PI / 180;
  return new THREE.Vector3(
    -radius * Math.cos(phi) * Math.sin(theta),
     radius * Math.cos(theta),
     radius * Math.sin(phi) * Math.sin(theta)
  );
}

/** Inverse of the above, for turning a click into a coordinate. */
export function vec3ToLatLon(v) {
  const n = v.clone().normalize();
  const lat = 90 - Math.acos(THREE.MathUtils.clamp(n.y, -1, 1)) * 180 / Math.PI;
  let lon = Math.atan2(n.z, -n.x) * 180 / Math.PI - 180;
  while (lon < -180) lon += 360;
  while (lon > 180) lon -= 360;
  return { lat, lon };
}

/* ---------------------------------------------------------------- shaders */

const SURFACE_VERT = /* glsl */`
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vViewDir;
varying vec3 vWorldPos;

void main() {
  vUv = uv;
  vNormal = normalize(mat3(modelMatrix) * normal);
  vec4 worldPos = modelMatrix * vec4(position, 1.0);
  vWorldPos = worldPos.xyz;
  vViewDir = normalize(cameraPosition - worldPos.xyz);
  gl_Position = projectionMatrix * viewMatrix * worldPos;
}
`;

const SURFACE_FRAG = /* glsl */`
uniform sampler2D dayMap;
uniform sampler2D nightMap;
uniform sampler2D cloudMap;
uniform sampler2D oceanMap;
uniform sampler2D reliefMap;
uniform vec3  sunDirection;
uniform float cloudOffset;
uniform float nightGain;
uniform float exposure;

varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vViewDir;
varying vec3 vWorldPos;

void main() {
  vec3 N = normalize(vNormal);
  vec3 L = normalize(sunDirection);
  vec3 V = normalize(vViewDir);

  // --- relief: perturb the normal using the slope of the height map -------
  vec2 texel = vec2(1.0 / 2048.0, 1.0 / 1024.0);
  float hL = texture2D(reliefMap, vUv - vec2(texel.x, 0.0)).r;
  float hR = texture2D(reliefMap, vUv + vec2(texel.x, 0.0)).r;
  float hD = texture2D(reliefMap, vUv - vec2(0.0, texel.y)).r;
  float hU = texture2D(reliefMap, vUv + vec2(0.0, texel.y)).r;
  vec3 bump = normalize(vec3((hL - hR) * 2.2, (hD - hU) * 2.2, 1.0));

  // build a tangent frame so the bump lives in surface space
  vec3 up = abs(N.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
  vec3 T = normalize(cross(up, N));
  vec3 B = cross(N, T);
  vec3 Nb = normalize(T * bump.x + B * bump.y + N * bump.z);

  float ocean = texture2D(oceanMap, vUv).r;      // 1 = water, 0 = land
  vec3 Nsurf = mix(Nb, N, ocean);                // seas stay smooth

  // --- terminator ----------------------------------------------------------
  float lambert = dot(Nsurf, L);
  // a soft band rather than a hard edge: the sun is a disc, and the atmosphere
  // scatters light some way past the geometric terminator
  float daylight = smoothstep(-0.09, 0.22, lambert);
  float twilight = smoothstep(-0.28, 0.02, lambert) * (1.0 - daylight);

  // --- clouds --------------------------------------------------------------
  vec2 cloudUv = vec2(fract(vUv.x + cloudOffset), vUv.y);
  float cloud = texture2D(cloudMap, cloudUv).r;
  // clouds cast a soft shadow, offset slightly toward the sun
  vec2 shadowUv = vec2(fract(vUv.x + cloudOffset - 0.0032), vUv.y - 0.0018);
  float cloudShadow = texture2D(cloudMap, shadowUv).r;

  // --- day side ------------------------------------------------------------
  vec3 albedo = texture2D(dayMap, vUv).rgb;
  albedo *= (1.0 - 0.42 * cloudShadow);
  vec3 dayColor = albedo * (0.06 + 0.98 * daylight);

  // warm the light near the terminator, the way a low sun does
  vec3 sunset = vec3(1.32, 0.72, 0.42);
  dayColor *= mix(vec3(1.0), sunset, twilight * 0.85);

  // --- ocean specular ------------------------------------------------------
  vec3 H = normalize(L + V);
  float spec = pow(max(dot(Nsurf, H), 0.0), 62.0);
  dayColor += vec3(0.85, 0.93, 1.0) * spec * ocean * daylight * 1.5;

  // --- night side ----------------------------------------------------------
  vec3 lights = texture2D(nightMap, vUv).rgb;
  float lightMask = smoothstep(0.04, 0.32, dot(lights, vec3(0.33)));
  float nightFactor = 1.0 - smoothstep(-0.14, 0.06, lambert);
  vec3 nightColor = lights * lightMask * nightFactor * nightGain
                    * vec3(1.0, 0.86, 0.62);
  nightColor *= (1.0 - 0.75 * cloud);           // cloud cover hides the cities

  vec3 color = dayColor + nightColor;

  // --- cloud tops ----------------------------------------------------------
  float cloudLit = 0.09 + 0.98 * daylight;
  color = mix(color, vec3(1.0) * cloudLit, cloud * 0.68);

  // --- limb scattering -----------------------------------------------------
  float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.1);
  vec3 rim = vec3(0.28, 0.52, 1.0) * fresnel * (0.24 + 0.9 * daylight);
  color += rim;

  // Output linear radiance. Tone mapping and the sRGB transfer happen once,
  // in the renderer, so every material in the scene shares one response curve.
  gl_FragColor = vec4(color * exposure, 1.0);
}
`;

const CORONA_VERT = /* glsl */`
varying vec3 vNormal;
varying vec3 vWorldPos;
void main() {
  vNormal = normalize(mat3(modelMatrix) * normal);
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWorldPos = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}
`;

const CORONA_FRAG = /* glsl */`
uniform vec3  sunDirection;
uniform vec3  glowColor;
uniform float intensity;
uniform float power;

varying vec3 vNormal;
varying vec3 vWorldPos;

void main() {
  vec3 N = normalize(vNormal);
  vec3 V = normalize(cameraPosition - vWorldPos);
  vec3 L = normalize(sunDirection);

  // back-facing shell: the rim is where the surface turns away from the eye
  float rim = pow(max(1.0 - abs(dot(N, V)), 0.0), power);

  // only the sunlit limb should glow, and it glows hardest looking through
  // the atmosphere toward the sun (forward scattering)
  float lit = smoothstep(-0.55, 0.35, dot(N, L));
  float forward = pow(max(dot(V, -L), 0.0), 2.2);

  float a = rim * intensity * (lit * 0.82 + forward * 0.55);
  gl_FragColor = vec4(glowColor * (0.75 + forward * 0.9), a);
}
`;

/* ------------------------------------------------------------------ build */

export function createEarth(textures) {
  const group = new THREE.Group();

  const sunDirection = new THREE.Vector3(1, 0.2, 0.35).normalize();

  /* ---- 1. surface ---- */
  const surfaceUniforms = {
    dayMap:      { value: textures.day },
    nightMap:    { value: textures.night },
    cloudMap:    { value: textures.clouds },
    oceanMap:    { value: textures.ocean },
    reliefMap:   { value: textures.relief },
    sunDirection:{ value: sunDirection },
    cloudOffset: { value: 0 },
    nightGain:   { value: 1.35 },
    exposure:    { value: 1.18 },
  };

  const surface = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS, 192, 128),
    new THREE.ShaderMaterial({
      uniforms: surfaceUniforms,
      vertexShader: SURFACE_VERT,
      fragmentShader: SURFACE_FRAG,
    })
  );
  surface.name = 'earth-surface';
  group.add(surface);

  /* ---- 2. cloud shell ----
     A real shell rather than a texture on the surface, so it casts a visible
     parallax edge at the limb and can drift at its own rate. */
  const clouds = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.006, 128, 84),
    new THREE.MeshPhongMaterial({
      map: textures.clouds,
      alphaMap: textures.clouds,
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
      blending: THREE.NormalBlending,
      shininess: 0,
    })
  );
  group.add(clouds);

  /* ---- 3. inner haze ---- */
  const haze = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.014, 96, 64),
    new THREE.ShaderMaterial({
      uniforms: {
        sunDirection: { value: sunDirection },
        glowColor:    { value: new THREE.Color(0x6fb4ff) },
        intensity:    { value: 0.5 },
        power:        { value: 3.4 },
      },
      vertexShader: CORONA_VERT,
      fragmentShader: CORONA_FRAG,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    })
  );
  group.add(haze);

  /* ---- 4. outer corona ---- */
  const corona = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.09, 96, 64),
    new THREE.ShaderMaterial({
      uniforms: {
        sunDirection: { value: sunDirection },
        glowColor:    { value: new THREE.Color(0x3d7dff) },
        intensity:    { value: 0.62 },
        power:        { value: 2.1 },
      },
      vertexShader: CORONA_VERT,
      fragmentShader: CORONA_FRAG,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    })
  );
  group.add(corona);

  return {
    group, surface, clouds, haze, corona, sunDirection,

    /** Move the sun; every layer shares the direction vector. */
    setSunDirection(v) {
      sunDirection.copy(v).normalize();
    },

    update(dt) {
      surfaceUniforms.cloudOffset.value =
        (surfaceUniforms.cloudOffset.value + dt * 0.0016) % 1.0;
      clouds.rotation.y += dt * 0.0102;
    },
  };
}

/* ----------------------------------------------------------- texture load */

export function loadTextures(onProgress) {
  const loader = new THREE.TextureLoader();
  const files = {
    day:    '/textures/earth_day.jpg',
    night:  '/textures/earth_night.jpg',
    clouds: '/textures/earth_clouds.jpg',
    ocean:  '/textures/earth_specular.jpg',
    relief: '/textures/earth_normal.jpg',
    moon:   '/textures/moon.jpg',
  };
  const keys = Object.keys(files);
  let done = 0;

  return Promise.all(keys.map(k => new Promise((resolve, reject) => {
    loader.load(files[k], tex => {
      tex.colorSpace = (k === 'day' || k === 'night' || k === 'moon')
        ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      tex.anisotropy = 8;
      tex.wrapS = THREE.RepeatWrapping;
      done++;
      if (onProgress) onProgress(done / keys.length, k);
      resolve([k, tex]);
    }, undefined, reject);
  }))).then(pairs => Object.fromEntries(pairs));
}
