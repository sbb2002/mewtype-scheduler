// notices.js — 예고판 상단 "소식" 티커 (v2.7). notices.json 을 읽어 한 줄씩 순환 표시.
// 계약·목업: docs/plan/v2_7_notice_board.md, v2_7_notice_board_mockup.html
//
// renderNotices(section, data) 는 poll 마다 호출된다. 내용이 안 바뀌면 아무것도 안 하고
// 계속 돌린다. 만료(expires_at 지남) 소식은 프론트에서도 숨긴다(백엔드 sweep 지연 대비).

const CAT_KO = { live: "라이브예고", release: "음반·굿즈", platform: "타 플랫폼", etc: "기타" };
const SITE_ICON = {
  youtube: '<path fill="currentColor" d="M23 12s0-3.7-.5-5.5a3 3 0 0 0-2.1-2.1C18.6 3.9 12 3.9 12 3.9s-6.6 0-8.4.5A3 3 0 0 0 1.5 6.5C1 8.3 1 12 1 12s0 3.7.5 5.5a3 3 0 0 0 2.1 2.1c1.8.5 8.4.5 8.4.5s6.6 0 8.4-.5a3 3 0 0 0 2.1-2.1C23 15.7 23 12 23 12ZM9.8 15.4V8.6l6 3.4-6 3.4Z"/>',
  x: '<path fill="currentColor" d="M18.9 2.6h3.3l-7.2 8.2 8.5 11.3h-6.7l-5.2-6.8-6 6.8H1.3l7.7-8.8L.7 2.6h6.9l4.7 6.2 5.6-6.2Zm-1.2 17.7h1.9L7.2 4.4H5.2l12.5 15.9Z"/>',
  bilibili: '<path fill="currentColor" d="M7.2 2.7 9.9 5.4h4.2l2.7-2.7 1.5 1.5-1.2 1.2H18a3 3 0 0 1 3 3v7.4a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V8.4a3 3 0 0 1 3-3h1.9L6.7 4.2l1.5-1.5ZM6 7.4a1 1 0 0 0-1 1v7.4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8.4a1 1 0 0 0-1-1H6Zm2.6 2.3 1.7 1.7-1.7 1.7-1.7-1.7 1.7-1.7Zm6.8 0 1.7 1.7-1.7 1.7-1.7-1.7 1.7-1.7Z"/>',
  music: '<path fill="currentColor" d="M9 17.4a3 3 0 1 1-2-2.8V5.8l11-2.4v9.2a3 3 0 1 1-2-2.8V5.9L9 7.5v9.9Z"/>',
  store: '<path fill="currentColor" d="M6 7.5V6a4 4 0 0 1 8 0v1.5h3.3l1 12.9H1.7l1-12.9H6Zm2 0h4V6a2 2 0 1 0-4 0v1.5Z"/>',
  web: '<path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.9 6h-3a15 15 0 0 0-1.3-3.6A8 8 0 0 1 18.9 8ZM12 4c.8 1 1.5 2.4 1.9 4h-3.8C10.5 6.4 11.2 5 12 4ZM4.3 14a8 8 0 0 1 0-4h3.4a17 17 0 0 0 0 4H4.3Zm.8 2h3a15 15 0 0 0 1.3 3.6A8 8 0 0 1 5.1 16Zm3-8h-3a8 8 0 0 1 4.3-3.6A15 15 0 0 0 8.1 8ZM12 20c-.8-1-1.5-2.4-1.9-4h3.8c-.4 1.6-1.1 3-1.9 4Zm2.3-6H9.7a15 15 0 0 1 0-4h4.6a15 15 0 0 1 0 4Zm.3 5.6a15 15 0 0 0 1.3-3.6h3a8 8 0 0 1-4.3 3.6Zm1.7-5.6a17 17 0 0 0 0-4h3.4a8 8 0 0 1 0 4h-3.4Z"/>',
};

const _st = { built: false, sig: "", idx: 0, collapsed: true, open: false, timer: null, paused: false, tlang: "orig", longPressTimer: null, longPressItem: null };

const NTLANG_KEY = "mew:ntlang";  // ponytail: 소식 번역 토글 기억

function _todayKST() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" }); // YYYY-MM-DD
}

function _getNtlang() {
  try { return localStorage.getItem(NTLANG_KEY) || "orig"; } catch { return "orig"; }
}

function _setNtlang(lang) {
  try { localStorage.setItem(NTLANG_KEY, lang); } catch { /* private mode 등 */ }
  _st.tlang = lang;
}

function _dday(dateIso) {
  if (!dateIso) return { cls: "d-none", text: "—", n: null };
  const t0 = new Date(_todayKST() + "T00:00:00+09:00").getTime();
  const t1 = new Date(dateIso + "T00:00:00+09:00").getTime();
  const n = Math.round((t1 - t0) / 86400000);
  if (n <= 0) return { cls: "d-today", text: "TODAY", n: 0 };
  if (n <= 7) return { cls: "d-soon", text: "D-" + n, n };
  return { cls: "d-far", text: "D-" + n, n };
}

function _svg(site) {
  const inner = SITE_ICON[site] || SITE_ICON.web;
  return `<svg class="ntc__ic" viewBox="0 0 24 24" aria-hidden="true">${inner}</svg>`;
}

function _visible(data) {
  const now = Date.now();
  const list = ((data && data.notices) || []).filter((n) => {
    if (!n || !n.expires_at) return true;
    const e = Date.parse(n.expires_at);
    return isNaN(e) || e > now;
  });
  list.sort((a, b) =>
    (a.date || "9999-99-99").localeCompare(b.date || "9999-99-99") ||
    (a.time || "99:99").localeCompare(b.time || "99:99") ||
    String(a.id).localeCompare(String(b.id))
  );
  return list;
}

function _itemHTML(n) {
  const cat = CAT_KO[n.category] ? n.category : "etc";
  const dd = _dday(n.date);
  const dateTxt = n.date ? (n.deadline ? "〜 " : "") + n.date.slice(5).replace("-", "/") : "—";
  const timeTxt = n.time || "—";
  const href = n.url || n.tweet_url || "#";
  const src = n.tweet_url || href;
  const handle = n.src_handle || "@BDP_yumemita";
  const site = SITE_ICON[n.site] ? n.site : "web";
  const titleText = n.title_ko && _st.tlang === "ko" ? n.title_ko : (n.title || "(제목 없음)");
  return (
    `<div class="ntc__item" data-cat="${cat}" ${n.title_ko ? `data-id="${_attr(n.id)}" data-title-orig="${_attr(n.title || "(제목 없음)")}" data-title-ko="${_attr(n.title_ko)}"` : ""}>` +
      `<span class="ntc__date${n.date ? "" : " is-none"}"><time>${dateTxt}</time></span>` +
      `<span class="ntc__badge ${dd.cls}">${dd.text}</span>` +
      `<span class="ntc__time${n.time ? "" : " is-none"}">${_svg(site)}<time>${timeTxt}</time></span>` +
      `<a class="ntc__title" href="${_attr(href)}" target="_blank" rel="noopener">` +
        `<span class="ntc__title-in">${_esc(titleText)}</span></a>` +
      `<a class="ntc__src" href="${_attr(src)}" target="_blank" rel="noopener" aria-label="원문 트윗">` +
        _svg("x") + `<span class="nm">${_esc(handle)}</span></a>` +
    `</div>`
  );
}

function _esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function _attr(s) { return _esc(s).replace(/'/g, "&#39;"); }

function _marquee(scope) {
  scope.querySelectorAll(".ntc__title").forEach((vp) => {
    const inner = vp.querySelector(".ntc__title-in");
    if (!inner || vp.classList.contains("is-marquee")) return;
    if (inner.scrollWidth <= vp.clientWidth + 4) return;
    const t = inner.textContent;
    inner.textContent = "";
    const a = document.createElement("span"); a.className = "seg"; a.textContent = t;
    const b = a.cloneNode(true); b.setAttribute("aria-hidden", "true");
    inner.append(a, b);
    inner.style.setProperty("--dur", Math.max(9, t.length * 0.42).toFixed(1) + "s");
    vp.classList.add("is-marquee");
  });
}

export function renderNotices(section, data) {
  if (!section) return;
  _st.tlang = _getNtlang();
  const list = _visible(data);

  if (!list.length) {
    // 숨기지 않는다 — 빈 막대만 두고 펼치기는 비활성. (요청: 소식 0건이어도 자리 유지)
    if (_st.timer) { clearInterval(_st.timer); _st.timer = null; }
    _st.built = false; _st.sig = ""; _st.open = false; _st.idx = 0;
    if (section.dataset.empty !== "1") {
      section.hidden = false;
      section.className = "ntc is-empty is-collapsed";
      section.innerHTML =
        `<div class="ntc__bar">` +
          `<span class="ntc__tag"><span class="ntc__lamp" aria-hidden="true"></span>` +
            `<span class="ntc__label">소식</span></span>` +
          `<div class="ntc__ticker"><span class="ntc__empty">새 소식이 없습니다</span></div>` +
          `<button class="ntc__tgl" type="button" disabled aria-disabled="true" aria-label="소식 없음">▾</button>` +
        `</div>`;
      section.dataset.empty = "1";
    }
    return;
  }
  section.dataset.empty = "0";

  const sig = list.map((n) => n.id + ":" + (n.last_updated || "")).join("|");
  if (_st.built && sig === _st.sig) return;   // 변화 없음 → 계속 돌림
  _st.sig = sig;

  const hasToday = list.some((n) => _dday(n.date).n === 0);
  const itemsHTML = list.map(_itemHTML).join("");
  const first = list.length ? _itemHTML(list[0]) : "";   // 무한 순환용 클론

  section.hidden = false;
  section.className = "ntc" + (hasToday ? " has-today" : "") + (_st.open ? " is-open" : " is-collapsed");
  section.innerHTML =
    `<div class="ntc__bar">` +
      `<span class="ntc__tag"><span class="ntc__lamp" aria-hidden="true"></span>` +
        `<span class="ntc__label">소식</span>` +
        `<span class="ntc__all"${_st.open ? "" : " hidden"}>전체 ${list.length}건</span></span>` +
      `<div class="ntc__ticker"><div class="ntc__track">${itemsHTML}${first}</div></div>` +
      `<button class="ntc__tgl" type="button" aria-expanded="${_st.open}" aria-label="소식 전체 보기">` +
        `${_st.open ? "▴" : "▾"}</button>` +
    `</div>` +
    `<ul class="ntc__list">${list.map((n) => "<li>" + _itemHTML(n) + "</li>").join("")}</ul>`;

  const track = section.querySelector(".ntc__track");
  const ticker = section.querySelector(".ntc__ticker");
  const tgl = section.querySelector(".ntc__tgl");
  const listEl = section.querySelector(".ntc__list");
  _marquee(track);
  _marquee(listEl);

  const H = track.firstElementChild ? track.firstElementChild.getBoundingClientRect().height : 35;
  const N = list.length;
  _st.idx = Math.min(_st.idx, N - 1);

  const show = (i, animate) => {
    track.style.transition = animate ? "" : "none";
    track.style.transform = `translateY(${-i * H}px)`;
  };
  const advance = () => {
    _st.idx++;
    show(_st.idx, true);
    if (_st.idx === N) setTimeout(() => { _st.idx = 0; show(0, false); }, 520);
  };
  const play = () => {
    if (_st.open || _st.paused || N < 2) return;
    if (_st.timer) clearInterval(_st.timer);
    track.classList.add("is-live");
    _st.timer = setInterval(advance, 5000);
  };
  const stop = () => { if (_st.timer) { clearInterval(_st.timer); _st.timer = null; } track.classList.remove("is-live"); };
  _st.play = play; _st.stop = stop;   // 재빌드 시 최신 클로저로 교체 (visibility 리스너가 참조)

  ticker.addEventListener("mouseenter", () => { _st.paused = true; stop(); });
  ticker.addEventListener("mouseleave", () => { _st.paused = false; play(); });
  ticker.addEventListener("focusin", () => { _st.paused = true; stop(); });
  ticker.addEventListener("focusout", () => { _st.paused = false; play(); });

  // 펼침 높이를 실측해서 넣어야 max-height 트랜지션이 딱 그 거리만큼 "스르륵".
  const applyListHeight = () => {
    if (!listEl) return;
    if (_st.open) {
      const h = Math.min(listEl.scrollHeight, Math.round(window.innerHeight * 0.7));
      listEl.style.maxHeight = h + "px";
    } else {
      listEl.style.maxHeight = "0px";
    }
  };

  const setOpen = (open) => {
    _st.open = open;
    section.classList.toggle("is-open", open);
    section.classList.toggle("is-collapsed", !open);
    tgl.setAttribute("aria-expanded", String(open));
    tgl.textContent = open ? "▴" : "▾";
    const all = section.querySelector(".ntc__all");
    if (all) all.hidden = !open;
    applyListHeight();
    if (open) stop();
    else { show(_st.idx % N, false); play(); }
  };
  _st.setOpen = setOpen;

  tgl.addEventListener("click", () => setOpen(!_st.open));

  show(_st.open ? 0 : _st.idx % N, false);
  if (_st.open && listEl) {
    // 이미 펼친 채로 재빌드된 경우: 슬라이드 없이 즉시 펼친 높이로
    listEl.style.transition = "none";
    applyListHeight();
    void listEl.offsetHeight;
    listEl.style.transition = "";
  }
  play();
  _st.built = true;

  // ponytail: 길게 누르기(0.5s) 로 제목 번역 토글
  if (!_st._longPress) {
    _st._longPress = true;
    document.addEventListener("pointerdown", (e) => {
      const item = e.target.closest(".ntc__item[data-title-ko]");
      if (!item) return;
      _st.longPressItem = item;
      _st.longPressTimer = setTimeout(() => {
        const orig = item.getAttribute("data-title-orig");
        const ko = item.getAttribute("data-title-ko");
        if (!orig || !ko) return;
        _setNtlang(_st.tlang === "ko" ? "orig" : "ko");
        const titleSpan = item.querySelector(".ntc__title-in");
        if (titleSpan) titleSpan.textContent = _st.tlang === "ko" ? ko : orig;
      }, 500);
    });
    document.addEventListener("pointerup", () => {
      if (_st.longPressTimer) { clearTimeout(_st.longPressTimer); _st.longPressTimer = null; }
      _st.longPressItem = null;
    });
  }

  if (!_st._vis) {
    _st._vis = true;
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) _st.stop && _st.stop();
      else if (!_st.open && !_st.paused && _st.play) _st.play();
    });
  }

  // 펼친 상태에서 영역 밖을 "탭"하면 닫힘. 드래그(모바일 목록 스크롤 등)는 무시 —
  // pointerdown~up 이동량이 작을 때만 닫는다. (#notice 노드는 재빌드돼도 동일)
  if (!_st._out) {
    _st._out = true;
    let down = null;
    document.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, outside: !section.contains(e.target) };
    }, true);
    document.addEventListener("pointerup", (e) => {
      const d = down;
      down = null;
      if (!d || !_st.open || !d.outside) return;
      if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 10) return;   // 드래그
      if (section.contains(e.target)) return;
      _st.setOpen && _st.setOpen(false);
    }, true);
  }
}
