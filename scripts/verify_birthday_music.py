"""실제 Chromium에서 앱/정본을 캡처하고 생일 음악 계약을 검증한다."""
from pathlib import Path
import functools, http.server, threading, json, time, statistics
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HANDOFF=Path(r'C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Documents-pyworks-mewtype-scheduler\cd557148-9ec6-47cb-b90f-a459b94aa233\scratchpad\handoff')
OUT=HANDOFF/'verify'
OUT.mkdir(exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self,path):
        if path.startswith('/reference/'):
            return str(HANDOFF/path.split('?',1)[0].removeprefix('/reference/'))
        return super().translate_path(path)
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8100),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL='http://127.0.0.1:8100/src/frontend/'
results={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
    context=browser.new_context(viewport={'width':1440,'height':900},device_scale_factor=1)
    def routes(route):
        url=route.request.url
        if '127.0.0.1' not in url:
            route.fulfill(status=200,content_type='application/json',body='{}');return
        if '/data/' in url:
            file=ROOT/'fixtures'/(url.rsplit('/',1)[1].replace('.json','.sample.json'))
            route.fulfill(status=200,content_type='application/json',body=file.read_text(encoding='utf8') if file.exists() else '{}');return
        if url.split('?')[0].endswith('/birthdayui.js'):
            source=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')
            source+='\nwindow.__birthday={get scene(){return ctrl},get audio(){return music},get player(){return player},teardown,evaluate,setFull};'
            route.fulfill(content_type='text/javascript',body=source);return
        if url.endswith('/bdayscene-yuno.js'):
            source=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8')
            wrap='window.stageCosts={};\n'
            for name in ['bg','skyProps','floorWave','visual','skyUfos','front']:
                wrap+=f'const original_{name}={name};{name}=(...args)=>{{const start=performance.now();const result=original_{name}(...args);(window.stageCosts.{name}||=[]).push(performance.now()-start);return result}};\n'
            source=source.replace(" const canvas=document.createElement('canvas');",wrap+" const canvas=document.createElement('canvas');")
            route.fulfill(content_type='text/javascript',body=source);return
        route.continue_()
    context.route('**/*',routes)
    page=context.new_page();errors=[];requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r.url))
    page.goto(URL);page.wait_for_timeout(1500)
    results['ordinary_birthday_requests']=[u for u in requests if any(k in u for k in ['bdayscene','bdayaudio','bdaysign','bdaylogic','/birthday/'])]
    requests.clear();page.goto(URL+'?bday=yuno&ufo=sign')
    page.wait_for_function('window.__birthday?.audio && window.__birthday?.player',timeout=30000)
    page.wait_for_timeout(1000)
    results['initial']=page.evaluate('''()=>({paused:__birthday.audio.paused,volume:__birthday.audio.volume,context:__birthday.audio.diagnostics(),track:__birthday.audio.track.title})''')
    results['brightness']=[]
    for t in [0,1.5,3,10,17,17.2,17.9,18.2,18.7]:
        page.evaluate('async(t)=>{__birthday.audio.pause();await __birthday.audio.seek(t)}',t)
        page.wait_for_timeout(80)
        results['brightness'].append({'time':t,'filter':page.locator('#bday-bg canvas').first.evaluate('(e)=>getComputedStyle(e).filter')})
        if t in [0,3,17.2,18.7]:page.screenshot(path=str(OUT/f'intro-{t}.png'))
    page.evaluate('''()=>__birthday.audio.seek(25)''');page.wait_for_timeout(6000)
    page.screenshot(path=str(OUT/'pc-app.png'))
    results['guard']=page.evaluate('''()=>{const cv=document.querySelector('#bday-bg canvas');return {data:cv.toDataURL(),contextmenu:!document.querySelector('#bday-music').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true})),drag:!document.querySelector('#bday-bg').dispatchEvent(new Event('dragstart',{cancelable:true})),F12:!document.dispatchEvent(new KeyboardEvent('keydown',{key:'F12',cancelable:true})),imageData:cv.getContext('2d').getImageData(0,0,1,1).data.join(',')}}''')
    results['guard']['body_contextmenu']=page.evaluate('()=>!document.body.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true}))')
    results['guard']['blob_is_null']=page.evaluate('()=>new Promise(resolve=>document.querySelector("#bday-bg canvas").toBlob(b=>resolve(b===null)))')
    for w,h in [(390,844),(412,915),(360,800)]:
        page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(300)
        page.evaluate('()=>{__birthday.scene.setStill(true);__birthday.scene.renderAt(118.5)}')
        page.screenshot(path=str(OUT/f'mobile-{w}x{h}.png'))
        results[f'mobile-{w}']=page.evaluate('''()=>{const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};return {layout:__birthday.scene.diagnostics().layout,bar:rect('.bday-music__bar'),title:rect('.bday-music__title'),disc:rect('.bday-music__disc'),slider:getComputedStyle(document.querySelector('.bday-volume')).display}}''')
    page.set_viewport_size({'width':1440,'height':900})
    page.evaluate('()=>__birthday.scene.setStill(false)')
    page.wait_for_timeout(650)
    box=page.locator('.bday-btn').bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.wait_for_timeout(550);page.mouse.move(40,210,steps=6);page.mouse.up();page.wait_for_timeout(600)
    results['cake_drag']=page.evaluate('()=>({saved:JSON.parse(localStorage.getItem("bday-btn")),dragging:document.querySelector("#bday-ui").classList.contains("is-drag")})')
    page.evaluate('()=>{document.activeElement.blur();__birthday.audio.setVolume(.46)}');page.keyboard.press('ArrowUp');page.keyboard.press('m')
    results['keyboard']=page.evaluate('()=>({volume:__birthday.audio.volume,muted:__birthday.audio.muted,saved:localStorage.getItem("bday-vol")})')
    page.evaluate('()=>__birthday.audio.mute()')
    page.evaluate('()=>__birthday.audio.next()');page.wait_for_timeout(800)
    results['next']=page.evaluate('()=>({index:__birthday.audio.index,title:document.querySelector(".bday-track").textContent,beat:__birthday.scene.diagnostics().snapshot?.t})')
    page.evaluate('()=>__birthday.audio.seek(143)');page.wait_for_timeout(300)
    results['seek']=page.evaluate('()=>__birthday.audio.audio.currentTime')
    page.evaluate('async()=>{await __birthday.audio.seek(__birthday.audio.audio.duration-.25);await __birthday.audio.play()}');page.wait_for_function('__birthday.audio.index===0')
    results['natural_boundary']=page.evaluate('()=>({index:__birthday.audio.index,paused:__birthday.audio.paused,title:document.querySelector(".bday-track").textContent})')
    # 재생 상태에서 CPU 비용 120프레임을 수집한다.
    page.evaluate('()=>__birthday.audio.play()');page.wait_for_timeout(3500)
    costs=page.evaluate('()=>__birthday.scene.diagnostics().costs.slice(-120)')
    results['cpu']={'samples':len(costs),'mean':statistics.mean(costs),'p95':sorted(costs)[int(len(costs)*.95)],'max':max(costs)}
    results['stage_cpu']=page.evaluate('()=>Object.fromEntries(Object.entries(stageCosts).map(([k,v])=>[k,v.slice(-120).reduce((a,b)=>a+b,0)/Math.min(v.length,120)]))')
    page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(150)
    results['reduced']=page.evaluate('()=>__birthday.scene.diagnostics().raf')
    page.emulate_media(reduced_motion='no-preference')
    page.wait_for_timeout(100)
    page.evaluate('()=>__birthday.scene.finale()');page.wait_for_timeout(100)
    results['finale_particles']=page.evaluate('()=>__birthday.scene.diagnostics().particles')
    page.screenshot(path=str(OUT/'pc-finale.png'))
    page.evaluate('()=>__birthday.scene.celebrate(.5,.3)')
    results['celebrate_particles']=page.evaluate('()=>__birthday.scene.diagnostics().particles')
    page.evaluate('()=>{Object.defineProperty(document,"hidden",{configurable:true,get:()=>true});document.dispatchEvent(new Event("visibilitychange"))}')
    results['hidden_scene_raf']=page.evaluate('()=>__birthday.scene.diagnostics().raf')
    page.evaluate('()=>{delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))}')
    page.evaluate('()=>document.querySelector("#bday-bg").style.transform="translateX(300vw)"');page.wait_for_timeout(200)
    results['outside_scene_raf']=page.evaluate('()=>__birthday.scene.diagnostics().raf')
    page.evaluate('()=>document.querySelector("#bday-bg").style.transform=""');page.wait_for_timeout(100)
    results['guard_restore']=page.evaluate('''()=>{__birthday.setFull(false);return document.querySelector('#bday-bg canvas').toDataURL().slice(0,22)}''')
    page.evaluate('''()=>{window.oldAudio=__birthday.audio;window.oldScene=__birthday.scene;__birthday.teardown()}''');page.wait_for_timeout(200)
    results['destroy']=page.evaluate('()=>({audio:oldAudio.diagnostics(),scene:oldScene.diagnostics().raf,canvas:document.querySelectorAll("#bday-bg canvas").length,ui:document.querySelectorAll("#bday-music").length})')
    results['errors']=errors;results['sign_image_requests']=[u for u in requests if 'sign.' in u and not u.endswith('.js')]
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    browser.close()
server.shutdown()
print(json.dumps(results,ensure_ascii=False,indent=2))
