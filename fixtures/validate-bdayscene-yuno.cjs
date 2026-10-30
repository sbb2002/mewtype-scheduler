const fs=require('fs'),path=require('path'),cp=require('child_process'),assert=require('assert');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.join(__dirname,'bdayscene-yuno-shots');fs.mkdirSync(out,{recursive:true});
 const server=cp.spawn('python',['-m','http.server','8876','--bind','127.0.0.1'],{cwd:root,windowsHide:true,stdio:'ignore'});
 let ws,send,chrome;
 try {
 chrome=cp.spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--remote-debugging-port=9251','--user-data-dir='+path.join(process.env.TEMP,'birthday-module20'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 await wait(1500);
 const tabs=await(await fetch('http://127.0.0.1:9251/json')).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let id=0;const jobs=new Map(),errors=[],requests=[],bad=[];
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const j=jobs.get(m.id);jobs.delete(m.id);m.error?j.reject(m.error):j.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errors.push(m.params.entry);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url);if(m.method==='Network.responseReceived'&&m.params.response.status>=400)bad.push(m.params.response.url)};
 send=(method,params={})=>new Promise((resolve,reject)=>{jobs.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw r.exceptionDetails;return r.result.value};
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Log.enable');
 await send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__activeFrames=new Set;const rr=requestAnimationFrame,cc=cancelAnimationFrame;window.requestAnimationFrame=cb=>{let id=rr(t=>{__activeFrames.delete(id);cb(t)});__activeFrames.add(id);return id};window.cancelAnimationFrame=id=>{__activeFrames.delete(id);cc(id)};window.__observers=0;for(const k of ['ResizeObserver','IntersectionObserver']){const Base=window[k];window[k]=class extends Base{constructor(cb){super(cb);this.live=true;__observers++}disconnect(){if(this.live){__observers--;this.live=false}super.disconnect()}}}`});
 await send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__sceneListeners=new Set;const aa=EventTarget.prototype.addEventListener,dd=EventTarget.prototype.removeEventListener;EventTarget.prototype.addEventListener=function(type,fn,...args){if(['resize','visibilitychange','change'].includes(type))__sceneListeners.add(fn);return aa.call(this,type,fn,...args)};EventTarget.prototype.removeEventListener=function(type,fn,...args){if(['resize','visibilitychange','change'].includes(type))__sceneListeners.delete(fn);return dd.call(this,type,fn,...args)}`});
 const report={views:[]};
 for(const [name,width,height] of [['pc',1440,900],['tablet',768,1024],['mobile390',390,844],['mobile360',360,740]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  await send('Page.navigate',{url:'http://127.0.0.1:8876/fixtures/bdayscene-yuno.html'});await wait(300);await ev('window.ready');await wait(200);
  assert(await ev('document.querySelectorAll(".bdayscene").length===1&&document.querySelectorAll(".bdayscene img").length===9&&[...document.querySelectorAll(".bdayscene img")].every(i=>i.complete&&i.naturalWidth>0)'));
  const geometry=await ev(`(()=>{const root=document.querySelector('.bdayscene'),head=root.querySelector('.rig-head').getBoundingClientRect(),left=root.querySelector('.rig-arm8_l').getBoundingClientRect(),right=root.querySelector('.rig-arm8_r').getBoundingClientRect();return {viewBox:root.querySelector('svg').getAttribute('viewBox'),head:{x:head.x,y:head.y,width:head.width,height:head.height},hands:[left,right].map(r=>({x:r.x,y:r.y,width:r.width,height:r.height})),frames:__activeFrames.size}})()`);
  report.views.push({name,width,height,...geometry});
  await ev('scene.setStill(true)');const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(shot.data,'base64'));
 }
 // Rendered poses must exactly match approved pure calculations at the live record clock.
 await ev('scene.setStill(false)');await wait(250);
 report.motion=await ev(`(async()=>{const {yunoPose,spectrum}=await import('/src/frontend/js/bdaybeat.js');const rows=[];return await new Promise(resolve=>{function sample(){const root=document.querySelector('.bdayscene'),r=root.querySelector('[data-dj-record="right"]').getAttribute('transform'),t=+r.match(/rotate\\(([^)]*)/)[1]/37.5,q=yunoPose(t),m=new DOMMatrix(getComputedStyle(root.querySelector('.rig-head')).transform),l=new DOMMatrix(getComputedStyle(root.querySelector('.rig-arm8_l')).transform);rows.push({t,headError:Math.abs(m.m42-q.headY),armError:Math.abs(Math.atan2(l.m12,l.m11)*180/Math.PI-q.left),eqError:Math.abs(+root.querySelector('.equalizer').getAttribute('height')-spectrum(t,0,40).height)});if(rows.length>=150)resolve(rows);else requestAnimationFrame(sample)}requestAnimationFrame(sample)})})()`);
 assert(report.motion.every(r=>r.headError<.001&&r.armError<.001&&r.eqError<.01));
 const clock=()=>ev('document.querySelector("[data-dj-record=right]").getAttribute("transform")');
 await ev('scene.setStill(true)');const paused=await clock();await wait(250);report.still=paused===await clock();
 report.cssPaused=await ev('[...document.querySelector(".bdayscene").getAnimations({subtree:true})].every(a=>a.playState==="paused")');
 assert(report.still&&report.cssPaused&&await ev('__activeFrames.size===0'));
 await ev('scene.setStill(false)');await wait(140);report.resume=paused!==await clock();assert(report.resume);
 await ev('scene.celebrate()');await wait(350);report.celebrate=await ev('document.querySelector(".bdayscene canvas").getContext("2d").getImageData(0,0,document.querySelector(".bdayscene canvas").width,document.querySelector(".bdayscene canvas").height).data.some(v=>v>0)');assert(report.celebrate);
 await ev('scene.setStill(true)');report.particlesCleared=await ev('!document.querySelector(".bdayscene canvas").getContext("2d").getImageData(0,0,document.querySelector(".bdayscene canvas").width,document.querySelector(".bdayscene canvas").height).data.some(v=>v>0)');assert(report.particlesCleared);await ev('scene.setStill(false)');
 await ev('document.querySelector("#scene-host").style.transform="translateY(200vh)"');await wait(180);report.offscreenStopped=await ev('__activeFrames.size===0');assert(report.offscreenStopped);await ev('document.querySelector("#scene-host").style.transform=""');await wait(100);
 await ev('Object.defineProperty(document,"hidden",{configurable:true,get:()=>true});document.dispatchEvent(new Event("visibilitychange"))');const hidden=await clock();await wait(180);report.hidden=hidden===await clock();assert(report.hidden&&await ev('__activeFrames.size===0'));
 await ev('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))');
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});const reduced=await clock();await wait(150);report.reduced=reduced===await clock();assert(report.reduced&&await ev('__activeFrames.size===0'));
 await ev('scene.destroy();scene.destroy()');await wait(100);report.destroy=await ev('({roots:document.querySelectorAll(".bdayscene").length,frames:__activeFrames.size,observers:__observers,listeners:__sceneListeners.size})');assert.deepEqual(report.destroy,{roots:0,frames:0,observers:0,listeners:0});
 // Reduced motion from first mount and repeated instances / private gradient IDs.
 await ev('(async()=>{window.a=mountYunoScene(document.querySelector("#scene-host"));window.b=mountYunoScene(document.querySelector("#scene-host"));await Promise.all([a.whenReady,b.whenReady])})()');await wait(100);
 report.multiple=await ev('({uniqueIds:new Set([...document.querySelectorAll(".bdayscene [id]")].map(e=>e.id)).size===document.querySelectorAll(".bdayscene [id]").length,frames:__activeFrames.size})');assert(report.multiple.uniqueIds&&report.multiple.frames===0);
 await ev('a.destroy();b.destroy()');
 report.imageFailure=await ev('(async()=>{const original=HTMLImageElement.prototype.decode;HTMLImageElement.prototype.decode=function(){return Promise.reject(new Error("simulated decode failure"))};const c=mountYunoScene(document.querySelector("#scene-host"));await c.whenReady;const fallback=[...document.querySelectorAll(".bdayscene foreignObject")].every(e=>e.style.display==="none")&&document.querySelectorAll(".equalizer").length===40;c.destroy();HTMLImageElement.prototype.decode=original;return fallback})()');assert(report.imageFailure);
 report.errors=errors;report.failedResponses=bad;report.externalRequests=requests.filter(u=>/^https?:/.test(u)&&!u.startsWith('http://127.0.0.1:8876/'));
 assert(errors.length===0&&bad.length===0&&report.externalRequests.length===0);
 fs.writeFileSync(path.join(out,'validation.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,motion:`${report.motion.length} RAF samples`,views:report.views},null,2));
 } finally {if(send)try{await send('Browser.close')}catch{} ws?.close();server.kill();chrome?.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
