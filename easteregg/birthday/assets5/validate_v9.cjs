const fs=require('fs'),path=require('path'),cp=require('child_process'),vm=require('vm'),crypto=require('crypto');
(async()=>{
 const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'birthday_bg_v9.html'),'utf8');
 new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
 const report={bytes:Buffer.byteLength(html),within12MB:Buffer.byteLength(html)<12000000,externalSourceAttributes:/(src|href)=["'](?:https?:|refs)/.test(html),oldVectorCharacterRenderer:html.includes('function mascot('),v2Unchanged:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'birthday_bg_v2.html'))).digest('hex')===fs.readFileSync(path.join(__dirname,'v2_preserved.sha256'),'utf8').trim()};
 cp.spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-sandbox','--disable-gpu','--disable-gpu-sandbox','--remote-debugging-port=9242','--user-data-dir='+path.join(process.env.TEMP,'birthday-v12-check'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1400);
 const ts=await(await fetch('http://127.0.0.1:9242/json')).json(),ws=new WebSocket(ts.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>ws.onopen=r);let id=0;const jobs=new Map(),errors=[],requests=[];
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=jobs.get(m.id);jobs.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url)};
 const send=(method,params={})=>new Promise((resolve,reject)=>{jobs.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw r.exceptionDetails;return r.result.value};
 const shot=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(root,'qa','shots12',name+'.png'),Buffer.from(r.data,'base64'))};
 await send('Runtime.enable');await send('Network.enable');await send('Page.enable');
 await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.__frames=0;const r=requestAnimationFrame;window.requestAnimationFrame=function(cb){return r.call(window,t=>{window.__frames++;cb(t)})}'});
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'file:///'+path.join(root,'birthday_bg_v9.html').replaceAll('\\','/')});await wait(250);await send('Page.bringToFront');
 fs.mkdirSync(path.join(root,'qa','shots12'),{recursive:true});report.scenes=[];
 for(let i=0;i<5;i++){
  await ev('document.querySelectorAll("[role=tab]")['+i+'].click()');await wait(60);
  await wait(300);await shot('scene-'+i);report.scenes.push(await ev('({name:document.querySelector("#memberName").textContent,characters:Array.from(document.querySelectorAll(".raster-character")).map(e=>e.dataset.character),loaded:Array.from(document.querySelectorAll(".raster-rig img")).every(i=>i.complete&&i.naturalWidth>0),imageCount:document.querySelectorAll(".raster-rig img").length,allImagesDataURI:Array.from(document.querySelectorAll(".raster-rig img")).every(i=>i.getAttribute("src").startsWith("data:image/webp;base64,"))})'));
 }

 report.miyakoFrames=[];
 await ev('document.querySelector("#tab-miyako").click()');await wait(200);
 await ev('document.querySelectorAll("#scene *").forEach(e=>e.getAnimations().forEach(a=>a.pause()))');
 for(const [state,t] of [['open',0],['closed',3058]]){
  await ev('document.querySelectorAll("#scene *").forEach(e=>e.getAnimations().forEach(a=>a.currentTime='+t+'))');
  const clip=await ev('(()=>{const r=document.querySelector("[data-character=miyako] .rig-head").getBoundingClientRect();return {x:r.x-12,y:r.y-12,width:r.width+24,height:r.height+24,scale:3}})()');
  const capture=await send('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});fs.writeFileSync(path.join(root,'qa','shots12','miyako_'+state+'.png'),Buffer.from(capture.data,'base64'));
  report.miyakoFrames.push({state,t,opacities:await ev('({open:getComputedStyle(document.querySelector("[data-character=miyako] .rig-open")).opacity,closed:getComputedStyle(document.querySelector("[data-character=miyako] .rig-closed")).opacity})')});
 }
 require('assert')(report.miyakoFrames[0].opacities.open==='1'&&report.miyakoFrames[1].opacities.closed==='1');
 await shot('miyako_closed_scene');
 await ev('document.querySelector("#tab-arale").click()');
 await ev('document.querySelector(".arale-trigger").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))');report.araleKeyboardJump=await ev('!!document.querySelector(".arale-jump")');const t1=await ev('getComputedStyle(document.querySelector(".rig-head")).transform');await wait(220);
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
 report.preserved=Object.entries(JSON.parse(fs.readFileSync(path.join(__dirname,'round12_preserved.json')))).every(([f,h])=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')===h);report.runtimeErrors=errors.length;report.externalNetworkRequests=requests.filter(u=>/^https?:/.test(u));
 report.disclaimer=html.includes('비공식 팬 제작 · AI 생성 일러스트 · 공식과 무관');
 const prev=fs.readFileSync(path.join(root,'birthday_bg_v8.html'),'utf8');
 const pattern=/const RASTER_RIGS=(.*?);\n/;const before=JSON.parse(prev.match(pattern)[1]),after=JSON.parse(html.match(pattern)[1]);
 const unchangedNames=['arale','yuno','ritsu','nonoka','maru','duck'];report.otherCharactersUnchanged=unchangedNames.every(n=>JSON.stringify(before[n])===JSON.stringify(after[n]));
 const extraCSS=fs.readFileSync(path.join(__dirname,'round12.css'),'utf8');
 report.otherSceneCodeUnchanged=prev.replace(pattern,'RIG_DATA')===html.replace(extraCSS+'\n','').replace(pattern,'RIG_DATA');
 const originalProof=JSON.parse(fs.readFileSync(path.join(__dirname,'round11_original_hashes.json'),'utf8'));
 report.restoredOriginalFiles=Object.entries(originalProof.files).every(([f,h])=>crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,f))).digest('hex')===h&&crypto.createHash('sha256').update(fs.readFileSync(path.join(originalProof.source,f))).digest('hex')===h);
 report.originalWebPEmbedded=['ritsu','nonoka'].every(n=>['arm_l','arm_r'].every(k=>after[n].urls[k]==='data:image/webp;base64,'+fs.readFileSync(path.join(originalProof.source,n+'_'+k+'.webp')).toString('base64')));
 require('assert')(report.otherCharactersUnchanged&&report.otherSceneCodeUnchanged&&report.restoredOriginalFiles&&report.originalWebPEmbedded);
 fs.writeFileSync(path.join(__dirname,'validation_v9.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 await send('Browser.close');ws.close();
 const assert=require('assert');assert(report.within12MB&&report.preserved);assert(!report.externalSourceAttributes&&report.externalNetworkRequests.length===0&&report.runtimeErrors===0);assert(report.scenes.length===5&&report.scenes.every(s=>s.loaded&&s.allImagesDataURI));assert(report.araleKeyboardJump&&report.fireworksVisible&&report.fireworksCleared);assert(report.pause.rafStopped&&report.pause.cssPaused==='paused'&&report.syntheticHiddenStopsRAF);assert(report.reducedMotion.animatedCount===0&&report.responsive.every(r=>!r.overflow));
})().catch(e=>{console.error(e);process.exit(1)});
