const fs=require('fs'),path=require('path'),cp=require('child_process'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.join(root,'qa','shots16');fs.mkdirSync(out,{recursive:true});fs.mkdirSync(path.join(out,'gif_frames'),{recursive:true});
 const html=fs.readFileSync(path.join(root,'birthday_bg_v13.html'),'utf8'),old=fs.readFileSync(path.join(root,'birthday_bg_v12.html'),'utf8');
 new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
 const getRigs=h=>JSON.parse(h.match(/const RASTER_RIGS=(.*?);\n/)[1]);
 const section=(h,name)=>{const a=h.indexOf('function '+name+'('),b=h.indexOf('\nfunction ',a+1);return h.slice(a,b<0?h.length:b)};
 const floor=h=>{const a=h.indexOf('floorLines.forEach',h.indexOf('function frame('));return h.slice(a,h.indexOf(' if(parts.length)',a))};
 const report={bytes:Buffer.byteLength(html),within12MB:Buffer.byteLength(html)<12000000,allRasterRigsUnchanged:JSON.stringify(getRigs(html))===JSON.stringify(getRigs(old)),otherScenesUnchanged:['araleScene','ritsuScene','miyakoScene','nonokaScene'].every(n=>section(html,n)===section(old,n)),floorDriftCodeUnchanged:floor(html)===floor(old),preserved:Object.entries(JSON.parse(fs.readFileSync(path.join(__dirname,'round15_preserved.json')))).every(([f,h])=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')===h),disclaimer:html.includes('비공식 팬 제작 · AI 생성 일러스트 · 공식과 무관')};
 assert(report.within12MB&&report.allRasterRigsUnchanged&&report.otherScenesUnchanged&&report.floorDriftCodeUnchanged&&report.preserved&&report.disclaimer);
 cp.spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--remote-debugging-port=9246','--user-data-dir='+path.join(process.env.TEMP,'birthday-v16-check'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1400);
 const tabs=await(await fetch('http://127.0.0.1:9246/json')).json(),ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let id=0;const jobs=new Map(),errors=[],requests=[];
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=jobs.get(m.id);jobs.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url)};
 const send=(method,params={})=>new Promise((resolve,reject)=>{jobs.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw r.exceptionDetails;return r.result.value};
 const shot=async(name,clip)=>{const r=await send('Page.captureScreenshot',{format:'png',...(clip?{clip,captureBeyondViewport:true}:{})});fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(r.data,'base64'))};
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.__BIRTHDAY_QA__=true;window.__frames=0;const rr=requestAnimationFrame;window.requestAnimationFrame=function(cb){return rr.call(window,t=>{window.__frames++;cb(t)})}'});
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'file:///'+path.join(root,'birthday_bg_v13.html').replaceAll('\\','/')});await wait(300);await send('Page.bringToFront');
 report.scenes=[];
 for(let i=0;i<5;i++){
  await ev('document.querySelectorAll("[role=tab]")['+i+'].click()');await wait(150);
  report.scenes.push(await ev('({name:document.querySelector("#memberName").textContent,loaded:Array.from(document.querySelectorAll(".raster-rig img")).every(e=>e.complete&&e.naturalWidth>0)})'));
 }
 await ev('document.querySelector("#tab-yuno").click()');await wait(200);await ev('document.querySelector("#pause").click()');await wait(50);
 const oldJs=fs.readFileSync(path.join(__dirname,'round15.js'),'utf8'),newJs=fs.readFileSync(path.join(__dirname,'round16.js'),'utf8');
 const pose=src=>{const ctx={window:{}};vm.createContext(ctx);vm.runInContext(src,ctx);return t=>vm.runInContext('djPose15('+t+')',ctx)};
 const before=pose(oldJs),after=pose(newJs);let maxError=0;
 for(let i=0;i<=1920;i++){const a=before((i+.123)/60),b=after((i+.123)/60*1.2);for(const key of ['left','right','knob','nod','bounce','tail','leftRecord','rightRecord','energy','mic','ear'])maxError=Math.max(maxError,Math.abs(a[key]-b[key]));}
 report.tempoComparison={oldBpm:120,newBpm:100,scale:1.2,oldBeatSeconds:.5,newBeatSeconds:.6,oldBarSeconds:2,newBarSeconds:2.4,oldScratchRoundTrip:.25,newScratchRoundTrip:.3,oldDirectionInterval:.125,newDirectionInterval:.15,oldBurstRest:.5,newBurstRest:.6,oldEightBars:16,newEightBars:19.2,oldSixteenBars:32,newSixteenBars:38.4,oldRightRecordDegreesPerSecond:45,newRightRecordDegreesPerSecond:37.5,maxPhaseMatchedError:maxError};assert(maxError<1e-8);
 report.bpm=await ev('window.__birthdayDj15.bpm');assert(report.bpm===100);
 const clip=await ev('(()=>{const m=document.querySelector("#scene").getScreenCTM(),a=new DOMPoint(465,220).matrixTransform(m),b=new DOMPoint(885,650).matrixTransform(m);return {x:a.x,y:a.y,width:b.x-a.x,height:b.y-a.y,scale:2}})()');
 const times=[0,.0625,.1875,.5625,.6875,1.0625,1.1875,1.5625,1.6875,1.9375].map(t=>t*1.2);report.frames=[];
 for(let i=0;i<times.length;i++){
  const q=await ev('window.__birthdayDj15.seek('+times[i]+')');
  const joints=await ev('Array.from(document.querySelectorAll(".rig-yuno .rig-arm8_l,.rig-yuno .rig-arm8_r")).map(e=>({part:e.className,origin:getComputedStyle(e).transformOrigin,matrix:getComputedStyle(e).transform}))');
  report.frames.push({...q,joints});await shot('yuno_t'+i,clip);
 }
 await ev('window.__birthdayDj15.seek(0)');await shot('yuno_scene');
 report.variations=[];
 for(const [name,t] of [['cue_depart',15.1],['cue_contact',15.4],['cue_return',15.7],['bar16_pattern',30.5625]]){
  report.variations.push({name,...await ev('window.__birthdayDj15.seek('+(t*1.2)+')')});await shot(name,clip);
 }
 report.contactSweep=await ev(`(()=>{
  const r={samples:0,leftOnRecord:true,rightOnMixer:true,cueOnRightRecord:true,travelOnDeck:true,maxScratchAngle:0,maxLeftRecordOffset:0,recordHandError:0,patterns:[]};
  for(const start of [0,14,30])for(let i=0;i<=400;i++){
   const q=window.__birthdayDj15.sample((start+i/200)*1.2),l=q.leftContact.scene,v=q.rightContact.scene;r.samples++;
   r.leftOnRecord&&=((l[0]-584)/61)**2+((l[1]-542)/16)**2<=1;
   if(q.mode==='right-record')r.cueOnRightRecord&&=((v[0]-766)/61)**2+((v[1]-542)/16)**2<=1;
   else if(q.mode==='travel'){const yy=(v[1]-522)/40;r.travelOnDeck&&=yy>=0&&yy<=1&&v[0]>=497-18*yy&&v[0]<=830+37*yy;}
   else r.rightOnMixer&&=v[0]>=650&&v[0]<=699&&v[1]>=524&&v[1]<=550;
   r.maxScratchAngle=Math.max(r.maxScratchAngle,Math.abs(q.left));r.maxLeftRecordOffset=Math.max(r.maxLeftRecordOffset,Math.abs(q.leftRecord-q.leftCoast));r.recordHandError=Math.max(r.recordHandError,Math.abs(q.leftRecord-q.leftCoast-26*q.left/5.5));if(!r.patterns.includes(q.pattern))r.patterns.push(q.pattern);
  }return r;
 })()`);
 assert(report.contactSweep.leftOnRecord&&report.contactSweep.rightOnMixer&&report.contactSweep.cueOnRightRecord&&report.contactSweep.travelOnDeck&&report.contactSweep.recordHandError<1e-9);
 assert(report.frames[1].left>5&&report.frames[2].left< -5&&report.frames[1].leftRecord>20&&report.frames[2].leftRecord< -20);
 assert(report.frames.every(f=>f.joints.length===2&&f.joints.every(j=>j.matrix.split(',').slice(4).every(v=>Math.abs(parseFloat(v))<1e-6))));
 const animationClip={...clip,scale:1};
 for(let i=0;i<50;i++){await ev('window.__birthdayDj15.seek('+(i*.048)+')');await shot('gif_frames/frame_'+String(i).padStart(3,'0'),animationClip)}
 report.gifFrames=50;
 // Runtime clock must stop, then resume without incorporating the paused interval.
 await ev('document.querySelector("#tab-yuno").click();document.querySelector("#pause").click()');await wait(230);
 await ev('document.querySelector("#pause").click()');const paused=await ev('window.__birthdayDj15.now()');await wait(220);
 report.pauseClockStopped=(await ev('window.__birthdayDj15.now()'))===paused;
 await ev('document.querySelector("#pause").click()');await wait(140);const resumed=await ev('window.__birthdayDj15.now()');report.resumeAdvance=resumed-paused;
 assert(report.pauseClockStopped&&report.resumeAdvance>=0&&report.resumeAdvance<.22);
 await ev('Object.defineProperty(document,"hidden",{configurable:true,get:()=>true});document.dispatchEvent(new Event("visibilitychange"))');const hidden=await ev('window.__birthdayDj15.now()');await wait(160);
 report.hiddenClockStopped=(await ev('window.__birthdayDj15.now()'))===hidden;
 await ev('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))');
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});const reduced=await ev('window.__birthdayDj15.now()');await wait(160);
 report.reducedClockStopped=(await ev('window.__birthdayDj15.now()'))===reduced;
 report.reducedAnimatedCount=await ev('Array.from(document.querySelectorAll("#scene *")).filter(e=>getComputedStyle(e).animationName!=="none").length');
 assert(report.hiddenClockStopped&&report.reducedClockStopped&&report.reducedAnimatedCount===0);
 report.runtimeErrors=errors;report.externalNetworkRequests=requests.filter(u=>/^https?:/.test(u));
 assert(report.runtimeErrors.length===0&&report.externalNetworkRequests.length===0&&report.scenes.every(s=>s.loaded));
 fs.writeFileSync(path.join(__dirname,'validation_v13.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({bytes:report.bytes,rigsUnchanged:report.allRasterRigsUnchanged,scenesUnchanged:report.otherScenesUnchanged,contactSweep:report.contactSweep,pause:report.pauseClockStopped,resumeAdvance:report.resumeAdvance,hidden:report.hiddenClockStopped,reduced:report.reducedClockStopped,errors:report.runtimeErrors.length,externalRequests:report.externalNetworkRequests.length},null,2));
 await send('Browser.close');ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
