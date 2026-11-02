// v4.11.7 브라우저 검증 — 조회 실패 복구 · 점 색 · 시트 닫기 · 멤버 기억 · 터치 영역. localhost 만, 프로젝트 파일 수정 없음.
// 먼저 python scripts/serve_local.py 를 띄운다. Playwright 는 npx 캐시의 playwright-core 와 설치된 Chromium 을 쓴다.
// 사용: node scripts/verify_ui_refine.cjs [network|dots|sheets|memory|touch]
const fs=require('fs'),path=require('path');
const root='C:/Users/user/AppData/Local/npm-cache/_npx';
let pw=null;
for(const d of fs.readdirSync(root)){const p=path.join(root,d,'node_modules/playwright-core');
 if(fs.existsSync(p)){const v=require(p+'/package.json').version; if(v.startsWith('1.6')||v>='1.5'){pw=pw&&pw.v>v?pw:{v,p};}}}
const {chromium}=require(pw.p);
const exe=process.env.LOCALAPPDATA+'/ms-playwright/chromium-1228/chrome-win64/chrome.exe';
const SHOTS=process.env.VERIFY_SHOTS||path.join(__dirname,'..','_local','verify_shots');fs.mkdirSync(SHOTS,{recursive:true});
async function open({phone=true,theme='dark',w,h,offline=false}={}){
 const browser=await chromium.launch({executablePath:exe,headless:true});
 const ctx=await browser.newContext(phone?{viewport:{width:w||390,height:h||844},deviceScaleFactor:2,isMobile:true,hasTouch:true,locale:'ko-KR',timezoneId:'Asia/Seoul',colorScheme:theme}:{viewport:{width:w||1440,height:h||900},deviceScaleFactor:1,locale:'ko-KR',timezoneId:'Asia/Seoul',colorScheme:theme});
 await ctx.addInitScript(t=>{try{localStorage.setItem('theme',t)}catch(e){}},theme);
 const page=await ctx.newPage();
 const errs=[];page.on('pageerror',e=>errs.push('pageerror '+e.message));page.on('console',m=>{if(m.type()==='error')errs.push(m.text().slice(0,160))});
 return {browser,ctx,page,errs,shot:(n)=>page.screenshot({path:path.join(SHOTS,n+'.png')})};
}
const URL = process.env.VERIFY_URL || 'http://localhost:8099/src/frontend/';
const results = [];
const check = (name, ok, extra = '') => { results.push([ok, name, extra]); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
const route = (page, st) => page.route('**/data/*.json', async r => {
  if (st.mode === 'net') return r.abort('internetdisconnected');
  if (st.mode === 'http') return r.fulfill({ status: 500, body: 'x' });
  r.continue();
});
const S = p => p.evaluate(() => {
  const a = document.getElementById('net-alert');
  const sh = document.querySelector('.ntc-sheet');
  return {
    alert: a && !a.hidden ? a.textContent : null,
    rows: document.querySelectorAll('#notice [data-nid]').length,
    empty: (document.querySelector('.ntc__empty') || {}).textContent || null,
    sheetId: !!document.body.classList.contains('ntc-sheet-open'),
    badges: [...document.querySelectorAll('.lane__tw')].filter(e => e.getBoundingClientRect().width > 0).length,
    footStatus: !!document.getElementById('foot-status'),
    boardText: document.getElementById('board').innerText.slice(0, 30),
    mark: window.__mark || null,
  };
});
const refetch = p => p.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
const tapOpts = (phone) => phone ? 'tap' : 'click';

async function network() {
  const st = { mode: 'ok' };
  const o = await open({ phone: true }); const p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  await p.evaluate(() => { window.__mark = 'same-page'; });
  let s = await S(p);
  check('초기: 안내 숨김 · 업데이트 지연 요소 없음', s.alert === null && !s.footStatus);
  const foot0 = await p.evaluate(() => document.getElementById('foot').getBoundingClientRect().height);

  // 일시 실패 — 1회 실패 뒤 복구: 안내 안 뜸
  st.mode = 'net'; await refetch(p); await p.waitForTimeout(500); st.mode = 'ok';
  let seen = false; for (let i = 0; i < 14; i++) { await p.waitForTimeout(500); if ((await S(p)).alert) seen = true; }
  check('앱 복귀 직후 1회 실패: 재시도 성공, 안내 안 뜸', !seen);

  // 소식 시트 연 채로 지속 실패
  await (await p.$('.ntc__tgl')).tap(); await p.waitForTimeout(800);
  const row = await p.$('#notice [data-nid]'); await row.scrollIntoViewIfNeeded(); await row.tap(); await p.waitForTimeout(1200);
  s = await S(p); check('소식 시트 열림', s.sheetId);
  const shots0 = s;
  st.mode = 'net'; const t0 = Date.now(); await refetch(p);
  await p.waitForTimeout(2000); s = await S(p); check('지속 실패 +2초: 아직 안내 없음', s.alert === null, JSON.stringify(s.alert));
  await p.waitForTimeout(5000); s = await S(p); check('지속 실패 +7초: 아직 안내 없음', s.alert === null);
  let shown = 0; for (let i = 0; i < 40 && !shown; i++) { await p.waitForTimeout(250); if ((await S(p)).alert) shown = Date.now() - t0; }
  s = await S(p);
  check('재시도 2회 소진 뒤 안내', !!shown, `${shown}ms`);
  check('안내 문구(네트워크)', s.alert === '!네트워크가 불안정하여 최신정보를 업데이트하지 못했어요.', s.alert);
  check('끊겨도 소식 유지 · 시트 유지', s.rows === shots0.rows && s.sheetId, `rows=${s.rows} sheet=${s.sheetId}`);
  check('끊겨도 트윗 배지 유지', s.badges === shots0.badges, `${s.badges}`);
  await o.shot('v-alert-sheet');
  const pe = await p.evaluate(() => { const a = document.getElementById('net-alert'), r = a.getBoundingClientRect(), cs = getComputedStyle(a); return { pe: cs.pointerEvents, x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height, top: document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.id }; });
  check('안내가 화면 중앙 · 입력 안 막음', pe.pe === 'none' && Math.abs(pe.x - 195) < 2 && Math.abs(pe.y - 422) < 3 && pe.top !== 'net-alert', JSON.stringify(pe));
  const foot1 = await p.evaluate(() => document.getElementById('foot').getBoundingClientRect().height);
  check('푸터 높이 안 늘어남', foot0 === foot1, `${foot0}→${foot1}`);

  // 복구: online 이벤트 5초
  st.mode = 'ok'; await p.evaluate(() => window.dispatchEvent(new Event('online')));
  await p.waitForTimeout(4000); s = await S(p); check('online +4초: 아직 재조회 전', s.alert !== null);
  await p.waitForTimeout(2200); s = await S(p); check('online +6초: 재조회 성공, 안내 사라짐', s.alert === null);
  check('페이지 전체 새로 고침 없음(플레이어 유지 조건)', s.mark === 'same-page');
  check('복구 뒤에도 시트 유지', s.sheetId);
  await o.browser.close();

  // HTTP 오류
  const st2 = { mode: 'ok' }; const o2 = await open({ phone: true }); const p2 = o2.page;
  await route(p2, st2); await p2.goto(URL); await p2.waitForTimeout(2000);
  st2.mode = 'http'; await refetch(p2); await p2.waitForTimeout(13500);
  s = await S(p2); check('서버 오류 문구', s.alert === '!최신정보를 업데이트하지 못했어요.', s.alert);
  check('서버 오류에도 소식 유지', s.rows > 0, `${s.rows}`);
  await o2.browser.close();

  // 처음부터 실패
  const st3 = { mode: 'net' }; const o3 = await open({ phone: true }); const p3 = o3.page;
  await route(p3, st3); await p3.goto(URL); await p3.waitForTimeout(13500);
  s = await S(p3);
  check('첫 로드 실패: 안내 + 소식 막대 문구', !!s.alert && s.empty === '소식을 불러오지 못했어요', JSON.stringify([s.alert, s.empty, s.boardText]));
  await o3.shot('v-firstfail');
  st3.mode = 'ok'; await p3.evaluate(() => window.dispatchEvent(new Event('online'))); await p3.waitForTimeout(6500);
  s = await S(p3);
  check('첫 로드 실패 뒤 복구: 보드 · 소식 정상', s.alert === null && s.rows > 0 && !s.boardText.includes('문제가'), `rows=${s.rows}`);
  await o3.browser.close();
}

async function dots() {
  for (const theme of ['dark', 'light']) {
    const st = { mode: 'ok' }; const o = await open({ phone: true, theme }); const p = o.page;
    await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
    await (await p.$('.week-btn')).tap(); await p.waitForTimeout(800);
    const d = await p.evaluate(() => [...document.querySelectorAll('.wk-sheet .wk2__row .wk2__dot')].slice(0, 40).map(b => ({ ended: b.classList.contains('is-ended'), op: getComputedStyle(b).opacity, seg: [...b.querySelectorAll('.wk2__seg')].map(s => [s.dataset.channel, getComputedStyle(s).backgroundColor]) })));
    const expect = theme === 'dark' ? ['dark', 'darkEnded'] : ['light', 'lightEnded'];
    const cfg = fs.readFileSync(path.join(__dirname, '..', 'src/frontend/js/config.js'), 'utf8');
    const tbl = {}; for (const m of cfg.matchAll(/(\w+):\s*\{ dark: "(#\w+)", darkEnded: "(#\w+)", light: "(#\w+)", lightEnded: "(#\w+)"/g)) tbl[m[1]] = { dark: m[2], darkEnded: m[3], light: m[4], lightEnded: m[5] };
    const rgb = h => `rgb(${parseInt(h.slice(1, 3), 16)}, ${parseInt(h.slice(3, 5), 16)}, ${parseInt(h.slice(5, 7), 16)})`;
    let bad = 0; for (const x of d) for (const [k, c] of x.seg) if (c !== rgb(tbl[k][expect[x.ended ? 1 : 0]])) { bad++; console.log('  색 불일치', k, c, x.ended); }
    check(`${theme}: 점 ${d.length}개가 표의 색과 일치 · 불투명도 1`, d.length > 0 && bad === 0 && d.every(x => x.op === '1'), `종료 ${d.filter(x => x.ended).length}개`);
    await o.shot(`v-week-${theme}`);
    const hasX = await p.evaluate(() => !!document.querySelector('.wk-sheet__x') || [...document.querySelectorAll('.wk-sheet button')].some(b => b.textContent.trim() === '닫기'));
    check(`${theme}: 이후 예고 시트 닫기 버튼 없음`, !hasX);
    await o.browser.close();
  }
}

const drag = async (p, sel) => { const b = await (await p.$(sel)).boundingBox(); const x = b.x + b.width / 2, y = b.y + Math.min(14, b.height / 2); await p.mouse.move(x, y); await p.mouse.down(); for (let i = 1; i <= 12; i++) { await p.mouse.move(x, y + i * 28); await p.waitForTimeout(16); } await p.mouse.up(); await p.waitForTimeout(700); };
async function sheets() {
  // 터치 탭 닫기
  const st = { mode: 'ok' }; let o = await open({ phone: true }); let p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  await (await p.$('.week-btn')).tap(); await p.waitForTimeout(700);
  await p.touchscreen.tap(195, 60); await p.waitForTimeout(600);
  check('이후 예고: 바깥 탭으로 닫힘', await p.evaluate(() => document.querySelector('.wk-scrim').hidden || !document.querySelector('.wk-scrim').classList.contains('is-open')));
  await (await p.$('.ntc__tgl')).tap(); await p.waitForTimeout(800);
  const row = await p.$('#notice [data-nid]'); await row.scrollIntoViewIfNeeded(); await row.tap(); await p.waitForTimeout(1200);
  check('소식 시트: ✕ 숨김', await p.evaluate(() => { const x = document.querySelector('.ntc-sheet .ntc-card__x'); return !x || getComputedStyle(x).display === 'none'; }));
  check('소식 시트: 포커스가 시트', await p.evaluate(() => document.activeElement === document.querySelector('.ntc-sheet')));
  await o.shot('v-notice-sheet');
  await p.touchscreen.tap(195, 40); await p.waitForTimeout(700);
  check('소식 시트: 바깥 탭으로 닫힘', !(await S(p)).sheetId);
  await o.browser.close();

  o = await open({ phone: true }); p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  await (await p.$('.player-btn--dock')).tap(); await p.waitForTimeout(1800);
  const pi = await p.evaluate(() => ({ x: getComputedStyle(document.querySelector('.mp-x')).display, f: document.activeElement.className, open: document.querySelector('.mp-scrim').classList.contains('is-open'), grab: getComputedStyle(document.querySelector('.mp-pop__grab')).display }));
  check('플레이어: 내리기 숨김 · 손잡이 보임 · 포커스 시트', pi.x === 'none' && pi.grab === 'block' && /mp-pop/.test(pi.f) && pi.open, JSON.stringify(pi));
  await o.shot('v-player');
  const sc = await (await p.$('.mp-pop')).boundingBox();
  await p.touchscreen.tap(195, Math.max(10, sc.y - 12)); await p.waitForTimeout(800);
  check('플레이어: 바깥 탭으로 닫힘', await p.evaluate(() => !document.querySelector('.mp-scrim').classList.contains('is-open')));
  await o.browser.close();

  // 끌어 닫기 — 마우스로 폰 폭
  o = await open({ phone: false, w: 390, h: 844 }); p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  await (await p.$('.week-btn')).click(); await p.waitForTimeout(700);
  await drag(p, '.wk-sheet__head');
  check('이후 예고: 끌어 닫기', await p.evaluate(() => !document.querySelector('.wk-scrim').classList.contains('is-open')));
  await (await p.$('.player-btn--dock')).click(); await p.waitForTimeout(1800);
  await drag(p, '.mp-pop__head');
  check('플레이어: 끌어 닫기', await p.evaluate(() => !document.querySelector('.mp-scrim').classList.contains('is-open')));
  await (await p.$('.week-btn')).click(); await p.waitForTimeout(700);
  await p.keyboard.press('Escape'); await p.waitForTimeout(600);
  check('이후 예고: Esc 닫기', await p.evaluate(() => !document.querySelector('.wk-scrim').classList.contains('is-open')));
  await o.browser.close();

  // PC
  o = await open({ phone: false }); p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  const tt = await p.evaluate(() => getComputedStyle(document.querySelector('.tt__title')).fontSize);
  check('PC 제목 16px', tt === '16px', tt);
  await (await p.$('.ntc__tgl')).click(); await p.waitForTimeout(800);
  const r2 = await p.$('#notice [data-nid]'); await r2.click(); await p.waitForTimeout(1000);
  check('PC 소식 팝업 ✕ 유지', await p.evaluate(() => { const x = [...document.querySelectorAll('.ntc-card__x')].find(e => e.getBoundingClientRect().width > 0); return !!x; }));
  await o.shot('v-pc-notice');
  await p.keyboard.press('Escape'); await p.waitForTimeout(500); await (await p.$('.ntc__tgl')).click(); await p.waitForTimeout(500);
  await o.shot('v-pc-board');
  await o.browser.close();
}

async function memory() {
  const st = { mode: 'ok' }; const o = await open({ phone: true }); const p = o.page;
  await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
  const active = () => p.evaluate(() => [document.querySelector('.lane--active')?.dataset.channel, (() => { try { return localStorage.getItem('mew.lane.last'); } catch { return 'ERR'; } })()]);
  check('첫 방문: 첫 멤버', (await active())[0] === 'arale', JSON.stringify(await active()));
  const dots = await p.$$('#pager-dots .dot'); await dots[4].tap(); await p.waitForTimeout(1200);
  const a1 = await active(); check('멤버 전환이 저장됨', a1[1] === a1[0] && a1[0] !== 'arale', JSON.stringify(a1));
  const want = a1[0];
  for (let i = 0; i < 4; i++) { await p.reload(); await p.waitForTimeout(2200); const a = await active(); check(`새로고침 ${i + 1}: 복원`, a[0] === want && a[1] === want, JSON.stringify(a)); }
  await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await p.waitForTimeout(1000);
  check('재조회 뒤에도 유지', (await active())[0] === want);
  await p.evaluate(() => localStorage.setItem('mew.lane.last', 'nobody')); await p.reload(); await p.waitForTimeout(2200);
  check('잘못된 값: 첫 멤버', (await active())[0] === 'arale');
  await o.browser.close();
  // 저장소 차단
  const o2 = await open({ phone: true }); const p2 = o2.page;
  await o2.ctx.addInitScript(() => { const t = Storage.prototype.getItem; Storage.prototype.getItem = function (k) { if (k === 'mew.lane.last') throw new Error('blocked'); return t.call(this, k); }; const s = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) { if (k === 'mew.lane.last') throw new Error('blocked'); return s.call(this, k, v); }; });
  await route(p2, st); await p2.goto(URL); await p2.waitForTimeout(2500);
  const dd = await p2.$$('#pager-dots .dot'); await dd[2].tap(); await p2.waitForTimeout(800);
  check('저장소 차단: 예외 없이 동작', !o2.errs.some(e => /blocked/.test(e)), o2.errs.join(' | ').slice(0, 120));
  await o2.browser.close();
}

async function touch() {
  for (const w of [390, 320]) {
    const st = { mode: 'ok' }; const o = await open({ phone: true, w, h: 780 }); const p = o.page; const bad = {}; p.on('response', r => { if (r.status() >= 400) { const k = r.status() + ' ' + new (require('url').URL)(r.url()).host + new (require('url').URL)(r.url()).pathname.slice(0, 30); bad[k] = (bad[k] || 0) + 1; } });
    await route(p, st); await p.goto(URL); await p.waitForTimeout(2500);
    const r = await p.evaluate(() => {
      const out = {};
      const hit = (el, dx, dy) => { const b = el.getBoundingClientRect(); const t = document.elementFromPoint(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy); return t === el || el.contains(t); };
      const span = (el, axis) => { let n = 0, m = 0; for (let d = 1; d < 40; d++) { if (hit(el, axis === 'x' ? d : 0, axis === 'y' ? d : 0)) n = d; else break; } for (let d = 1; d < 40; d++) { if (hit(el, axis === 'x' ? -d : 0, axis === 'y' ? -d : 0)) m = d; else break; } return n + m + 1; };
      const list = { dot: '#pager-dots .dot', player: '#pager-dots .player-btn--dock', week: '#pager-dots .week-btn', yt: '.lane--active .lane__nav-yt', x: '.lane--active .lane__nav-x', tw: '.lane--active .lane__tw', chip: '.ntc__cchip', tgl: '.ntc__tgl', theme: '.ntc__theme' };
      for (const [k, s] of Object.entries(list)) { const e = document.querySelector(s); out[k] = e ? { w: span(e, 'x'), h: span(e, 'y') } : null; }
      out.scroll = [document.documentElement.scrollWidth, innerWidth];
      return out;
    });
    console.log(`  폭 ${w}`, JSON.stringify(r));
    check(`${w}: 가로 넘침 없음`, r.scroll[0] <= r.scroll[1], r.scroll.join('/'));
    check(`${w}: 멤버 점 세로 44 · 가로 40`, r.dot && r.dot.h >= 43 && r.dot.w >= 39, JSON.stringify(r.dot));
    check(`${w}: 플레이어 · 표 버튼 세로 44`, r.player.h >= 43 && r.week.h >= 43, JSON.stringify([r.player, r.week]));
    check(`${w}: YT · X 가로 44`, r.yt.w >= 43 && r.x.w >= 43, JSON.stringify([r.yt, r.x]));
    check(`${w}: 소식 칩 세로 34`, r.chip.h >= 33, JSON.stringify(r.chip));
    if (r.tw) check(`${w}: 트윗 배지 32 이상`, r.tw.w >= 31 && r.tw.h >= 31, JSON.stringify(r.tw));
    if (w === 390) { await o.shot('v-phone-board'); }
    check(`${w}: 페이지 예외 없음`, !o.errs.some(e => e.startsWith('pageerror')), o.errs.filter(e => e.startsWith('pageerror')).join(' | '));console.log('  실패 응답', JSON.stringify(bad));
    await o.browser.close();
  }
}

(async () => {
  const which = process.argv[2];
  for (const [n, f] of Object.entries({ network, dots, sheets, memory, touch })) if (!which || which === n) { console.log('=== ' + n); try { await f(); } catch (e) { check(n + ' 실행', false, String(e).slice(0, 300)); } }
  const fail = results.filter(r => !r[0]);
  console.log(`\n합계 ${results.length - fail.length}/${results.length} 통과`);
  fail.forEach(f => console.log('FAIL', f[1], f[2]));
})();
