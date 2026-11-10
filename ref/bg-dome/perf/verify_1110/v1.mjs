import { open, sleep } from "../cdp.mjs";
const B = "http://127.0.0.1:8131/src/frontend/index.html";
const c = await open(9341);
const probe = `(() => { const r = performance.getEntriesByType("resource").map(e => e.name.split("/").pop().split("?")[0]);
  return { domegl: r.includes("bgdomegl.js"), ground: r.includes("bgground.js"), imgs: r.filter(n => /\.(webp|png|jpg)$/.test(n)).length,
    canvas: !!document.querySelector("#bgdeco canvas"), svg: !!document.querySelector("#bgdeco svg.bgdm-dome"), sky: !!document.querySelector("#bgdeco .bgdm-sky"),
    bday: document.documentElement.getAttribute("data-bday"), variant: document.querySelector("#bgdeco")?.dataset.variant || null }; })()`;
for (const [name, url] of [["dome", B], ["classic", B + "?bg=classic"], ["bday", B + "?bday=yuno"]]) {
  c.logs.length = 0; await c.load(url); await sleep(1500);
  console.log(name, JSON.stringify(await c.ev(probe)), c.logs.filter(l => /EXC|error|bgdome/i.test(l)).slice(0, 5));
  await c.shot(`v1_${name}.jpg`);
  if (name === "bday") {
    await c.ev(`import("/src/frontend/js/birthdayui.js").then(m => m.setBirthdayOn(false))`); await sleep(3000);
    console.log("bday-off", JSON.stringify(await c.ev(probe)), c.logs.filter(l => /EXC|error|bgdome/i.test(l)).slice(0, 5));
    await c.shot("v1_bdayoff.jpg");
  }
}
await c.load(B + "?bg=classic"); await c.ev(`import("/src/frontend/js/bgdeco.js").then(m => m.setBgTheme("dome"))`); await sleep(3000);
console.log("classic->dome", JSON.stringify(await c.ev(probe)), c.logs.filter(l => /EXC|error/i.test(l)).slice(0, 5));
await c.close(); process.exit(0);
