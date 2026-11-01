// 생일 음악 두 곡 완곡 판정과 보상 해제 기억.
// 완곡 = 그 곡의 98% 이상을 소리를 켜고 재생했고(탐색으로 건너뛴 구간 · 반복 재생 · 볼륨 0 · 음소거 구간은 세지 않음) 곡 끝에서 소리가 켜진 채 다음 곡으로 넘어감.
export const REWARD_KEY='bday-yuno-controls-unlocked-v1';
const MIN_COVERAGE=.98,CARD_COVERAGE=.96,MAX_STEP=1.5,END_MARGIN=2;

export function createListenTracker(trackCount=2){
  const tracks=Array.from({length:trackCount},()=>({buckets:null,ended:false}));
  let last=null;
  const coverage=i=>{const b=tracks[i].buckets;if(!b)return 0;let n=0;for(const v of b)n+=v;return n/b.length};
  return {
    // 일시정지 · 탐색(시간이 뒤로 가거나 MAX_STEP 초과)은 감상으로 세지 않는다.
    update({index,time,duration,paused,silent=false}){
      if(!Number.isFinite(duration)||duration<=0||!Number.isFinite(time))return;
      const t=tracks[index];t.buckets??=new Uint8Array(Math.ceil(duration));
      if(last){
        if(last.index!==index&&last.time>=last.duration-END_MARGIN)tracks[last.index].ended=!last.silent; // 가장 최근 마무리가 무음이면 앞선 완곡도 무효.
        const step=time-last.time;
        if(last.index===index&&!paused&&!last.paused&&!silent&&!last.silent&&step>0&&step<=MAX_STEP)
          for(let s=Math.floor(last.time);s<=Math.floor(time)&&s<t.buckets.length;s++)t.buckets[s]=1;
      }
      last={index,time,duration,paused,silent};
    },
    coverage,
    complete(){return tracks.every((t,i)=>t.ended&&coverage(i)>=MIN_COVERAGE)},
    // 감사 카드는 곡이 끝나기 조금 전에 뜬다 — 첫 곡은 완곡, 둘째 곡은 카드 시각까지 들었는지만 본다.
    cardReady(){return !last?.silent&&tracks[0].ended&&coverage(0)>=MIN_COVERAGE&&coverage(1)>=CARD_COVERAGE},
  };
}

export function loadUnlocked(storage){try{return storage.getItem(REWARD_KEY)==='1'}catch{return false}}
export function saveUnlocked(storage){try{storage.setItem(REWARD_KEY,'1')}catch{}}

// 저장이 막혀도 이번 방문에는 해제 상태가 유지된다.
export function mountBirthdayReward({audio,onUnlock=()=>{}}){
  const tracker=createListenTracker();
  let unlocked=loadUnlocked(localStorage),timer=0;
  function tick(){
    const a=audio.audio;tracker.update({index:audio.index,time:a.currentTime,duration:a.duration,paused:audio.paused,silent:audio.silent});
    if(!tracker.complete())return;
    clearInterval(timer);timer=0;
    if(!unlocked){unlocked=true;saveUnlocked(localStorage);onUnlock()}
  }
  // 탭을 숨겨도 음악은 계속되므로 RAF 가 아니라 타이머로 잰다.
  timer=setInterval(tick,250);
  return {get unlocked(){return unlocked},cardReady:()=>!unlocked&&tracker.cardReady(),destroy(){clearInterval(timer);timer=0}};
}
