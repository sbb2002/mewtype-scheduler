// DOM 없는 생일 장면 계산. 정본 표의 밝기 표본을 연속 선형 보간한다.
export const DROP = 17.14;
export function introBrightness(t, reduced=false) {
  if(reduced)return .03+.97*Math.min(1,Math.max(0,t/3));
  const points=[[0,.03],[1.5,.17],[3,.30],[17.139999,.30],[17.14,2.4],[17.2,2.4],[17.9,1.7],[18.2,1.45],[18.64,1]];
  for(let i=1;i<points.length;i++)if(t<points[i][0]){const [a,x]=points[i-1],[b,y]=points[i];return x+(y-x)*Math.max(0,(t-a)/(b-a))}
  return 1;
}
export function sceneLayout(w,h) {
  const r=h/w,portrait=r>=1.25,scale=portrait?w/820:Math.max(w/1200,h/760);
  const offsetY=portrait?h*.68-395*scale:(h-760*scale)/2;
  return {portrait,scale,offsetY,sunScale:portrait?(r>=1.9?1.6:1.45):1,signWidth:portrait?697:440,signY:portrait?(h*.25-offsetY)/scale-180*(697/440):0};
}
export function decodeTrack(t,bands=null) {
  const q=bands?new Uint8Array(bands):Uint8Array.from(atob(t.bands),v=>v.charCodeAt(0));
  if(q.length!==t.frames*t.nb)throw new Error('박 지도 크기 불일치');
  return {...t,q};
}
export function smoothClock(state,target,now,paused) {
  if(paused){state.value=null;return target}
  target+=.02;
  if(state.value==null||Math.abs(target-state.value)>.15)state.value=target;
  else {state.value+=now-state.now;state.value+=(target-state.value)*.12}
  state.now=now;return state.value;
}

// 첫 곡 최초 재생의 일출·조명·점등 전파. 위치는 장면 좌표이다.
export function introScene(t,L,enabled=true,reduced=false) {
 const clamp=x=>Math.max(0,Math.min(1,x)),u=clamp((t-10)/6.9),rise=u*u*(3-2*u);
 const scale=L.sunScale||1,x=L.portrait?775:850,target=267;
 const y=enabled&&!reduced&&t<16.9?395+103*scale+(target-395-103*scale)*rise:target;
 const spot=enabled?(reduced?0:clamp((t-6.3)/.9)*(1-clamp((t-DROP)/1))):0;
 return {x,y,scale,rise:enabled?rise:1,spot,wave:enabled&&!reduced&&t>=DROP?clamp((t-DROP)/.5):0};
}


