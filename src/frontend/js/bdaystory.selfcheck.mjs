import assert from 'node:assert/strict';
import { STORY_CUES, STORY_MAX_GAP, STORY_SKY_SHOWS, birthdayStoryCue } from './bdaystorylogic.js';
import { fitSkySign, grandLayout, ymmtLetters, ymmtTilt, fitYmmtRotation, YMMT_INK_W, YMMT_INK_H } from './bdaylogic.js';
import { fireworkFrame, fireworkShot, fireworkSalvo } from './bdayfireworks.js';
import { decodeSign, signDrawOrder } from './bdaysign.js';

// 문구 간격 — 인사말(19~26초 부근)이 채우는 인트로 뒤 구간까지 포함해 곡마다 상한 이하, 겹침 없음.
// 고정 하늘 장면(별자리)은 화면을 채우는 구간으로 치되, 문구와 겹치면 안 된다(겹치면 그 문구가 가려져 안 나온다 — v4.11.8 count).
for(const track of [0,1]){
 const cues=STORY_CUES.filter(c=>c.track===track),shows=STORY_SKY_SHOWS.filter(s=>s.track===track);
 for(const c of cues)for(const s of shows)assert.ok(c.end<=s.start||c.start>=s.end,`${c.id} 가 ${s.id} 와 겹침`);
 const filled=[...cues,...shows].sort((a,b)=>a.start-b.start);
 for(let i=1;i<filled.length;i++){const gap=filled[i].start-filled[i-1].end;assert.ok(gap>=0,filled[i].id);assert.ok(gap<=STORY_MAX_GAP,`${filled[i].id} ${gap}`)}
}
// 인트로 문구는 드럼(17.14초) 전에 끝나고, 인트로가 아니면 나오지 않는다
assert.ok(STORY_CUES.filter(c=>c.intro).every(c=>c.end<17.14));
assert.equal(birthdayStoryCue(0,8,true).id,'listen');
assert.equal(birthdayStoryCue(0,8,false),null);
assert.equal(birthdayStoryCue(0,31).id,'invitation');

// YMMT — 글자 칸이 겹치지 않고, 시드가 같으면 같은 모양, 다르면 다른 모양
const box=l=>{const x=l.points.map(p=>p[0]),y=l.points.map(p=>p[1]);return {l:Math.min(...x),r:Math.max(...x),t:Math.min(...y),b:Math.max(...y)}};
for(let seed=0;seed<2000;seed++){
 const boxes=ymmtLetters(seed).map(box);
 for(let i=1;i<4;i++)assert.ok(boxes[i].l-boxes[i-1].r>=5,`seed ${seed}`);
 for(const b of boxes)assert.ok(b.l>=-20&&b.r<=335&&b.t>=-20&&b.b<=100,`seed ${seed}`);
}
assert.deepEqual(ymmtLetters(7),ymmtLetters(7));
assert.notDeepEqual(ymmtLetters(7),ymmtLetters(8));
// 사인 — 어떤 화면에서도 ±4도 기울여 하늘을 벗어나지 않고, 큰 장면에서 YMMT 와 겹치지 않는다
const corners=(fit,tilt)=>[[45,30],[565,30],[45,375],[565,375]].map(([x,y])=>{const dx=x-305,dy=y-202.5,c=Math.cos(tilt),s=Math.sin(tilt);return [fit.cx+fit.scale*(dx*c-dy*s),fit.cy+fit.scale*(dx*s+dy*c)]});
const views=[[{left:0,top:0,width:1200,height:395},false],[{left:-200,top:0,width:1600,height:395},false],[{left:0,top:0,width:900,height:395},false],[{left:190,top:-830,width:830,height:1225},true],[{left:230,top:-600,width:740,height:995},true]];
// UFO 사인의 실제 획 칸(0.88배) + 양쪽 기울임 + UFO 반폭 · 글로우 24.
const grandSign=fit=>[.07,-.07].flatMap(tilt=>[[32,9],[514,9],[32,333],[514,333]].map(([x,y])=>{const dx=x-305,dy=y-202.5,c=Math.cos(tilt),s=Math.sin(tilt);return [fit.cx+fit.scale*(dx*c-dy*s),fit.cy+fit.scale*(dx*s+dy*c)]}));
const inside=(v,p)=>p[0]>=v.left-.01&&p[0]<=v.left+v.width+.01&&p[1]>=v.top-.01&&p[1]<=v.top+v.height+.01;
for(const [view,portrait] of views){
 for(const place of ['center','left'])for(const tilt of [-.07,0,.07])for(const p of corners(fitSkySign(view,portrait,place),tilt))assert.ok(inside(view,p),JSON.stringify([view,place,p]));
 const {sign,ymmt}=grandLayout(view,portrait),rect=grandSign(sign),x=rect.map(p=>p[0]),y=rect.map(p=>p[1]);
 const yl=ymmt.cx-ymmt.w/2,yr=ymmt.cx+ymmt.w/2,yt=ymmt.cy-ymmt.h/2,yb=ymmt.cy+ymmt.h/2;
 assert.ok(Math.max(...x)<=yl||Math.max(...y)<=yt,JSON.stringify(view));
 assert.ok(yl>=view.left-.01&&yr<=view.left+view.width+.01&&yt>=view.top-.01&&yb<=view.top+view.height+.01,JSON.stringify(view));
}
// 폭죽 — 끈 뒤에는 새로 쏘지 않되 이미 쏜 것은 끝까지 그린다. 단발 · 사인 폭죽은 결정적이고 상한을 지킨다.
{const v={left:0,top:0,width:1200,height:395};
 assert.ok(fireworkFrame(8.5,3,v,{until:8.1}).particles.length+fireworkFrame(8.5,3,v,{until:8.1}).rockets.length>0);
 const none=fireworkFrame(16.3,3,v,{until:15.9});assert.equal(none.particles.length+none.rockets.length,0);
 assert.deepEqual(fireworkShot(1,7,v),fireworkShot(1,7,v));assert.equal(fireworkShot(.3,7,v).rockets.length,1);assert.equal(fireworkShot(4,7,v).particles.length,0);
 const salvo=fireworkSalvo(.8,9,v);assert.ok(salvo.particles.length>500&&salvo.particles.length<=1400&&!salvo.rockets.length);
 assert.equal(fireworkSalvo(4.3,9,v).particles.length,0)}
// 사인 — 가운데 y 는 한 붓(점 사이 끊김 없음), 순서는 y → m → o, 원본 획의 점은 하나도 빠지지 않는다.
{const [raw]=decodeSign(),drawn=signDrawOrder(raw),y=drawn[2],gap=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
 assert.ok(y.every((p,i)=>!i||gap(p,y[i-1])<.1));assert.deepEqual(drawn[3],raw[3]);assert.deepEqual(drawn[4],raw[4]);assert.deepEqual(y.at(-1),raw[8].at(-1));assert.deepEqual(y[0],raw[2].at(-1));
 assert.equal(drawn.length,raw.length-1);const seen=new Set(drawn.flat().map(String));assert.ok(raw.flat().every(p=>seen.has(String(p))))}
console.log('bdaystory selfcheck ok');

// 전체 회전 후 글로우 여백을 포함한 외곽이 원래 칸 안에 남고 큰 장면의 사인을 침범하지 않는다.
for(const [view,portrait] of views)for(let seed=0;seed<2000;seed++){
 const angle=ymmtTilt(seed);assert.ok(Math.abs(angle)<=8*Math.PI/180);
 const layout=grandLayout(view,portrait);
 const normal={cx:view.left+view.width*.5,cy:view.top+view.height*.35,scale:Math.min(view.width*.8/355,view.height*.48/120)};
 for(const original of [normal,layout.ymmt]){
  const fit=fitYmmtRotation(original,angle),c=Math.cos(angle),s=Math.sin(angle),grand=original===layout.ymmt,hw=grand?YMMT_INK_W/2:177.5,hh=grand?YMMT_INK_H/2:60,halfW=grand?original.w/2:177.5*original.scale,halfH=grand?original.h/2:60*original.scale;
  for(const [x,y] of [[-hw,-hh],[hw,-hh],[-hw,hh],[hw,hh]]){
   const p=[fit.cx+fit.scale*(x*c-y*s),fit.cy+fit.scale*(x*s+y*c)];
   assert.ok(inside(view,p),JSON.stringify({view,seed,p}));
   assert.ok(Math.abs(p[0]-original.cx)<=halfW+.01&&Math.abs(p[1]-original.cy)<=halfH+.01);
   if(grand){const sc=grandSign(layout.sign);assert.ok(p[0]>=Math.max(...sc.map(v=>v[0]))||p[1]>=Math.max(...sc.map(v=>v[1])))}
  }
 }
}
for(const small of [false,true])for(let seed=0;seed<40;seed++)for(let t=0;t<42;t+=.13){
 const v={left:0,top:0,width:small?820:1200,height:600},frame=fireworkFrame(t,seed,v,{small});
 assert.ok(frame.particles.length+frame.rockets.length<=(small?420:720));
 const limited=fireworkFrame(t,seed,v,{small,budget:17});assert.ok(limited.particles.length+limited.rockets.length<=17);
 assert.deepEqual(frame,fireworkFrame(t,seed,v,{small}));
 const calm=fireworkFrame(t,seed,v,{small,reduced:true});assert.equal(calm.rockets.length,0);
}
console.log('YMMT 회전 외곽 2000시드·폭죽 입자 상한·축소 모션 selfcheck 통과');
