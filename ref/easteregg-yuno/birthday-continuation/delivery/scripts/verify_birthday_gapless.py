from pathlib import Path
import functools,http.server,threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
import os,tempfile
OUT=Path(os.environ.get('BIRTHDAY_VERIFY_OUT',str(Path(tempfile.gettempdir())/'birthday-verify-third')))
OUT.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8111),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
result={}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
 page=b.new_page()
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  if r.request.url.endswith('/bdayaudio.js'):
   s=(ROOT/'src/frontend/js/bdayaudio.js').read_text(encoding='utf8').replace('  return api;','  window.audioTest={get context(){return context},get buffers(){return buffers},get gain(){return gain}};return api;')
   r.fulfill(content_type='text/javascript',body=s)
  elif '/test.html' in r.request.url:r.fulfill(content_type='text/html',body='<body>audio test</body>')
  else:r.continue_()
 page.route('**/*',route);page.goto('http://127.0.0.1:8111/test.html')
 page.evaluate('''async()=>{const m=await import('/src/frontend/js/bdayaudio.js');window.audio=await m.mountBirthdayAudio();await audio.play()}''')
 page.wait_for_function('audio.diagnostics().engine==="buffer"')
 result['initial']=page.evaluate('()=>audio.diagnostics()')
 page.evaluate('''async()=>{
   const ctx=audioTest.context;
   const code=`class Capture extends AudioWorkletProcessor{process(inputs){if(inputs[0]?.[0])this.port.postMessage({frame:currentFrame,data:inputs[0].map(channel=>channel.slice())});return true}}registerProcessor('capture',Capture)`;
   const u=URL.createObjectURL(new Blob([code],{type:'text/javascript'}));await ctx.audioWorklet.addModule(u);URL.revokeObjectURL(u);
   window.capture=new AudioWorkletNode(ctx,'capture');audioTest.gain.connect(capture);capture.connect(ctx.destination);
   window.chunks=[];capture.port.onmessage=e=>chunks.push(e.data);
 }''')
 for turn in range(3):
  page.evaluate('''async()=>{audio.pause();chunks.length=0;await audio.seek(audio.audio.duration-.5);await audio.play();window.scheduled=audio.diagnostics().scheduled}''')
  if turn==2:
   page.wait_for_timeout(200)
   page.evaluate('()=>{const until=performance.now()+1000;while(performance.now()<until){}}')
  else:page.wait_for_timeout(900)
  row=page.evaluate('''()=>{
   const fs=audioTest.context.sampleRate,boundary=scheduled[0].end;
   let count=0,bad=0,sum=0,max=0;const channels=new Set();
   for(const chunk of chunks)for(let ch=0;ch<chunk.data.length;ch++)for(let k=0;k<chunk.data[ch].length;k++){
    channels.add(ch);
    const frame=chunk.frame+k,t=frame/fs;
    if(Math.abs(t-boundary)>.08)continue;
    const r=scheduled.find(r=>frame>=Math.round(r.start*fs)&&frame<Math.round(r.end*fs));if(!r)continue;
    const data=audioTest.buffers[r.i].getChannelData(ch),n=frame-Math.round(r.start*fs)+Math.round(r.offset*fs);
    if(n<0||n>=data.length)continue;
    const error=Math.abs(chunk.data[ch][k]-data[n]*audio.volume);max=Math.max(max,error);sum+=error*error;bad+=error>1e-5;count++;
   }
   return {index:audio.index,channels:[...channels],count,bad,maxError:max,rmsError:Math.sqrt(sum/count),diagnostics:audio.diagnostics()};
  }''')
  assert row['channels']==[0,1],row
  assert row['count']>10000,row
  assert row['bad']==0,row
  assert all(t['gap']==0 for t in row['diagnostics']['transitions']),row
  result[f'boundary-{turn}']=row
 page.evaluate('()=>audio.pause()')
 result['paused']=page.evaluate('()=>audio.diagnostics()')
 assert not result['paused']['scheduled'] and not result['paused']['timer']
 page.evaluate('async()=>{await audio.seek(110.125)}')
 result['seek']=page.evaluate('()=>audio.audio.currentTime');assert result['seek']==110.125
 page.evaluate('async()=>{await Promise.all([audio.next(),audio.previous()]);audio.pause()}')
 result['racing_select']=page.evaluate('()=>({index:audio.index,time:audio.audio.currentTime,d:audio.diagnostics()})')
 page.evaluate('()=>{capture.disconnect();audio.destroy()}')
 result['destroy']=page.evaluate('()=>audio.diagnostics()')
 assert result['destroy']['dead'] and result['destroy']['blobURLs']==0 and not result['destroy']['scheduled'] and not result['destroy']['timer']
 assert not errors,errors
 result['errors']=errors
 b.close()
server.shutdown()
(OUT/'gapless.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
