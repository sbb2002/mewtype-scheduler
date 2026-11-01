"""실제 서비스 조건에서 메인 기능과 생일 이스터에그가 서로 영향을 주지 않는지 검사한다.

운영 data 브랜치의 JSON 을 받아 /data/*.json 으로 내주고(로컬 주소는 이 경로를 읽는다), 폴링 주기를 줄여
평상 → 버스트 → 503 → 응답 없음 → 깨진 JSON → 빈 데이터 → 복구를 차례로 지나게 한다.
POLL_MS 환경변수로 폴링 주기를 정한다(기본 3000, 실제 주기 시험은 75000). PHASE_POLLS 로 단계별 폴링 횟수를 배수 조절한다.
"""
from pathlib import Path
import copy,functools,http.server,json,os,sys,tempfile,threading,time,urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(tempfile.gettempdir())/'birthday-story'/'service';OUT.mkdir(parents=True,exist_ok=True)
POLL=int(os.environ.get('POLL_MS','3000'))
RAW='https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/'
FILES={'preview':'preview.json','notices':'notices.json','tweets':'tweets.json','banners':'banners.json','preview_archive':'preview_archive.json','songs':'songs.json'}
def fetch(name):
 try:
  with urllib.request.urlopen(RAW+name,timeout=15) as r:return json.load(r)
 except Exception:return None
BASE={k:fetch(v) for k,v in FILES.items()}
assert BASE['preview'] and BASE['notices'] and BASE['tweets'],'운영 데이터를 받지 못했다'

class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
 def copyfile(self,source,outputfile):
  try:super().copyfile(source,outputfile)
  except (ConnectionResetError,BrokenPipeError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{server.server_port}/src/frontend/'

class Feed:
 """폴링 응답을 단계에 따라 바꾼다. 버스트는 폴링마다 새 글이 무더기로 들어온다."""
 def __init__(self):self.mode='normal';self.tick=0;self.hits={}
 def body(self,key):
  data=copy.deepcopy(BASE[key])
  if data is None:return None
  if self.mode!='burst':return data
  self.tick+=1;n=self.tick
  if key=='preview':
   src=data['items'];start=time.time()+3600
   for i in range(30):
    it=copy.deepcopy(src[i%len(src)]);member=data['channel_order'][i%5]
    stamp=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(start+i*1800))
    it.update(id=f'pv_burst_{n}_{i}',video_id=f'burst{n:03d}{i:03d}',title=f'버스트 예고 {n}-{i}',title_ko=f'버스트 예고 {n}-{i}',channel_key=member,scheduled_start=stamp,announced_start=stamp,state='upcoming',expires_at='2030-01-01T00:00:00Z')
    src.append(it)
   if src:src[0]=dict(src[0],state='live',actual_start=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-600)),channel_key='nonoka')
  elif key=='notices':
   src=data['notices']
   for i in range(40):
    it=copy.deepcopy(src[i%len(src)]);it.update(id=f'nt_burst_{n}_{i}',title_ko=f'버스트 소식 {n}-{i}',title=f'버스트 소식 {n}-{i}',title_slug=f'burst-{n}-{i}',expires_at='2030-01-01T00:00:00Z');src.insert(0,it)
  elif key=='tweets':
   for member,rows in data['tweets'].items():
    for i in range(12):
     it=copy.deepcopy(rows[i%len(rows)]) if rows else {'channel_key':member}
     it.update(id=f'9{n:04d}{i:04d}',posted_at=time.strftime('%Y-%m-%dT%H:%M:%SZ'),expires_at='2030-01-01T00:00:00Z');rows.insert(0,it)
  elif key=='banners':
   src=data['banners']
   for i in range(3):
    if src:it=copy.deepcopy(src[0]);it['id']=f'bn_burst_{n}_{i}';src.append(it)
  return data
 def route(self,r):
  u=r.request.url;key=u.rsplit('/',1)[-1].split('.')[0].split('?')[0];self.hits[key]=self.hits.get(key,0)+1
  if self.mode=='503':return r.fulfill(status=503,body='upstream')
  if self.mode=='hang':return None                       # 답하지 않는다 → api.js 가 8초 뒤 끊는다
  if self.mode=='badjson':return r.fulfill(content_type='application/json',body='{"items":[')
  if self.mode=='empty':return r.fulfill(content_type='application/json',body='{}')
  data=self.body(key)
  if data is None:return r.fulfill(status=404,body='')
  r.fulfill(content_type='application/json',body=json.dumps(data,ensure_ascii=False))

PROBE="""
window.__m={gaps:[],long:[],audio:[],marks:[],cue:0};
let last=performance.now();(function t(){const n=performance.now();__m.gaps.push([n,n-last]);last=n;requestAnimationFrame(t)})();
new PerformanceObserver(l=>{for(const e of l.getEntries())__m.long.push([e.startTime,e.duration])}).observe({entryTypes:['longtask']});
setInterval(()=>{const a=window.__birthday?.audio;if(a)__m.audio.push([performance.now(),a.audio.currentTime,a.index,a.paused]);if(document.querySelector('.bday-story.is-visible'))__m.cue++},500);
"""
def scene_route(feed,page):
 def route(r):
  u=r.request.url
  if '/data/' in u:return feed.route(r)
  if u.endswith('/js/config.js'):
   return r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/config.js').read_text(encoding='utf8').replace('POLL_MS = 75000',f'POLL_MS = {POLL}'))
  if u.split('?')[0].endswith('/birthdayui.js'):
   return r.fulfill(content_type='text/javascript',body=(ROOT/'src/frontend/js/birthdayui.js').read_text(encoding='utf8')+';window.__birthday={get scene(){return ctrl},get audio(){return music},teardown};')
  r.continue_()
 page.route('**/*',route)

def summarize(m,t0,t1,polls):
 g=sorted(x[1] for x in m['gaps'] if t0<=x[0]<t1);long=[x[1] for x in m['long'] if t0<=x[0]<t1];a=[x for x in m['audio'] if t0<=x[0]<t1]
 drift=0
 for p,q in zip(a,a[1:]):
  if p[2]==q[2] and not p[3] and not q[3]:drift=max(drift,abs((q[1]-p[1])-(q[0]-p[0])/1000))
 return {'polls':polls,'fps':round(len(g)/max(.001,(t1-t0)/1000)),'gap_max':round(g[-1]) if g else None,'long_n':len(long),'long_max':round(max(long)) if long else 0,'audio_drift_s':round(drift,2),'paused':any(x[3] for x in a)}

def run(browser,tag,ctx_opts,unlocked):
 feed=Feed();context=browser.new_context(**ctx_opts)
 context.add_init_script(("localStorage.setItem('bday-yuno-controls-unlocked-v1','1');" if unlocked else '')+PROBE)
 page=context.new_page();errors=[];console=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:console.append(m.text) if m.type=='error' and 'Failed to load' not in m.text and 'favicon' not in m.text else None)
 scene_route(feed,page)
 page.goto(URL+'?bday=yuno',wait_until='commit')
 page.wait_for_function('window.__birthday?.scene && __birthday.audio');page.wait_for_selector('[data-bday-revealed]',state='attached',timeout=40000)
 rows={}
 phases=[('평상','normal',4),('버스트','burst',6),('503','503',2),('응답 없음','hang',4),('깨진 JSON','badjson',2),('빈 데이터','empty',2),('복구','normal',2)]
 if POLL>=60000:phases=[('평상','normal',1),('버스트','burst',2),('503','503',1),('복구','normal',1)]
 bad=[]
 for name,mode,polls in phases:
  feed.mode=mode;before=dict(feed.hits);t0=page.evaluate('performance.now()');page.wait_for_timeout(polls*POLL)
  t1=page.evaluate('performance.now()');m=page.evaluate('__m');row=summarize(m,t0,t1,sum(feed.hits.values())-sum(before.values()))
  row['nodes']=page.evaluate("document.getElementsByTagName('*').length");rows[name]=row;print(tag,name,row,flush=True)
  if name=='버스트':
   page.screenshot(path=str(OUT/f'{tag}-full-burst.png'))
   top=page.evaluate('''()=>[[.5,.2],[.2,.5],[.8,.5],[.5,.6]].map(([x,y])=>{const e=document.elementFromPoint(innerWidth*x,innerHeight*y);return e?.closest('#notice,#board,#player-dock,#player-frame,#foot,#pager-dots')?.id||''})''')
   if any(top):bad.append(f'온전히 보기 위로 메인 화면이 올라옴 {top}')
 if rows['복구']['paused']:bad.append('복구 뒤 음악이 멈춤')
 m=page.evaluate('__m')
 if not unlocked and m['cue']==0:bad.append('대사가 한 번도 안 나옴')
 # 온전히 보기를 닫고 메인 화면 확인
 feed.mode='burst';page.wait_for_timeout(POLL+500);feed.mode='normal'
 page.keyboard.press('Escape');page.wait_for_timeout(1400);page.screenshot(path=str(OUT/f'{tag}-main-after.png'))
 state=page.evaluate('''()=>({full:document.documentElement.hasAttribute('data-bday-full'),inert:[...document.querySelectorAll('[inert]')].map(e=>e.id).filter(Boolean),board:document.querySelector('#board').children.length,boardText:document.querySelector('#board').innerText.length,notice:document.querySelector('#notice').innerText.length,foot:document.querySelector('#foot').innerText.slice(0,70),audio:window.__birthday.audio.paused})''')
 print(tag,'메인',state,flush=True)
 if state['full'] or state['inert']:bad.append(f'메인 화면이 잠긴 채 남음 {state}')
 if not state['board'] or not state['boardText']:bad.append(f'보드가 비어 있음 {state}')
 if state['audio']:bad.append('메인 화면에서 음악이 멈춤')
 # 유메미타 플레이어 우선권
 prio=page.evaluate('''async()=>{const m=await import('./js/musicpriority.js');const a=window.__birthday.audio;m.setMainMusicActive(true);await new Promise(r=>setTimeout(r,300));const paused=a.paused;await a.play().catch(()=>{});await new Promise(r=>setTimeout(r,300));const blocked=a.paused;m.setMainMusicActive(false);return {paused,blocked}}''')
 print(tag,'플레이어 우선권',prio,flush=True)
 if not prio['paused'] or not prio['blocked']:bad.append(f'유메미타 재생 때 생일 음악이 안 멈춤 {prio}')
 if errors:bad.append(f'페이지 오류 {errors[:3]}')
 if console:bad.append(f'콘솔 오류 {console[:3]}')
 context.close();return rows,bad

def run_plain(browser,tag,now_iso,expect_birthday):
 feed=Feed();context=browser.new_context(viewport={'width':1280,'height':800})
 context.add_init_script(f"const n=Date.parse('{now_iso}'),s=Date.now();Date.now=()=>n+(performance.now());")
 page=context.new_page();errors=[];reqs=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda q:reqs.append(q.url))
 scene_route(feed,page)
 page.goto(URL,wait_until='commit');page.wait_for_selector('#board *',timeout=20000,state='attached')
 feed.mode='burst';page.wait_for_timeout(POLL*3);feed.mode='503';page.wait_for_timeout(POLL*2);feed.mode='normal';page.wait_for_timeout(POLL*2)
 page.screenshot(path=str(OUT/f'{tag}.png'))
 bday=[u for u in reqs if '/js/bday' in u or '/birthday/' in u or 'bdayplayer' in u]
 st=page.evaluate("()=>({board:document.querySelector('#board').children.length,notice:document.querySelector('#notice').innerText.length,skin:!!document.querySelector('#bday-bg')})")
 print(tag,st,'생일 파일 요청',len(bday),flush=True)
 bad=[]
 if not expect_birthday and (bday or st['skin']):bad.append(f'평소 날에 생일 파일을 받음 {bday[:3]}')
 if expect_birthday and not st['skin']:bad.append('생일 당일 장면이 안 뜸')
 if not st['board']:bad.append('보드가 비어 있음')
 if errors:bad.append(f'페이지 오류 {errors[:3]}')
 context.close();return bad

failed=[]
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=False,args=['--autoplay-policy=no-user-gesture-required'])
 print('폴링',POLL,'ms · 운영 데이터 예고',len(BASE['preview']['items']),'소식',len(BASE['notices']['notices']))
 if POLL<60000:
  failed+=run_plain(browser,'평소날',"2026-11-02T03:00:00Z",False)
  failed+=run_plain(browser,'생일당일',"2026-11-04T03:00:00Z",True)
 targets=[('PC첫방문',{'viewport':{'width':1440,'height':900}},False),('PC해금',{'viewport':{'width':944,'height':889}},True),('모바일',{'viewport':{'width':390,'height':844},'device_scale_factor':3,'is_mobile':True,'has_touch':True},True)]
 if POLL>=60000:targets=targets[1:2]
 for tag,opts,unlocked in targets:
  rows,bad=run(browser,tag,opts,unlocked);failed+=[f'{tag}: {x}' for x in bad]
  (OUT/f'{tag}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf8')
 browser.close()
server.shutdown()
print('실패' if failed else 'OK',failed,OUT)
sys.exit(1 if failed else 0)
