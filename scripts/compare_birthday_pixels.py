"""시안 함수 원문과 앱의 같은 곡/시각을 실제 Chromium 픽셀로 비교."""
from pathlib import Path
import re, json, functools, threading, http.server, io
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
H=Path(r'C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Documents-pyworks-mewtype-scheduler\cd557148-9ec6-47cb-b90f-a459b94aa233\scratchpad\handoff')
OUT=H/'verify';OUT.mkdir(exist_ok=True)
s=(H/'prototype_v12.html').read_text(encoding='utf8');s=s[s.index('const spectrumHash19'):]
body=s[:s.index('const TRACKS=')]+s[s.index('function line('):s.index('function seekAudio(')]
body=body.replace("i.src='yuno/'+n+'.webp'","i.src='/src/frontend/assets/birthday/yuno/'+n+'.webp'").replace("skyUFO.src='ufo.png'","skyUFO.src='/src/frontend/assets/birthday/ufo.png'")
ref='export async function mountReference(host,T,normalized=false){'+body+'''
 TRK=T;
 const canvas=document.createElement('canvas');canvas.width=1440;canvas.height=900;host.append(canvas);const c=canvas.getContext('2d');
 await Promise.all([...Object.values(YN),skyUFO].map(i=>i.decode()));
 return {renderAt(t){c.setTransform(1,0,0,1,0,0);c.clearRect(0,0,1440,900);const s=Math.max(1440/1200,900/760);c.setTransform(s,0,0,s,0,(900-760*s)/2);bg(c);skyProps(c,t);floorWave(c,0,t);visual(c,5,t);skyUfos(c,t);c.save();if(normalized)c.translate(-75,0);front(c,t);c.restore()}};
}'''
# 정본과 차이가 허용된 x/사인 폭/드롭만 보정한 비교도 별도로 수행한다.
norm=ref.replace('drop:midnight?24:32','drop:midnight?24:beatPos(17.14)').replace('drop:B[drop]','drop:mid?B[drop]:17.14').replace('birth:B[drop]-6','birth:(mid?B[drop]:17.14)-6')
norm=norm.replace('function skySignDraw(c,f,age){','function skySignDraw(c,f,age){c.save();c.translate(55,30);c.scale(.88,.88);c.translate(-55,-30);originalSign(c,f,age);c.restore()}\nfunction originalSign(c,f,age){')
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8101),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
    page.add_init_script('Math.random=()=>.314159;')
    def route(r):
        if r.request.url.endswith('/ref.js'):r.fulfill(content_type='text/javascript',body=ref)
        elif r.request.url.endswith('/norm.js'):r.fulfill(content_type='text/javascript',body=norm)
        elif '/verify.html' in r.request.url:r.fulfill(content_type='text/html',body='<style>body{margin:0}#host{position:fixed;inset:0}canvas{display:block;width:100%;height:100%}</style><div id="host"></div>')
        else:r.continue_()
    page.route('**/*',route)
    for key,t in [('midnight',60.2),('midnight',143),('noctural',17.5),('noctural',25),('noctural',110),('noctural',114),('noctural',118)]:
        shots={}
        for mode in ['app','ref','normalized']:
            page.goto('http://127.0.0.1:8101/verify.html?ufo=sign')
            page.evaluate('''async({key,t,mode})=>{
             const {decodeTrack}=await import('/src/frontend/js/bdaylogic.js');const T=decodeTrack(await(await fetch('/src/frontend/assets/birthday/beat/'+key+'.json')).json(),await(await fetch('/src/frontend/assets/birthday/beat/'+key+'.bin')).arrayBuffer());
             const host=document.querySelector('#host');
             if(mode==='app'){const {mountYunoScene}=await import('/src/frontend/js/bdayscene-yuno.js');window.scene=mountYunoScene(host);scene.setTrack(T);await scene.whenReady;scene.setStill(true);scene.renderAt(t)}
             else{const {mountReference}=await import(mode==='ref'?'/ref.js':'/norm.js');window.scene=await mountReference(host,T,mode==='normalized');scene.renderAt(t)}
            }''',{'key':key,'t':t,'mode':mode})
            raw=page.screenshot(path=str(OUT/f'pixels-{key}-{t}-{mode}.png'))
            shots[mode]=np.asarray(Image.open(io.BytesIO(raw)).convert('RGB')).astype(np.int16)
        record={'track':key,'time':t}
        for mode in ['ref','normalized']:
            d=np.abs(shots['app']-shots[mode]);mask=np.max(d,axis=2)>2
            record[mode]={'changed_pixels_percent':float(mask.mean()*100),'mean_channel_difference':float(d.mean()),'max_channel_difference':int(d.max())}
            if mode=='normalized':Image.fromarray((np.clip(d*4,0,255)).astype('uint8')).save(OUT/f'diff-{key}-{t}.png')
        results.append(record)
    browser.close()
server.shutdown()
(OUT/'pixels.json').write_text(json.dumps(results,indent=2),encoding='utf8')
print(json.dumps(results,indent=2))
