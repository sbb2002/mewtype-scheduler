// Seeded ground data. All distances/heights are km; approved outdoor imagery loads on demand.
// Debug-only URL controls: ?bgdebug&bgground=city|mountain|sea&bgseed=integer&bgalt=1|2|3.
// Overrides never overwrite the first-visit world. bgspeed=0 also freezes the 64s animation loop.
import { createTerrain, terrainShader } from "./bgterrain.js";

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

export function createGroundTextures(gl, world, changed) {
  let state = world.seed;
  const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
  const N = 512, P = 2048, tile = new Uint8Array(N * N * 4), ridge = new Uint8Array(P * 4 * 4);
  const indoorTile = world.kind === "city" ? new Uint8Array(tile.length) : tile;
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
      tile[i + 2] = h * 255;
      tile[i + 3] = 255 * (.5 + .5 * Math.sin(Math.PI*2*(u*3+v*5)) * Math.sin(Math.PI*2*(u*4-v*2)));
    } else if (world.kind === "mountain") {
      tile[i] = h * 255; tile[i + 1] = Math.max(0, Math.min(255, 128 + dx * 1800));
      tile[i + 2] = Math.max(0, Math.min(255, 128 + dy * 1800)); tile[i + 3] = noise(u, v, 4) * 255;
    } else {
      // 8km repeat: 250m blocks with irregular parks/districts, 16m roads and roofs.
      const bx = Math.floor(u * 32), by = Math.floor(v * 32), rx = u * 32 % 1, ry = v * 32 % 1;
      const district = noise(u, v, 0), block = noise((bx + .5) / 32, (by + .5) / 32, 2);
      const road = Math.min(rx, 1 - rx, ry, 1 - ry) < .035;
      const indoorRoof = Math.sin(rx * 31) * Math.sin(ry * 23) > -.25 ? .08 : -.06;
      indoorTile[i] = (road ? .13 : .28 + block * .26 + indoorRoof) * 255;
      indoorTile[i + 1] = district * 255; indoorTile[i + 2] = road ? 255 : 0;
      indoorTile[i + 3] = road && ((x + y * 3) % 11 < 2) ? 230 : 0;
      // Outdoor fallback has no block/road lattice. Indoor bytes above stay exact.
      const hash = Math.imul((x + y * N) ^ world.seed, 1597334677) >>> 0;
      const lamp = h < .58 && hash / 4294967296 < .055 ? 100 + (hash >>> 24) * .55 : 0;
      tile[i] = hash & 256 ? lamp : 0;
      tile[i + 1] = hash & 256 ? 0 : lamp;
      tile[i + 2] = h * 255; tile[i + 3] = 255;
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
  const anisotropy = gl.getExtension("EXT_texture_filter_anisotropic");
  function upload(unit, width, height_, data, mip) {
    const texture = gl.createTexture(); textures.push(texture);
    gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, width, height_, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, mip ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mip ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    if (mip) gl.generateMipmap(gl.TEXTURE_2D);
    if (anisotropy && world.kind === "city" && (unit === 5 || unit === 7))
      gl.texParameterf(gl.TEXTURE_2D,anisotropy.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(8,gl.getParameter(anisotropy.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
    return texture;
  }
  const groundTile = upload(5, N, N, tile, true); upload(6, P, 4, ridge, false);
  if (indoorTile !== tile) upload(10, N, N, indoorTile, true);
  else { gl.activeTexture(gl.TEXTURE10); gl.bindTexture(gl.TEXTURE_2D, groundTile); }
  // Unit 7 starts neutral; setAlbedo uploads the selected approved photo later.
  upload(7, 1, 1, new Uint8Array([128, 128, 128, 255]), false);
  gl.activeTexture(gl.TEXTURE0);
  const terrain = world.kind === "mountain" ? createTerrain(gl, world, changed) : null;
  const destroy = () => { terrain?.destroy(); textures.forEach(t => gl.deleteTexture(t)); };
  destroy.terrain = terrain;
  destroy.setAlbedo = image => {
    // Mountain crop excludes the eastern city strip; never enlarge the source.
    const width = world.kind === "mountain" ? Math.floor(image.width * 5 / 6) : image.width;
    const height = image.height, canvas = document.createElement("canvas");
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(image,0,0,width,height,0,0,width,height);
    const pixels = ctx.getImageData(0,0,width,height), src = pixels.data;
    if (world.kind === "city") {
      const lights = new Uint8Array(src.length);
      let lamps = 0;
      // Photo-derived likelihood, not a surveyed road/building segmentation.
      // Vegetation and blue/dark water stay unlit; gray roofs/roads seed tiny lamps.
      for (let y=0;y<height;y++) for (let x=0;x<width;x++) {
        const i=(y*width+x)*4, r=src[i], g=src[i+1], b=src[i+2];
        const hi=Math.max(r,g,b),lo=Math.min(r,g,b),l=.2126*r+.7152*g+.0722*b;
        const green=Math.max(0,Math.min(1,(g-Math.max(r,b)*1.04)/18));
        const water=l<65 && b>r*.95 && b>g*.95 ? 1 : 0;
        const neutral=Math.max(0,1-(hi-lo)/Math.max(hi,1)*3.2);
        const built=neutral * Math.max(0,Math.min(1,(l-42)/45)) * (1-green) * (1-water);
        lights[i+2]=built*255; lights[i+3]=255;
      }
      const dirs=[1,0,0,1,1,1,1,-1];
      const at=(x,y)=>lights[(((y+height)%height)*width+(x+width)%width)*4+2]/255;
      for(let y=0;y<height;y++)for(let x=0;x<width;x++) {
        const i=(y*width+x)*4, built=lights[i+2]/255;
        if(built<.04)continue;
        let road=0;
        // Coherent narrow gray runs favor roads over broad gray roofs. The four
        // directions are image evidence, not a generated world road lattice.
        for(let axis=0;axis<8;axis+=2) {
          const dx=dirs[axis],dy=dirs[axis+1];
          const along=Math.min(at(x+dx*4,y+dy*4),at(x-dx*4,y-dy*4),at(x+dx*2,y+dy*2),at(x-dx*2,y-dy*2));
          const across=(at(x-dy*2,y+dx*2)+at(x+dy*2,y-dx*2))*.5;
          road=Math.max(road,along*(1-across*.8));
        }
        road*=built;
        let hash=Math.imul((x+y*width)^world.seed,1597334677)>>>0;
        hash=Math.imul(hash^(hash>>>16),2246822519)>>>0;
        if(hash/4294967296 < .06*built+.3*road) {
          const strength=75+((hash>>>8)&255)*.35+road*180;
          lights[i+(hash&512?0:1)]=Math.min(255,strength); lamps++;
        }
      }
      upload(5,width,height,lights,true);
      gl.deleteTexture(groundTile); textures.splice(textures.indexOf(groundTile),1);
    }
    // Local luminance integral: remove 45% of broad baked illumination while
    // retaining roofs/forest color and some relief. This is an albedo estimate.
    const stride = width+1, sum = new Float64Array(stride*(height+1));
    for (let y=0;y<height;y++) {
      let row=0;
      for (let x=0;x<width;x++) {
        const i=(y*width+x)*4;
        row += .2126*src[i]+.7152*src[i+1]+.0722*src[i+2];
        sum[(y+1)*stride+x+1]=sum[y*stride+x+1]+row;
      }
    }
    const mean = sum[height*stride+width]/(width*height), out = new Uint8Array(src.length);
    for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
      const x0=Math.max(0,x-64),x1=Math.min(width,x+65),y0=Math.max(0,y-64),y1=Math.min(height,y+65);
      const local=(sum[y1*stride+x1]-sum[y0*stride+x1]-sum[y1*stride+x0]+sum[y0*stride+x0])/((x1-x0)*(y1-y0));
      const gain=Math.max(.72,Math.min(1.45,Math.pow(mean/Math.max(local,8),.45)));
      const i=(y*width+x)*4;
      for(let c=0;c<3;c++) out[i+c]=Math.min(255,src[i+c]*gain);
      out[i+3]=255;
    }
    // NAIP quarter-tile joins inferred from the supplied geographic crop:
    // longitude -104.9375, latitude 39.75 within [-104.977,-104.883,39.694,39.766].
    // Match strip means with bounded scalar gains (preserve hue and detail).
    if (world.kind === "city") {
      const jx=Math.round(width*.0395/.094), jy=Math.round(height*.016/.072);
      const meanBox=(x0,y0,x1,y1)=>{
        let total=0,count=0;
        for(let y=y0;y<y1;y+=2)for(let x=x0;x<x1;x+=2){const i=(y*width+x)*4;total+=.2126*out[i]+.7152*out[i+1]+.0722*out[i+2];count++;}
        return Math.max(8,total/count);
      };
      const lr=(y0,y1)=>Math.log(meanBox(jx-20,y0,jx,y1)/meanBox(jx,y0,jx+20,y1));
      const tb=(x0,x1)=>Math.log(meanBox(x0,jy-20,x1,jy)/meanBox(x0,jy,x1,jy+20));
      const top=lr(0,jy),left=tb(0,jx);
      const gains=[0,top,left,(top+tb(jx,width)+left+lr(jy,height))*.5];
      const center=gains.reduce((a,b)=>a+b,0)/4;
      for(let y=0;y<height;y++)for(let x=0;x<width;x++){
        const gain=Math.exp(Math.max(-.08,Math.min(.08,gains[(y>=jy?2:0)+(x>=jx?1:0)]-center)));
        const i=(y*width+x)*4;
        for(let c=0;c<3;c++)out[i+c]=Math.min(255,out[i+c]*gain);
      }
    }
    // Wrapped edge crossfade on both axes; exact edge pair agreement, same size.
    for(const vertical of [true,false]) {
      const length=vertical?width:height, across=vertical?height:width, band=32;
      const copy=out.slice();
      for(let b=0;b<across;b++)for(let a=0;a<band;a++) {
        const i=(vertical?b*width+a:a*width+b)*4;
        const j=(vertical?b*width+length-1-a:(length-1-a)*width+b)*4;
        const weight=.5*(1-a/band)*(1-a/band);
        for(let c=0;c<3;c++){out[i+c]=copy[i+c]*(1-weight)+copy[j+c]*weight;out[j+c]=copy[j+c]*(1-weight)+copy[i+c]*weight;}
      }
    }
    upload(7,width,height,out,true);
    gl.activeTexture(gl.TEXTURE0);
  };
  // Match the shader's LINEAR wrapped ridge samples, including the RG encoding.
  const ridgeAt = (az, layer) => {
    const x = az / (Math.PI * 2) * P - .5, left = Math.floor(x), f = x - left;
    const at = col => {
      const i = (layer * P + (col % P + P) % P) * 4;
      return (ridge[i] * 256 + ridge[i + 1]) * 4 / 65535;
    };
    return at(left) * (1 - f) + at(left + 1) * f;
  };
  destroy.sourceVisibility = (direction, radius, pixel) => {
    const alt = world.altitude, GR = 6371, dip = -Math.sqrt(alt * (2 * GR + alt)) / (GR + alt);
    const horizontal = Math.hypot(direction[0], direction[2]);
    const right = horizontal > 1e-8 ? [direction[2] / horizontal, 0, -direction[0] / horizontal] : [1, 0, 0];
    const up = [direction[1] * right[2], direction[2] * right[0] - direction[0] * right[2], -direction[1] * right[0]];
    const clamp = x => Math.max(0, Math.min(1, x));
    let visible = 0;
    for (let y = -1; y <= 1; y++) for (let x = -1; x <= 1; x++) {
      const ray = direction.map((v, i) => v + radius * .65 * (x * right[i] + y * up[i]));
      const length = Math.hypot(...ray); for (let i = 0; i < 3; i++) ray[i] /= length;
      if (terrain?.ready) {
        visible += clamp(.5 + (Math.asin(ray[1]) - terrain.horizon(Math.atan2(ray[0], ray[2]), Math.asin(ray[1]))) / pixel);
        continue;
      }
      let mask = clamp(.5 + (dip - ray[1]) / pixel);
      const b = (GR + alt) * ray[1], c = alt * (2 * GR + alt);
      let distance = c / Math.max(-b + Math.sqrt(Math.max(b * b - c, 0)), .001);
      if (world.index === 1) {
        const az = Math.atan2(ray[0], ray[2]), h = Math.max(Math.hypot(ray[0], ray[2]), .0001);
        for (let i = 2; i >= 0; i--) {
          const r = (world.index === 0 ? [8, 22, 65] : [12, 35, 80])[i];
          const edge = (ridgeAt(az, i) - alt - r * r / (2 * GR)) / r;
          const k = clamp(.5 + (edge * h - ray[1]) / pixel);
          if (k > 0 && (mask < .5 || r / h < distance)) { mask = Math.max(mask, k); distance = r / h; }
        }
      }
      visible += 1 - mask;
    }
    return visible / 9;
  };
  return destroy;
}

// Preserve the existing indoor material exactly, including its neutral color blend.
const groundIndoorSurface = `
vec3 groundSurfaceIndoor(vec3 ray, vec4 geometry, float pixel) {
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
  vec4 data = textureLod(uGroundIndoorTile, uv, lod);
  float day = uOut > .5 ? uSolar.x : .65;
  float night = uOut > .5 ? max(uNight, 1.0 - day) : .15;
  vec3 albedo, emission = vec3(0);
  if (uGroundKind > 1.5) {
    // Two precomputed periodic slope fields, 64s closed loop; no per-pixel noise synthesis.
    float phase = mod(uTime, 64.0) / 64.0;
    vec2 slope = textureLod(uGroundIndoorTile, pos.xz / 1.4 + vec2(phase, 0), max(0.0, lod + 2.0)).rg;
    slope += textureLod(uGroundIndoorTile, pos.xz / 2.1 + vec2(0, -phase), max(0.0, lod + 1.0)).rg;
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
    vec4 cars = textureLod(uGroundIndoorTile, uv + vec2(phase,0), lod);
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

export const groundShader = `
uniform sampler2D uGroundTile, uGroundRidge, uGroundAlbedo, uGroundIndoorTile;
uniform float uGroundKind, uGroundAlt, uGroundAlbedoOn, uGroundMoonLight;
uniform vec2 uGroundSourceVisibility;
vec3 groundDx, groundDy;
vec2 cityDx, cityDy;
const float GR = 6371.0;
float ridgeHeight(float az, int layer) {
  vec4 h = textureLod(uGroundRidge, vec2(az / TAU, (float(layer) + .5) / 4.0), 0.0);
  return dot(h.rg, vec2(65280.0, 255.0)) * (4.0 / 65535.0);
}
// Prototypes allow the shared geometry to use the mountain-only baked path.
#if GROUND_OUTDOOR
vec4 terrainGeometry(vec3 ray, float pixel);
vec3 terrainSurface(vec3 ray, vec4 geometry, float pixel);
uniform float uTerrainOn;
#endif
// Shared geometry for surface, celestial occultation, and lens source visibility.
// External origin is independent of dome E/zoom. Three radial distance belts, no raymarch.
vec4 groundGeometry(vec3 ray, float pixel) {
#if GROUND_OUTDOOR
  if (uGroundKind > .5 && uGroundKind < 1.5 && uTerrainOn > .5) return terrainGeometry(ray, pixel);
#endif
  // Conservative bound: no surface or ridge can reach above this elevation.
  float top = uGroundKind < .5 ? (.28 - uGroundAlt) / 65.0 : (3.5 - uGroundAlt) / 12.0;
  if (ray.y > max(top, 0.0) + pixel) return vec4(0, 300, -1, 1);
  float dip = -sqrt(uGroundAlt * (2.0 * GR + uGroundAlt)) / (GR + uGroundAlt);
  float mask = clamp(.5 + (dip - ray.y) / pixel, 0.0, 1.0);
  float b = (GR + uGroundAlt) * ray.y;
  float c = uGroundAlt * (2.0 * GR + uGroundAlt);
  float root = sqrt(max(b * b - c, 0.0));
  // Rationalized near root avoids cancellation looking straight down.
  float distance = c / max(-b + root, .001);
  float selected = -1.0, edgeCoverage = 1.0;
#if GROUND_OUTDOOR
  if (uGroundKind > .5 && uGroundKind < 1.5) {
#else
  if (uGroundKind < 1.5) {
#endif
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
${terrainShader}
${groundIndoorSurface}
// Three translated photo charts on a 16km triangular lattice. The hash changes
// per world vertex: there is no exact 8km repeated photograph or checkerboard.
vec4 cityPhoto(sampler2D tex, vec2 uv) {
  vec2 cell=floor(uv*.5), f=fract(uv*.5);
  vec2 a=cell, b=cell+vec2(1,0), c=cell+vec2(0,1);
  vec3 w=vec3(1.0-f.x-f.y,f.x,f.y);
  if (f.x+f.y>1.0) { a=cell+vec2(1); w=vec3(f.x+f.y-1.0,1.0-f.y,1.0-f.x); }
  // Drop negligible contributions continuously before normalization. Large
  // coherent regions need one chart, retaining full filtering of the visible lights.
  w=max(w*w*w-vec3(.01),vec3(0)); w/=dot(w,vec3(1));
  vec4 color=vec4(0);
  if(w.x>0.0)color+=textureGrad(tex,uv+vec2(h2(a),h2(a+71.7)),cityDx,cityDy)*w.x;
  if(w.y>0.0)color+=textureGrad(tex,uv+vec2(h2(b),h2(b+71.7)),cityDx,cityDy)*w.y;
  if(w.z>0.0)color+=textureGrad(tex,uv+vec2(h2(c),h2(c+71.7)),cityDx,cityDy)*w.z;
  return color;
}
vec3 groundSurface(vec3 ray, vec4 geometry, float pixel) {
  if (uOut < .5) return groundSurfaceIndoor(ray, geometry, pixel);
#if GROUND_OUTDOOR
  if (uGroundKind > .5 && uGroundKind < 1.5 && uTerrainOn > .5) return terrainSurface(ray, geometry, pixel);
#endif
  vec3 pos = vec3(0, GR + uGroundAlt, 0) + ray * geometry.y;
  vec3 n = normalize(pos), v = -ray;
  vec2 uv = pos.xz / (uGroundKind < .5 ? 8.0 : 32.0);
  // Analytic sphere Jacobian from ray derivatives computed before divergence.
  float plane=min(dot(n,ray),-.001);
  cityDx=(geometry.y*(groundDx-ray*dot(n,groundDx)/plane)).xz/8.0;
  cityDy=(geometry.y*(groundDy-ray*dot(n,groundDy)/plane)).xz/8.0;
  // Derivatives from the ray footprint, not a discontinuous longitude or selected belt.
  float footprint = min(8.0, pixel * geometry.y / max(abs(dot(n, ray)), .025));
  float lod = max(0.0, log2(512.0 * footprint / (uGroundKind < .5 ? 8.0 : 32.0)));
  if (uGroundKind > .5 && uGroundKind < 1.5 && geometry.z >= 0.0) {
    float elevation = uGroundAlt + ray.y * geometry.y + dot(pos.xz,pos.xz)/(2.0*GR);
    uv = vec2(atan(ray.x,ray.z) / TAU * 5.0, elevation / 3.5 + geometry.z * .31);
    lod = max(0.0,log2(pixel * geometry.y * 512.0 / 3.5));
  }
  vec4 data = vec4(0);
  if (uGroundKind > .5 && uGroundKind < 1.5) data = textureLod(uGroundTile, uv, lod);
  float day = uOut > .5 ? uSolar.x : .65;
  float night = uOut > .5 ? max(uNight, 1.0 - day) : .15;
  vec3 albedo, emission = vec3(0);
  if (uGroundKind > 1.5) {
    // Two precomputed periodic slope fields, 64s closed loop; no per-pixel noise synthesis.
    float phase = mod(uTime, 64.0) / 64.0;
    vec2 slope = textureLod(uGroundTile, pos.xz / 1.4 + vec2(phase, 0), max(0.0, lod + 2.0)).rg;
    slope += textureLod(uGroundTile, pos.xz / 2.1 + vec2(0, -phase), max(0.0, lod + 1.0)).rg;
    vec3 baseN = n;
    n = normalize(n + vec3((slope.x - 1.0) * .16, 0, (slope.y - 1.0) * .16));
    float swellLod = max(0.0, log2(512.0 * footprint / 12.0));
    float swell = textureLod(uGroundTile, pos.xz / 12.0 + vec2(phase, -phase), swellLod).b;
    float patchLod=max(0.0,log2(512.0*footprint/5.0));
    vec4 facets=textureLod(uGroundTile,pos.xz/5.0+vec2(phase,-phase),patchLod);
    // Travelling, irregular facets split the existing source column. Both fields
    // wrap after exactly 64s; mipmaps suppress distant temporal sparkle.
    float glint=(.2+.8*smoothstep(.32,.72,swell))
      *(.12+2.0*smoothstep(.36,.65,facets.b*.45+facets.a*.55));
    n=normalize(n+vec3((facets.b-.5)*.025,0,(facets.a-.5)*.025));
    float fresnel = .02 + .98 * pow(1.0 - max(dot(n,v), 0.0), 5.0);
    albedo = mix(vec3(.012,.045,.055), groundAir(ray) * .65, fresnel);
    for (int i = 0; i < 2; i++) {
      float light = i == 0 ? uSolar.z * (.45 + .55 * day) * 1.4 : uGroundMoonLight * .85;
      float sourceClear = i == 0 ? vSourceClear.x : vSourceClear.y;
      float sourceVisible = i == 0 ? uGroundSourceVisibility.x : uGroundSourceVisibility.y;
      if (light * sourceClear * sourceVisible < .00001) continue;
      vec3 l = i == 0 ? uSunDir : uMoonDir;
      vec3 halfway = (v + l) / max(length(v + l), .00001);
      // Anisotropic microfacets spread the source along its azimuth toward the
      // horizon. A finite pixel footprint filters distant ripples, not the source.
      vec3 across = normalize(cross(baseN, l) + vec3(.00001,0,0));
      vec3 along = cross(across, n);
      float nh = max(dot(n, halfway), 0.0), nl = max(dot(n, l), 0.0);
      float ax = .065 + min(footprint / 12.0, .025), ay = .3;
      float hx = dot(halfway, across) / ax, hy = dot(halfway, along) / ay;
      float den = hx * hx + hy * hy + nh * nh;
      float specular = 1.0 / max(3.14159 * ax * ay * den * den, .00001);
      // Microfacet BRDF nl cancellation: grazing reflection must not disappear at sunset.
      float brdf = specular * (.02 + .98 * pow(1.0 - max(dot(v,halfway),0.0),5.0));
      brdf /= 4.0 * max(dot(n,v), .035);
      emission += (i == 0 ? uSunCol : uMoonCol) * min(brdf, 8.0) * smoothstep(0.0,.018,nl) * light * .10 * glint * sourceClear * sourceClear * sourceVisible;
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
    vec4 lamps=cityPhoto(uGroundTile,uv);
    albedo=vec3(.08,.085,.085);
    float shimmer=1.0+.012*sin(uTime*TAU/16.0+uv.x*1.7+uv.y*.8);
    emission=(vec3(1.0,.43,.12)*lamps.r+vec3(.78,.87,1.0)*lamps.g)*6.5*night*shimmer;
  }
  float photoGain=uGroundKind<.5 ? smoothstep(.005,.08,day) : 1.0;
  if (uGroundAlbedoOn > .5 && uGroundKind < 1.5 && photoGain>.001) {
    // Photo resolution is twice the procedural tile; the cropped mountain
    // covers 26.67km east-west. Ridge UV uses only the rural cropped texture.
    vec2 photoUV = uv;
    if (uGroundKind > .5 && geometry.z < 0.0) photoUV.x *= 1.2;
    vec3 photo = pow((uGroundKind < .5 ? cityPhoto(uGroundAlbedo,uv) : textureLod(uGroundAlbedo,photoUV,lod+1.0)).rgb,vec3(2.2));
    albedo = mix(albedo,photo,.84*photoGain);
  }
  float diffuse = max(dot(n,uSunDir),0.0);
  vec3 surface = albedo * (.055 + day * (.42 + .75 * diffuse)) + emission;
  if (uOut < .5) {
    float gray = dot(surface,vec3(.2126,.7152,.0722));
    surface = mix(groundAir(ray) * vec3(.85,.69,.8), vec3(.46,.29,.38) + gray * .3, .4);
  }
  float haze = uGroundKind > 1.5 ? .009 : (uGroundKind < .5 ? mix(.021,.012,night) : .021);
  return mix(groundAir(ray), surface, geometry.w * exp(-geometry.y * haze));
}
`;
