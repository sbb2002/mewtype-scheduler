// DOM 없는 생일 장면 계산. 인계에서 확정한 양 끝 값과 ease-out 곡선을 따른다.
export const DROP = 17.14;
export function introBrightness(t, reduced=false) {
  if(reduced)return .03+.97*Math.min(1,Math.max(0,t/3));
  const ease=x=>1-(1-Math.min(1,Math.max(0,x)))**2;
  if(t<3)return .03+.27*ease(t/3);
  if(t<DROP)return .30;
  return 2.4-1.4*ease((t-DROP)/1.5);
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
