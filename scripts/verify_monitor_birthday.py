"""실제 모니터 리포트와 마우스·Android 터치로 생일 진입/초기화 회귀를 검사한다."""
from pathlib import Path
import functools,http.server,threading,json,os,tempfile,sys
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.backend.monitor_report import build_day_from_text,render_html
date='2026-10-31'
day=build_day_from_text(date,'',now_hm='12:00',down_ranges=[],vercel_deploys=None)
report=render_html({'date':date,'monthly':False,'yearly':False,'dates':[date],'days':{date:day}})
OUT=Path(os.environ.get('BIRTHDAY_VERIFY_OUT',str(Path(tempfile.gettempdir())/'birthday-verify-third')))/'monitor'
OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  # 생일 화면 진입 직후 다음 검사로 이동하면 진행 중 음원 요청이 정상 취소될 수 있다.
  try:super().copyfile(source,outputfile)
  except (BrokenPipeError,ConnectionResetError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8120),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:8120/src/frontend/monitor.html?va=claude'
code='UUDDLRLR'
results={}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for mobile in [False,True]:
   name='android-touch' if mobile else 'pc-mouse'
   kwargs={'viewport':{'width':390,'height':844},'is_mobile':True,'has_touch':True,'device_scale_factor':1,
           'user_agent':'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Mobile Safari/537.36'} if mobile else {'viewport':{'width':1440,'height':900}}
   ctx=browser.new_context(**kwargs);page=ctx.new_page();errors=[];requests=[];mode={'fallback':False,'snapshots':0}
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('request',lambda r:requests.append(r.url))
   def route(r):
    u=r.request.url
    if u.endswith('/monitor-live'):
     r.fulfill(status=503 if mode['fallback'] else 200,content_type='text/html',body='' if mode['fallback'] else report)
    elif 'monitoring/latest.html' in u:
     mode['snapshots']+=1;r.fulfill(content_type='text/html',body=report)
    elif '127.0.0.1' not in u:r.fulfill(content_type='application/json',body='{}')
    else:r.continue_()
   page.route('**/*',route)
   page.goto(url);frame=page.frame_locator('#f');frame.locator('#tabBtnApp').wait_for(state='visible')
   page.wait_for_timeout(150)
   page.evaluate('()=>localStorage.setItem("monitor-test","keep")')
   # 평소 탭 조작은 숨은 입력으로 처리하지 않는다.
   frame.locator('#tabBtnExt').click();frame.locator('#tabBtnApp').click();assert page.url==url
   cdp=ctx.new_cdp_session(page) if mobile else None
   def open_dialog():
    page.locator('#reset-open').click();page.wait_for_timeout(300)
    assert page.locator('#reset-dlg').evaluate('(d)=>d.open')
   def swipe(direction,shot=None):
    r=page.locator('#reset-dlg').bounding_box();left,top=r['x'],r['y'];right,bottom=left+r['width'],top+r['height'];cx,cy=(left+right)/2,(top+bottom)/2
    start,end={'U':((cx,top+32),(cx,top-14)), 'D':((left+25,bottom-32),(left+25,bottom+14)),
               'L':((left+32,cy),(left-14,cy)), 'R':((right-32,cy),(right+14,cy))}[direction]
    if mobile:
     cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':start[0],'y':start[1],'id':1}]})
     for n in range(1,7):cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':start[0]+(end[0]-start[0])*n/6,'y':start[1]+(end[1]-start[1])*n/6,'id':1}]})
    else:
     page.mouse.move(*start);page.mouse.down();page.mouse.move(*end,steps=6)
    page.wait_for_function('(d)=>document.getElementById("reset-dlg").dataset.bdayEdge===d',arg=direction)
    page.wait_for_timeout(130)
    style=page.locator('#reset-dlg').evaluate('(d)=>({opacity:getComputedStyle(d,"::after").opacity,shadow:getComputedStyle(d,"::after").boxShadow})')
    assert float(style['opacity'])>.9 and style['shadow']!='none',style
    if shot:page.screenshot(path=str(OUT/f'{name}-{shot}.png'))
    if mobile:cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    else:page.mouse.up()
   def arm():
    open_dialog()
    for i,d in enumerate(code):swipe(d,'edge-'+d if i in [0,2,4,7] else None)
    page.wait_for_function('!document.getElementById("reset-dlg").open')
    assert page.locator('#reset-open').evaluate('(e)=>e.classList.contains("bday-armed")')
    assert page.evaluate('()=>localStorage.getItem("monitor-test")')=='keep'
    assert not [u for u in requests if '/assets/birthday/' in u or '/bdayaudio.js' in u]
   # 틀린 방향과 취소는 창/기록을 그대로 유지한다.
   open_dialog()
   for d in 'UUDDLRLL':swipe(d)
   assert page.locator('#reset-dlg').evaluate('(d)=>d.open')
   assert not page.locator('#reset-open').evaluate('(e)=>e.classList.contains("bday-armed")')
   page.locator('#reset-cancel').click()
   assert page.evaluate('()=>localStorage.getItem("monitor-test")')=='keep'
   # 준비 뒤 틀린 탭은 해제하며 평소 탭 전환은 동작한다.
   arm();frame.locator('#tabBtnApp').click();assert page.url==url
   assert not page.locator('#reset-open').evaluate('(e)=>e.classList.contains("bday-armed")')
   # 30초 무입력 해제: 실제 타이머를 브라우저 가상 시계로 전진한다.
   page.clock.install();arm();page.clock.fast_forward(31000)
   assert not page.locator('#reset-open').evaluate('(e)=>e.classList.contains("bday-armed")')
   frame.locator('#tabBtnExt').click();frame.locator('#tabBtnApp').click();assert page.url==url
   # 준비 뒤 라이브 실패→스냅샷으로 교체돼도 새 iframe의 탭을 인식한다.
   arm();mode['fallback']=True
   page.evaluate('()=>refresh()');frame.locator('#tabBtnApp').wait_for(state='visible');page.wait_for_timeout(200)
   assert mode['snapshots']>0
   assert page.locator('#reset-open').evaluate('(e)=>e.classList.contains("bday-armed")')
   page.screenshot(path=str(OUT/f'{name}-armed.png'))
   frame.locator('#tabBtnExt').click();assert page.url==url
   frame.locator('#tabBtnApp').click();page.wait_for_url('**/?bday=yuno&va=claude')
   query=parse_qs(urlparse(page.url).query);assert query=={'bday':['yuno'],'va':['claude']}
   page.wait_for_selector('html[data-bday="yuno"]');page.wait_for_selector('#bday-bg canvas')
   assert page.evaluate('()=>localStorage.getItem("monitor-test")')=='keep'
   # 다시 방문한 모니터에서도 명시적인 되돌리기는 정상 작동한다.
   page.goto(url);frame.locator('#tabBtnApp').wait_for(state='visible')
   open_dialog();page.locator('#reset-ok').click()
   assert page.evaluate('()=>localStorage.getItem("monitor-test")') is None
   assert '처음 상태로' in page.locator('#toast').text_content()
   assert not errors,errors
   results[name]={'directions':'UUDDLRLR','edge_glow':['U','D','L','R'],'armed_glow':True,'wrong_direction':True,'wrong_tab':True,
                  'timeout':True,'snapshot_reload':mode['snapshots'],'url_query':query,'storage_preserved_on_entry':True,'normal_reset':True,'errors':errors}
   ctx.close()
  browser.close()
finally:server.shutdown()
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))
