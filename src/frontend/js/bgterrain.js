// A finite Front Range patch, seen from one stationary eye. No repeated DEM/photo.
// Heavy work, including photo de-lighting, lives in a disposable inline Worker.
// GPU storage: base 2048x640x12 B, two 512x1024x12 B detail slots, 256 KiB horizons.
const RAD = Math.PI / 180, TAU = Math.PI * 2;
const BASE = { az: Math.PI, el: -32 * RAD, da: Math.PI, de: 40 * RAD, w: 2048, h: 640 };

function terrainWorker() {
  const R = 6371, D = Math.PI / 180, T = Math.PI * 2;
  // Geographic pixel edges, not pixel centers. Photo crop is exactly 853/1024.
  const fullW = .374 * D * R * Math.cos(39.674 * D), H = .288 * D * R;
  const W = fullW * 853 / 1024, datum = 1.674, apron = 2;
  let dem, eyeX, eyeZ, altitude;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
  function raw(x, z) {
    const px = clamp(x / fullW * 512 - .5, 0, 511), py = clamp((1 - z / H) * 512 - .5, 0, 511);
    const ix = Math.min(510, Math.floor(px)), iy = Math.min(510, Math.floor(py)), fx = px - ix, fy = py - iy, i = iy * 512 + ix;
    return (dem[i] * (1 - fx) + dem[i + 1] * fx) * (1 - fy) + (dem[i + 512] * (1 - fx) + dem[i + 513] * fx) * fy;
  }
  function weight(x, z) {
    return smooth(1 - Math.max(-x, x - W, -z, z - H, 0) / apron);
  }
  function height(x, z) { return (raw(x, z) - datum) * weight(x, z); }
  async function pixels(url) {
    const response = await fetch(url); if (!response.ok) throw Error('terrain ' + response.status);
    const image = await createImageBitmap(await response.blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
    const c = new OffscreenCanvas(image.width, image.height), ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(image, 0, 0); image.close();
    return ctx.getImageData(0, 0, c.width, c.height);
  }
  // (11-05 Claude) 촬영 때 지형 음영 지우기 — 지형 보정(C-correction).
  // Landsat 9 LC09_L2SP_033033_20240831 촬영 순간 해 = 방위 143.82° · 고도 54.33°(STAC view:sun_*).
  // 사진 ≈ 바탕색 × (cosI + C), 평지 = 바탕색 × (cos(천정각) + C) → 바탕색 비율 = (sin 고도 + C) / (cosI + C).
  // C(산란광 비율)가 그늘 속 픽셀을 나눌 때 잡음이 커지는 것을 막고, 이득도 0.7 ~ 1.9 로 묶는다.
  const CAPTURE = { az: 143.82 * D, el: 54.33 * D }, C = .45;
  function photo(data) {
    const w = 853, h = data.height, src = data.data, out = new Uint8Array(w * h * 4), eps = .045;
    const lx = Math.sin(CAPTURE.az) * Math.cos(CAPTURE.el), ly = Math.sin(CAPTURE.el), lz = Math.cos(CAPTURE.az) * Math.cos(CAPTURE.el);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const px = (x + .5) / w * W, pz = (1 - (y + .5) / h) * H;
      const nx = -(height(px + eps, pz) - height(px - eps, pz)) / (2 * eps), nz = -(height(px, pz + eps) - height(px, pz - eps)) / (2 * eps);
      const cosI = (nx * lx + ly + nz * lz) / Math.hypot(nx, 1, nz);
      const gain = clamp((ly + C) / (Math.max(cosI, 0) + C), .7, 1.9), i = (y * w + x) * 4, j = (y * data.width + x) * 4;
      for (let c = 0; c < 3; c++) out[i + c] = Math.min(255, src[j + c] * gain);
      out[i + 3] = 255;
    }
    return out;
  }
  function horizons() {
    // 16 azimuths at each 128x128 geographic point, positive terrain horizon.
    // Curvature included. Out-of-data apron is a reconstruction, never a tile.
    const n = 128, out = new Uint8Array(n * n * 16);
    for (let a = 0; a < 16; a++) {
      const sx = Math.sin(a * T / 16), sz = Math.cos(a * T / 16);
      for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
        const px = (x + .5) / n * W, pz = (1 - (y + .5) / n) * H, h = height(px, pz);
        let edge = 0;
        for (let r = .09; r < 42; r = r * 1.14 + .04) {
          const xx = px + sx * r, zz = pz + sz * r;
          if (xx < -apron || xx > W + apron || zz < -apron || zz > H + apron) break;
          edge = Math.max(edge, Math.atan2(height(xx, zz) - h - r * r / (2 * R), r));
        }
        out[(a * n + y) * n + x] = Math.round(edge / (Math.PI / 2) * 255);
      }
    }
    return out;
  }
  function bake(q) {
    const start = performance.now(), { w, h, az, el, da, de } = q;
    const geometry = new Uint16Array(w * h * 4), normal = new Uint8Array(w * h * 4), skyline = new Float32Array(w);
    const step = q.detail ? .006 : .025;
    for (let col = 0; col < w; col++) {
      const a = az + (col + .5) / w * da, sx = Math.sin(a), sz = Math.cos(a);
      let lo = 0, hi = 100;
      for (const [origin, slope, min, max] of [[eyeX, sx, -apron, W + apron], [eyeZ, sz, -apron, H + apron]]) {
        if (Math.abs(slope) < 1e-10) { if (origin < min || origin > max) hi = -1; }
        else { const a = (min - origin) / slope, b = (max - origin) / slope; lo = Math.max(lo, Math.min(a, b)); hi = Math.min(hi, Math.max(a, b)); }
      }
      let edge = -Math.PI / 2, row = 0, prevR = lo, prevA = -Math.PI / 2, last = null;
      const store = (y, r) => {
        const x = eyeX + sx * r, z = eyeZ + sz * r, hh = height(x, z), yy = Math.sqrt((R + hh) ** 2 - r * r) - R - altitude;
        const i = (y * w + col) * 4, eps = .04;
        let nx = -(height(x + eps, z) - height(x - eps, z)) / (2 * eps) + sx * r / R;
        let nz = -(height(x, z + eps) - height(x, z - eps)) / (2 * eps) + sz * r / R;
        const len = Math.hypot(nx, 1, nz); nx /= len; nz /= len;
        // UNORM16 UVs retain sub-metre coordinates at x30; half floats would
        // quantize the photo into ~13m blocks. Distance has 5m precision.
        geometry[i] = Math.round(clamp(x / W, 0, 1) * 65535); geometry[i + 1] = Math.round(clamp(1 - z / H, 0, 1) * 65535);
        geometry[i + 2] = Math.round(Math.hypot(r, yy) * 200); geometry[i + 3] = 1;
        normal[i] = Math.round((nx * .5 + .5) * 255); normal[i + 1] = Math.round((nz * .5 + .5) * 255);
        // Blend the photo to lowland at every finite edge; never crossfade opposite edges.
        normal[i + 2] = Math.round(smooth(Math.min(x, W - x, z, H - z) / .8) * weight(x, z) * 255); normal[i + 3] = 255;
        last = i;
      };
      for (let r = lo; r <= hi + step * .5; r += step) {
        const rr = Math.min(r, hi), x = eyeX + sx * rr, z = eyeZ + sz * rr, hh = height(x, z);
        const a = Math.atan2(Math.sqrt((R + hh) ** 2 - rr * rr) - R - altitude, rr);
        // Forward visibility: increasing profile angles expose new pixels. Each
        // row receives its FIRST intersection; hidden valleys cost no row writes.
        if (a > prevA) while (row < h && el + (row + .5) / h * de <= a) {
          const target = el + (row + .5) / h * de;
          if (target >= prevA) store(row, prevR + (rr - prevR) * clamp((target - prevA) / (a - prevA), 0, 1));
          row++;
        }
        edge = Math.max(edge, a); prevA = a; prevR = rr;
      }
      skyline[col] = edge;
      // Extend the last valid texel above the silhouette, preventing sky texels
      // from bleeding into the finite-disk antialiasing at the mountain edge.
      if (last !== null) for (let y = row; y < h; y++) { const i = (y * w + col) * 4; geometry.set(geometry.subarray(last, last + 4), i); normal.set(normal.subarray(last, last + 4), i); }
    }
    return { ...q, geometry, normal, skyline, cpu: performance.now() - start };
  }
  onmessage = async ({ data: q }) => {
    try {
      if (q.type === 'init') {
        const start = performance.now(), [heightImage, photoImage] = await Promise.all([pixels(q.heightURL), pixels(q.photoURL)]);
        const decoded = performance.now();
        altitude = q.altitude; eyeX = fullW + 2; eyeZ = H * (.4 + (q.seed % 1009) / 1009 * .2);
        dem = new Float32Array(512 * 512);
        for (let i = 0; i < dem.length; i++) dem[i] = (heightImage.data[i * 4] * 256 + heightImage.data[i * 4 + 1]) * .0005 + 1.5;
        const photoStart = performance.now(), image = photo(photoImage), shadowStart = performance.now(), shadow = horizons(), bakeStart = performance.now(), result = bake(q.base);
        postMessage({ type: 'base', ...result, image, shadow, wall: performance.now() - start,
          phases: { fetchDecode: decoded - start, dem: photoStart - decoded, photo: shadowStart - photoStart, shadow: bakeStart - shadowStart },
          eye: [eyeX, datum + altitude, eyeZ], extent: [W, H], datum }, [result.geometry.buffer, result.normal.buffer, result.skyline.buffer, image.buffer, shadow.buffer]);
      } else { const result = bake(q); postMessage({ type: 'detail', ...result }, [result.geometry.buffer, result.normal.buffer, result.skyline.buffer]); }
    } catch (e) { postMessage({ type: 'error', message: String(e) }); }
  };
}

export function createTerrain(gl, world, changed) {
  let worker, dead = false, ready = false, failed = false, pending = false, uploading = false, pendingStart = 0, timer = 0, wanted, motion = 0, selected, serial = 0;
  const textures = [], cache = [], metrics = { base: null, details: [], detailCount: 0, uploads: [], uploadTotal: 0, mainTasks: [], cacheBytes: 0, failed: null };
  let skyline, promise, resolveStart, rejectStart;
  function upload(unit, w, h, data, half = false, linear = false, channels = 4) {
    const t = performance.now(), tex = gl.createTexture(); textures.push(tex);
    gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, half === 'uint' ? gl.RGBA16UI : half === 'float' ? gl.R32F : channels === 1 ? gl.R8 : gl.RGBA8, w, h, 0,
      half === 'uint' ? gl.RGBA_INTEGER : channels === 1 ? gl.RED : gl.RGBA, half === 'uint' ? gl.UNSIGNED_SHORT : half === 'float' ? gl.FLOAT : gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, linear ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, linear ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (selected && (unit === 13 || unit === 14)) gl.bindTexture(gl.TEXTURE_2D, unit === 13 ? selected.geometry : selected.normal);
    const elapsed = performance.now() - t;
    gl.activeTexture(gl.TEXTURE0); metrics.uploadTotal += elapsed; metrics.uploads.push(elapsed);
    if (metrics.uploads.length > 64) metrics.uploads.shift(); return tex;
  }
  // Valid sampler bindings before first bake; the existing terrain remains visible.
  const placeholder = {};
  for (const unit of [8, 11, 12, 13, 14, 15]) placeholder[unit] = upload(unit, 1, 1, unit === 11 || unit === 13 ? new Uint16Array(4) : new Uint8Array(4), unit === 11 || unit === 13 ? 'uint' : false);
  function remove(tex) { gl.deleteTexture(tex); const i = textures.indexOf(tex); if (i >= 0) textures.splice(i, 1); }
  function afterGPU(run) {
    // Texture mutation can otherwise wait synchronously for an older draw on
    // software/loaded GPUs. Keep the last frame while draining without blocking.
    uploading = true;
    const fence = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0); gl.flush();
    const poll = () => {
      if (dead || gl.isContextLost()) { if (fence && !gl.isContextLost() && gl.isSync(fence)) gl.deleteSync(fence); return; }
      if (fence && gl.clientWaitSync(fence, 0, 0) === gl.TIMEOUT_EXPIRED) { setTimeout(poll, 8); return; }
      if (fence) gl.deleteSync(fence); run();
    };
    setTimeout(poll, 0);
  }
  function contains(q, v) {
    const dx = Math.atan2(Math.sin(v.az - q.az - q.da / 2), Math.cos(v.az - q.az - q.da / 2));
    return Math.abs(dx) + v.da / 2 <= q.da / 2 - q.da / q.w && v.el >= q.el && v.el + v.de <= q.el + q.de
      && q.da / q.w <= v.da / v.width && q.de / q.h <= v.de / v.height;
  }
  function schedule() {
    if (timer || !ready || pending || !wanted || wanted.zoom < 3 || cache.some(q => contains(q, wanted))) return;
    const a = (wanted.az % TAU + TAU) % TAU;
    if ((a + wanted.da / 2 < Math.PI && a - wanted.da / 2 > 0) || wanted.el > 8 * RAD || wanted.el + wanted.de < -32 * RAD) return;
    timer = setTimeout(() => {
      timer = 0;
      if (dead || performance.now() - motion < 110) { schedule(); return; }
      pending = true;
      pendingStart = performance.now();
      worker.postMessage({ type: 'bake', detail: true, id: ++serial, az: wanted.az - wanted.da * .6, el: wanted.el - wanted.de * .1, da: wanted.da * 1.2, de: wanted.de * 1.2,
        w: Math.min(2048, 2 ** Math.ceil(Math.log2(wanted.width * 1.2))), h: Math.min(2048, 2 ** Math.ceil(Math.log2(wanted.height * 1.2))) });
    }, 120);
  }
  function start() {
    if (promise) return promise;
    promise = new Promise((resolve, reject) => { resolveStart = resolve; rejectStart = reject; });
    const url = URL.createObjectURL(new Blob(['(' + terrainWorker.toString() + ')()'], { type: 'text/javascript' }));
    const began = performance.now();
    const fail = message => { if (dead) return; failed = true; metrics.failed = message; worker?.terminate(); clearTimeout(timer); rejectStart(Error(message)); if (ready) changed(); };
    try {
      worker = new Worker(url); URL.revokeObjectURL(url);
      worker.onerror = e => { e.preventDefault(); fail(e.message); };
      worker.onmessage = ({ data: q }) => {
        if (dead || gl.isContextLost()) return;
        if (q.type === 'error') { fail(q.message); return; }
        if (q.type === 'base') {
          skyline = q.skyline;
          // Upload separate textures in separate tasks: the expensive computation and
          // photo correction are already off the main thread.
          const jobs = [
            () => { upload(11, q.w, q.h, q.geometry, 'uint'); }, () => { upload(12, q.w, q.h, q.normal, false, true); },
            () => { upload(15, 128, 2048, q.shadow, false, true, 1); },
            () => {
              upload(7, 853, 1024, q.image, false, true);
              gl.activeTexture(gl.TEXTURE7); gl.generateMipmap(gl.TEXTURE_2D); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR); gl.activeTexture(gl.TEXTURE0);
            },
            () => { const h = new Float32Array(q.w * 2); h.set(q.skyline); upload(8, q.w, 2, h, 'float', false, 1); },
          ];
          const next = () => {
            if (dead || gl.isContextLost()) return;
            if (jobs.length) { const begin = performance.now(); jobs.shift()(); metrics.mainTasks.push(performance.now() - begin); setTimeout(next, 0); }
            else { ready = true; uploading = false; metrics.base = { worker: q.wall, bake: q.cpu, wall: performance.now() - began, phases: q.phases, eye: q.eye, extent: q.extent, datum: q.datum }; resolveStart(); changed(); schedule(); }
          };
          afterGPU(next);
        } else {
          const tile = { az: q.az, el: q.el, da: q.da, de: q.de, w: q.w, h: q.h };
          tile.skyline = q.skyline;
          afterGPU(() => {
            tile.geometry = upload(13, q.w, q.h, q.geometry, 'uint');
            setTimeout(() => {
              if (dead || gl.isContextLost()) return;
              tile.normal = upload(14, q.w, q.h, q.normal, false, true); cache.unshift(tile);
              if (cache.length > 2) { const old = cache.pop(); remove(old.geometry); remove(old.normal); }
              metrics.details.push({ cpu: q.cpu, wall: performance.now() - pendingStart, az: q.az, el: q.el, da: q.da, de: q.de });
              metrics.cacheBytes = cache.reduce((sum, tile) => sum + tile.w * tile.h * 12, 0);
              metrics.detailCount++; if (metrics.details.length > 32) metrics.details.shift();
              pending = false; uploading = false; selected = null; changed(); schedule();
            }, 0);
          });
        }
      };
      worker.postMessage({ type: 'init', base: BASE, altitude: world.altitude, seed: world.seed,
        heightURL: new URL('../assets/bg/ground-mountain-height.webp', import.meta.url).href,
        photoURL: new URL('../assets/bg/ground-mountain-albedo.webp', import.meta.url).href });
    } catch (e) { URL.revokeObjectURL(url); fail(String(e)); }
    return promise;
  }
  return {
    start, metrics,
    get uploading() { return uploading; },
    get ready() { return ready && !failed; },
    horizon(az, el) {
      if (!ready) return null;
      const a = (az % TAU + TAU) % TAU;
      if (a < Math.PI) return -Math.acos(6371 / (6371 + world.altitude));
      const tile = (el == null ? cache : selected ? [selected] : []).find(q => {
        const dx = (a - q.az + TAU) % TAU;
        return dx >= 0 && dx < q.da && (el == null || (el >= q.el && el <= q.el + q.de));
      });
      const dip = -Math.acos(6371 / (6371 + world.altitude));
      if (tile) { const x = (a - tile.az + TAU) % TAU / tile.da * tile.w - .5, l = Math.floor(x), f = x - l; return Math.max(dip, tile.skyline[Math.max(0, l)] * (1 - f) + tile.skyline[Math.min(tile.w - 1, l + 1)] * f); }
      const x = (a - Math.PI) / Math.PI * BASE.w - .5, l = Math.floor(x), f = x - l;
      return Math.max(dip, skyline[Math.max(0, l)] * (1 - f) + skyline[Math.min(BASE.w - 1, l + 1)] * f);
    },
    /** 13 · 14번 칸을 지형 것으로 되돌린다 — 실내 프로그램이 그 칸에 우주 사진(float)을 꽂아 쓰므로 지형 프로그램으로 돌아올 때 부른다(11-06) */
    rebind() {
      gl.activeTexture(gl.TEXTURE13); gl.bindTexture(gl.TEXTURE_2D, selected ? selected.geometry : placeholder[13]);
      gl.activeTexture(gl.TEXTURE14); gl.bindTexture(gl.TEXTURE_2D, selected ? selected.normal : placeholder[14]);
      gl.activeTexture(gl.TEXTURE0);
    },
    view(U, az, el, hfov, vfov, zoom, width, height) {
      if (failed || !ready) { gl.uniform1f(U.uTerrainOn, 0); return; }
      az = (az % TAU + TAU) % TAU;
      gl.uniform1f(U.uTerrainOn, 1);
      const v = { az, el: el - vfov / 2, da: hfov, de: vfov, zoom, width: Math.min(width, 1706), height: Math.min(height, 1706) };
      if (!wanted || Math.abs(az - wanted.az) + Math.abs(el - wanted.el - wanted.de / 2) + Math.abs(hfov - wanted.da) > hfov * .005) motion = performance.now();
      wanted = v;
      const tile = zoom >= 3 && cache.find(q => contains(q, v));
      gl.uniform1f(U.uTerrainDetailOn, tile ? 1 : 0);
      if (tile) {
        if (tile !== selected) {
          gl.activeTexture(gl.TEXTURE13); gl.bindTexture(gl.TEXTURE_2D, tile.geometry); gl.activeTexture(gl.TEXTURE14); gl.bindTexture(gl.TEXTURE_2D, tile.normal);
          gl.activeTexture(gl.TEXTURE8); gl.texSubImage2D(gl.TEXTURE_2D,0,0,1,tile.w,1,gl.RED,gl.FLOAT,tile.skyline);
          gl.activeTexture(gl.TEXTURE0); selected = tile;
        }
        gl.uniform4f(U.uTerrainDetailRect, tile.az, tile.el, tile.da, tile.de);
      } else selected = null;
      schedule();
    },
    destroy() { dead = true; clearTimeout(timer); worker?.terminate(); textures.forEach(t => gl.deleteTexture(t)); },
  };
}

export const terrainShader = `
#if GROUND_OUTDOOR
uniform highp usampler2D uTerrainGeometry, uTerrainDetail;
uniform sampler2D uTerrainNormal, uTerrainDetailNormal, uTerrainSkyline, uTerrainShadow;
uniform float uTerrainDetailOn;
uniform vec4 uTerrainDetailRect;
vec4 terrainHit; vec3 terrainN; float terrainPhoto, terrainBlend, terrainBaseDistance;
vec4 terrainDecode(uvec4 data) { return vec4(vec2(data.rg)/65535.0,float(data.b)*.005,float(data.a)); }
float terrainEdge(float x, int row, int width) {
  float f=x*float(width)-.5; int l=int(floor(f));
  return mix(texelFetch(uTerrainSkyline,ivec2(clamp(l,0,width-1),row),0).r,texelFetch(uTerrainSkyline,ivec2(clamp(l+1,0,width-1),row),0).r,fract(f));
}
vec4 terrainGeometry(vec3 ray, float pixel) {
  if(ray.y>.139174) return vec4(0,300,-2,1);
  float az = mod(atan(ray.x,ray.z) + TAU, TAU), el = asin(clamp(ray.y,-1.0,1.0));
  float dip = -acos(GR / (GR + uGroundAlt));
  float b = (GR + uGroundAlt) * ray.y, c = uGroundAlt * (2.0 * GR + uGroundAlt);
  float distance = min(c / max(-b + sqrt(max(b*b-c,0.0)),.001),300.0);
  terrainBaseDistance=distance; terrainBlend=0.0;
  float edge = dip;
  vec4 hit=vec4(0), norm=vec4(.5,.5,0,1);
  if (az >= 3.14159265) {
    vec2 uv=vec2((az-3.14159265)/3.14159265,(el+.55850536)/.69813170);
    float dx=mod(az-uTerrainDetailRect.x+TAU,TAU);
    vec2 fine=vec2(dx,el-uTerrainDetailRect.y)/uTerrainDetailRect.zw;
    if(uTerrainDetailOn>.5 && min(fine.x,fine.y)>=0.0 && max(fine.x,fine.y)<=1.0) {
      edge=terrainEdge(fine.x,1,textureSize(uTerrainDetail,0).x);
      if(el>max(edge,dip)+pixel*.5) return vec4(0,300,-2,1);
      hit=terrainDecode(textureLod(uTerrainDetail,fine,0.0)); norm=textureLod(uTerrainDetailNormal,fine,0.0);
    } else {
      edge=terrainEdge(uv.x,0,2048);
      if(el>max(edge,dip)+pixel*.5) return vec4(0,300,-2,1);
      hit=terrainDecode(textureLod(uTerrainGeometry,uv,0.0)); norm=textureLod(uTerrainNormal,uv,0.0);
    }
    if(hit.a>.5 && el<=edge+pixel*.5 && (el>=-.55850536 && el<=.13962634) && (ray.y>sin(dip) || hit.z<distance)) {
      distance=hit.z; terrainBlend=clamp(.5+(edge-el)/pixel,0.0,1.0);
    }
    else {hit=vec4(0);norm=vec4(.5,.5,0,1);}
  }
  terrainHit=hit; terrainPhoto=norm.b;
  vec2 slope=norm.rg*2.0-1.0; terrainN=normalize(vec3(slope.x,sqrt(max(.001,1.0-dot(slope,slope))),slope.y));
  return vec4(clamp(.5+(max(edge,dip)-el)/pixel,0.0,1.0),distance,-2,1);
}
// (11-05 Claude) 그림자 경계 폭 soft(rad)는 해 고도에 따라 넓어진다 — 낮은 해일수록 길고 부드러운 그림자.
float terrainShadow(vec2 uv, vec3 light, float soft) {
  float dir=mod(atan(light.x,light.z)+TAU,TAU)/TAU*16.0, a=floor(dir), f=fract(dir);
  vec2 p=clamp(uv,vec2(.5/128.0),vec2(1.0-.5/128.0));
  float h0=textureLod(uTerrainShadow,vec2(p.x,(p.y+a)/16.0),0.0).r;
  float h1=textureLod(uTerrainShadow,vec2(p.x,(p.y+mod(a+1.0,16.0))/16.0),0.0).r;
  return smoothstep(-soft,soft,asin(clamp(light.y,-1.0,1.0))-mix(h0,h1,f)*1.57079633);
}
// 하늘이 보이는 정도(sky view) — 같은 horizon map 의 4방위 평균 지평선 각. 계곡 · 골짜기는 하늘빛을 덜 받는다.
float terrainSky(vec2 uv) {
  vec2 p=clamp(uv,vec2(.5/128.0),vec2(1.0-.5/128.0));
  float h=0.0;
  for(int k=0;k<4;k++) h+=textureLod(uTerrainShadow,vec2(p.x,(p.y+float(k*4))/16.0),0.0).r;
  return clamp(1.0-1.6*sin(h*.25*1.57079633),.4,1.0);
}
vec3 terrainSurface(vec3 ray, vec4 geometry, float pixel) {
  vec3 air=groundAir(ray), lowland=vec3(.082,.084,.062);   // (11-05) 8월 Front Range 동쪽 평지의 마른 풀빛 — 직사가 세져 진한 초록이 튀었다
  vec3 plain=mix(air,lowland*(.018+uSolar.x*.65+uGroundMoonLight*.05),exp(-terrainBaseDistance*.014));
  if(terrainBlend<=0.0) return plain;
  vec3 n=terrainN;
  float lod=max(0.0,log2(1024.0*pixel*geometry.y/(32.0*max(abs(dot(n,ray)),.04))));
  vec3 albedo=lowland;
  if(terrainPhoto>0.0) albedo=mix(lowland,pow(textureLod(uGroundAlbedo,terrainHit.xy,lod).rgb,vec3(2.2)),terrainPhoto);
  // (11-05 Claude) 사진은 Worker 에서 촬영 때 지형 음영을 지운 바탕색(C-correction)이라 여기서 새 해로 다시 칠한다.
  // 빛 = 직사(해 고도 · 그림자) + 하늘빛(위에서, 하늘 보이는 정도) + 땅 반사(아래에서). 환경광을 줄여 빛 닿는 면이 도드라지게.
  float low=1.0-smoothstep(.03,.5,uSunDir.y);   // 해가 낮을수록 1
  float sun=0.0, moon=0.0, sky=mix(1.0,terrainSky(terrainHit.xy),terrainPhoto);
  if(uSolar.x>.001) {
    float ndl=dot(n,uSunDir);
    float shade=mix(1.0,terrainShadow(terrainHit.xy,uSunDir,mix(.010,.040,low)),terrainPhoto);
    // 낮은 해: 해를 향한 경사만 빛을 받고(대비 ↑) 능선 · 볕드는 면이 금빛으로 더 밝아진다.
    sun=max(ndl,0.0)*shade*vSourceClear.x*(1.0+1.4*low*smoothstep(.1,.5,ndl));
  }
  if(uGroundMoonLight>.001) moon=max(dot(n,uMoonDir),0.0)*mix(1.0,terrainShadow(terrainHit.xy,uMoonDir,.02),terrainPhoto)*vSourceClear.y;
  vec3 skyCol=mix(vec3(.30,.36,.46),vec3(.30,.24,.30),uSolar.y);   // 낮 = 푸른 하늘빛, 노을 = 보랏빛
  // 하늘빛 = 지금 지평선 하늘색(groundAir)을 섞어 — 노을 · 박명에 하늘이 밝으면 그늘진 산도 그만큼 밝다.
  vec3 ambient=(skyCol*.45+air*.75)*sky*(.5+.5*n.y)*(.85-.25*low)+uSunCol*.08*(1.0-n.y);
  // 하늘빛은 해가 낮아도 오래 남는다(sqrt) — 역광인 저녁 산이 시커멓지 않게.
  vec3 light=vec3(.016)+sqrt(uSolar.x)*ambient+uSolar.x*uSunCol*1.75*sun+uGroundMoonLight*(vec3(.035,.045,.065)*sky+uMoonCol*.30*moon);
  // (11-05 운영자) 산이 시커멓게 보인다 → 실제 산처럼 녹색으로. Landsat 8월 사진은 마른 올리브 · 갈색(평균 sRGB 68 · 68 · 52)이라
  // 채도를 올리고 초록 쪽으로 틀어 숲 색을 살리고, 노출을 올린다. 평지(사진 밖)는 그대로.
  float lum=dot(albedo,vec3(.2126,.7152,.0722));
  vec3 forest=max(mix(vec3(lum),albedo,1.35)*vec3(.80,1.18,.72),0.0);
  albedo=mix(albedo,forest,terrainPhoto)*mix(1.0,2.2,terrainPhoto);
  vec3 surface=albedo*light;
  // 해 쪽 공기: 해를 향해 볼수록 멀리 있는 능선 사이 공기가 해 색으로 번진다(낮은 해일수록).
  float fwd=max(dot(ray,uSunDir),0.0);
  vec3 airSun=air+uSunCol*uSolar.x*low*.35*pow(fwd,6.0);
  surface=mix(airSun,surface,exp(-geometry.y*.010));   // 원경 공기 조금 옅게 — 푸른 회색이 산 색을 덮었다
  return mix(plain,surface,terrainBlend);
}
#endif
`;
