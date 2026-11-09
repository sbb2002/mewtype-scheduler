// monitorminesui.js — 모니터링 페이지 「모두 열기」 지뢰찾기 화면(운영자 11-09, 정본 = devpapers docs/plan/bg-dome/hud_implementation.md).
// 숨은 입력(초기화 확인창 밀어내기 ↑↑↓↓←→←→)에서 방향 8개를 넣은 직후, 리포트(iframe — srcdoc 이라 같은 출처)의 전체 추이 잔디 그리드를
// 5 × 7 붉은 버튼 판으로 바꾼다. 규칙은 monitormines.js. 깃발 3개가 모두 지뢰 위면 배경 테마 이스터에그를 모두 열고(bgunlock.unlockAllStored) 안내 창,
// 지뢰를 누르면 폭발 효과 뒤 처음 화면(잔디 그리드)으로 — 다시 하려면 숨은 입력을 처음부터. 방향 뒤 B · A(생일 이스터에그)는 그대로 쓸 수 있다.
// 고정 문구 · 숫자만 쓰고 createElement · textContent 로 만든다(innerHTML 금지).

import { createGame, reveal, toggleFlag, count, flagsUsed, MAX_FLAGS } from "./monitormines.js";
import { unlockAllStored } from "./bgunlock.js";

const LONG_MS = 450;
const CSS = `
.mon-mines{display:grid;gap:10px;justify-items:center;padding:6px 0 4px}
.mon-mines__bar{font:600 12px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.08em;color:#ffc1da;text-shadow:0 0 8px #ff488d}
.mon-mines__grid{display:grid;grid-template-columns:repeat(7,34px);gap:4px;touch-action:manipulation;user-select:none;-webkit-user-select:none}
.mon-mines__c{width:34px;height:34px;padding:0;border:1px solid #ff6b8f;border-radius:4px;background:linear-gradient(160deg,#c3243f,#7d0f23);color:#fff;
  font:700 15px ui-monospace,Menlo,Consolas,monospace;cursor:pointer;box-shadow:inset 0 1px 0 #ff9fb0,0 0 6px #ff304f55;-webkit-touch-callout:none}
.mon-mines__c:focus-visible{outline:2px solid #8ae3e2;outline-offset:2px}
.mon-mines__c.is-open{background:#1c1e24;border-color:#2c2f38;box-shadow:none;cursor:default}
.mon-mines__c.is-flag::after{content:"⚑";color:#ffe27a;text-shadow:0 0 6px #ffb800}
.mon-mines__c.is-mine{background:#3a0710;border-color:#ff304f}
.mon-mines__c.is-mine::after{content:"✸";color:#ffcc66}
.mon-mines__c[data-n="1"]{color:#7fd0ff}.mon-mines__c[data-n="2"]{color:#8fe3a8}.mon-mines__c[data-n="3"]{color:#ffd27a}.mon-mines__c[data-n="4"]{color:#ff9ad0}
.mon-mines__hint{margin:0;font-size:11px;color:#8b8f99}
.mon-mines.is-boom{animation:mon-mines-shake .5s cubic-bezier(.36,.07,.19,.97) 2}
.mon-mines__flash{position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at var(--bx) var(--by),#fff 0,#ffcc66 6%,#ff304fcc 18%,#ff304f00 55%);opacity:0;z-index:50}
.mon-mines__flash.is-on{animation:mon-mines-flash 1.2s ease-out forwards}
@keyframes mon-mines-shake{10%,90%{transform:translateX(-2px)}20%,80%{transform:translateX(4px)}30%,50%,70%{transform:translateX(-7px)}40%,60%{transform:translateX(7px)}}
@keyframes mon-mines-flash{0%{opacity:0}8%{opacity:1}100%{opacity:0}}
@media(prefers-reduced-motion:reduce){.mon-mines.is-boom{animation:none}.mon-mines__flash.is-on{animation:none;opacity:.6}}
`;

function el(doc, tag, cls, text) { const e = doc.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

/** frame = 리포트 iframe. onEnd() = 폭발이 끝남(처음 화면으로) — 부르는 쪽이 숨은 입력 진행을 되돌린다 */
export function createMines(frame, { onEnd }) {
  let box = null, cal = null, style = null, flash = null, game = null, timers = [];
  const later = (fn, ms) => { const t = setTimeout(fn, ms); timers.push(t); };

  function hide() {
    for (const t of timers) clearTimeout(t); timers = [];
    box?.remove(); style?.remove(); flash?.remove(); box = style = flash = null; game = null;
    if (cal) { cal.style.display = ""; cal = null; }
  }
  function draw() {
    const cells = box.querySelectorAll(".mon-mines__c");
    cells.forEach((c, i) => {
      const open = game.open[i], flag = game.flag[i], mine = game.mine && game.mine[i] && game.state === "boom";
      c.classList.toggle("is-open", open && !mine);
      c.classList.toggle("is-flag", flag && !open);
      c.classList.toggle("is-mine", !!mine);
      const n = open && !mine ? count(game, i) : 0;
      c.textContent = n ? String(n) : "";
      if (n) c.dataset.n = String(n); else delete c.dataset.n;
      c.setAttribute("aria-label", mine ? "지뢰" : flag ? "깃발" : open ? (n ? `${n}` : "빈칸") : "닫힌 칸");
    });
    box.querySelector(".mon-mines__bar").textContent = `남은 깃발 ${MAX_FLAGS - flagsUsed(game)} / ${MAX_FLAGS}`;
  }
  function boom(cell) {
    const doc = frame.contentDocument, r = cell.getBoundingClientRect();
    flash = el(doc, "div", "mon-mines__flash");
    flash.style.setProperty("--bx", `${r.left + r.width / 2}px`); flash.style.setProperty("--by", `${r.top + r.height / 2}px`);
    doc.body.append(flash);
    void flash.offsetWidth; flash.classList.add("is-on"); box.classList.add("is-boom");
    later(() => { hide(); onEnd(); }, 1400);
  }
  function win() {
    const ok = unlockAllStored(window.localStorage);
    popup(ok ? "배경 테마 이스터에그를 모두 열었어요. 메인 화면의 배경 보기에서 확인해 보세요." : "이 브라우저에서는 저장할 수 없어 열지 못했어요.");
    later(() => { hide(); onEnd(); }, 300);
  }
  function popup(text) {
    const p = document.createElement("div");
    p.className = "mon-mines-pop"; p.setAttribute("role", "alertdialog"); p.setAttribute("aria-modal", "true");
    const msg = document.createElement("p"); msg.textContent = text;
    const ok = document.createElement("button"); ok.type = "button"; ok.textContent = "확인";
    ok.addEventListener("click", () => p.remove());
    p.append(msg, ok);
    if (!document.getElementById("mon-mines-pop-style")) {
      const st = document.createElement("style"); st.id = "mon-mines-pop-style";
      st.textContent = ".mon-mines-pop{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:20;max-width:min(360px,calc(100vw - 32px));padding:18px 18px 14px;background:#14161c;border:1px solid #ff488d;border-radius:8px;box-shadow:0 0 24px #ff488d55;color:#e8e8ea;font:14px/1.6 system-ui,sans-serif;display:grid;gap:12px}.mon-mines-pop p{margin:0}.mon-mines-pop button{justify-self:end;padding:6px 16px;border:1px solid #8ae3e2;border-radius:4px;background:#1c2a30;color:#e8e8ea;font:inherit;cursor:pointer}";
      document.head.append(st);
    }
    document.body.append(p); ok.focus();
  }

  function show() {
    hide();
    let doc;
    try { doc = frame.contentDocument; } catch { return false; }
    const target = doc && doc.getElementById("grassCal");
    if (!target) return false;
    cal = target; cal.style.display = "none";
    style = el(doc, "style"); style.textContent = CSS; doc.head.append(style);
    game = createGame();
    box = el(doc, "div", "mon-mines");
    const grid = el(doc, "div", "mon-mines__grid");
    grid.setAttribute("role", "grid"); grid.setAttribute("aria-label", "지뢰찾기 5 × 7");
    for (let i = 0; i < game.n; i++) {
      const c = el(doc, "button", "mon-mines__c"); c.type = "button";
      let pressT = 0, longDone = false;
      const flagIt = () => { const r = toggleFlag(game, i); draw(); if (r === "win") win(); };
      c.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; longDone = false; clearTimeout(pressT); pressT = setTimeout(() => { longDone = true; flagIt(); }, LONG_MS); });
      const cancel = () => clearTimeout(pressT);
      c.addEventListener("pointerup", cancel); c.addEventListener("pointerleave", cancel); c.addEventListener("pointercancel", cancel);
      c.addEventListener("contextmenu", (e) => { e.preventDefault(); if (!longDone) { clearTimeout(pressT); flagIt(); } longDone = false; });   // PC 오른쪽 클릭도 깃발
      c.addEventListener("click", () => {
        if (longDone) { longDone = false; return; }   // 길게 누른 뒤 따라오는 click 은 무시
        if (!game || game.state !== "play") return;
        const r = reveal(game, i); draw();
        if (r === "boom") boom(c);
      });
      grid.append(c);
    }
    box.append(el(doc, "p", "mon-mines__bar"), grid, el(doc, "p", "mon-mines__hint", "누르기 = 열기 · 길게 누르기 = 깃발(3개)"));
    cal.after(box);
    draw();
    return true;
  }
  return { show, hide, get active() { return !!box; } };
}
