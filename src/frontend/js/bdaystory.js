import { birthdayStoryCue } from './bdaystorylogic.js';

export function mountBirthdayStory({audio,scene,shell,reduced}){
 const root=document.documentElement,abort=new AbortController(),signal=abort.signal;
 const message=document.createElement('div');message.className='bday-story';message.setAttribute('aria-hidden','true');
 const stars=document.createElement('div');stars.className='bday-story__stars';
 const text=document.createElement('div');text.className='bday-story__text';message.append(stars,text);
 const card=document.createElement('section');card.className='bday-memory';card.hidden=true;card.setAttribute('aria-label','생일 밤의 감사 카드');
 const ornament=document.createElement('div');ornament.className='bday-memory__stars';ornament.textContent='✦  ✧  ✦';ornament.setAttribute('aria-hidden','true');
 const title=document.createElement('h2');title.textContent='함께해 줘서 고마워';
 const note=document.createElement('p');note.textContent='유노의 생일 밤을\n끝까지 빛내 준 당신에게.';
 const signature=document.createElement('p');signature.className='bday-memory__signature';signature.textContent='Happy Birthday, Yuno.';
 const close=document.createElement('button');close.type='button';close.textContent='밤 풍경 더 보기';
 card.append(ornament,title,note,signature,close);shell.append(message,card);
 let raf=0,dead=false,key='',finale=false,finished=false,cardPending=false;
 function visible(){return root.hasAttribute('data-bday-full')&&root.hasAttribute('data-bday-revealed')}
 function paint(){
  if(dead)return;
  const index=audio.index,time=audio.audio.currentTime,cue=visible()?birthdayStoryCue(index,time):null,next=cue?.id||'';
  if(next!==key){
   key=next;message.classList.remove('is-visible');
   if(cue){text.textContent=cue.text;stars.textContent=cue.stars?'✦ '.repeat(cue.stars).trim():'';message.classList.add('is-visible')}
  }
  if(index===1&&time>=209&&!finale&&!audio.paused&&visible()){
   finale=true;if(!reduced())scene.finale();
  }
  if(index===1&&time>=211&&!finished&&!audio.paused){finished=true;cardPending=true}
  if(cardPending&&visible()){card.hidden=false;cardPending=false;message.classList.remove('is-visible')}
  card.inert=!visible();card.setAttribute('aria-hidden',String(!visible()||card.hidden));
 }
 function frame(){raf=0;paint();if(!dead&&!audio.paused&&!document.hidden)raf=requestAnimationFrame(frame)}
 function wake(){if(dead)return;paint();if(!raf&&!audio.paused&&!document.hidden)raf=requestAnimationFrame(frame)}
 close.addEventListener('click',e=>{e.stopPropagation();card.hidden=true},{signal});
 card.addEventListener('click',e=>e.stopPropagation(),{signal});
 const unsubscribe=audio.subscribe(wake);
 document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0}else wake()},{signal});
 const observer=new MutationObserver(wake);observer.observe(root,{attributes:true,attributeFilter:['data-bday-full','data-bday-revealed']});
 wake();
 return {destroy(){dead=true;cancelAnimationFrame(raf);unsubscribe();observer.disconnect();abort.abort();message.remove();card.remove()}};
}
