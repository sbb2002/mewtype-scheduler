// 곡 시각으로 샘플링하므로 일시정지·탐색·곡 교체에도 별도 타이머가 필요 없다.
const hash = n => { const x=Math.sin(n*127.1+19.73)*43758.5453; return x-Math.floor(x); };
export function backgroundStars(t,seed=0) {
  const stars=[];
  for(let i=0;i<24;i++){
    const period=5+hash(i+1+seed)*3,phase=t+hash(i+31+seed)*period,cycle=Math.floor(phase/period),age=phase-cycle*period;
    const life=1.2+hash(i+61)*.8;
    if(age>=life)continue;
    const starSeed=i+cycle*101+seed;
    stars.push({x:.04+.92*hash(starSeed+91),y:.06+.82*hash(starSeed+151),radius:1.2+1.4*hash(starSeed+211),alpha:.75*Math.sin(Math.PI*age/life)**2});
  }
  return stars;
}

// 방문/곡마다 한 번 계획한다. 고정 연출과 겹치는 후보는 다음 빈 구간으로 넘긴다.
export function createAmbientTimeline(duration,blocked,seed) {
  const events=[];let start=19+2+hash(seed+11)*3;
  for(let i=0;start<duration&&i<2000;i++){
    let kind=hash(seed+i*37+21)<.5?'meteor':'fireworks';
    if(events.length>=2&&events.slice(-2).every(e=>e.kind===kind))kind=kind==='meteor'?'fireworks':'meteor';
    const life=kind==='meteor'?1.5:2.85;
    const conflict=blocked.find(([a,b])=>start<b+.8&&start+life>a-.8);
    if(conflict){start=conflict[1]+1+hash(seed+i*41+31)*3;continue}
    if(start+life>duration)break;
    events.push({kind,start,end:start+life,seed:seed+i*53});
    start+=life+5+hash(seed+i*43+41)*6;
  }
  return events;
}

export function ambientVisibility(t,blocked){
  let alpha=1;
  for(const [a,b] of blocked){
    if(t>=a&&t<=b)return 0;
    const distance=t<a?a-t:t-b,u=Math.min(1,distance/.8);alpha=Math.min(alpha,u*u*(3-2*u));
  }
  return alpha;
}

export function backgroundFireworks(t,timeline) {
  const event=timeline.find(e=>e.kind==='fireworks'&&t>=e.start&&t<e.end);
  if(!event)return [];
  const age=t-event.start,bursts=[];
  for(let i=0;i<2;i++){
    const a=age-i*.55;if(a<0||a>=2.3)continue;
    const seed=event.seed+i*71;
    bursts.push({x:.12+.76*hash(seed+301),y:.14+.42*hash(seed+401),age:a,color:i?'#8ae3e2':'#ffb1d1',alpha:Math.min(1,a/.1)*(1-a/2.3)**1.6});
  }
  return bursts;
}

export function backgroundMeteors(t,timeline) {
  const event=timeline.find(e=>e.kind==='meteor'&&t>=e.start&&t<e.end);
  if(!event)return [];
  const age=t-event.start;
  const u=age/1.5;
  return [{x:1.12-1.24*u,y:.06+.12*hash(event.seed+501)+.32*u,alpha:Math.sin(Math.PI*u)**.6}];
}
