const fs=require('fs'),path=require('path'),cp=require('child_process'),vm=require('vm'),crypto=require('crypto');
(async()=>{
 const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'birthday_bg_v3.html'),'utf8');
 new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
 const report={bytes:Buffer.byteLength(html),within12MB:Buffer.byteLength(html)<12000000,externalSourceAttributes:/(src|href)=["'](?:https?:|refs)/.test(html),oldVectorCharacterRenderer:html.includes('function mascot('),v2Unchanged:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'birthday_bg_v2.html'))).digest('hex')===fs.readFileSync(path.join(__dirname,'v2_preserved.sha256'),'utf8').trim()};
 cp.spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--disable-gpu-sandbox','--remote-debugging-port=9231','--user-data-dir='+path.join(process.env.TEMP,'birthday-v5-check'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1400);
 const ts=await(await fetch('http://127.0.0.1:9231/json')).json(),ws=new WebSocket(ts.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>ws.onopen=r);let id=0;const jobs=new Map(),errors=[],requests=[];
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=jobs.get(m.id);jobs.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url)};
 const send=(method,params={})=>new Promise((resolve,reject)=>{jobs.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw r.exceptionDetails;return r.result.value};
 const shot=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(__dirname,name+'.png'),Buffer.from(r.data,'base64'))};
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.__frames=0;const r=requestAnimationFrame;window.requestAnimationFrame=function(cb){return r.call(window,t=>{window.__frames++;cb(t)})}'});
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'file:///'+path.join(root,'birthday_bg_v3.html').replaceAll('\\','/')});await wait(250);await send('Page.bringToFront');
 report.scenes=[];
 for(let i=0;i<5;i++){
  await ev('document.querySelectorAll("[role=tab]")['+i+'].click()');await wait(60);
  report.scenes.push(await ev('({name:document.querySelector("#memberName").textContent,characters:Array.from(document.querySelectorAll(".raster-character")).map(e=>e.dataset.character),loaded:Array.from(document.querySelectorAll(".raster-rig img")).every(i=>i.complete&&i.naturalWidth>0),imageCount:document.querySelectorAll(".raster-rig img").length,allImagesDataURI:Array.from(document.querySelectorAll(".raster-rig img")).every(i=>i.getAttribute("src").startsWith("data:image/webp;base64,"))})'));
 }
 await ev('document.querySelector("#tab-arale").click()');
 const t1=await ev('getComputedStyle(document.querySelector(".rig-head")).transform');await wait(220);
 report.headReallyMoves=await ev('getComputedStyle(document.querySelector(".rig-head")).transform!=='+JSON.stringify(t1));
 await ev('document.querySelectorAll(".rig-open,.rig-closed").forEach(e=>e.getAnimations().forEach(a=>{a.pause();a.currentTime=3458}));document.querySelectorAll(".rig-ear-l,.rig-ear-r").forEach(e=>e.getAnimations().forEach(a=>{a.pause();a.currentTime=4050}))');
 report.generatedBlinkFrame=await ev('({open:getComputedStyle(document.querySelector(".rig-open")).opacity,closed:getComputedStyle(document.querySelector(".rig-closed")).opacity,earTransform:getComputedStyle(document.querySelector(".rig-ear-l")).transform})');
 await shot('arale_motion_check');
 await ev('document.querySelector("#tab-miyako").click()');
 report.maruPresent=await ev('!!document.querySelector("[data-character=maru] .raster-rig img")');await shot('miyako_marukun_scene');
 await send('Page.bringToFront');await ev('document.querySelector("#tab-arale").click();document.querySelector("#tab-arale").focus()');
 await send('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,nativeVirtualKeyCode:39});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,nativeVirtualKeyCode:39});await wait(30);report.keyboardSelected=await ev('document.querySelector("#memberName").textContent');
 await ev('document.querySelector("#tab-ritsu").click()');report.cometDuration=await ev('getComputedStyle(document.querySelector(".meteor")).animationDuration');
 await ev('document.querySelector("#burst").click()');await wait(80);
 const hasPixels='(function(){var c=document.querySelector("canvas"),d=c.getContext("2d").getImageData(0,0,c.width,c.height).data;return d.some((v,i)=>i%4===3&&v>0)})()';
 report.fireworksVisible=await ev(hasPixels);await wait(2800);report.fireworksCleared=!(await ev(hasPixels));
 await ev('document.querySelector("#pause").click()');let n=await ev('window.__frames');await wait(120);
 report.pause=await ev('({rafStopped:window.__frames==='+n+',cssPaused:getComputedStyle(document.querySelector(".raster-rig")).animationPlayState,burstDisabled:document.querySelector("#burst").disabled})');
 await ev('document.querySelector("#background").click()');report.backgroundOff=await ev('getComputedStyle(document.querySelector(".art")).visibility');
 await ev('document.querySelector("#background").click();document.querySelector("#pause").click();Object.defineProperty(document,"hidden",{configurable:true,get:()=>true});document.dispatchEvent(new Event("visibilitychange"))');n=await ev('window.__frames');await wait(100);report.syntheticHiddenStopsRAF=await ev('window.__frames==='+n);await ev('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))');
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await send('Page.captureScreenshot',{format:'png'});await wait(60);
 report.reducedMotion=await ev('({disabled:document.querySelector("#pause").disabled,animatedCount:Array.from(document.querySelectorAll("#scene *")).filter(e=>getComputedStyle(e).animationName!=="none").length,open:getComputedStyle(document.querySelector(".rig-open")).opacity,closed:getComputedStyle(document.querySelector(".rig-closed")).opacity})');
 report.responsive=[];
 for(const width of [320,375,414,768]){await send('Emulation.setDeviceMetricsOverride',{width,height:960,deviceScaleFactor:1,mobile:false});await wait(40);report.responsive.push({width,overflow:await ev('document.documentElement.scrollWidth>innerWidth')});}
 report.runtimeErrors=errors.length;report.externalNetworkRequests=requests.filter(u=>/^https?:/.test(u));
 fs.writeFileSync(path.join(__dirname,'validation.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 await send('Browser.close');ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
