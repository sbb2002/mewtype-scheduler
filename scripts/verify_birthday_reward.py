"""실제 두 곡을 끝까지 재생해 완곡 해제 · 재방문 기억 · 미해제 상태를 확인한다(약 8분)."""
from pathlib import Path
import json, threading, functools, http.server
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__import__('tempfile').gettempdir())/'birthday-story'/'reward';OUT.mkdir(parents=True,exist_ok=True)
KEY='bday-yuno-controls-unlocked-v1'
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno'
def routes(route):
    u=route.request.url
    if '127.0.0.1' not in u:route.fulfill(status=200,content_type='application/json',body='{}')
    elif '/data/' in u:
        f=ROOT/'fixtures'/u.rsplit('/',1)[1].replace('.json','.sample.json')
        route.fulfill(content_type='application/json',body=f.read_text(encoding='utf8') if f.exists() else '{}')
    else:route.continue_()
STATE='''()=>({prev:!document.querySelector('.bday-ib.prev').hidden,next:!document.querySelector('.bday-ib.next').hidden,effects:!document.querySelector('.bday-effects').hidden,
 unlocked:document.querySelector('.bday-music').hasAttribute('data-unlocked'),card:!document.querySelector('.bday-memory').hidden,title:document.querySelector('.bday-track').textContent,key:localStorage.getItem('%s')})'''%KEY
result={};errors=[]
def enter(ctx):
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(URL)
    page.wait_for_selector('.bday-music');page.wait_for_timeout(1500)
    if page.locator('.bday-start').is_visible():page.locator('.bday-start').click(force=True)
    return page
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
    ctx=browser.new_context(viewport={'width':1440,'height':900});ctx.route('**/*',routes)
    page=enter(ctx)
    page.wait_for_function("document.documentElement.hasAttribute('data-bday-revealed')",timeout=40000)
    result['after_intro']=page.evaluate(STATE)
    assert not result['after_intro']['prev'] and not result['after_intro']['effects']
    page.keyboard.press('ArrowRight');page.wait_for_timeout(500)
    assert 'Noctural' in page.evaluate(STATE)['title'],'해제 전 방향키 선곡 차단'
    page.wait_for_function("document.querySelector('.bday-track').textContent.includes('Midnight')",timeout=240000)
    result['track2']=page.evaluate(STATE);assert not result['track2']['unlocked']
    page.wait_for_function("!document.querySelector('.bday-memory').hidden",timeout=230000)
    result['card']=page.evaluate(STATE);assert not result['card']['key'],'카드 시각에는 아직 해제 전'
    page.screenshot(path=str(OUT/'card.png'))
    page.wait_for_function("document.querySelector('.bday-music').hasAttribute('data-unlocked')",timeout=20000)
    page.wait_for_timeout(450);page.screenshot(path=str(OUT/'unlock-middle.png'));page.wait_for_timeout(1500)
    result['unlocked']=page.evaluate(STATE);assert result['unlocked']['key']=='1' and result['unlocked']['prev'] and result['unlocked']['effects']
    page.screenshot(path=str(OUT/'unlocked.png'));page.close()
    again=enter(ctx);again.wait_for_function("document.documentElement.hasAttribute('data-bday-revealed')",timeout=40000)
    result['revisit']=again.evaluate(STATE);assert result['revisit']['unlocked'] and result['revisit']['prev']
    fresh=browser.new_context(viewport={'width':1440,'height':900});fresh.route('**/*',routes)
    other=enter(fresh);other.wait_for_function("document.documentElement.hasAttribute('data-bday-revealed')",timeout=40000)
    result['other_browser']=other.evaluate(STATE);assert not result['other_browser']['unlocked']
    browser.close()
result['errors']=errors;assert not errors,errors
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=1),encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=1))
