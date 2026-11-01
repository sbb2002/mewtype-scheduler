"""생일 시작 · 종료 자정 전환을 실제 시간으로 검사한다. YouTube 는 호출을 기록하는 대역으로 바꾼다."""
from pathlib import Path
import functools,http.server,json,sys,tempfile,threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'midnight';OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{server.server_port}/src/frontend/'
# 곡 목록은 앱에 같이 배포되는 시드를 쓴다.
YT_STUB="""
window.__yt={calls:[],vol:100,state:-1,vols:[]};
window.YT={PlayerState:{UNSTARTED:-1,ENDED:0,PLAYING:1,PAUSED:2,BUFFERING:3,CUED:5},Player:class{
 constructor(el,o){this.o=o;this.frame=document.createElement('iframe');setTimeout(()=>o.events.onReady({target:this}),0)}
 set(s){__yt.state=s;this.o.events.onStateChange?.({data:s,target:this})}
 playVideo(){__yt.calls.push('play');setTimeout(()=>this.set(1),0)} pauseVideo(){__yt.calls.push('pause');setTimeout(()=>this.set(2),0)} stopVideo(){__yt.calls.push('stop');this.set(0)}
 loadVideoById(v){__yt.calls.push('load');__yt.vid=v;setTimeout(()=>this.set(1),0)} cueVideoById(v){__yt.calls.push('cue');__yt.vid=v;setTimeout(()=>this.set(5),0)}
 getVolume(){return __yt.vol} setVolume(v){__yt.vol=v;__yt.vols.push([performance.now(),v])} seekTo(){} getDuration(){return 200} getCurrentTime(){return 12} getPlayerState(){return __yt.state} getVideoData(){return {video_id:__yt.vid}} getIframe(){return this.frame} destroy(){}
}};
setTimeout(()=>window.onYouTubeIframeAPIReady?.(),0);
"""
# 새로고침해도 시계가 처음으로 돌아가지 않게 차이를 탭에 남긴다.
def clock(iso):return f"let o;try{{o=sessionStorage.getItem('clock')}}catch{{}}if(o===null||o===undefined){{o=Date.parse('{iso}')-Date.now();try{{sessionStorage.setItem('clock',o)}}catch{{}}}}o=+o;const r=Date.now.bind(Date);Date.now=()=>r()+o;"
def page_at(browser,iso,opts):
 context=browser.new_context(**opts);context.add_init_script(clock(iso))
 page=context.new_page();errors=[];reqs=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda q:reqs.append(q.url))
 def route(r):
  u=r.request.url
  if 'youtube.com/iframe_api' in u:return r.fulfill(content_type='text/javascript',body=YT_STUB)
  if '/data/' in u:return r.fulfill(status=404,body='')
  if '127.0.0.1' not in u:return r.abort()
  if u.split('?')[0].endswith('/birthdayui.js'):
   return r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music}};')
  r.continue_()
 page.route('**/*',route);return context,page,errors,reqs
bad=[]
def check(ok,msg):
 print('통과' if ok else '실패',msg,flush=True)
 if not ok:bad.append(msg)
EVE='2026-11-03T14:59:52Z'   # KST 11-03 23:59:52
LAST='2026-11-04T14:59:54Z'  # KST 11-04 23:59:54
bgm="()=>({on:!!document.querySelector('#bday-bg'),audio:window.__birthday?.audio?{paused:window.__birthday.audio.paused,t:window.__birthday.audio.audio.currentTime}:null})"
with sync_playwright() as p:
 browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
 # 1. 전날 밤에 PC 도크로 듣는 중
 context,page,errors,_=page_at(browser,EVE,{'viewport':{'width':1280,'height':800}})
 page.goto(URL,wait_until='commit');page.wait_for_selector('#player-dock .mp-main',timeout=20000)
 check(not page.evaluate(bgm)['on'],'전날 밤에는 장면이 없다')
 page.locator('#player-dock .mp-main').click();page.wait_for_function('__yt.state===1',timeout=5000)
 vid=page.evaluate('__yt.vid');calls=page.evaluate('__yt.calls.length')
 page.wait_for_selector('#bday-bg',state='attached',timeout=11000);page.evaluate('__tOn=performance.now()')
 page.wait_for_function('window.__birthday?.audio&&!__birthday.audio.paused',timeout=6000)
 mid=page.evaluate('__yt.state');check(mid==1,'소리를 줄이는 동안 유튜브는 계속 재생 중')
 page.wait_for_function('__yt.state===2',timeout=6000);page.wait_for_timeout(300)
 y=page.evaluate('({vols:__yt.vols.map(v=>v[1]),span:__yt.vols.at(-2)?__yt.vols.at(-2)[0]-__yt.vols[0][0]:0,vol:__yt.vol,calls:__yt.calls,vid:__yt.vid})')
 steps=y['vols'][:-1]
 check(len(steps)>=20 and all(a>=b for a,b in zip(steps,steps[1:])) and steps[-1]==0,f"볼륨이 서서히 0 까지 내려감 {len(steps)}단계")
 check(2200<y['span']<3300,f"페이드 시간 {round(y['span'])}ms")
 check(y['vol']==100,'멈춘 뒤 볼륨을 원래 값으로 되돌림')
 check(y['vid']==vid and not {'load','cue','stop'}&set(y['calls'][calls:]),'곡을 바꾸거나 정지하지 않음(재생목록 유지)')
 s=page.evaluate(bgm);page.wait_for_timeout(1000);s2=page.evaluate(bgm)
 check(s['audio'] and not s['audio']['paused'] and s2['audio']['t']>s['audio']['t'],'생일 음악이 재생 중')
 check(page.evaluate("document.documentElement.hasAttribute('data-bday-full')"),'온전히 보기로 켜짐')
 page.screenshot(path=str(OUT/'live-pc.png'))
 check(not errors,f'페이지 오류 없음 {errors[:2]}');context.close()
 # 2. 아무것도 안 듣는 중
 context,page,errors,_=page_at(browser,EVE,{'viewport':{'width':1280,'height':800}})
 page.goto(URL,wait_until='commit');page.wait_for_selector('#bday-bg',state='attached',timeout=12000)
 page.wait_for_function('window.__birthday?.audio&&!__birthday.audio.paused',timeout=6000);check(True,'듣는 곡이 없어도 00:00 에 켜짐');check(not errors,f'페이지 오류 없음 {errors[:2]}');context.close()
 # 3. 모바일 팝업을 열어 둔 채
 context,page,errors,_=page_at(browser,EVE,{'viewport':{'width':390,'height':844},'is_mobile':True,'has_touch':True,'device_scale_factor':3})
 page.goto(URL,wait_until='commit');page.wait_for_timeout(1500)
 page.evaluate("document.dispatchEvent(new CustomEvent('mew:player-open'))");page.wait_for_selector('.mp-scrim.is-open',timeout=5000)
 page.locator('.mp-scrim .mp-main').click();page.wait_for_function('__yt.state===1',timeout=5000)
 page.wait_for_selector('#bday-bg',state='attached',timeout=11000);page.wait_for_function('__yt.state===2',timeout=7000);page.wait_for_timeout(600)
 check(not page.evaluate("!!document.querySelector('.mp-scrim.is-open')"),'모바일 팝업이 내려감')
 page.screenshot(path=str(OUT/'live-mobile.png'));check(not errors,f'페이지 오류 없음 {errors[:2]}');context.close()
 # 4. 생일이 끝나는 자정
 context,page,errors,reqs=page_at(browser,LAST,{'viewport':{'width':1280,'height':800}})
 page.goto(URL,wait_until='commit');page.wait_for_function('window.__birthday?.audio&&!__birthday.audio.paused',timeout=8000)
 page.wait_for_timeout(9000);s=page.evaluate(bgm);page.wait_for_timeout(800);s2=page.evaluate(bgm)
 check(page.evaluate('Date.now()')>=0 and s['on'] and s2['audio']['t']>s['audio']['t'],'생일이 끝나도 켜 둔 장면 · 음악 유지')
 page.evaluate("document.dispatchEvent(new Event('visibilitychange'))");page.wait_for_timeout(300);check(page.evaluate(bgm)['on'],'탭을 오가도 유지')
 reqs.clear();page.reload(wait_until='commit');page.wait_for_selector('#board',state='attached');page.wait_for_timeout(2500)
 check(not page.evaluate(bgm)['on'] and not [u for u in reqs if '/js/bday' in u],'새로고침하면 사라지고 생일 파일을 받지 않음')
 check(not errors,f'페이지 오류 없음 {errors[:2]}');context.close()
 # 5. 다음 날 처음 들어온 사람
 context,page,errors,reqs=page_at(browser,'2026-11-04T15:00:30Z',{'viewport':{'width':1280,'height':800}})
 page.goto(URL,wait_until='commit');page.wait_for_selector('#board',state='attached');page.wait_for_timeout(2500)
 check(not page.evaluate(bgm)['on'] and not [u for u in reqs if '/js/bday' in u],'다음 날 들어오면 볼 수 없음');context.close()
 browser.close()
server.shutdown()
print('실패' if bad else 'OK',bad,OUT);sys.exit(1 if bad else 0)
