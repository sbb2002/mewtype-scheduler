import assert from 'node:assert/strict';
import { STORY_CUES, STORY_MAX_GAP, birthdayStoryCue } from './bdaystorylogic.js';
import { fitSkySign, grandLayout, ymmtLetters } from './bdaylogic.js';

// 문구 간격 — 인사말(19~26초 부근)이 채우는 인트로 뒤 구간까지 포함해 곡마다 상한 이하, 겹침 없음
for(const track of [0,1]){
 const cues=STORY_CUES.filter(c=>c.track===track);
 for(let i=1;i<cues.length;i++){const gap=cues[i].start-cues[i-1].end;assert.ok(gap>=0,cues[i].id);assert.ok(gap<=STORY_MAX_GAP,`${cues[i].id} ${gap}`)}
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
const inside=(v,p)=>p[0]>=v.left-.01&&p[0]<=v.left+v.width+.01&&p[1]>=v.top-.01&&p[1]<=v.top+v.height+.01;
for(const [view,portrait] of views){
 for(const place of ['center','left'])for(const tilt of [-.07,0,.07])for(const p of corners(fitSkySign(view,portrait,place),tilt))assert.ok(inside(view,p),JSON.stringify([view,place,p]));
 const {sign,ymmt}=grandLayout(view,portrait),rect=corners(sign,.07).concat(corners(sign,-.07)),x=rect.map(p=>p[0]),y=rect.map(p=>p[1]);
 const yl=ymmt.cx-177.5*ymmt.scale,yr=ymmt.cx+177.5*ymmt.scale,yt=ymmt.cy-60*ymmt.scale,yb=ymmt.cy+60*ymmt.scale;
 assert.ok(Math.max(...x)<=yl||Math.max(...y)<=yt,JSON.stringify(view));
 assert.ok(yl>=view.left-.01&&yr<=view.left+view.width+.01&&yt>=view.top-.01&&yb<=view.top+view.height+.01,JSON.stringify(view));
}
console.log('bdaystory selfcheck ok');
