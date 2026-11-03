"""자동재생 정책, 실제 곡 종료, 자정 재판정과 리소스 수명 검증."""
from pathlib import Path
import json, threading, functools, http.server
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Documents-pyworks-mewtype-scheduler\cd557148-9ec6-47cb-b90f-a459b94aa233\scratchpad\handoff\verify')
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8102),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
audit='''(()=>{
 const add=EventTarget.prototype.addEventListener,remove=EventTarget.prototype.removeEventListener,records=[];
 EventTarget.prototype.addEventListener=function(type,fn,opt){const rec={target:this,type,fn,capture:typeof opt==='boolean'?opt:!!opt?.capture,active:true,birthday:/\\/(bday[^/]*|birthdayui)\\.js/.test(new Error().stack)};records.push(rec);if(opt?.signal)add.call(opt.signal,'abort',()=>rec.active=false,{once:true});return add.call(this,type,fn,opt)};
 EventTarget.prototype.removeEventListener=function(type,fn,opt){const capture=typeof opt==='boolean'?opt:!!opt?.capture;for(const r of records)if(r.target===this&&r.type===type&&r.fn===fn&&r.capture===capture)r.active=false;return remove.call(this,type,fn,opt)};
 const raf=window.requestAnimationFrame,caf=window.cancelAnimationFrame,frames=new Set();window.requestAnimationFrame=fn=>{const id=raf.call(window,t=>{frames.delete(id);fn(t)});frames.add(id);return id};window.cancelAnimationFrame=id=>{frames.delete(id);caf.call(window,id)};
 const make=URL.createObjectURL,revoke=URL.revokeObjectURL,urls=new Set();URL.createObjectURL=b=>{const u=make(b);urls.add(u);return u};URL.revokeObjectURL=u=>{urls.delete(u);revoke(u)};
 const NativeAudio=window.Audio,audios=[];window.Audio=function(...args){const a=new NativeAudio(...args);audios.push(a);return a};
 const NativeContext=window.AudioContext,contexts=[];window.AudioContext=function(...args){const c=new NativeContext(...args);contexts.push(c);return c};
 const now=Date.now;Date.now=()=>window.testNow??now();
 window.testAudios=audios;window.audit=()=>({listeners:records.filter(r=>r.active&&(!('isConnected' in r.target)||r.target.isConnected)).length,birthdayListeners:records.filter(r=>r.active&&r.birthday&&(!('isConnected' in r.target)||r.target.isConnected)).length,raf:frames.size,urls:urls.size,audios:audios.filter(a=>!!a.getAttribute('src')||!a.paused).length,contexts:contexts.filter(c=>c.state!=='closed').length});
})();'''
def routes(route):
    u=route.request.url
    if '127.0.0.1' not in u:route.fulfill(status=200,content_type='application/json',body='{}')
    elif '/data/' in u:
        f=ROOT/'fixtures'/u.rsplit('/',1)[1].replace('.json','.sample.json')
        route.fulfill(content_type='application/json',body=f.read_text(encoding='utf8') if f.exists() else '{}')
    elif u.endswith('/birthdayui.js'):
        s=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+'\nwindow.__birthday={get scene(){return ctrl},get audio(){return music},get player(){return player},teardown,evaluate,setFull,destroyBirthday};'
        route.fulfill(content_type='text/javascript',body=s)
    else:route.continue_()
result={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--autoplay-policy=document-user-activation-required'])
    ctx=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1')
    ctx.add_init_script(audit);ctx.route('**/*',routes)
    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # wait_for_function/evaluate는 CDP userGesture를 부여하므로 최초 차단 판정 이전에는 사용하지 않는다.
    page.goto('http://127.0.0.1:8102/src/frontend/?bday=yuno&ufo=sign');page.wait_for_timeout(2000)
    result['blocked']=page.evaluate('()=>({paused:__birthday.audio.paused,time:__birthday.audio.audio.currentTime,prompt:!document.querySelector(".bday-start").hidden,filter:getComputedStyle(document.querySelector("#bday-bg canvas")).filter,volume:__birthday.audio.diagnostics().volume})')
    print('BLOCKED',json.dumps(result['blocked']),flush=True)
    page.screenshot(path=str(OUT/'autoplay-blocked.png'))
    page.tap('.bday-start');page.wait_for_timeout(600)
    result['tap']=page.evaluate('()=>({paused:__birthday.audio.paused,time:__birthday.audio.audio.currentTime,prompt:!document.querySelector(".bday-start").hidden,gain:__birthday.audio.diagnostics().volume,mediaVolume:__birthday.audio.audio.volume})')
    page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(25)}');page.wait_for_function('!document.documentElement.hasAttribute("data-bday-intro")')
    result['ios_shape']=page.evaluate('()=>({slider:getComputedStyle(document.querySelector(".bday-volume")).display,muted:__birthday.audio.muted})')
    page.tap('.bday-ib.mute');result['ios_mute']=page.evaluate('()=>__birthday.audio.diagnostics().volume')
    page.evaluate('()=>__birthday.audio.setVolume(.64)')
    page.wait_for_function('__birthday.audio.diagnostics().decoded')
    # 예약한 실제 곡 경계까지 재생한다(합성 ended 이벤트 없음).
    page.evaluate('async()=>{await __birthday.audio.seek(__birthday.audio.audio.duration-.35);await __birthday.audio.play()}')
    page.wait_for_function('__birthday.audio.index===1',timeout=10000)
    page.wait_for_timeout(200)
    result['natural_boundary']=page.evaluate('()=>({index:__birthday.audio.index,paused:__birthday.audio.paused,title:document.querySelector(".bday-track").textContent,blob:__birthday.audio.audio.src.startsWith("blob:")})')
    result['scheduled_transitions']=page.evaluate('()=>__birthday.audio.diagnostics().transitions')
    assert result['scheduled_transitions'] and all(t['gap']==0 for t in result['scheduled_transitions'])
    # previous와 임의 탐색은 일시정지 상태에서 오차 측정.
    page.evaluate('()=>__birthday.audio.previous()');page.wait_for_timeout(200)
    result['previous']=page.evaluate('()=>__birthday.audio.index')
    page.evaluate('async()=>{__birthday.audio.pause();await __birthday.audio.seek(110.125)}');page.wait_for_timeout(150)
    result['paused_seek_error_seconds']=page.evaluate('()=>Math.abs(__birthday.audio.audio.currentTime-110.125)')
    page.evaluate('()=>__birthday.teardown()');page.wait_for_timeout(200)
    result['after_teardown']=page.evaluate('()=>audit()')
    # 동일 문서에서 다시 마운트: 저장값 복원 및 자정 evaluate 정리.
    page.evaluate('()=>__birthday.evaluate()');page.wait_for_function('__birthday.player');page.wait_for_timeout(200)
    result['restore_volume']=page.evaluate('()=>__birthday.audio.volume')
    result['before_midnight']=page.evaluate('()=>audit()')
    page.evaluate('()=>{history.replaceState(null,"",location.pathname);window.testNow=Date.parse("2026-11-04T15:00:01Z");__birthday.evaluate()}');page.wait_for_timeout(300)
    result['after_midnight']=page.evaluate('()=>({audit:audit(),birthday:document.documentElement.hasAttribute("data-bday"),scene:__birthday.scene,audio:__birthday.audio})')
    page.evaluate('()=>__birthday.destroyBirthday()');page.wait_for_timeout(200)
    result['after_destroyBirthday']=page.evaluate('()=>audit()')
    page.goto('http://127.0.0.1:8102/src/frontend/');page.wait_for_timeout(1000)
    result['ordinary_baseline']=page.evaluate('()=>audit()')
    result['errors']=errors
    browser.close()
server.shutdown()
(OUT/'lifecycle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
