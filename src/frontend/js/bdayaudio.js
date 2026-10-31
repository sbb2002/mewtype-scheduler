// 첫 곡은 즉시 스트리밍하고 디코드 뒤에는 AudioContext 시계로 세 곡을 미리 예약한다.
import { decodeTrack, smoothClock } from './bdaylogic.js';
import { mainMusicActive, subscribeMainMusic } from './musicpriority.js';
export const TRACKS=[{key:'noctural',title:'Noctural Run'},{key:'midnight',title:'Midnight Groove'}];
export async function mountBirthdayAudio(onChange=()=>{}) {
  const abort=new AbortController(),events=new AbortController(),urls=new Map(),preloads=new Map(),maps=new Map(),listeners=new Set();
  let dead=false,index=0,context=null,gain=null,streamGain=null,muted=false,volume=.3,revision=0,playRevision=0;
  let buffers=null,warming=null,bufferMode=false,playing=false,position=0,queue=[],handover=0,poll=0,autoplayTimer=0;
  const transitions=[];
  try{const saved=localStorage.getItem('bday-vol');if(saved!==null&&Number.isFinite(+saved))volume=Math.min(1,Math.max(0,+saved))}catch{}
  const audios=TRACKS.map(()=>{const a=new Audio();a.preload='auto';return a});
  const state={};
  const asset=(kind,key,ext)=>new URL(`../assets/birthday/${kind}/${key}.${ext}`,import.meta.url).href;
  async function map(i){if(!maps.has(i))maps.set(i,Promise.all(['json','bin'].map(ext=>fetch(asset('beat',TRACKS[i].key,ext),{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('박 지도 로드 실패');return ext==='json'?r.json():r.arrayBuffer()}))).then(([t,q])=>decodeTrack(t,q)));return maps.get(i)}
  function emit(){if(!dead){onChange(api);for(const fn of listeners)fn(api)}}
  function applyVolume(){if(gain)gain.gain.value=muted?0:volume;else for(const a of audios)a.volume=muted?0:volume}
  function ensureContext(){if(context)return;const AC=window.AudioContext||window.webkitAudioContext;if(AC){context=new AC();gain=context.createGain();streamGain=context.createGain();streamGain.connect(gain);gain.connect(context.destination);for(const a of audios){a.volume=1;context.createMediaElementSource(a).connect(streamGain)}applyVolume()}}
  // blob 교체 뒤 메타데이터가 준비되기 전에 탐색하면 브라우저가 시각을 0으로 되돌릴 수 있다.
  function metadata(a){return new Promise((resolve,reject)=>{
    const cleanup=()=>{a.removeEventListener('loadedmetadata',ready);a.removeEventListener('error',fail);abort.signal.removeEventListener('abort',fail)};
    const ready=()=>{cleanup();resolve()},fail=()=>{cleanup();reject(abort.signal.reason||new Error('음원 메타데이터 로드 실패'))};
    if(abort.signal.aborted||a.error)return fail();if(a.readyState>=1)return ready();
    a.addEventListener('loadedmetadata',ready);a.addEventListener('error',fail);abort.signal.addEventListener('abort',fail,{once:true});
  })}
  async function preload(i){
    if(preloads.has(i))return preloads.get(i);
    const p=Promise.all([map(i),fetch(asset('bgm',TRACKS[i].key,'mp3'),{signal:abort.signal}).then(r=>{if(!r.ok)throw Error('음원 로드 실패');return r.blob()}).then(async b=>{if(dead)return;const u=URL.createObjectURL(b);urls.set(i,u);if(audios[i].paused&&!bufferMode){const t=audios[i].currentTime;audios[i].src=u;await metadata(audios[i]);if(dead)return;if(t)audios[i].currentTime=t}return b})]).then(([,blob])=>blob);
    preloads.set(i,p);p.catch(()=>{});return p;
  }
  function stopNodes(){clearTimeout(handover);handover=0;clearInterval(poll);poll=0;for(const r of queue){r.node.onended=null;try{r.node.stop()}catch{}r.node.disconnect()}queue=[];if(streamGain){streamGain.gain.cancelScheduledValues(0);streamGain.gain.value=bufferMode?0:1}}
  function schedule(i,start,offset=0){
    const node=context.createBufferSource();node.buffer=buffers[i];node.connect(gain);
    const fs=context.sampleRate,startFrame=Math.round(start*fs),offsetFrame=Math.round(offset*fs);
    start=startFrame/fs;offset=offsetFrame/fs;
    const r={i,start,offset,end:(startFrame+node.buffer.length-offsetFrame)/fs,node};queue.push(r);
    node.onended=()=>{node.disconnect();sync()};node.start(start,offset);return r;
  }
  function fillQueue(){while(queue.length<3){const last=queue.at(-1);schedule(1-last.i,last.end)}}
  function sync(){
    if(!bufferMode||!playing||dead)return;
    let changed=false;
    while(queue.length>1&&context.currentTime>=queue[1].start){const old=queue.shift(),next=queue[0];old.node.onended=null;old.node.disconnect();index=next.i;state.value=null;changed=true;transitions.push({from:old.i,to:next.i,end:old.end,start:next.start,gap:next.start-old.end});if(transitions.length>12)transitions.shift();fillQueue()}
    if(changed)emit();
  }
  function currentTime(){sync();if(!bufferMode)return audios[index].currentTime;if(!playing)return position;const r=queue[0];return Math.min(buffers[index].duration,Math.max(r.offset,r.offset+context.currentTime-r.start))}
  function startBuffers(offset,when=context.currentTime+.08){
    stopNodes();position=Math.min(Math.max(0,offset),buffers[index].duration);
    playing=true;schedule(index,when,position);fillQueue();poll=setInterval(sync,50);
  }
  async function warm(){
    if(!context||dead||warming)return warming;
    const ctx=context;
    warming=Promise.all(TRACKS.map(async(_,i)=>{const blob=await preload(i);if(dead)return null;return ctx.decodeAudioData(await blob.arrayBuffer())})).then(decoded=>{
      if(dead)return;buffers=decoded;
      // 현재 곡을 멈추지 않고 같은 예약 시각에 스트림 Gain을 교체한다.
      if(!audios[index].paused){const a=audios[index],when=ctx.currentTime+.08,offset=a.currentTime+.08;if(offset>=buffers[index].duration)return;
        bufferMode=true;startBuffers(offset,when);streamGain.gain.setValueAtTime(1,ctx.currentTime);streamGain.gain.setValueAtTime(0,when);
        handover=setTimeout(()=>{handover=0;for(const media of audios)media.pause()},100);emit();
      }
    }).catch(()=>{if(!dead)warming=null});
    return warming;
  }
  async function play(){
    if(dead||mainMusicActive())return;const rev=++playRevision;ensureContext();const resume=context?.resume();
    if(buffers){
      await resume;if(dead||rev!==playRevision)return;if(context.state!=='running')throw new DOMException('사용자 조작이 필요합니다','NotAllowedError');
      if(bufferMode&&playing)return;
      const offset=bufferMode?position:audios[index].currentTime;bufferMode=true;for(const a of audios)a.pause();startBuffers(offset);emit();return;
    }
    const media=audios[index],attempt=media.play();resume?.catch(()=>{});
    // 정지된 AudioContext에서는 play 요청도 대기하는 브라우저가 있어 탭 안내로 전환한다.
    if(context?.state==='suspended'){
      try{await Promise.race([attempt,new Promise((resolve,reject)=>{autoplayTimer=setTimeout(()=>{
        autoplayTimer=0;if(dead||rev!==playRevision)return resolve();
        if(context?.state==='suspended'){media.pause();reject(new DOMException('사용자 조작이 필요합니다','NotAllowedError'))}else resolve(attempt);
      },250)})])}finally{clearTimeout(autoplayTimer);autoplayTimer=0}
    }else await attempt;
    if(context?.state==='suspended')await Promise.race([resume,new Promise(resolve=>setTimeout(resolve,100))]);
    if(dead||rev!==playRevision)return;
    if(context?.state==='suspended'){audios[index].pause();throw new DOMException('사용자 조작이 필요합니다','NotAllowedError')}
    emit();preload(1-index).catch(()=>{});warm();
  }
  function pause(){if(dead)return;playRevision++;if(bufferMode){position=currentTime();playing=false;stopNodes()}for(const a of audios)a.pause();emit()}
  async function select(next,autoplay=true){
    const rev=++revision;pause();const i=(next+2)%2;await preload(i);if(dead||rev!==revision)return;
    index=i;state.value=null;position=0;audios[i].currentTime=0;emit();if(autoplay)await play();
  }
  async function seek(t){
    const rev=++revision,i=index;await preload(i);if(warming)await warming;if(dead||rev!==revision)return;
    const target=Math.min(Math.max(0,Number.isFinite(t)?t:0),buffers?.[i].duration||(audios[i].duration>0&&Number.isFinite(audios[i].duration)?audios[i].duration:Infinity));
    state.value=null;
    if(buffers&&!bufferMode){playing=!audios[i].paused;bufferMode=true;audios[i].pause()}
    if(bufferMode){position=target;if(playing)startBuffers(target);else stopNodes()}else audios[i].currentTime=target;
    emit();
  }
  for(const [i,a] of audios.entries()){
    a.addEventListener('ended',()=>{if(!bufferMode&&i===index)select(1-index).catch(()=>{if(!dead)emit()})},{signal:events.signal});
    for(const type of ['play','pause','volumechange'])a.addEventListener(type,()=>{if(!bufferMode)emit()},{signal:events.signal});
  }
  const bufferView={get currentTime(){return currentTime()},set currentTime(t){void seek(t)},get duration(){sync();return buffers[index].duration},get volume(){return 1},get paused(){return !playing},get src(){sync();return urls.get(index)||audios[index].src}};
  const api={get index(){sync();return index},get track(){sync();return TRACKS[index]},get beat(){sync();return maps.get(index)},get audio(){sync();return bufferMode?bufferView:audios[index]},get volume(){return volume},get muted(){return muted},get paused(){return bufferMode?!playing:audios[index].paused},
    clock(){return smoothClock(state,currentTime(),performance.now()/1000,api.paused)},
    play,pause,toggle(){return api.paused?play():Promise.resolve(pause())},next(){return select(api.index+1)},previous(){return select(api.index-1)},seek,
    setVolume(v){volume=Math.min(1,Math.max(0,v));muted=false;applyVolume();try{localStorage.setItem('bday-vol',String(volume))}catch{}emit()},mute(){muted=!muted;applyVolume();emit()},subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},
    diagnostics(){return {dead,context:context?.state,blobURLs:urls.size,listeners:listeners.size,volume:gain?.gain.value,engine:bufferMode?'buffer':'stream',decoded:!!buffers,scheduled:queue.map(({i,start,end,offset})=>({i,start,end,offset})),transitions:[...transitions],timer:!!poll,handover:!!handover,autoplayTimer:!!autoplayTimer}},
    destroy(){if(dead)return;releasePriority();dead=true;revision++;playRevision++;playing=false;clearTimeout(autoplayTimer);autoplayTimer=0;stopNodes();abort.abort();events.abort();listeners.clear();for(const a of audios){a.pause();a.removeAttribute('src');a.load()}streamGain?.disconnect();gain?.disconnect();if(context){context.close();context=null}gain=streamGain=null;buffers=null;for(const u of urls.values())URL.revokeObjectURL(u);urls.clear();maps.clear();preloads.clear()}
  };
  audios[0].src=asset('bgm','noctural','mp3');applyVolume();
  const releasePriority=subscribeMainMusic(active=>{if(active)pause()});
  try{await map(0)}catch(e){api.destroy();throw e}
  return api;
}
