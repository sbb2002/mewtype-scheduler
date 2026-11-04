// D 시험안: 구름은 CSS로 흐르고, 반구 유리와 바닥은 크기가 바뀔 때만 투영한다.
const NS = "http://www.w3.org/2000/svg";
const DEG = Math.PI / 180;

function sv(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value);
  if (parent) parent.appendChild(e);
  return e;
}

/** 단위 반구 안쪽 카메라. 경위도와 반사는 모두 같은 구면 좌표계를 쓴다. */
export function domeGeometry(W, H) {
  const phone = W <= 767;
  const focal = phone ? W * 1.25 : W * 0.76;
  const pitch = 28 * DEG, eyeY = 0.24, eyeZ = -0.42;
  const c = Math.cos(pitch), s = Math.sin(pitch);
  const rimY = H - (phone ? 68 : 130);
  const centerY = rimY - focal * (eyeY * c + (1 - eyeZ) * s) / (-eyeY * s + (1 - eyeZ) * c);
  function project(lat, lon) {
    const x = Math.cos(lat) * Math.sin(lon);
    const y = Math.sin(lat) - eyeY, z = Math.cos(lat) * Math.cos(lon) - eyeZ;
    const depth = y * s + z * c;
    if (depth < 0.06) return null;
    return [W / 2 + focal * x / depth, centerY - focal * (y * c - z * s) / depth];
  }
  function path(points) {
    let d = "", open = false;
    for (const point of points) {
      // 뒷면·근평면을 가로질러 선이 연결되지 않게 끊는다.
      if (!point) { open = false; continue; }
      d += `${open ? "L" : "M"}${point[0].toFixed(2)},${point[1].toFixed(2)}`;
      open = true;
    }
    return d;
  }
  const samples = (n, fn) => Array.from({ length: n + 1 }, (_, i) => fn(i / n));
  const latitudes = [18, 40, 62].map((lat) => path(samples(360, (t) => project(lat * DEG, (-180 + t * 360) * DEG))));
  // 경도선은 천정까지 잇는다(2026-11-04 운영자 결정 — 11-02 의 「62°에서 멈춤」을 거뒀다)
  const longitudes = Array.from({ length: 12 }, (_, i) => path(samples(150, (t) => project(t * 90 * DEG, i * 30 * DEG))));
  // 앞쪽 적도가 돔과 바닥의 접점이다. 같은 투영으로 격자 끝과 정확히 맞춘다.
  const rimPoints = samples(240, (t) => project(0, (-88 + t * 176) * DEG));
  const rim = path(rimPoints);
  const first = rimPoints[0], last = rimPoints.at(-1);
  const floor = `${rim} L${last[0].toFixed(2)},${H + 200} L${first[0].toFixed(2)},${H + 200} Z`;
  const reflections = [-71, 69].map((lon) => path(samples(120, (t) => project((8 + t * 76) * DEG, lon * DEG))));
  return { latitudes, longitudes, rim, floor, reflections };
}

function clouds(host) {
  if (host.querySelector(".bgdm-sky")) return;
  const sky = document.createElement("div");
  sky.className = "bgdm-sky";
  for (const layer of ["far", "near"]) {
    const track = document.createElement("div");
    track.className = `bgdm-cloud bgdm-cloud--${layer}`;
    sky.appendChild(track);
  }
  host.appendChild(sky);
}

export function buildDomeScene(host, W, H) {
  clouds(host);
  const geo = domeGeometry(W, H), phone = W <= 767;
  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", focusable: "false", class: "bgdm-dome" });
  const defs = sv("defs", {}, svg);
  // 사진의 명암·알파는 유지하면서 야간 색을 장밋빛으로 제한한다.
  // 색상 회전만 쓰면 원본의 노란 구름 가장자리가 녹갈색으로 변할 수 있다.
  for (const [id, values] of [
    ["bgdm-rose-sky", ".204 .408 .068 0 .04 .084 .168 .028 0 .02 .132 .264 .044 0 .04 0 0 0 1 0"],
    ["bgdm-rose-cloud", ".27 .54 .09 0 .06 .15 .30 .05 0 .02 .204 .408 .068 0 .04 0 0 0 1 0"],
  ]) {
    const filter = sv("filter", { id, x: 0, y: 0, width: "100%", height: "100%", "color-interpolation-filters": "sRGB" }, defs);
    sv("feColorMatrix", { type: "matrix", values }, filter);
  }
  const floorTone = sv("linearGradient", { id: "bgdm-floor-tone", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
  sv("stop", { offset: 0, class: "bgdm-floor-back" }, floorTone);
  sv("stop", { offset: 1, class: "bgdm-floor-front" }, floorTone);
  const glass = sv("g", { class: "bgdm-glass" }, svg);
  for (const d of [...geo.latitudes, ...geo.longitudes]) sv("path", { d, class: "bgdm-grid" }, glass);
  for (const d of geo.reflections) sv("path", { d, class: "bgdm-reflection" }, glass);
  sv("path", { d: geo.floor, class: "bgdm-floor" }, svg);
  sv("path", { d: geo.rim, class: "bgdm-rim-base" }, svg);
  sv("path", { d: geo.rim, class: "bgdm-rim-light" }, svg);

  // 범용 도형 네 개만 실내에 둔다. 외부 하늘·유리는 물리 그룹에 들어가지 않는다.
  const edge = phone ? 34 : 28, u = phone ? 10 : 17;
  const spots = [[edge, H * .19], [W - edge, H * .34], [edge, H * .69], [W - edge, H - 67]];
  const items = [], els = [];
  spots.forEach(([x, y], i) => {
    const phys = sv("g", { class: "bgdm-body" }, svg);
    phys.style.transformOrigin = `${x}px ${y}px`;
    const g = sv("g", { transform: `translate(${x} ${y})`, class: `bgdm-piece bgdm-piece--${i}` }, phys);
    if (i === 0) sv("circle", { r: u, class: "bgdm-outline" }, g);
    if (i === 1) sv("path", { d: `M0 ${-u} L${u} ${u * .8} H${-u} Z`, class: "bgdm-outline" }, g);
    if (i === 2) sv("path", { d: `M${-u * 1.4} 0 q${u * .7} ${-u} ${u * 1.4} 0 t${u * 1.4} 0`, class: "bgdm-outline" }, g);
    if (i === 3) sv("rect", { x: -u * .65, y: -u * .65, width: u * 1.3, height: u * 1.3, rx: 2, transform: "rotate(30)", class: "bgdm-gem" }, g);
    items.push({ x, y, u, ang: 0 }); els.push({ phys });
  });
  return { svg, items, els };
}
