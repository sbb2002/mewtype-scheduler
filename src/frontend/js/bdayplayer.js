// 생일 음악 컨트롤과 곡 시계 기준 인트로.
import { introBrightness } from './bdaylogic.js';
import { mountBirthdayPlayerDrag } from './bdayplayerdrag.js';
import { mountBirthdayStory } from './bdaystory.js';
import { mountBirthdayReward } from './bdayreward.js';
// 효과 버튼 아이콘(20×20, 선 도형). 이름은 aria-label · title 로 남긴다.
const EFFECTS=[
 ['fireworks','폭죽','M10 2v4M10 14v4M2 10h4M14 10h4M4.3 4.3l2.8 2.8M12.9 12.9l2.8 2.8M15.7 4.3l-2.8 2.8M7.1 12.9l-2.8 2.8'],
 ['pulse','태양 펄스','M10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM5.5 5.5a6.4 6.4 0 0 0 0 9M14.5 5.5a6.4 6.4 0 0 1 0 9M3 3a10 10 0 0 0 0 14M17 3a10 10 0 0 1 0 14'],
 ['ufo','UFO','M6 9a4 4 0 0 1 8 0M2 11.5c0-1.4 3.6-2.5 8-2.5s8 1.1 8 2.5-3.6 2.5-8 2.5-8-1.1-8-2.5zM7 16l-1 2M13 16l1 2'],
 ['sign','별자리 · 사인','M4 5l6 4 6-6M10 9l6 5M3 18q7-3 14 0M3 5a1 1 0 1 0 2 0 1 1 0 0 0-2 0M9 9a1 1 0 1 0 2 0 1 1 0 0 0-2 0M15 3a1 1 0 1 0 2 0 1 1 0 0 0-2 0M15 14a1 1 0 1 0 2 0 1 1 0 0 0-2 0'],
 ['shower','유성우','M17 2l-7 7M11 3L6 8M17 8l-6 6M9 10.5h.01M5 9.5h.01M10 15.5h.01'],
];
const SPEAKER_BODY='M3 7.5v5h3l4.5 3.5V4L6 7.5z',SPEAKER_ON=SPEAKER_BODY+'M13 7.5a3.5 3.5 0 0 1 0 5M15.2 5a7 7 0 0 1 0 10',SPEAKER_OFF=SPEAKER_BODY+'M3 3l14 14';
// 짧게 누름 = tap, 0.5초 이상 눌렀다 뗌 = hold. down 은 누르는 순간(박자에 맞춰야 하는 효과용).
const HOLD_MS=500,HOLD_HELP={fireworks:'폭죽 — 클릭 1발 · 길게 누르면 연속 켜기/끄기',pulse:'태양 펄스 — 클릭 1파 · 누르고 있으면 박마다 파동 · 떼면 다음 박에 큰 펄스',sign:'YMMT 별자리 — 길게 누르면 유노 사인'};
function holdable(b,{down,tap,hold,charge,cancel},signal){
 let timer=0,charged=false,active=false;
 const begin=()=>{if(active||b.disabled)return;active=true;charged=false;b.setAttribute('data-charging','');down?.();timer=setTimeout(()=>{charged=true;b.setAttribute('data-charged','');charge?.()},HOLD_MS)};
 const finish=run=>{if(!active)return;active=false;clearTimeout(timer);b.removeAttribute('data-charging');b.removeAttribute('data-charged');if(run&&!b.disabled)(charged?hold:tap)?.();else if(charged)cancel?.()};
 const on=(type,fn)=>b.addEventListener(type,fn,{signal});
 on('pointerdown',e=>{if(e.button)return;b.setPointerCapture?.(e.pointerId);begin()});on('pointerup',()=>finish(true));on('pointercancel',()=>finish(false));on('lostpointercapture',()=>finish(false));on('blur',()=>finish(false));
 on('keydown',e=>{if(e.key!=='Enter'&&e.key!==' ')return;e.preventDefault();if(!e.repeat)begin()});on('keyup',e=>{if(e.key==='Enter'||e.key===' ')finish(true)});
 on('contextmenu',e=>e.preventDefault());
}
function icon(path){const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),p=document.createElementNS(ns,'path');svg.setAttribute('viewBox','0 0 20 20');svg.setAttribute('aria-hidden','true');p.setAttribute('d',path);svg.append(p);return svg}
export function mountBirthdayPlayer(audio,scene,host,ui,{setFull,reduced}) {
  const events=new AbortController(),signal=events.signal,root=document.documentElement;
  let dead=false,raf=0,idle=0,intro=true,lastIndex=-1,ready=false,starting=false,unsub;
  const el=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls;if(text)n.textContent=text;return n};
  const shell=el('div','bday-music');shell.id='bday-music';
  const bar=el('div','bday-music__bar');bar.setAttribute('role','group');bar.setAttribute('aria-label','생일 음악');
  const title=el('div','bday-music__title'),eq=el('span','bday-eq'),name=el('span','bday-track');
  for(let i=0;i<4;i++)eq.append(el('i',''));title.append(eq,name);
  const disc=el('div','bday-music__disc','듣고 계시는 이 음악은 SUNO로 제작되었습니다.');
  const prompt=el('button','bday-start','탭하여 시작 ♪');prompt.type='button';prompt.setAttribute('aria-label','탭하여 생일 음악 시작');prompt.hidden=true;
  const grip=el('button','bday-grip');grip.type='button';grip.setAttribute('aria-label','음악 플레이바 이동');grip.title='잡고 이동 · 방향키로 이동 · Home으로 원래 위치';
  const dots=el('span','bday-grip__dots');dots.setAttribute('aria-hidden','true');for(let i=0;i<6;i++)dots.append(el('i',''));grip.append(dots);bar.append(grip);
  function button(cls,label,text,fn){const b=el('button','bday-ib '+cls,text);b.type='button';b.setAttribute('aria-label',label);b.addEventListener('click',e=>{e.stopPropagation();if(!reduced()){const r=el('span','bday-ripple');b.append(r);r.addEventListener('animationend',()=>r.remove(),{once:true})}if(navigator.vibrate)navigator.vibrate(10);Promise.resolve(fn()).catch(()=>{prompt.hidden=false})},{signal});bar.append(b);return b}
  const prev=button('prev','이전 곡','◀│',()=>audio.previous());
  const pp=button('pp','재생','▶',()=>audio.toggle());
  const next=button('next','다음 곡','│▶',()=>audio.next());
  const mute=button('mute','음소거','',()=>audio.mute()),speaker=icon(SPEAKER_ON);mute.append(speaker);
  const vol=el('label','bday-volume'),range=el('input',''),tip=el('output','bday-vtip');range.type='range';range.min=0;range.max=1;range.step=.01;range.setAttribute('aria-label','음악 볼륨');vol.append(range,tip);bar.append(vol);
  range.addEventListener('input',()=>audio.setVolume(+range.value),{signal});
  const effects=el('div','bday-effects');effects.setAttribute('role','group');effects.setAttribute('aria-label','하늘 효과');
  for(const [kind,label,path] of EFFECTS){
   const toggle=kind==='fireworks'||kind==='shower',held=kind in HOLD_HELP;
   const b=button('effect '+kind,label,'',()=>{if(held)return;const on=scene.triggerManual(kind);if(toggle)b.setAttribute('aria-pressed',String(on))});
   if(toggle)b.setAttribute('aria-pressed','false');b.title=HOLD_HELP[kind]||label;b.append(icon(path));effects.append(b);
   if(kind==='fireworks')holdable(b,{tap:()=>scene.triggerManual('shot'),hold:()=>b.setAttribute('aria-pressed',String(scene.triggerManual('fireworks')))},signal);
   // 펄스는 박자에 맞출 수 있게 누르는 순간 한 파가 나간다. 0.5초 넘게 누르면 곡의 박마다 파동이 나가고, 떼면 다음 박에 큰 펄스.
   if(kind==='pulse')holdable(b,{down:()=>scene.triggerManual('pulse'),charge:()=>scene.pulseHold(true),hold:()=>scene.pulseHold(false),cancel:()=>scene.pulseHold(false,false)},signal);
   if(kind==='sign')holdable(b,{tap:()=>scene.triggerManual('ymmt'),hold:()=>scene.triggerManual('sign')},signal);
  }
  // 유노 얼굴 = 「밤 풍경 더 보기」 다시 보기. 재생 중에는 효과 버튼을 잠시 잠근다(켜 둔 토글은 그대로).
  const grand=button('effect grand','밤 풍경 더 보기','',()=>scene.grandShow()),face=new Image();
  face.src=new URL('../assets/birthday/yuno/head_open.webp',import.meta.url).href;face.alt='';face.draggable=false;grand.title='밤 풍경 더 보기';grand.append(face);effects.append(grand);
  scene.onGrand(on=>{for(const b of effects.querySelectorAll('button'))b.disabled=on;shell.toggleAttribute('data-grand',on)});
  bar.append(effects);
  const scan=el('span','bday-panel-scan');scan.setAttribute('aria-hidden','true');bar.append(scan);
  bar.addEventListener('animationend',e=>{if(e.target===scan)shell.removeAttribute('data-fresh-unlock')},{signal});
  bar.addEventListener('animationcancel',e=>{if(e.target===scan)shell.removeAttribute('data-fresh-unlock')},{signal});
  bar.addEventListener('click',e=>e.stopPropagation(),{signal});
  shell.append(bar,title,disc,prompt);document.body.append(shell);
  const drag=mountBirthdayPlayerDrag({bar,grip,shell,title,disc});
  function update(){
    pp.textContent=audio.paused?'▶':'';pp.classList.toggle('is-paused-icon',!audio.paused);pp.setAttribute('aria-label',audio.paused?'재생':'일시정지');
    scene.setEyesClosed(audio.silent);speaker.firstChild.setAttribute('d',audio.silent?SPEAKER_OFF:SPEAKER_ON);mute.setAttribute('aria-pressed',String(audio.muted));
    range.value=audio.volume;range.style.setProperty('--v',audio.volume*100+'%');tip.textContent=Math.round(audio.volume*100)+'%';shell.classList.toggle('playing',!audio.paused);
    if(lastIndex!==audio.index){lastIndex=audio.index;const expectedIndex=lastIndex;name.textContent='♪ '+audio.track.title;name.getAnimations().forEach(a=>a.cancel());if(!reduced())name.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'none'}],{duration:450});audio.beat.then(t=>{if(!dead&&expectedIndex===audio.index)scene.setTrack(t)});}
  }
  unsub=audio.subscribe(update);update();scene.setClock(()=>audio.clock());scene.setIntro(()=>intro&&!reduced());
  // 보상 전 · 인트로 중에는 이전/다음 곡이 화면 · 포커스 · 키보드 어디에도 없다.
  function syncReward(){const on=reward.unlocked&&!intro;prev.hidden=next.hidden=effects.hidden=!on;shell.toggleAttribute('data-unlocked',on)}
  const reward=mountBirthdayReward({audio,onUnlock:()=>{if(!reduced())shell.setAttribute('data-fresh-unlock','');syncReward()}});syncReward();
  const story=mountBirthdayStory({audio,scene,shell,reduced,reward});
  function wake(){shell.classList.remove('idle');clearTimeout(idle);idle=setTimeout(()=>shell.classList.add('idle'),5000)}
  for(const type of ['pointermove','pointerdown','keydown'])document.addEventListener(type,wake,{signal});wake();
  document.addEventListener('keydown',e=>{
    if(intro||!root.hasAttribute('data-bday-full')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName)||e.target.isContentEditable||e.ctrlKey||e.metaKey||e.altKey)return;
    const action={' ':()=>audio.toggle(),ArrowLeft:reward.unlocked?()=>audio.previous():null,ArrowRight:reward.unlocked?()=>audio.next():null,ArrowUp:()=>audio.setVolume(audio.volume+.05),ArrowDown:()=>audio.setVolume(audio.volume-.05),m:()=>audio.mute(),M:()=>audio.mute()}[e.key];
    if(action){e.preventDefault();Promise.resolve(action()).catch(()=>{prompt.hidden=false})}
  },{signal});
  async function start(){if(starting||dead)return;starting=true;try{audio.audio.currentTime=0;await audio.play();if(dead)return;prompt.hidden=true;ready=true;root.setAttribute('data-bday-started','')}catch(e){if(!dead){prompt.hidden=false;if(e.name!=='NotAllowedError')prompt.textContent='탭하여 다시 시작 ♪'}}finally{starting=false}}
  const first=e=>{if(!ready&&prompt.hidden===false){if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault();e.stopPropagation();start()}};
  document.addEventListener('pointerdown',first,{signal,capture:true});document.addEventListener('keydown',first,{signal,capture:true});
  function tick(){
    raf=0;
    if(dead)return;
    if(intro){const t=ready?audio.audio.currentTime:0;scene.setBrightness(!reduced()&&t>=17.14&&t<17.64?.3:introBrightness(t,reduced()));
      if(ready&&t>=19){intro=false;root.removeAttribute('data-bday-intro');root.setAttribute('data-bday-revealed','');host.style.filter='';syncReward()}
    }
    if(intro&&!document.hidden)raf=requestAnimationFrame(tick);
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0}else if(intro&&!raf&&!dead)raf=requestAnimationFrame(tick)},{signal});
  root.setAttribute('data-bday-intro','');setFull(true);raf=requestAnimationFrame(tick);start();
  return {shell,get intro(){return intro},destroy(){dead=true;cancelAnimationFrame(raf);clearTimeout(idle);reward.destroy();story.destroy();drag.destroy();events.abort();unsub();shell.remove();host.style.filter='';for(const k of ['data-bday-intro','data-bday-started','data-bday-revealed'])root.removeAttribute(k)}};
}
