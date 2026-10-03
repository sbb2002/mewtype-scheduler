// 프론트 banners.js 의 상태 · 텍스트를 시각별로 계산해 JSON 으로 돌려준다 (banner_scenarios.py 가 호출).
//   node banner_front.mjs <in.json> <out.json>     in = {points:[{label, now_iso, banner}]}
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const here = path.dirname(url.fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, "../../../src/frontend/js/banners.js"), "utf8");
const tmp = path.join(here, "run", "banners_front_copy.mjs");   // banners.js 는 package type 이 없어 .mjs 사본으로 import
fs.mkdirSync(path.dirname(tmp), { recursive: true });
fs.writeFileSync(tmp, src);
const m = await import(url.pathToFileURL(tmp).href);

const strip = (h) => h.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();
const [, , inp, outp] = process.argv;
const { points } = JSON.parse(fs.readFileSync(inp, "utf8"));
const out = points.map((p) => {
  const now = Date.parse(p.now_iso);
  const info = m.bannerInfo(p.banner, now);
  const visible = m.visibleBanners({ banners: [p.banner] }, now).length > 0;
  let text = "", dates = "", ends = [], bubble = "";
  if (visible) {
    const html = m.bannerHTML([p.banner], now);
    text = strip(html);
    const g = (re) => { const x = html.match(re); return x ? strip(x[1]) : ""; };
    dates = g(/class="bnr__dates">([\s\S]*?)<\/div>/);
    bubble = g(/class="bnr__bd">([\s\S]*?)<\/div>/);
    ends = [...html.matchAll(/class="bnr__end ([^"]*)"><small>([\s\S]*?)<\/small><b>([\s\S]*?)<\/b>/g)].map((x) => `${strip(x[2])} ${strip(x[3])}${x[1].trim() ? " {" + x[1].trim() + "}" : ""}`);
  }
  return { label: p.label, st: info.st, visible, pct: Math.round(info.pct), bubble: info.bubble, chip: info.chip, dates, ends, htmlBubble: bubble };
});
fs.writeFileSync(outp, JSON.stringify(out, null, 1));
