// Seeded ground data. All distances/heights are km; no downloaded imagery.
// Debug-only URL controls: ?bgdebug&bgground=city|mountain|sea&bgseed=integer&bgalt=1|2|3.
// Overrides never overwrite the first-visit world. bgspeed=0 also freezes the 64s animation loop.
export function groundWorld(qs, debug) {
  let saved;
  try { saved = Number(localStorage.getItem("bg-ground-seed-v1")); } catch (_) { /* private storage */ }
  if (!Number.isInteger(saved) || saved <= 0 || saved > 0xffffffff) {
    saved = crypto.getRandomValues(new Uint32Array(1))[0] || 1;
    try { localStorage.setItem("bg-ground-seed-v1", String(saved)); } catch (_) { /* session world */ }
  }
  const forced = debug && /^-?\d+$/.test(qs.get("bgseed") || "") ? Number(qs.get("bgseed")) : NaN;
  const seed = Number.isSafeInteger(forced) ? forced >>> 0 : saved;
  const kinds = ["city", "mountain", "sea"];
  const kind = debug && kinds.includes(qs.get("bgground")) ? qs.get("bgground") : kinds[seed % 3];
  return { seed, kind, index: kinds.indexOf(kind), altitude: debug && ["1", "2", "3"].includes(qs.get("bgalt")) ? Number(qs.get("bgalt")) : 2 };
}

export function createGroundTextures(gl, world) {
  let state = world.seed;
  const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
  const N = 512, P = 2048, tile = new Uint8Array(N * N * 4), ridge = new Uint8Array(P * 4 * 4);
  const fields = [8, 16, 32, 64, 128].map(size => ({ size, data: Float32Array.from({ length: size * size }, random) }));
  const noise = (x, y, octave) => {
    const { size, data } = fields[octave], px = x * size, py = y * size;
    const ix = Math.floor(px), iy = Math.floor(py), fx = px - ix, fy = py - iy;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const at = (a, b) => data[((b % size + size) % size) * size + (a % size + size) % size];
    return (at(ix, iy) * (1 - sx) + at(ix + 1, iy) * sx) * (1 - sy) + (at(ix, iy + 1) * (1 - sx) + at(ix + 1, iy + 1) * sx) * sy;
  };
  const height = (x, y) => noise(x, y, 0) * .52 + noise(x, y, 1) * .25 + noise(x, y, 2) * .13 + noise(x, y, 3) * .07 + noise(x, y, 4) * .03;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const u = x / N, v = y / N, i = (y * N + x) * 4;
    const h = height(u, v), dx = height(u + 1 / N, v) - height(u - 1 / N, v), dy = height(u, v + 1 / N) - height(u, v - 1 / N);
    if (world.kind === "sea") {
      // Periodic slope template; moving samples interpolate continuously, including at wrap.
      const a = Math.PI * 2 * (u * 7 + v * 13), b = Math.PI * 2 * (u * 19 - v * 5);
      tile[i] = 128 + 58 * Math.sin(a) + 26 * Math.sin(b);
      tile[i + 1] = 128 + 50 * Math.cos(a) - 31 * Math.cos(b);
      tile[i + 2] = h * 255; tile[i + 3] = 255;
    } else if (world.kind === "mountain") {
      tile[i] = h * 255; tile[i + 1] = Math.max(0, Math.min(255, 128 + dx * 1800));
      tile[i + 2] = Math.max(0, Math.min(255, 128 + dy * 1800)); tile[i + 3] = noise(u, v, 4) * 255;
    } else {
      // 8km repeat: 250m blocks with irregular parks/districts, 16m roads and roofs.
      const bx = Math.floor(u * 32), by = Math.floor(v * 32), rx = u * 32 % 1, ry = v * 32 % 1;
      const district = noise(u, v, 0), block = noise((bx + .5) / 32, (by + .5) / 32, 2);
      const road = Math.min(rx, 1 - rx, ry, 1 - ry) < .035;
      const roof = Math.sin(rx * 31) * Math.sin(ry * 23) > -.25 ? .08 : -.06;
      tile[i] = (road ? .13 : .28 + block * .26 + roof) * 255;
      tile[i + 1] = district * 255; tile[i + 2] = road ? 255 : 0;
      // Fixed lamps, with mipmaps preserving average radiance at subpixel sizes.
      tile[i + 3] = road && ((x + y * 3) % 11 < 2) ? 230 : 0;
    }
  }
  for (let layer = 0; layer < 4; layer++) {
    const phases = Array.from({ length: 12 }, () => random() * Math.PI * 2);
    for (let x = 0; x < P; x++) {
      const a = x / P * Math.PI * 2;
      let h = .5;
      for (let k = 0; k < 12; k++) h += Math.sin(a * (3 + k * k) + phases[k]) * .22 / Math.pow(k + 1, 1.1);
      h = Math.max(.05, Math.min(.98, h));
      if (world.kind === "city") {
        // Stable contiguous roof spans rather than independently jittering angular pixels.
        const cell = Math.floor(x / (3 + layer * 2));
        h = .03 + .24 * ((Math.imul(cell + world.seed + layer * 73, 16807) >>> 0) % 997) / 997;
      } else h = .45 + 3.0 * h;
      const encoded = Math.round(h / 4 * 65535), i = (layer * P + x) * 4;
      ridge[i] = encoded >> 8; ridge[i + 1] = encoded & 255;
      ridge[i + 2] = 128 + 85 * Math.sin(a * 47 + phases[0]); ridge[i + 3] = 255;
    }
  }
  const textures = [];
  function upload(unit, width, height_, data, mip) {
    const texture = gl.createTexture(); textures.push(texture);
    gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, width, height_, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, mip ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    if (mip) gl.generateMipmap(gl.TEXTURE_2D);
  }
  upload(5, N, N, tile, true); upload(6, P, 4, ridge, false);
  // Approved future albedo: replace unit 7 with seamless natural-color sRGB RGB,
  // mipmapped REPEAT, 8km tile (city) / 32km (mountain). Shader decodes sRGB;
  // set uGroundAlbedoOn=1. No baked sunlight, shadows, labels, clouds or night lights.
  upload(7, 1, 1, new Uint8Array([128, 128, 128, 255]), false);
  gl.activeTexture(gl.TEXTURE0);
  return () => textures.forEach(t => gl.deleteTexture(t));
}

export const groundShader = `
uniform sampler2D uGroundTile, uGroundRidge, uGroundAlbedo;
uniform float uGroundKind, uGroundAlt, uGroundAlbedoOn, uGroundMoonLight;
const float GR = 6371.0;
float ridgeHeight(float az, int layer) {
  vec4 h = textureLod(uGroundRidge, vec2(az / TAU, (float(layer) + .5) / 4.0), 0.0);
  return dot(h.rg, vec2(65280.0, 255.0)) * (4.0 / 65535.0);
}
// Shared geometry for surface, celestial occultation, and lens source visibility.
// External origin is independent of dome E/zoom. Three radial distance belts, no raymarch.
vec4 groundGeometry(vec3 ray, float pixel) {
  float dip = -sqrt(uGroundAlt * (2.0 * GR + uGroundAlt)) / (GR + uGroundAlt);
  float mask = clamp(.5 + (dip - ray.y) / pixel, 0.0, 1.0);
  float b = (GR + uGroundAlt) * ray.y;
  float c = uGroundAlt * (2.0 * GR + uGroundAlt);
  float root = sqrt(max(b * b - c, 0.0));
  // Rationalized near root avoids cancellation looking straight down.
  float distance = c / max(-b + root, .001);
  float selected = -1.0, edgeCoverage = 1.0;
  if (uGroundKind < 1.5) {
    float az = atan(ray.x, ray.z), horizontal = max(length(ray.xz), .0001);
    for (int i = 2; i >= 0; i--) {
      float r = uGroundKind < .5 ? (i == 0 ? 8.0 : (i == 1 ? 22.0 : 65.0)) : (i == 0 ? 12.0 : (i == 1 ? 35.0 : 80.0));
      float h = ridgeHeight(az, i), curve = r * r / (2.0 * GR);
      float edge = (h - uGroundAlt - curve) / r;
      float k = clamp(.5 + (edge * horizontal - ray.y) / pixel, 0.0, 1.0);
      // A belt contributes only in front of the analytic base surface.
      if (k > 0.0 && (mask < .5 || r / horizontal < distance)) {
        mask = max(mask, k); distance = r / horizontal; selected = float(i); edgeCoverage = k;
      }
    }
  }
  return vec4(mask, min(distance, 300.0), selected, edgeCoverage);
}
vec3 groundAir(vec3 ray) {
  float u = atan(ray.x, ray.z) / TAU * 3.0;
  vec3 a = clamp(uSkyM * textureLod(uSky, vec2(u, .97), 6.0).rgb + uSkyO, 0.0, 1.0);
  vec3 b = clamp(uSkyM2 * textureLod(uSky2, vec2(u, .97), 6.0).rgb + uSkyO2, 0.0, 1.0);
  vec3 air = uTex > .5 ? mix(a, b, uMix) : uSkyBase;
  if (uOut < .5) return air;
  air = mix(air, air * vec3(.42, .54, .82), uNight);
  float forward = pow(max(dot((vec3(ray.x, 0, ray.z) / max(length(ray.xz), .00001)), uSunHorizon), 0.0), 4.0);
  return mix(air, uSunGlow * (.72 + .3 * dot(air, vec3(.2126,.7152,.0722))), forward * uSolar.y * uSunAir.z * .64);
}
vec3 groundSurface(vec3 ray, vec4 geometry, float pixel) {
  vec3 pos = vec3(0, GR + uGroundAlt, 0) + ray * geometry.y;
  vec3 n = normalize(pos), v = -ray;
  vec2 uv = pos.xz / (uGroundKind < .5 ? 8.0 : 32.0);
  // Derivatives from the ray footprint, not a discontinuous longitude or selected belt.
  float footprint = min(8.0, pixel * geometry.y / max(abs(dot(n, ray)), .025));
  float lod = max(0.0, log2(512.0 * footprint / (uGroundKind < .5 ? 8.0 : 32.0)));
  if (uGroundKind > .5 && uGroundKind < 1.5 && geometry.z >= 0.0) {
    float elevation = uGroundAlt + ray.y * geometry.y + dot(pos.xz,pos.xz)/(2.0*GR);
    uv = vec2(atan(ray.x,ray.z) / TAU * 5.0, elevation / 3.5 + geometry.z * .31);
    lod = max(0.0,log2(pixel * geometry.y * 512.0 / 3.5));
  }
  vec4 data = textureLod(uGroundTile, uv, lod);
  float day = uOut > .5 ? uSolar.x : .65;
  float night = uOut > .5 ? max(uNight, 1.0 - day) : .15;
  vec3 albedo, emission = vec3(0);
  if (uGroundKind > 1.5) {
    // Two precomputed periodic slope fields, 64s closed loop; no per-pixel noise synthesis.
    float phase = mod(uTime, 64.0) / 64.0;
    vec2 slope = textureLod(uGroundTile, pos.xz / 1.4 + vec2(phase, 0), max(0.0, lod + 2.0)).rg;
    slope += textureLod(uGroundTile, pos.xz / 2.1 + vec2(0, -phase), max(0.0, lod + 1.0)).rg;
    n = normalize(n + vec3((slope.x - 1.0) * .13, 0, (slope.y - 1.0) * .13));
    float fresnel = .02 + .98 * pow(1.0 - max(dot(n,v), 0.0), 5.0);
    albedo = mix(vec3(.012,.045,.055), groundAir(ray) * .65, fresnel);
    for (int i = 0; i < 2; i++) {
      vec3 l = i == 0 ? uSunDir : uMoonDir;
      vec3 halfway = (v + l) / max(length(v + l), .00001);
      float nh = max(dot(n, halfway), 0.0), nl = max(dot(n, l), 0.0);
      float alpha = .055, den = nh * nh * (alpha * alpha - 1.0) + 1.0;
      float specular = alpha * alpha / max(3.14159 * den * den, .00001);
      float sourceClear = i == 0 ? 1.0 - cloudAtSun() : 1.0;
      float light = i == 0 ? uSolar.z * (.45 + .55 * day) * 1.4 : uGroundMoonLight * .38;
      // Microfacet BRDF nl cancellation: grazing reflection must not disappear at sunset.
      float brdf = specular * (.02 + .98 * pow(1.0 - max(dot(v,halfway),0.0),5.0));
      brdf /= 4.0 * max(dot(n,v), .035);
      emission += (i == 0 ? uSunCol : uMoonCol) * min(brdf, 12.0) * smoothstep(0.0,.018,nl) * light * .18 * sourceClear * sourceClear;
    }
  } else if (uGroundKind > .5) {
    n = normalize(n + vec3((data.g - .5) * 1.7, 0, (data.b - .5) * 1.7));
    albedo = mix(vec3(.065,.11,.075), vec3(.29,.275,.25), smoothstep(.4,.76,data.r));
    albedo *= .72 + .5 * data.a;
    albedo *= .8 + .4 * abs(data.r * 2.0 - 1.0);
    if (geometry.z >= 0.0) {
      float h = ridgeHeight(atan(ray.x,ray.z), int(geometry.z));
      float elevation = uGroundAlt + ray.y * geometry.y + length(pos.xz)*length(pos.xz)/(2.0*GR);
      albedo = mix(albedo, vec3(.62,.65,.64), smoothstep(2.45,3.1,elevation) * smoothstep(.6,.9,h/3.5));
    }
  } else {
    albedo = mix(vec3(data.r * .85), vec3(.07,.12,.085), smoothstep(.65,.8,data.g));
    // Lamps almost fixed. Subpixel texture features converge to their mip average.
    float shimmer = 1.0 + .025 * sin(uTime * TAU / 8.0);
    // 8km / 512s = 15.6m/s traffic; loop closes without a jump.
    float phase = mod(uTime, 512.0) / 512.0;
    vec4 cars = textureLod(uGroundTile, uv + vec2(phase,0), lod);
    float traffic = data.b * cars.a * .23;
    emission = vec3(1.0,.63,.28) * (data.a * .9 * shimmer + data.b * .09 + traffic + .008 * data.g) * night;
  }
  if (uGroundAlbedoOn > .5 && uGroundKind < 1.5) albedo = pow(textureLod(uGroundAlbedo, uv, lod).rgb, vec3(2.2));
  float diffuse = max(dot(n,uSunDir),0.0);
  vec3 surface = albedo * (.055 + day * (.42 + .75 * diffuse)) + emission;
  if (uOut < .5) {
    float gray = dot(surface,vec3(.2126,.7152,.0722));
    surface = mix(groundAir(ray) * vec3(.85,.69,.8), vec3(.46,.29,.38) + gray * .3, .4);
  }
  return mix(groundAir(ray), surface, geometry.w * exp(-geometry.y * (uGroundKind > 1.5 ? .013 : .021)));
}
`;
