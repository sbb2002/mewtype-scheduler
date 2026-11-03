// 음원과 박 지도는 생일 장면에서만 요청한다. 첫 곡은 스트리밍, 다음 곡은 blob 선로딩.
import { decodeTrack, smoothClock } from './bdaylogic.js';
export const TRACKS=[{key:'noctural',title:'Noctural Run'},{key:'midnight',title:'Midnight Groove'}];
export async function mountBirthdayAudio(onChange=()=>{}) {
  const abort=new AbortController(),urls=new Map(),preloads=new Map(),maps=new Map(),listeners=new Set(),events=new AbortController();
  let dead=false,index=0,context=null,gain=null,muted=false,volume=.3,revision=0;
  try{const saved=localStorage.getItem('bday-vol');if(saved!==null&&Number.isFinite(+saved))volume=Math.min(1,Math.max(0,+saved))}catch{}
  const audios=TRACKS.map(()=>{const a=new Audio();a.preload='auto';return a});
  const state={};
  const asset=(kind,key,ext)=>new URL(`../assets/birthday/${kind}/${key}.${ext}`,import.meta.url).href;
  async function map(i){if(!maps.has(i))maps.set(i,Promise.all(['json','bin'].map(ext=>fetch(asset('beat',TRACKS[i].key,ext),{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('박 지도 로드 실패');return ext==='json'?r.json():r.arrayBuffer()}))).then(([t,q])=>decodeTrack(t,q)));return maps.get(i)}
  function emit(){if(!dead){onChange(api);for(const fn of listeners)fn(api)}}
  function applyVolume(){if(gain)gain.gain.value=muted?0:volume;else for(const a of audios)a.volume=muted?0:volume}
  function ensureContext(){if(context)return;const AC=window.AudioContext||window.webkitAudioContext;if(AC){context=new AC();gain=context.createGain();gain.connect(context.destination);for(const a of audios){a.volume=1;context.createMediaElementSource(a).connect(gain)}applyVolume()}}
  async function preload(i){
    if(preloads.has(i))return preloads.get(i);
    const p=Promise.all([map(i),fetch(asset('bgm',TRACKS[i].key,'mp3'),{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('음원 로드 실패');return r.blob()}).then(b=>{if(dead)return;const u=URL.createObjectURL(b);urls.set(i,u);if(audios[i].paused){const t=audios[i].currentTime;audios[i].src=u;if(t)audios[i].currentTime=t}})]);
    preloads.set(i,p);p.catch(()=>{});return p;
  }
  async function play(){
    if(dead)return;ensureContext();const resume=context?.resume();
    await audios[index].play();
    // 일부 브라우저는 play()를 허용해도 AudioContext.resume()을 사용자 탭까지 보류한다.
    if(context?.state==='suspended')await Promise.race([resume,new Promise(resolve=>setTimeout(resolve,100))]);
    if(dead)return;
    if(context?.state==='suspended'){audios[index].pause();throw new DOMException('사용자 조작이 필요합니다','NotAllowedError')}
    emit();preload(1-index).catch(()=>{});
  }
  async function select(next,autoplay=true){const rev=++revision;audios[index].pause();const i=(next+2)%2;await preload(i);if(dead||rev!==revision)return;index=i;state.value=null;audios[i].currentTime=0;emit();if(autoplay)await play();}
  for(const [i,a] of audios.entries()){
    a.addEventListener('ended',()=>{if(i===index)select(1-index).catch(e=>{if(!dead)emit()})},{signal:events.signal});
    for(const type of ['play','pause','volumechange'])a.addEventListener(type,emit,{signal:events.signal});
  }
  const api={get index(){return index},get track(){return TRACKS[index]},get beat(){return maps.get(index)},get audio(){return audios[index]},get volume(){return volume},get muted(){return muted},get paused(){return audios[index].paused},
    clock(){return smoothClock(state,audios[index].currentTime,performance.now()/1000,audios[index].paused)},
    play,pause(){audios[index].pause();emit()},toggle(){return audios[index].paused?play():Promise.resolve(api.pause())},next(){return select(index+1)},previous(){return select(index-1)},
    setVolume(v){volume=Math.min(1,Math.max(0,v));muted=false;applyVolume();try{localStorage.setItem('bday-vol',String(volume))}catch{}emit()},mute(){muted=!muted;applyVolume();emit()},subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},
    async seek(t){await preload(index);if(!dead){audios[index].currentTime=t;state.value=null}},
    diagnostics(){return {dead,context:context?.state,blobURLs:urls.size,listeners:listeners.size,volume:gain?.gain.value}},
    destroy(){if(dead)return;dead=true;abort.abort();events.abort();listeners.clear();for(const a of audios){a.pause();a.removeAttribute('src');a.load()}gain?.disconnect();if(context){context.close();context=null}gain=null;for(const u of urls.values())URL.revokeObjectURL(u);urls.clear()}
  };
  audios[0].src=asset('bgm','noctural','mp3');applyVolume();
  try{await map(0)}catch(e){api.destroy();throw e}
  return api;
}
