"""선택 배경 2안·기본 그리기 불변성·수평 눈 자산을 검증하고 확대 캡처한다."""
from pathlib import Path
import functools,http.server,threading,tempfile,json,hashlib
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from build_birthday_flat_head import build

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'round7';OUT.mkdir(parents=True,exist_ok=True)
source,expected,allowed=build()
asset=Image.open(ROOT/'src/frontend/assets/birthday/yuno/head_flat.webp').convert('RGBA')
original=np.array(source);actual=np.array(asset)
assert asset.size==(380,339) and np.array_equal(actual,np.array(expected))
assert np.array_equal(actual[~allowed],original[~allowed]) and np.array_equal(actual[:,:,3],original[:,:,3])
asset.resize((760,678)).save(OUT/'head-flat-2x.png')
asset.crop((210,195,335,265)).resize((1000,560)).save(OUT/'right-eye-after.png')
source.crop((210,195,335,265)).resize((1000,560)).save(OUT/'right-eye-before.png')
Image.fromarray(allowed.astype('uint8')*255).save(OUT/'eye-edit-mask.png')

class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results={'asset':{'dimensions':asset.size,'outside_mask_identical':True,'alpha_identical':True,'changed_pixels':int(np.any(actual!=original,axis=-1).sum())}}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
  for width,height in [(1440,900),(390,844),(320,568),(740,360)]:
   context=browser.new_context(viewport={'width':width,'height':height})
   context.add_init_script("Math.random=()=>.417;localStorage.setItem('bday-yuno-controls-unlocked-v1','1')")
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def route(r):
    if '127.0.0.1' not in r.request.url:r.fulfill(content_type='application/json',body='{}')
    elif '/birthdayui.js' in r.request.url:
     r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},teardown};')
    elif '/bdayscene-yuno.js' in r.request.url:
     s=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {skyBusy(t)','return {stopForTest(){cancelAnimationFrame(raf);raf=0},testPlan(){return skyPlan(TRK)},skyBusy(t)')
     r.fulfill(content_type='text/javascript',body=s)
    elif '/bdaybackdrop.js' in r.request.url:
     s=(ROOT/'src/frontend/js/bdaybackdrop.js').read_text(encoding='utf8').replace('function build(view,size){','function build(view,size){window.__backdropBuilds=(window.__backdropBuilds||0)+1;').replace('c.drawImage(cache,','window.__backdropDraws=(window.__backdropDraws||0)+1;c.drawImage(cache,')
     r.fulfill(content_type='text/javascript',body=s)
    else:r.continue_()
   page.route('**/*',route)
   def load(mode=''):
    page.goto(f'http://127.0.0.1:{server.server_port}/src/frontend/?bday=yuno&ufo=sign'+('&backdrop='+mode if mode else ''))
    page.wait_for_function('window.__birthday?.scene && document.documentElement.hasAttribute("data-bday-started")')
    page.evaluate('async()=>{__birthday.audio.pause();await __birthday.scene.whenReady;await __birthday.audio.seek(19.05)}')
    page.wait_for_selector('[data-bday-revealed]',state='attached')
    page.evaluate('()=>{for(const a of document.getAnimations())if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish();__birthday.scene.stopForTest();__birthday.scene.setIntro(()=>false);__birthday.scene.renderAt(50)}')
   def shot(mode,phase):
    path=OUT/f'{width}x{height}-{mode}-{phase}.png';page.screenshot(path=str(path))
    with Image.open(path) as im:im.resize((width*2,height*2)).save(path.with_stem(path.stem+'-2x'))
   load()
   assert page.evaluate('(window.__backdropBuilds||0)+(window.__backdropDraws||0)')==0
   # 그리기 호출을 완전히 지운 장면과 기본 장면을 같은 시드/시각에 비교한다.
   baseline=page.evaluate('()=>{__birthday.scene.stopForTest();__birthday.scene.renderAt(50);return HTMLCanvasElement.prototype.toDataURL.call(document.querySelector("#bday-bg canvas"))}')
   page.route('**/bdayscene-yuno.js*',lambda r:r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/bdayscene-yuno.js').read_text(encoding='utf8').replace('return {skyBusy(t)','return {stopForTest(){cancelAnimationFrame(raf);raf=0},skyBusy(t)').replace('  backdrop.draw(c,skyViewport,{width:w,height:h},introActive()?.35+.65*effect.rise:1);','')))
   load();control=page.evaluate('()=>{__birthday.scene.stopForTest();__birthday.scene.renderAt(50);return HTMLCanvasElement.prototype.toDataURL.call(document.querySelector("#bday-bg canvas"))}');assert len(baseline)>1000 and baseline==control
   page.unroute('**/bdayscene-yuno.js*')
   # 기본 화면 0% 표정과 일반 깜빡임의 자산 선택을 실제 drawImage에서 계측한다.
   page.evaluate('()=>{const draw=CanvasRenderingContext2D.prototype.drawImage;CanvasRenderingContext2D.prototype.drawImage=function(img,...args){if(img?.src?.includes("head_"))window.__headAsset=img.src.split("/").at(-1);return draw.call(this,img,...args)}}')
   page.evaluate('()=>{__birthday.audio.setVolume(0);__birthday.scene.renderAt(50)}');assert page.evaluate('window.__headAsset')=='head_flat.webp';shot('default','zero-volume')
   assert page.evaluate('()=>{__birthday.audio.setVolume(.3);__birthday.scene.renderAt(2.75);return window.__headAsset}')=='head_closed.webp'
   assert page.evaluate('()=>{__birthday.scene.renderAt(50);return window.__headAsset}')=='head_open.webp'
   modes={}
   for mode in ['mountain','cake']:
    load(mode);shot(mode,'normal')
    builds=page.evaluate('window.__backdropBuilds')
    page.evaluate('()=>{__birthday.scene.renderAt(51);__birthday.scene.renderAt(52)}')
    assert page.evaluate('window.__backdropBuilds')==builds
    page.evaluate('()=>{__birthday.scene.setIntro(()=>true);__birthday.scene.renderAt(19.05)}');shot(mode,'intro-after')
    page.evaluate('()=>{__birthday.scene.setIntro(()=>false);const f=__birthday.scene.testPlan().ufos[0];__birthday.scene.renderAt(f.birth+f.reveal+1)}');shot(mode,'sign')
    # 캔버스 크기 변경만 새 캐시를 만들고 destroy에서 정리한다.
    page.set_viewport_size({'width':width+1,'height':height});page.wait_for_timeout(100)
    assert page.evaluate('window.__backdropBuilds')>builds
    page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100)
    modes[mode]={'cached_between_frames':True,'resize_rebuild':True}
   assert not errors,errors
   page.evaluate('__birthday.teardown()')
   results[f'{width}x{height}']={'default_pixel_identical':True,'default_draw_calls':0,'default_sha256':hashlib.sha256(baseline.encode()).hexdigest(),'flat_only_at_zero':True,'normal_blink_unchanged':True,'modes':modes,'errors':errors}
   context.close()
  browser.close()
finally:server.shutdown()
(OUT/'backdrop-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))
