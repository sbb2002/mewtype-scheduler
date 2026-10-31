// 생일 음악 컨트롤과 곡 시계 기준 인트로.
import { introBrightness } from './bdaylogic.js';
import { mountBirthdayPlayerDrag } from './bdayplayerdrag.js';
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
  function button(cls,label,text,fn){const b=el('button','bday-ib '+cls,text);b.type='button';b.setAttribute('aria-label',label);b.addEventListener('click',e=>{e.stopPropagation();const r=el('span','bday-ripple');b.append(r);r.addEventListener('animationend',()=>r.remove(),{once:true});if(navigator.vibrate)navigator.vibrate(10);Promise.resolve(fn()).catch(()=>{prompt.hidden=false})},{signal});bar.append(b);return b}
  button('prev','이전 곡','◀│',()=>audio.previous());
  const pp=button('pp','재생','▶',()=>audio.toggle());
  button('next','다음 곡','│▶',()=>audio.next());
  const mute=button('mute','음소거','♫',()=>audio.mute());
  const vol=el('label','bday-volume'),range=el('input',''),tip=el('output','bday-vtip');range.type='range';range.min=0;range.max=1;range.step=.01;range.setAttribute('aria-label','음악 볼륨');vol.append(range,tip);bar.append(vol);
  range.addEventListener('input',()=>audio.setVolume(+range.value),{signal});
  shell.append(bar,title,disc,prompt);document.body.append(shell);
  const drag=mountBirthdayPlayerDrag({bar,grip,shell,title,disc});
  function update(){
    pp.textContent=audio.paused?'▶':'Ⅱ';pp.setAttribute('aria-label',audio.paused?'재생':'일시정지');
    mute.textContent=audio.muted||!audio.volume?'🔇':'♫';mute.setAttribute('aria-pressed',String(audio.muted));
    range.value=audio.volume;range.style.setProperty('--v',audio.volume*100+'%');tip.textContent=Math.round(audio.volume*100)+'%';shell.classList.toggle('playing',!audio.paused);
    if(lastIndex!==audio.index){lastIndex=audio.index;const expectedIndex=lastIndex;name.textContent='♪BGM '+audio.track.title;name.getAnimations().forEach(a=>a.cancel());if(!reduced())name.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'none'}],{duration:450});audio.beat.then(t=>{if(!dead&&expectedIndex===audio.index)scene.setTrack(t)});}
  }
  unsub=audio.subscribe(update);update();scene.setClock(()=>audio.clock());scene.setIntro(()=>intro&&!reduced());
  function wake(){shell.classList.remove('idle');clearTimeout(idle);idle=setTimeout(()=>shell.classList.add('idle'),5000)}
  for(const type of ['pointermove','pointerdown','keydown'])document.addEventListener(type,wake,{signal});wake();
  document.addEventListener('keydown',e=>{
    if(intro||!root.hasAttribute('data-bday-full')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName)||e.target.isContentEditable||e.ctrlKey||e.metaKey||e.altKey)return;
    const action={' ':()=>audio.toggle(),ArrowLeft:()=>audio.previous(),ArrowRight:()=>audio.next(),ArrowUp:()=>audio.setVolume(audio.volume+.05),ArrowDown:()=>audio.setVolume(audio.volume-.05),m:()=>audio.mute(),M:()=>audio.mute()}[e.key];
    if(action){e.preventDefault();Promise.resolve(action()).catch(()=>{prompt.hidden=false})}
  },{signal});
  async function start(){if(starting||dead)return;starting=true;try{audio.audio.currentTime=0;await audio.play();if(dead)return;prompt.hidden=true;ready=true;root.setAttribute('data-bday-started','')}catch(e){if(!dead){prompt.hidden=false;if(e.name!=='NotAllowedError')prompt.textContent='탭하여 다시 시작 ♪'}}finally{starting=false}}
  const first=e=>{if(!ready&&prompt.hidden===false){if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;e.preventDefault();e.stopPropagation();start()}};
  document.addEventListener('pointerdown',first,{signal,capture:true});document.addEventListener('keydown',first,{signal,capture:true});
  function tick(){
    raf=0;
    if(dead)return;
    if(intro){const t=ready?audio.audio.currentTime:0;scene.setBrightness(!reduced()&&t>=17.14&&t<17.64?.3:introBrightness(t,reduced()));
      if(ready&&t>=19){intro=false;root.removeAttribute('data-bday-intro');root.setAttribute('data-bday-revealed','');host.style.filter='';}
    }
    if(intro&&!document.hidden)raf=requestAnimationFrame(tick);
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0}else if(intro&&!raf&&!dead)raf=requestAnimationFrame(tick)},{signal});
  root.setAttribute('data-bday-intro','');setFull(true);raf=requestAnimationFrame(tick);start();
  return {shell,get intro(){return intro},destroy(){dead=true;cancelAnimationFrame(raf);clearTimeout(idle);drag.destroy();events.abort();unsub();shell.remove();host.style.filter='';for(const k of ['data-bday-intro','data-bday-started','data-bday-revealed'])root.removeAttribute(k)}};
}
