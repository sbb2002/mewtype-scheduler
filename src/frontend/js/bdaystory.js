import { birthdayStoryCue } from './bdaystorylogic.js';

export function mountBirthdayStory({audio,scene,shell,reduced,reward}){
 const root=document.documentElement,abort=new AbortController(),signal=abort.signal;
 const message=document.createElement('div');message.className='bday-story';message.setAttribute('aria-hidden','true');
 const stars=document.createElement('div');stars.className='bday-story__stars';
 const text=document.createElement('div');text.className='bday-story__text';message.append(stars,text);
 const card=document.createElement('section');card.className='bday-memory';card.hidden=true;card.setAttribute('aria-label','생일 밤의 감사 카드');
 const ornament=document.createElement('div');ornament.className='bday-memory__stars';ornament.textContent='✦  ✧  ✦';ornament.setAttribute('aria-hidden','true');
 const title=document.createElement('h2');title.textContent='“......고마워”';
 const note=document.createElement('p');note.textContent='“생일 같은 거 별거 아니라고 생각했는데,\n오늘은 의외로 나쁘지 않았어.”';
 const signature=document.createElement('p');signature.className='bday-memory__signature';signature.textContent='— yuno';
 const close=document.createElement('button');close.type='button';close.textContent='밤 풍경 더 보기';
 card.append(ornament,title,note,signature,close);shell.append(message,card);
 let raf=0,leaving=0,dead=false,key='',finale=false,finished=false,cardPending=false;
 function visible(){return root.hasAttribute('data-bday-full')&&root.hasAttribute('data-bday-revealed')}
 function introVisible(){return root.hasAttribute('data-bday-full')&&root.hasAttribute('data-bday-intro')}
 function paint(){
  if(dead)return;
  const index=audio.index,time=audio.audio.currentTime,cue=(visible()||introVisible())&&!audio.silent&&!scene.skyBusy?.(time)?birthdayStoryCue(index,time,root.hasAttribute('data-bday-intro')):null,next=cue?.id||'';
  if(next!==key){
   key=next;message.classList.remove('is-visible');
   if(cue){
    text.replaceChildren();text.setAttribute('aria-label',cue.text);text.style.setProperty('--story-tilt',reduced()?'0deg':((Math.random()*2-1)*2.5).toFixed(2)+'deg');let typed=0;message.classList.toggle('is-reduced',reduced());
    `“${cue.text}”`.split('\n').forEach((line,row)=>{const span=document.createElement('span');span.className='bday-story__line';span.setAttribute('aria-hidden','true');
     Array.from(line).forEach((char,i)=>{const glyph=document.createElement('span');glyph.textContent=char;glyph.className='bday-story__glyph';glyph.style.setProperty('--arrival',(row*.3+typed++*.065)+'s');span.append(glyph)});text.append(span)});
    stars.textContent=cue.stars?'✦ '.repeat(cue.stars).trim():'';message.classList.add('is-visible');
   }
  }
  // 퇴장도 곡 시각으로 계산해 탐색 후 같은 상태를 재현한다.
  if(cue)message.style.setProperty('--story-fade',String(Math.min(1,(cue.end-time)/.8)));
  if(index===1&&time>=209&&!finale&&!audio.paused&&visible()){
   finale=true;if(!reduced())scene.finale();
  }
  if(index===1&&time>=212.8&&!finished&&!audio.paused&&reward.cardReady()){finished=true;cardPending=true}
  if(cardPending&&visible()){card.hidden=false;cardPending=false;message.classList.remove('is-visible')}
  card.inert=!visible();card.setAttribute('aria-hidden',String(!visible()||card.hidden));
 }
 function frame(){raf=0;paint();if(!dead&&!audio.paused&&!document.hidden)raf=requestAnimationFrame(frame)}
 function wake(){if(dead)return;paint();if(!raf&&!audio.paused&&!document.hidden)raf=requestAnimationFrame(frame)}
 // 닫기 = 카드가 빛으로 터져 사라지고 큰 장면이 시작된다. 모션 줄이기는 바로 닫는다.
 close.addEventListener('click',e=>{e.stopPropagation();if(leaving)return;scene.grandShow?.();if(reduced()){card.hidden=true;return}leaving=setTimeout(()=>{leaving=0;card.hidden=true;card.classList.remove('is-leaving')},760);card.classList.add('is-leaving')},{signal});
 card.addEventListener('click',e=>e.stopPropagation(),{signal});
 const unsubscribe=audio.subscribe(wake);
 document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0}else wake()},{signal});
 const observer=new MutationObserver(wake);observer.observe(root,{attributes:true,attributeFilter:['data-bday-full','data-bday-revealed','data-bday-intro']});
 wake();
 return {destroy(){dead=true;clearTimeout(leaving);cancelAnimationFrame(raf);unsubscribe();observer.disconnect();abort.abort();message.remove();card.remove()}};
}
