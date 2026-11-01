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

// 사인·UFO·별과 글로우를 감싼 원본 영역까지 화면의 하늘 안에 맞춘다.
// 사인 획의 중심(305,202.5). 칸 543×380 = 획(520×345)을 ±4도 기울인 외곽이라 기울여도 빠져나가지 않는다.
const SIGN_W=543,SIGN_H=380,SIGN_CX=305,SIGN_CY=202.5,HEAD_FLOOR=262,LEFT_FLOOR=285,LEFT_RIGHT=465;
const signAt=(k,cx,cy)=>({scale:k,x:cx-SIGN_CX*k,y:cy-SIGN_CY*k,cx,cy});
function signLeft(view){
 const right=Math.min(view.left+view.width,LEFT_RIGHT),room=Math.min(view.top+view.height,LEFT_FLOOR)-view.top,width=right-view.left;
 return signAt(Math.max(.01,Math.min(width*.97/SIGN_W,room*.97/SIGN_H)),view.left+width/2,view.top+room/2);
}
// 세로 화면 = 하늘 맨 위. 가로 화면 = 머리 위 가운데, place 'left' 면 유노 왼쪽 위 하늘. 태양과는 겹쳐도 된다.
export function fitSkySign(view,portrait=false,place='center'){
 const room=Math.max(1,Math.min(view.top+view.height,HEAD_FLOOR)-view.top),k=Math.max(.01,Math.min(view.width*.97/SIGN_W,room*.97/SIGN_H)),cx=view.left+view.width/2;
 if(portrait)return signAt(k,cx,view.top+room*.03+SIGN_H*k/2);
 const center=signAt(k,cx,view.top+room/2);
 if(place!=='left')return center;
 const left=signLeft(view);return left.scale>=center.scale*.9?left:center;
}
// 「밤 풍경 더 보기」 — 사인과 YMMT 를 겹치지 않게 나눈다(가로 = 좌우, 세로 = 위아래).
export function grandLayout(view,portrait=false){
 if(portrait){
  const sign=fitSkySign(view,true),top=sign.cy+SIGN_H*sign.scale/2+10,bottom=Math.max(top+60,150);
  return {sign,ymmt:{cx:view.left+view.width/2,cy:(top+bottom)/2,scale:Math.min(view.width*.8/355,(bottom-top)*.8/120)}};
 }
 const sign=signLeft(view),left=sign.cx+SIGN_W*sign.scale/2+8,right=view.left+view.width,bottom=Math.min(view.top+view.height,HEAD_FLOOR);
 return {sign,ymmt:{cx:(left+right)/2,cy:(view.top+bottom)/2,scale:Math.min((right-left)*.92/355,(bottom-view.top)*.85/120)}};
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

// YMMT 별자리 — 글자마다 꼭짓점을 ±4, 회전을 ±6도 흔든다. 글자 칸 사이 25 에서 양쪽 최대 8.2 라 옆 글자를 넘지 않는다.
const YMMT_LETTERS=[
 {points:[[0,0],[30,40],[60,0],[30,80]],path:[0,1,2,1,3]},
 {points:[[85,80],[85,0],[115,45],[145,0],[145,80]],path:[0,1,2,3,4]},
 {points:[[170,80],[170,0],[200,45],[230,0],[230,80]],path:[0,1,2,3,4]},
 {points:[[255,0],[285,0],[315,0],[285,80]],path:[0,1,2,1,3]},
];
export function ymmtLetters(seed=0){
 let n=(seed*2654435761+1)>>>0;
 const rand=()=>{n=(n+0x6D2B79F5)>>>0;let t=Math.imul(n^n>>>15,1|n);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296};
 return YMMT_LETTERS.map(({points,path})=>{
  const xs=points.map(p=>p[0]),cx=(Math.min(...xs)+Math.max(...xs))/2,cy=40,angle=(rand()*2-1)*6*Math.PI/180,cos=Math.cos(angle),sin=Math.sin(angle);
  const moved=points.map(([x,y])=>{const dx=x+(rand()*2-1)*4-cx,dy=y+(rand()*2-1)*4-cy;return [cx+dx*cos-dy*sin,cy+dx*sin+dy*cos]});
  return {points:moved,path};
 });
}

// 방문별 전체 회전. 회전 외곽을 원래 칸에 맞추므로 grandLayout의 분리는 유지된다.
export function ymmtTilt(seed=0){return Math.sin(seed*127.1+19.73)*8*Math.PI/180}
export function fitYmmtRotation(box,angle){
 const c=Math.abs(Math.cos(angle)),s=Math.abs(Math.sin(angle));
 return {...box,scale:box.scale*Math.min(355/(355*c+120*s),120/(355*s+120*c)),angle};
}
