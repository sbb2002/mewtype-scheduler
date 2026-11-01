import { fireworkFrame, fireworkShot, fireworkSalvo, drawFireworkFrame, drawSpark, SHELL_LIFE, SALVO_LIFE } from './bdayfireworks.js';
import { createBirthdayBackdrop } from './bdaybackdrop.js';
// 정본 prototype_v12.html에서 수식·상수를 이식. 카메라/드롭/사인 폭만 정본 명세대로 변경.
import { createSkySign } from './bdaysign.js';
import { sceneLayout, introScene, introBrightness, fitSkySign, grandLayout, ymmtLetters, ymmtTilt, fitYmmtRotation } from './bdaylogic.js';
import { backgroundStars, backgroundFireworks, backgroundMeteors, createAmbientTimeline, ambientVisibility } from './bdaystars.js';
export function mountYunoScene(host,opts={}) {
let snapshot=null,activeLayout=null,introActive=()=>false,groundBottom=760;
let skyViewport={left:0,top:0,width:1200,height:395};
let effect={x:850,y:267,scale:1,spot:0,wave:0};
function sunTransform(c){c.translate(effect.x,effect.y);c.scale(effect.scale,effect.scale);c.translate(-850,-267)}
const spectrumHash19=(a,b)=>{const x=Math.sin((a%64+64)%64*127.1+b*311.7+19.73)*43758.5453;return x-Math.floor(x)};
// 음원 연동: 사전 분석한 박 지도(beats) · 킥 세기 · 24밴드 스펙트럼(30fps)을 읽는다
let TRK=null;
function beatIdx(t){const B=TRK.beats;let lo=0,hi=B.length-1;if(t<B[0])return 0;while(lo<hi){const m=(lo+hi+1)>>1;if(B[m]<=t)lo=m;else hi=m-1}return lo}
function beatPos(t){const B=TRK.beats,per=60/TRK.bpm;if(t<B[0])return (t-B[0])/per;const k=beatIdx(t),nx=k+1<B.length?B[k+1]-B[k]:per;return k+Math.min(1,(t-B[k])/nx)}
function lvl(t,b){const n=TRK.nb,F=TRK.frames-1,f=Math.max(0,t)*TRK.fps,i=Math.min(F,Math.floor(f)),j=Math.min(F,i+1),fr=f-Math.floor(f);b=Math.max(0,Math.min(n-1,b));const q=TRK.q;return (q[i*n+b]+(q[j*n+b]-q[i*n+b])*fr)/255}
function bandLvl(t,i,count){const x=(i+.5)/count*TRK.nb-.5,b0=Math.floor(x),fb=x-b0;return lvl(t,b0)*(1-fb)+lvl(t,b0+1)*fb}
function spectrum19(seconds,i,count){
 const l=bandLvl(seconds,i,count),h=18+93*Math.min(1,Math.pow(l,1.25)*1.08);
 let hold=0;for(let k=1;k<=9;k++)hold=Math.max(hold,bandLvl(seconds-k*.04,i,count)*(1-.065*k)); // 피크 홀드(약 0.36초 감쇠)
 return {height:h,cap:Math.max(h,18+93*Math.min(1,Math.pow(hold,1.25)*1.08))};
}

const P='#ff488d',C='#8ae3e2',V='#7844ba';

function line(c,pts,color,width=2,alpha=1){c.globalAlpha=alpha;c.strokeStyle=color;c.lineWidth=width;c.beginPath();pts.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.stroke();c.globalAlpha=1}
function bg(c){let g=c.createLinearGradient(0,0,0,580);g.addColorStop(0,'#170725');g.addColorStop(1,'#c62060');c.fillStyle=g;c.fillRect(0,0,1200,760);c.fillStyle='#8ae3e2';for(let i=0;i<34;i++){c.globalAlpha=.15+(i%4)*.06;c.fillRect((i*173+43)%1200,(i*71+41)%300,1.7,1.7)}c.globalAlpha=1;c.save();c.beginPath();c.rect(-2000,-2000,5200,2395);c.clip();sunTransform(c);c.beginPath();c.arc(850,267,102,0,Math.PI*2);c.clip();g=c.createLinearGradient(0,165,0,370);g.addColorStop(0,P);g.addColorStop(1,V);c.fillStyle=g;for(let y=165;y<370;y++)if(y<240||(y-240)%17>3+Math.floor((y-240)/17))c.fillRect(748,y,204,1);c.restore();g=c.createLinearGradient(0,395,0,760);g.addColorStop(0,'#250e30');g.addColorStop(1,'#110e20');c.fillStyle=g;c.fillRect(0,395,1200,365);line(c,[[0,395],[1200,395]],P,1.5,.5);for(const x of GRID_X)line(c,[[600,389],[x,760]],P,1,.22);for(let j=1;j<=12;j++){let y=395+365*(j/12)**2.5;line(c,[[0,y],[1200,y]],P,1,.12+j*.015)}}
const djClamp15=x=>Math.max(0,Math.min(1,x));
const djFrac15=x=>x-Math.floor(x);
const djTri15=u=>u<.25?4*u:u<.75?2-4*u:4*u-4;
const djEase15=x=>{x=djClamp15(x);return x*x*(3-2*x)};
function djContact15(shoulder,paw,degrees,bounce){
 const a=degrees*Math.PI/180,x=paw[0]-shoulder[0],y=paw[1]-shoulder[1];
 const rx=shoulder[0]+x*Math.cos(a)-y*Math.sin(a),ry=shoulder[1]+x*Math.sin(a)+y*Math.cos(a);
 return {rig:[rx,ry],scene:[675+(rx-120)*1.55,585+(ry-229+bounce)*1.55]};
}
function yunoPoseBase(beatPos0){
 const seconds=0,beats=Math.max(0,beatPos0),bar=Math.floor(beats/4),b=beats-bar*4,k=Math.floor(b),p=djFrac15(b);
 const scattered=bar%16===15,cue=bar%8===7;
 const swung=p<.62?p/.62*.5:.5+(p-.62)/.38*.5;
 const delayed=Math.max(0,beats-.04),dp=djFrac15(delayed),accent=Math.floor(delayed)%2?1.4:.7;
 const follow=djFrac15(Math.max(0,beats-.09));
 const ghost=(k===1||k===3)&&p>.62? .13*Math.sin((p-.62)/.38*Math.PI*2):0;
 const scratching=scattered?p<.62:(k===0||k===2);
 const scratch=scratching?djTri15(scattered?p/.62:djFrac15(swung*2)):ghost;
 const idle=scattered?k*.25+Math.max(0,p-.5)*.5:(b<1?0:b<2?(b-1)*.5:b<3?.5:.5+(b-3)*.5);
 const hit=dp<.14?1-Math.pow(1-dp/.14,3):Math.pow(1-(dp-.14)/.86,2);
 const anticipation=dp>.84?-.12*Math.sin((dp-.84)/.16*Math.PI):0;
 const nod=accent*hit+anticipation;
 const bounce=.7*nod;
 let right=0,mode='fader',knob=0;
 if(k===1)right=5*hit;
 if(k===2){
  mode='knob';
  if(p<.18)right=9*djEase15(p/.18);
  else if(p<.72){const u=(p-.18)/.54;right=9+1.4*djTri15(u);knob=26*djTri15(u)}
  else right=9*(1-djEase15((p-.72)/.28));
 }
 if(k===3)right=6*hit;
 if(cue&&b>=2){
  mode='travel';
  if(b<2.5)right=-79*djEase15((b-2)/.5);
  else if(b<3.25){mode='right-record';right=-79+1.2*djTri15(djFrac15((b-2.5)*2))}
  else if(b<3.75)right=-79*(1-djEase15((b-3.25)/.5));
  else {right=0;mode='fader'}
  knob=0;
 }
 const left=5.5*scratch;
 const leftContact=djContact15([86,164],[61.25,202.25],left,bounce);
 const rightContact=djContact15([153,164],[121.875,199.625],right,bounce);
 const tail=4*accent*hit;
 const bodyRoll=.65*Math.sin(Math.PI*beats);
 const ripple=.035*Math.exp(-Math.abs(p-.62)*35);
 const eqLow=(k%2?.48:1)*hit+ripple,eqHigh=(k%2?1:.45)*hit+ripple;
 return {eqLow,eqHigh,accentPulse:hit,bodyRoll,swung,swingRatio:.62,accent,seconds,bar,beat:k+1,phase:p,pattern:scattered?'single-per-beat':'paired-1-and-3',scratch,left,right,mode,knob,bounce,nod,tail,
  leftCoast:bar*32+32*idle,leftRecord:bar*32+32*idle+26*scratch,rightRecord:beats*22.5,
  headY:1.8*nod,headAngle:(Math.floor(beats)%2?1:-1)*.5*nod,
  ear:.9*accent*Math.sin(follow*Math.PI*2)*Math.exp(-follow*3),mic:1.2*accent*Math.sin(follow*Math.PI*2)*Math.exp(-follow*3),
  leftContact,rightContact,fader:mode==='fader'?rightContact.scene[0]-675:2.9,energy:Math.min(1, (.55+.3*(k%2))*Math.exp(-p*5.5)+.12*Math.exp(-Math.abs(p-.62)*22))};
}


// v6: immutable structure analysis, and pure beat-domain gesture envelopes.
const moveStructure=new WeakMap();
function moveEnergy(T,bp){
 if(!moveStructure.has(T)){
  const rows=[];
  for(let b=0;b<T.beats.length;b+=8){
   const end=Math.min(b+8,T.beats.length), t0=T.beats[b],t1=T.beats[end]||T.duration;
   let kick=0,high=0,n=0;
   for(let j=b;j<end;j++)kick+=T.kick[j];
   for(let f=Math.floor(t0*T.fps);f<Math.min(T.frames,Math.ceil(t1*T.fps));f++)for(let k=15;k<24;k++){high+=T.q[f*T.nb+k]/255;n++}
   rows.push(.65*kick/(end-b)+.35*high/Math.max(1,n));
  }
  moveStructure.set(T,rows);
 }
 const rows=moveStructure.get(T),x=Math.max(0,(bp-4)/8),i=Math.min(rows.length-1,Math.floor(x)),j=Math.min(rows.length-1,i+1);
 return rows[i]+(rows[j]-rows[i])*djEase15(x-Math.floor(x));
}
function yunoPoseB(bp){
 // Smooth the original piecewise gesture with a C2 cubic B-spline (support 0.24 beat); preserve its vocabulary.
 const grid=bp/.06,index=Math.floor(grid),u=grid-index;
 const weights=[(1-u)**3/6,(3*u**3-6*u*u+4)/6,(-3*u**3+3*u*u+3*u+1)/6,u**3/6];
 const poses=[-1,0,1,2].map(d=>yunoPoseBase((index+d)*.06)),q={...poses[1]};
 for(const key of Object.keys(q))if(typeof q[key]==='number')q[key]=poses.reduce((v,p,i)=>v+p[key]*weights[i],0);
 const b=Math.max(0,bp),cycle=djFrac15(b/16)*16,eight=djFrac15(b/8)*8;
 const window=(x,a,z,r=.8)=>djEase15((x-a)/r)*djEase15((z-x)/r);
 const midnight=TRK.bpm===100,buildStart=midnight?16:8,fullStart=midnight?24:32;
 const intro=1-djEase15((b-buildStart)/2),build=djEase15((b-buildStart)/2)*(1-djEase15((b-fullStart)/2));
 const energy=moveEnergy(TRK,b),full=djEase15((b-fullStart)/2)*djEase15((energy-.28)/.25);
 const quiet=djEase15((b-fullStart-8)/4)*(1-djEase15((energy-.25)/.18));
 const listen=Math.max(intro,quiet)*window(eight,0,4,1);
 const eq=build*window(eight,2,6,1),sweep=full*window(cycle,4,8,1),dual=full*window(cycle,10,14,1);
 const mix=(a,z,w)=>a+(z-a)*w;
 q.right=mix(q.right,155,listen);
 q.headAngle+=-9*listen;q.headY-=2*listen;q.mic+=4*listen;
 q.right=mix(q.right,9+2*Math.sin((eight-2)*Math.PI/2),eq);
 q.knob=mix(q.knob,-65+130*djEase15((eight-2)/4),eq);
 q.right=mix(q.right,10*Math.sin((cycle-4)*Math.PI/2),sweep);
 const wave=Math.sin(2*Math.PI*b);
 q.right=mix(q.right,-79+5*wave,dual);
 q.left=mix(q.left,-5*wave,dual);
 q.leftRecord+=dual*18*wave;
 q.rightRecord+=dual*(28*wave-18*Math.sin(Math.PI*b));
 q.sway=(.6+3.4*full+1.2*build)*Math.sin(Math.PI*b/2);
 q.tail+= (3+7*full)*Math.sin(Math.PI*b/2-.65);
 q.ear+=1.8*full*Math.sin(Math.PI*b/2+.4);
 q.bodyRoll*=.6; // large sway moves every part together; retain small original torso roll.
 q.leftContact=djContact15([86,164],[61.25,202.25],q.left,q.bounce);
 q.rightContact=djContact15([153,164],[121.875,199.625],q.right,q.bounce);
 q.fader=mix(q.fader,Math.max(-19,Math.min(19,q.rightContact.scene[0]-675+q.sway*1.55)),sweep);
 q.gestures={listen,eq,sweep,dual,full,build,energy};
 return q;
}

const YN={};['arm_l','arm_r','body','ear_l','ear_r','head_closed','head_flat','head_open','headset','tail'].forEach(n=>{const i=new Image();i.src=new URL('../assets/birthday/yuno/'+n+'.webp',import.meta.url).href;YN[n]=i});
const yok=()=>Object.values(YN).every(i=>i.complete&&i.naturalWidth>0);
function drawRot(c,img,x,y,w,h,deg,ox,oy){c.save();c.translate(ox,oy);c.rotate(deg*Math.PI/180);c.drawImage(img,x-ox,y-oy,w,h);c.restore()}
// 유노 + DJ 데크: 확정된 부위 이미지(webp)를 박 지도 기반 포즈로 구동한다. 좌표계는 bdayscene-yuno(RIG)와 동일.
// 소리가 없으면 유노가 눈을 감은 채로 있는다.
let yunoEyesClosed=false;
function front(c,t){
 if(!yok()){c.fillStyle='#140d20';c.beginPath();c.roundRect(557,268,236,277,44);c.fill();return}
 const bp=beatPos(t),q=yunoPoseB(bp),kb=beatIdx(t),kk=.6+.4*(TRK.kick[kb]+((TRK.kick[Math.min(kb+1,TRK.kick.length-1)]||0)-TRK.kick[kb])*djEase15(bp-Math.floor(bp))),bounce=q.bounce*kk,headY=q.headY*kk;
 // 그림자
 c.save();c.fillStyle='#10121e';c.globalAlpha=.45;c.filter='blur(7px)';c.beginPath();c.ellipse(675,630,200,22,0,0,7);c.fill();c.filter='none';c.globalAlpha=.225;c.beginPath();c.ellipse(675,630,130,8.36,0,0,7);c.fill();c.restore();
 const rig=fn=>{c.save();c.translate(675+q.sway*1.55,585);c.scale(1.55,1.55);c.translate(-120,-229+bounce);fn();c.restore()};
 // 몸통 · 꼬리 (데크 뒤)
 rig(()=>{
  drawRot(c,YN.tail,157,159,82,70,q.tail,157+.15*82,159+.75*70);
  c.save();c.translate(120,170);c.rotate(q.bodyRoll*Math.PI/180);c.translate(-120,-170);
  const x=59,y=154,w=126,h=80;c.beginPath();[[.25,0],[.75,0],[.75,.28],[.78,.66],[1,.85],[1,1],[0,1],[0,.85],[.22,.66],[.25,.28]].forEach(([u,v],i)=>i?c.lineTo(x+u*w,y+v*h):c.moveTo(x+u*w,y+v*h));c.closePath();c.clip();c.drawImage(YN.body,x,y,w,h);c.restore();
 });
 // 데크
 c.save();c.translate(675,550);
 c.fillStyle='#480c36';c.beginPath();c.moveTo(-178,-28);c.lineTo(155,-28);c.lineTo(192,12);c.lineTo(-196,12);c.closePath();c.fill();
 c.fillStyle='#10121e';c.fillRect(-196,12,388,41);c.strokeStyle='#ff488d';c.lineWidth=2;c.beginPath();c.moveTo(-196,12);c.lineTo(192,12);c.stroke();
 for(const x of [-91,91]){c.fillStyle='#10121e';c.beginPath();c.ellipse(x,-8,61,16,0,0,7);c.fill()}
 for(const [x,rot,rA,rB,col,l0,l1] of [[-91,q.leftRecord,28,12,'#ff477d',48,20],[91,q.rightRecord,23,11,'#8ae3e2',44,27]]){
  c.save();c.translate(x,-8);c.scale(1,.26);c.rotate(rot*Math.PI/180);
  c.fillStyle='#302335';c.beginPath();c.arc(0,0,49,0,7);c.fill();c.fillStyle='#480c36';c.beginPath();c.arc(0,0,rA,0,7);c.fill();c.fillStyle=col;c.beginPath();c.arc(0,0,rB,0,7);c.fill();
  c.strokeStyle=col;c.lineWidth=1;c.beginPath();c.moveTo(0,-l0);c.lineTo(x<0?6:4,-l1);c.stroke();c.restore()}
 c.fillStyle='#10121e';c.strokeStyle='#7844ba';c.lineWidth=.7;c.beginPath();c.roundRect(-25,-25,49,23,3);c.fill();c.stroke();
 c.fillStyle='#480c36';for(const x of [-18,10]){c.beginPath();c.arc(x,-19,3,0,7);c.fill()}
 c.save();c.translate(-5,-19);c.rotate(q.knob*Math.PI/180);c.fillStyle='#480c36';c.beginPath();c.arc(0,0,4,0,7);c.fill();c.stroke();c.strokeStyle='#8ae3e2';c.lineWidth=1;c.beginPath();c.moveTo(0,0);c.lineTo(0,-3);c.stroke();c.restore();
 c.fillStyle='#7844ba';c.beginPath();c.roundRect(-22,-12,44,2,1);c.fill();
 c.save();c.translate(q.fader,0);c.fillStyle='#ff477d';c.strokeStyle='#8ae3e2';c.lineWidth=.7;c.beginPath();c.roundRect(-3,-16,6,11,1.3);c.fill();c.stroke();c.restore();
 c.fillStyle='#8ae3e2';for(const x of [-137,-123,122,136]){c.beginPath();c.arc(x,25,2,0,7);c.fill()}
 c.strokeStyle='#10121e';c.lineWidth=12;c.beginPath();c.moveTo(-150,53);c.lineTo(-155,74);c.moveTo(145,53);c.lineTo(150,74);c.stroke();
 c.restore();
 // 팔 · 머리 (데크 앞)
 rig(()=>{
  drawRot(c,YN.arm_l,50,157,43,53,q.left,86,164);
  drawRot(c,YN.arm_r,114,157,45,52,q.right,153,164);
  c.save();c.translate(32+87.5,10+.88*156);c.translate(0,headY);c.rotate(q.headAngle*Math.PI/180);c.translate(-(32+87.5),-(10+.88*156));c.translate(32,10);
  const pct=((((t+.7)%7.6)+7.6)%7.6)/7.6*100,closed=yunoEyesClosed||pct>=44.5&&pct<46.3;
  c.drawImage(yunoEyesClosed?YN.head_flat:closed?YN.head_closed:YN.head_open,0,0,175,156);
  drawRot(c,YN.ear_l,0,0,175,156,-q.ear,.28*175,.45*156);
  drawRot(c,YN.ear_r,0,0,175,156,q.ear,.72*175,.45*156);
  drawRot(c,YN.headset,142,97,42,40,q.mic,142+21,97+20);
  c.restore();
 });
}
const historyCache=new Map();function past(t){const key=Math.round(Math.max(0,t)*10);if(!historyCache.has(key)){historyCache.set(key,Array.from({length:64},(_,i)=>spectrum19(key/10,Math.min(i,63-i)*2,64).height));if(historyCache.size>220)historyCache.delete(historyCache.keys().next().value)}return historyCache.get(key)}
const fxRows=T=>{
  if(T.fxRows7)return T.fxRows7;
  const rows=[];
  for(let b=0;b<T.beats.length;b+=8){
   const z=Math.min(b+8,T.beats.length),a=Math.floor(T.beats[b]*T.fps),end=Math.min(T.frames,Math.ceil((T.beats[z]??T.duration)*T.fps));
   const r={low:0,mid:0,high:0,kick:0,accent:0};
   for(let f=a;f<end;f++)for(let k=0;k<24;k++)r[k<6?'low':k<15?'mid':'high']+=T.q[f*24+k]/255;
   for(const [key,n] of [['low',6],['mid',9],['high',9]])r[key]/=Math.max(1,(end-a)*n);
   for(let j=b;j<z;j++){r.kick+=T.kick[j];r.accent+=T.accent[j]}
   r.kick/=z-b;r.accent/=z-b;rows.push(r);
  }
  T.fxRows7=rows;return rows;
 };

function skyStructure(t){
 const smooth=djEase15,bp=beatPos(t),rows=fxRows(TRK),x=Math.max(0,(bp-4)/8),ri=Math.min(rows.length-1,Math.floor(x)),rj=Math.min(rows.length-1,ri+1),u=smooth(x-Math.floor(x)),E={};
 for(const key of ['low','mid','high','kick','accent'])E[key]=rows[ri][key]*(1-u)+rows[rj][key]*u;
 const midnight=TRK.bpm===100;return {bp,E,midnight,bs:midnight?16:8,drop:midnight?24:beatPos(17.14)};
}
const skyUFO=new Image();skyUFO.src=new URL('../assets/birthday/ufo.png',import.meta.url).href;
const skyHash=n=>{n=Math.imul(n^0x9e3779b9,0x85ebca6b);n=Math.imul(n^(n>>>16),0xc2b2ae35);return ((n^(n>>>16))>>>0)/4294967296};

// Normalized alpha-skeleton centerlines, extracted from ref/sign.png (797 points).

const skyModes=new WeakMap();
const skyForcedMode=new URLSearchParams(location.search).get('ufo');
function skyMode(T){return skyModes.get(T)||(['sign','zig'].includes(skyForcedMode)?skyForcedMode:(skyHash(429+SKY_SALT*7)<.5)===(T.bpm===100)?'sign':'zig')} // 두 곡이 서로 반대라 한 바퀴에 사인이 꼭 한 번 나온다.
// 사인은 성능 때문에 품질을 낮추지 않는다. 사인의 별은 원래 그림자 그대로 그린다.
const {skySign,skySignPos,skySignDraw}=createSkySign({djClamp15,djEase15,skyStar:(...args)=>skyStar(...args.slice(0,6),SKY_STAR_Y,SKY_STAR_EDGE,true),skyUFO});
let skyRoutineAlpha=1;
const SIGN_TILT=4*Math.PI/180,SIGN_BURST=8; // SIGN_BURST = 사인 완성 뒤 무지개 유성 · 혜성이 쏟아지는 시간.
const tiltSign=(c,angle)=>{c.translate(305,202.5);c.rotate(angle);c.translate(-305,-202.5)};
const skyPlans=new WeakMap();
function skyPlan(T){
 if(skyPlans.has(T)&&skyPlans.get(T).ufos[0].mode===skyMode(T))return skyPlans.get(T);
 const mid=T.bpm===100,bs=mid?16:8,drop=mid?24:32,B=T.beats,seed=mid?73:25;
 const meteors=[...new Set((mid?[bs,bs+2,drop-4]:[bs,bs+4,drop-8]))].map((b,i)=>{
  const n=1+Math.floor(skyHash(seed+i*31)*20),parts=[];
  for(let j=0;j<n;j++){const h=k=>skyHash(seed+i*997+j*43+k*137);parts.push({delay:j*(.15+.25*h(1)),duration:4+4*h(2),y:-32+60*h(3),fall:180+100*h(4),len:85+80*h(5),size:1.5+1.6*h(6),alpha:(.38+.42*h(7))/Math.max(1,Math.sqrt(n/5))})}
  return {birth:B[b],beat:b,i,n,parts,life:Math.max(...parts.map(p=>p.delay+p.duration)),large:false};
 });
 meteors.push({birth:(mid?B[drop]:17.14)-6,beat:drop-6*T.bpm/60,i:3,n:1,large:true,life:5.95,parts:[{delay:0,duration:5.95,y:-20,fall:270,len:700,size:9,alpha:.85}]});
 const br=mid?224:192,en=mid?256:208;
 const f={type:2,seed:seed+700,birth:B[328],end:Math.min(T.duration,B[328]+11.25),stopX:1200*(.4+.3*skyHash(seed+501)),scan:2.25};
 const n2=6+Math.floor(skyHash(seed+503)*2),pin=2+Math.floor(skyHash(seed+504)*2);
 f.zig=skyMakePath(seed+505,{n:n2,pinIdx:pin,pinX:f.stopX,exitX:-80});
 f.arrive=f.zig.stopU*(f.end-f.birth-f.scan);f.leave=f.arrive+f.scan;
 const mode=skyMode(T),sign=mode==='sign',flight=sign?skySign.T+skySign.INTRO:4.25,reveal=flight+.92,fade=sign?5.5:0;
 const plan={meteors,drop:mid?B[drop]:17.14,quiet:[[B[br],B[en]],[B[320],T.duration]],ufos:[{type:1,mode,place:skyHash(seed+606+SKY_SALT)<.5?'left':'center',tilt:(skyHash(seed+707+SKY_SALT)*2-1)*SIGN_TILT,birth:B[br],end:sign?B[br]+reveal+fade:B[br]+4.75,flight,reveal,fade,zig:skyMakePath(seed+404)},f]};
 plan.blocked=[[0,19],[plan.drop,plan.drop+1.6],...plan.quiet,...meteors.map(m=>[m.birth,m.birth+m.life]),...plan.ufos.map(u=>[u.birth,Math.max(u.end,u.type===1?u.birth+skySign.T+skySign.INTRO+.92+5.5:0)+SKY_TRAIL_DECAY])].sort((a,b)=>a[0]-b[0]);
 // 전체 길이가 들어가는 빈 구간만 예약한다. 곡별 고정 해시로 반복·탐색에도 동일하다.
 const free=(a,len)=>!plan.blocked.some(([x,y])=>a<y+1&&a+len>x-1);
 const slots=[];for(let a=23;a<T.duration-10;a+=1)if(free(a,9))slots.push(a);
 plan.constellation=slots.length?slots[Math.floor(skyHash(seed+818)*slots.length)]:null;
 if(plan.constellation!==null)plan.blocked.push([plan.constellation,plan.constellation+9]);
 const showerSlots=[];for(let a=28;a<T.duration-7;a+=3)if(free(a,5))showerSlots.push(a);
 showerSlots.sort((a,b)=>skyHash(seed+a+SKY_SALT*7)-skyHash(seed+b+SKY_SALT*7));
 plan.showers=[];const showerLimit=2+Math.floor(skyHash(seed+SKY_SALT*13)*2);
 for(const a of showerSlots)if(plan.showers.length<showerLimit&&free(a,5)&&plan.showers.every(b=>Math.abs(a-b)>=24)){plan.showers.push(a);plan.blocked.push([a,a+5])}
 plan.showers.sort((a,b)=>a-b);
 plan.blocked.sort((a,b)=>a[0]-b[0]);
 plan.ambientSeed=seed+SKY_SALT*997;
 plan.ambient=createAmbientTimeline(T.duration,plan.blocked,plan.ambientSeed);
 skyPlans.set(T,plan);return plan;
}
// UFO1 지그재그 경로: 페이지를 열 때마다(SKY_SALT)·곡마다 무작위로 생성. 같은 세션 안에서는 어느 시점이든 동일(결정적).
const SKY_SALT=Math.floor(Math.random()*997);
function skyMakePath(seed,opt={}){
 const h=k=>skyHash(seed+k*53+SKY_SALT*7);
 const pts=[[1250,50+130*h(0)]],n=opt.n||11+Math.floor(h(1)*5);let x=1250,y=pts[0][1];
 for(let i=1;i<=n;i++){
  const back=i>2&&i<n-1&&h(10+i)<.28;
  x=back?Math.min(1240,x+30+70*h(30+i)):Math.max(95,x-(1150/n)*(.55+.95*h(30+i)));
  let ny=38+190*h(60+i);if(Math.abs(ny-y)<60)ny=y+(ny>y?1:-1)*(60+45*h(90+i));
  ny=Math.max(36,Math.min(228,ny));if(Math.abs(ny-y)<40)ny=y>130?y-80:y+80;y=ny;pts.push([x,y]);
 }
 pts[pts.length-1][0]=opt.exitX!==undefined?opt.exitX:90+80*h(2);
 if(opt.pinIdx!==undefined){pts[opt.pinIdx][0]=opt.pinX;if(Math.abs(pts[opt.pinIdx][1]-pts[opt.pinIdx-1][1])<50)pts[opt.pinIdx][1]=pts[opt.pinIdx-1][1]>130?pts[opt.pinIdx-1][1]-70:pts[opt.pinIdx-1][1]+70}
 // 꼭짓점(구간)마다 속도 배율이 달라진다: 이웃 구간과 최소 0.55 이상 차이가 나도록 교대
 const sp=[];for(let i=0;i<pts.length-1;i++){let v=.4+1.9*h(120+i);if(i&&Math.abs(v-sp[i-1])<.55)v=sp[i-1]>1.1?.4+.35*h(150+i):1.7+.6*h(150+i);sp.push(v)}
 // 궤적 종류는 UFO 마다 곡선 · 각진 직선 · 둘을 섞은 것 중 하나다.
 const style=['curve','angle','mixed'][Math.floor(h(300)*3)];
 const cv=sp.map((_,i)=>{const arc=(h(240+i)<.5?-1:1)*(.22+.3*h(270+i));return style==='angle'?0:style==='curve'?arc:h(210+i)<.5?arc:0});
 const segs=sp.map((v,i)=>Math.hypot(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1])*(1+2.7*cv[i]*cv[i])/v);
 const ex=sp.map((_,i)=>.75+.6*h(180+i));
 const total=segs.reduce((a,b)=>a+b,0);return {style,pts,segs,ex,cv,total,stopU:opt.pinIdx!==undefined?segs.slice(0,opt.pinIdx).reduce((a,b)=>a+b,0)/total:0};
}
function skyZig(f,u){
 const Z=f.zig;let d=djClamp15(u)*Z.total;
 for(let i=0;i<Z.segs.length;i++){if(d<=Z.segs[i]||i===Z.segs.length-1){let q=djClamp15(d/Z.segs[i]);q=i%2?q**Z.ex[i]:q**(1/Z.ex[i]);const a=Z.pts[i],b=Z.pts[i+1],k=Z.cv[i];if(!k)return [a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q,Math.atan2(b[1]-a[1],b[0]-a[0])];const dx=b[0]-a[0],dy=b[1]-a[1],cx=(a[0]+b[0])/2-dy*k,cy=(a[1]+b[1])/2+dx*k,o=1-q;return [o*o*a[0]+2*o*q*cx+q*q*b[0],o*o*a[1]+2*o*q*cy+q*q*b[1],Math.atan2(2*o*(cy-a[1])+2*q*(b[1]-cy),2*o*(cx-a[0])+2*q*(b[0]-cx))]}d-=Z.segs[i]}
}
function skyUfo2(f,age){
 // 각진 경로(꼭짓점 몇 군데, 구간마다 속도 다름): 가로 40~70% 위치의 지정 꼭짓점에서 정확히 한 번 멈춰 스캔한다.
 const travel=f.end-f.birth-f.scan,u0=f.zig.stopU;
 const scanning=age>=f.arrive&&age<=f.leave,u=Math.max(0,Math.min(1,(age-f.arrive)/f.scan));
 const pu=age<f.arrive?age/travel:age<=f.leave?u0:(age-f.scan)/travel;
 const [x,y,ang]=skyZig(f,pu),dirTilt=Math.max(-.3,Math.min(.3,.25*Math.sin(ang)));
 return {x,y,scanning,u,tilt:scanning?.16*Math.sin(u*5*Math.PI):dirTilt+.03*Math.sin(age*.9)};
}
const auroraGradients=new WeakMap();
// 오로라는 프레임마다 사각형 1,700여 개를 그려 곡에서 가장 무거운 구간이다. 움직임이 느리니 절반 해상도 층에 초당 20번만 그리고 복사한다.
const auroraLayer={cv:null,key:null};
function skyAurora(c,t,a,b){
 const fade=djEase15((t-a)/2.2)*djEase15((b-t)/2.2);if(fade<=0)return;
 if(!auroraLayer.cv){auroraLayer.cv=document.createElement('canvas');auroraLayer.cv.width=600;auroraLayer.cv.height=110}
 const key=Math.floor(t*20);
 if(auroraLayer.key!==key){auroraLayer.key=key;paintAurora(auroraLayer.cv.getContext('2d'),t)}
 c.save();c.globalAlpha*=fade;c.drawImage(auroraLayer.cv,0,20,1200,220);c.restore();
}
function paintAurora(c,t){
 c.setTransform(1,0,0,1,0,0);c.clearRect(0,0,600,110);c.setTransform(.5,0,0,.5,0,-10);
 // 정규화된 그라데이션 두 개를 좌표 변환으로 재사용한다. 색·곡선·시각은 정본 그대로다.
 if(!auroraGradients.has(c))auroraGradients.set(c,[false,true].map(middle=>{const g=c.createLinearGradient(0,0,0,1);g.addColorStop(0,'#7844ba00');g.addColorStop(.32,'#7844ba40');g.addColorStop(.7,middle?'#33edc2a0':'#50e897a0');g.addColorStop(.94,middle?'#8ae3e2':'#68ffa7');g.addColorStop(1,'#ff488d00');return g}));
 const gradients=auroraGradients.get(c);
 for(let j=0;j<3;j++){
  const edge=x=>138+j*25+29*Math.sin(x/165+t*.17+j*1.8)+19*Math.sin(x/68-t*.11+j)+7*Math.sin(x/37+t*.06);
  for(let x=16;x<1184;x+=2){
   const y=edge(x),height=103+29*Math.sin(x/140+j+t*.09),ends=Math.sin(Math.PI*(x-16)/1168)**.7;
   const ray=.18+.82*(.5+.5*Math.sin(x*1.83+1.7*Math.sin(x*.18)+t*.12+j))**3;
   const pulse=.72+.28*Math.sin(x*.008+t*.28+j);
   c.globalAlpha=ends*pulse*(.38+.55*ray)*(j===1?.95:.9);
   c.save();c.translate(x,y-height);c.scale(1,height+5);c.fillStyle=gradients[j===1?1:0];c.fillRect(0,0,2,1);c.restore();
  }
  // Soft, broken lower rim: avoid three continuous neon outlines.
  c.strokeStyle=j===1?'#8ae3e2':'#68ffa7';c.lineWidth=2;
  for(let x=20;x<1180;x+=8){const ends=Math.sin(Math.PI*(x-16)/1168)**.7;c.globalAlpha=ends*(.10+.10*Math.sin(x*.012+t*.2+j));c.beginPath();c.moveTo(x,edge(x)-3);c.lineTo(x+8,edge(x+8)-3);c.stroke()}
 }
}
// 별: 아라레처럼 노란색 · 무작위 각도로 틀어져 있고 사라지는 동안 천천히 회전한다. seed 로 각도·회전 방향이 결정(시간의 결정적 함수).
const SKY_STAR_Y='#ffd23f',SKY_STAR_EDGE='#ff9f1c';
function skyStar(c,x,y,u,seed=0,scale=1,color=SKY_STAR_Y,edge=SKY_STAR_EDGE,shadow=false){
 u=djClamp15(u);const h=k=>skyHash(seed*131+k*17+SKY_SALT*3),rot=h(1)*Math.PI*2+(h(2)<.5?-1:1)*u*1.1; // 사라지는 동안 약 63° 회전
 const a=Math.sin(Math.PI*u)**.6*(1-.35*u),r=(12+38*djEase15(Math.min(1,u*1.4)))*scale;
 c.save();c.translate(x,y);c.rotate(rot);c.fillStyle=c.strokeStyle=color;c.lineJoin='round';if(shadow){c.globalAlpha=a;c.shadowColor=color;c.shadowBlur=26*scale+4}c.beginPath();
 for(let i=0;i<8;i++){const ang=i*Math.PI/4-Math.PI/2,rr=i%2?r*.24:r;i?c.lineTo(Math.cos(ang)*rr,Math.sin(ang)*rr):c.moveTo(Math.cos(ang)*rr,Math.sin(ang)*rr)}
 c.closePath();if(shadow){c.fill();c.shadowBlur=0}else{c.globalAlpha=a*.14;c.lineWidth=20*scale+4;c.stroke();c.globalAlpha=a*.28;c.lineWidth=9*scale+2;c.stroke();c.globalAlpha=a;c.fill()}c.strokeStyle=edge;c.lineWidth=1.6*Math.max(.6,scale);c.stroke();c.restore();
}
// UFO 궤적 잔상: 지나온 경로 전체를 DECAY 초에 걸쳐 천천히 옅어지게 남긴다(UFO 가 사라진 뒤에도 남음).
const SKY_TRAIL_DECAY=9,TOGGLE_TAIL=3.4; // TOGGLE_TAIL = 토글을 끈 뒤 이미 나온 효과가 끝나는 데 걸리는 시간.
function skyTrail(c,fn,age,tmax){
 const t1=Math.min(age,tmax),t0=Math.max(0,age-SKY_TRAIL_DECAY);if(t1<=t0)return;
 const N=170;let prev=fn(t0);c.save();c.lineCap='round';c.lineJoin='round';c.shadowColor=C;
 for(let j=1;j<=N;j++){const ta=t0+(t1-t0)*j/N,p=fn(ta),k=1-(age-ta)/SKY_TRAIL_DECAY;
  if(k>0){c.globalAlpha=.78*Math.pow(k,1.1);c.strokeStyle=k>.55?C:k>.25?'#a07ae0':V;c.shadowBlur=k>.55?6:0;c.lineWidth=1.6+1.6*k;c.beginPath();c.moveTo(prev[0],prev[1]);c.lineTo(p[0],p[1]);c.stroke()}
  prev=p}
 c.restore();
}
function skyProps(c,t){
 const plan=skyPlan(TRK),env=(age,life,fade)=>djEase15(age/fade)*djEase15((life-age)/fade);
 // 세로 화면은 하늘이 위로 길다. 오로라와 고정 유성을 멘트 높이(하늘의 26%)로 올리고 폭에 맞춘다.
 const v=skyViewport,tall=activeLayout?.portrait,k=v.width/1200;
 const below=tall&&plan.ufos[0].mode==='sign'; // 사인이 나오는 곡의 오로라는 사인 아래로 내린다.
 c.save();if(tall){c.translate(v.left,v.top+v.height*(below?.56:.26)-197.5*k);c.scale(k,k)}c.beginPath();if(tall)c.rect(0,-300,1200,900);else c.rect(0,0,1200,395);c.clip();c.lineCap='round';
 for(const [a,b] of plan.quiet)if(t>=a&&t<=b)skyAurora(c,t,a,b);
 for(const m of plan.meteors)for(const p of m.parts){
  const age=t-m.birth-p.delay;if(age<0||age>p.duration)continue;
  const u=age/p.duration,x=1280-1460*u,y=p.y+p.fall*u,dy=p.len*p.fall/1460;
  const g=c.createLinearGradient(x+p.len,y-dy,x,y);g.addColorStop(0,'#7844ba00');g.addColorStop(.45,V);g.addColorStop(.84,P);g.addColorStop(1,C);
  c.globalAlpha=skyRoutineAlpha*p.alpha*env(age,p.duration,.35);c.strokeStyle=g;c.lineWidth=m.large?10:p.size;c.shadowColor=C;c.shadowBlur=m.large?22:5;c.beginPath();c.moveTo(x+p.len,y-dy);c.lineTo(x,y);c.stroke();c.fillStyle=C;c.beginPath();c.arc(x,y,p.size,0,Math.PI*2);c.fill();c.shadowBlur=0;
 }
 c.restore();
 // 유성의 원래 영역과 분리한다. 태양 펄스는 세로 화면의 확장 하늘 전체로 퍼진다.
 c.save();c.beginPath();c.rect(skyViewport.left,skyViewport.top,skyViewport.width,skyViewport.height);c.clip();c.lineCap='round';
 sunTransform(c);
 const age=t-plan.drop;
 if(!introActive()&&age>=0&&age<PULSE_LIFE.small)sunPulse(c,age,skyRoutineAlpha);
 c.restore();
}
// 효과가 겹칠 때 렉의 주범은 큰 도형의 shadowBlur 다(GPU). 움직이는 효과는 현재 경로를 넓고 옅게 겹쳐 그어 빛을 낸다.
const glowStroke=(c,alpha,width,blur)=>{c.globalAlpha=alpha*.14;c.lineWidth=width+blur*1.5;c.stroke();c.globalAlpha=alpha*.28;c.lineWidth=width+blur*.7;c.stroke();c.globalAlpha=alpha;c.lineWidth=width;c.stroke()};
// 태양 펄스 = 드롭 때 나오는 고리. 버튼 단발도 같은 그림이다. 호출 전에 sunTransform 을 적용해 둔다.
const PULSE_LIFE={small:1.6,big:2.6};
function sunPulse(c,age,k=1,lite=false){
 const u=age/PULSE_LIFE.small,e=djEase15(age/.09)*djEase15((PULSE_LIFE.small-age)/.09),g=c.createLinearGradient(550,40,1100,395);g.addColorStop(0,P);g.addColorStop(.5,V);g.addColorStop(1,C);
 for(let j=lite?0:2;j>=0;j--){const r=104+430*u-24*j;if(r<75)continue;
  c.strokeStyle=g;c.beginPath();c.arc(850,267,r,0,Math.PI*2);const width=(12-9*u)*(1-j*.17),a=k*e*(1-.65*u)*(.8-j*.15);
  if(lite){c.globalAlpha=a*.2;c.lineWidth=width+16;c.stroke();c.globalAlpha=a;c.lineWidth=width;c.stroke();return}
  glowStroke(c,a,width,18);
  if(j===0){c.globalAlpha=k*e*.065*(1-u);c.lineWidth=46;c.stroke()}
 }
 c.strokeStyle=P;c.beginPath();
 for(let j=0;j<20;j++){const ang=j*Math.PI/10,len=45*(1-u);c.moveTo(850+Math.cos(ang)*111,267+Math.sin(ang)*111);c.lineTo(850+Math.cos(ang)*(111+len),267+Math.sin(ang)*(111+len))}
 glowStroke(c,k*e*.7*(1-u),3,9);
}
// 버튼을 누르고 있는 동안의 파동. 얇은 고리 하나이며 마디의 박마다 모양이 다르다. reach = 퍼지는 거리(클릭 펄스 430).
const SMALL_WAVE={name:'small',life:1.6,reach:215,width:3};
const HOLD_WAVES=[SMALL_WAVE,SMALL_WAVE,{name:'back',life:.38,reach:60,width:2,back:true,color:'#ffd36b'},{name:'medium',life:1.6,reach:320,width:4.5}];
function sunWave(c,age,{life,reach,width,back,color=P}){
 const u=age/life,e=djEase15(age/.09)*djEase15((life-age)/.09),a=e*(back?.9:(1-.75*u)*.8),w=back?width*(.5+.5*u):width*(1-.66*u),r=104+reach*(back?1-u*u:u);
 c.strokeStyle=color;c.beginPath();c.arc(850,267,r,0,Math.PI*2);c.globalAlpha=a*.2;c.lineWidth=w+7;c.stroke();c.globalAlpha=a;c.lineWidth=w;c.stroke();
}
// 길게 눌렀다 뗀 큰 펄스: 고리 3겹이 시차를 두고 멀리 퍼지고, 빛살이 더 많고 길다.
function sunBigPulse(c,age){
 const life=PULSE_LIFE.big,u=age/life,e=djEase15(age/.09)*djEase15((life-age)/.3),g=c.createLinearGradient(400,-100,1300,500);g.addColorStop(0,P);g.addColorStop(.33,'#ffd36b');g.addColorStop(.66,V);g.addColorStop(1,C);
 const bloom=c.createRadialGradient(850,267,100,850,267,240+150*u);bloom.addColorStop(0,'#fff2c900');bloom.addColorStop(.28,'#ffdca0');bloom.addColorStop(.6,C);bloom.addColorStop(1,'#8ae3e200');
 c.globalAlpha=e*.09*(1-u)**2;c.fillStyle=bloom;c.fillRect(460,-123,780,780);
 for(let wave=0;wave<3;wave++){const a=age-wave*.22;if(a<0)continue;const q=a/(life-.44);if(q>=1)continue;
  for(let j=2;j>=0;j--){const r=104+1150*q-30*j;if(r<75)continue;
   c.strokeStyle=g;c.beginPath();c.arc(850,267,r,0,Math.PI*2);glowStroke(c,e*(1-.8*q)*(.95-j*.2),(20-15*q)*(1-j*.18),22);
   if(j===0){c.globalAlpha=e*.09*(1-q);c.lineWidth=80;c.stroke();c.strokeStyle='#e5ffff';c.beginPath();c.arc(850,267,r,.3+wave*2.1,1.4+wave*2.1);glowStroke(c,e*.75*(1-q),2.5,8)}
  }
 }
 for(const [color,hit] of [['#ffe9b0',j=>j%3],[C,j=>!(j%3)]]){c.strokeStyle=color;c.beginPath();
  for(let j=0;j<40;j++){if(!hit(j))continue;const ang=j*Math.PI/20+.08*u,inner=118+240*u,len=(j%2?75:170)*(1-u);c.moveTo(850+Math.cos(ang)*inner,267+Math.sin(ang)*inner);c.lineTo(850+Math.cos(ang)*(inner+len),267+Math.sin(ang)*(inner+len))}
  glowStroke(c,e*.85*(1-u),4,12);
 }
}
// UFO·궤적·사인: 유노 바로 뒤 · 그 밖의 모든 요소(halo·LED·유성·오로라 등) 앞에 그린다.
function skyUfos(c,t,events=skyPlan(TRK).ufos){
 const plan=skyPlan(TRK),env=(age,life,fade)=>djEase15(age/fade)*djEase15((life-age)/fade);
 const portrait=activeLayout?.portrait;
 const point=p=>portrait?[skyViewport.left+skyViewport.width*(.08+.84*p[0]/1200),skyViewport.top+skyViewport.height*(.06+.52*p[1]/395),p[2]]:p;
 c.save();c.beginPath();c.rect(skyViewport.left,skyViewport.top,skyViewport.width,skyViewport.height);c.clip();c.lineCap='round';
 if(skyUFO.complete&&skyUFO.naturalWidth)for(const f of events){
  const age=t-f.birth,life=f.end-f.birth;if(age<0||age>life+SKY_TRAIL_DECAY)continue;
  if(f.type===1){
   if(f.mode==='sign'){const fit=f.fit||fitSkySign(skyViewport,portrait,f.place);c.save();c.translate(fit.x,fit.y);c.scale(fit.scale,fit.scale);tiltSign(c,f.tilt);skySignDraw(c,f,age);c.restore();continue}
   skyTrail(c,ta=>point(skyZig(f,ta/f.flight)),age,f.flight);
   if(age>f.flight){if(age<=f.flight+1.3){const p=point(f.zig.pts.at(-1));skyStar(c,p[0],p[1],(age-f.flight)/1.3,998)}continue}
   for(let j=0;j<0;j++){const ta=age-.22*(1-j/26),tb=age-.22*(1-(j+1)/26);if(ta<0)continue;const a=skyZig(f,ta/f.flight),b=skyZig(f,tb/f.flight);c.globalAlpha=skyRoutineAlpha*.55*(j/26)**1.4*env(age,f.flight,.09);c.strokeStyle=j<13?V:C;c.lineWidth=2.8;c.beginPath();c.moveTo(a[0],a[1]);c.lineTo(b[0],b[1]);c.stroke()}
   const [x,y,angle]=point(skyZig(f,age/f.flight));c.save();c.translate(x,y);c.rotate(Math.sin(angle)*.16);c.globalAlpha=skyRoutineAlpha*env(age,f.flight,.09);c.shadowColor=P;c.shadowBlur=7;c.drawImage(skyUFO,-27,-27,54,54);c.restore();
  }else{
   skyTrail(c,ta=>{const q=skyUfo2(f,ta);return point([q.x,q.y])},age,life);
   if(age>life)continue;
   const pos={...skyUfo2(f,age)},alpha=env(age,life,.65),mapped=point([pos.x,pos.y]);pos.x=mapped[0];pos.y=mapped[1];
   if(pos.scanning){
    const e=djEase15(pos.u/.18)*djEase15((1-pos.u)/.18),sx=pos.x+2*Math.cos(pos.tilt)-11*Math.sin(pos.tilt),sy=pos.y+2*Math.sin(pos.tilt)+11*Math.cos(pos.tilt);
    const bottom=386,depth=Math.max(0,bottom-sy),width=Math.min(95,skyViewport.width*.19,depth*.30);
    const base=Math.max(skyViewport.left+width,Math.min(skyViewport.left+skyViewport.width-width,sx+Math.sin(pos.u*Math.PI*2)*Math.min(45,depth*.12)));
    if(depth>12){
     c.save();c.globalAlpha=skyRoutineAlpha*alpha*e*.82;const g=c.createLinearGradient(0,sy,0,bottom);g.addColorStop(0,'#d8fffee6');g.addColorStop(.3,'#8ae3e2b0');g.addColorStop(.75,'#8ae3e24d');g.addColorStop(1,'#8ae3e200');
     c.fillStyle=g;c.beginPath();c.moveTo(sx-12,sy);c.lineTo(base-width,bottom);c.quadraticCurveTo(base,bottom+7,base+width,bottom);c.lineTo(sx+12,sy);c.closePath();c.fill();
     const glow=c.createRadialGradient(base,0,0,base,0,Math.max(1,width));glow.addColorStop(0,'#c6fffdcc');glow.addColorStop(1,'#8ae3e200');
     c.translate(0,bottom);c.scale(1,.07);c.fillStyle=glow;c.fillRect(base-width,-width,width*2,width*2);c.restore();
    }
   }
   c.save();c.globalAlpha=skyRoutineAlpha*alpha;c.translate(pos.x,pos.y);c.rotate(pos.tilt);c.shadowColor=P;c.shadowBlur=7;c.drawImage(skyUFO,-31,-31,62,62);c.restore();
  }
 }
  c.restore();
}
function visual(c,type,t){const n=48,arr=Array.from({length:n},(_,i)=>spectrum19(t,Math.min(i,n-1-i)*2,n));
if(type===0){c.shadowColor=P;c.shadowBlur=10;for(let i=0;i<72;i++){const a=i/72*Math.PI*2;const h=spectrum19(t,Math.min(i,71-i),36).height*.63;line(c,[[850+Math.cos(a)*116,267+Math.sin(a)*116],[850+Math.cos(a)*(116+h),267+Math.sin(a)*(116+h)]],i%6===0?C:P,3.2)}c.shadowBlur=0;c.strokeStyle=V;c.lineWidth=1;c.beginPath();c.arc(850,267,111,0,7);c.stroke()}
if(type===1){const K=1.45;let reflection=c.createLinearGradient(0,405,0,550);reflection.addColorStop(0,'#8ae3e260');reflection.addColorStop(.65,'#7844ba18');reflection.addColorStop(1,'#7844ba00');for(let i=0;i<n;i++){let x=62+i*22.7,h=arr[i].height*K;c.fillStyle=i%4===0?C:P;c.shadowColor=c.fillStyle;c.shadowBlur=7;c.fillRect(x,399-h,10,h);c.shadowBlur=0;c.fillStyle=C;c.globalAlpha=.7;c.fillRect(x,395-arr[i].cap*K,10,2);c.globalAlpha=1;c.fillStyle=reflection;c.save();c.filter='blur(3px)';c.fillRect(x,405,10,h*.85);c.restore()}line(c,[[50,402],[1150,402]],C,1,.5)}
if(type===5){
 // v7 FX: immutable analysis cache; every pose is sampled from song time.
 const TAU=Math.PI*2,clamp=djClamp15,smooth=djEase15;
 const {bp,E,bs,drop,midnight}=skyStructure(t);
 const opened=smooth((bp-bs)/(drop-bs)),full=smooth((bp-drop)/2),build=opened*(1-full),riser=smooth((bp-(drop-8))/8)*(1-full);
 const energy=clamp(.45*E.kick+.25*E.accent+.18*E.mid+.12*E.high);
 const drive=full*smooth((E.kick-.12)/.58),presence=clamp(.35*E.low+.35*E.mid+.3*E.high);
 const density=clamp(.30+.38*opened+.32*drive)*smooth(presence/.12);
 const breath=.5+.5*Math.sin(TAU*bp/8),baseR=110+3*breath-2*riser;
 const pulse=age=>age<0||age>=.5?0:age<.035?1-Math.pow(1-age/.035,2):Math.pow(1-smooth((age-.035)/.465),1.35); // 상승 35ms(급) · 하강 ~0.47s(완만)
 const lobes=[];let punch=0;
 const kb=beatIdx(t);
 for(let j=Math.max(0,kb-3);j<=kb;j++){
  const age=t-TRK.beats[j],p=pulse(age),weight=midnight?(j%2===0?1:.55):1;
  const str=(.18+.82*TRK.kick[j])*weight,power=p*(.16+.32*build+1.0*drive)*(.55+.45*str);
  // Odd multiplier permutes all eight sectors; bounded jitter cannot leave its sector.
  const sector=(j*5+Math.floor(j/8)*3)%8,a=(sector+.15+.7*spectrumHash19(j,53))/8*TAU;
  const sharp=spectrumHash19(j,67),amp=.65+.6*spectrumHash19(j,71),width=(.48+.16*spectrumHash19(j,59))*(1-.25*riser);
  lobes.push({a,w:width,e:power*amp,m:sharp},{a:a+Math.PI,w:width*.9,e:power*amp*.8,m:sharp},{a:a+1.5,w:width*.7,e:power*.35,m:1-sharp});
  punch+=p*str;
 }
 const peak=yunoEyesClosed?.01:1; // 볼륨 0 · 음소거면 후광 · LED 의 비트 피크를 1/100 로 줄여 안 듣고 있는 게 보인다.
 const field=a=>{
  let e=0;for(const h of lobes){const d=Math.abs(Math.atan2(Math.sin(a-h.a),Math.cos(a-h.a)))/h.w;if(d<1)e+=h.e*((1-h.m)*Math.cos(d*Math.PI/2)**2+h.m*(1-d)**4)}return Math.min(1.2,e)*peak;
 };
 const lengths=Array.from({length:88},(_,i)=>{const a=i/88*TAU-Math.PI/2;return 3+peak*(4*presence+4*E.high*(.5+.5*Math.sin(5*a+bp*.12)))+138*field(a)});
 c.save();c.beginPath();c.rect(-2000,-2000,5200,2395);c.clip();
 sunTransform(c);const cx=850,cy=267,segment=(a,r,len)=>{c.beginPath();c.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);c.lineTo(cx+Math.cos(a)*(r+len),cy+Math.sin(a)*(r+len));c.stroke()};
 c.lineCap='round';
 // 후광 선은 많아서 선마다 그라데이션 · 그림자를 두지 않고 한 경로로 묶는다.
 {const r=baseR+5,fade=c.createRadialGradient(cx,cy,r,cx,cy,r+150);fade.addColorStop(0,'#7844ba88');fade.addColorStop(1,'#7844ba00');c.strokeStyle=fade;c.lineWidth=.9;c.globalAlpha=.5+.4*presence;c.beginPath();
  for(let i=0;i<180;i++){const a=i/180*TAU,len=8+130*field(a)+peak*12*E.high;c.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);c.lineTo(cx+Math.cos(a)*(r+len),cy+Math.sin(a)*(r+len))}c.stroke()}
 c.beginPath();for(let i=0;i<=256;i++){const a=i/256*TAU,r=baseR-3+2*breath+30*field(a),xx=cx+Math.cos(a)*r,yy=cy+Math.sin(a)*r;i?c.lineTo(xx,yy):c.moveTo(xx,yy)}
 c.closePath();c.strokeStyle=P;c.lineWidth=1.9;c.globalAlpha=.6+.4*presence;c.stroke();
 const spokes=(color,alpha,width,pick)=>{c.strokeStyle=color;c.globalAlpha=alpha;c.lineWidth=width;c.beginPath();for(let i=0;i<88;i++){if(!pick(i))continue;const a=i/88*TAU-Math.PI/2,r=baseR+5,len=lengths[i];c.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);c.lineTo(cx+Math.cos(a)*(r+len),cy+Math.sin(a)*(r+len))}c.stroke()};
 const body=.7+.3*presence,lit=lengths.map((_,i)=>Math.min(4,Math.ceil(clamp(field(i/88*TAU-Math.PI/2)*1.5)*4)));
 spokes(P,body*.3,7,i=>i%3===0);spokes(V,body*.3,7,i=>i%3!==0);spokes(P,body,4,i=>i%3===0);spokes(V,body,4,i=>i%3!==0);
 for(let n=1;n<=4;n++)spokes(C,.9*n/4,4,i=>lit[i]===n);
 c.restore();
 // Smooth finite-window band samples and finite-history peak: independent of playback history.
 const band=(now,i)=>bandLvl(Math.max(0,now),Math.min(i,39-i)*2,40); // 평활 없음: 원 신호 그대로(피크가 살아 있게)
 const heights=[],caps=[],alphas=[];
 for(let i=0;i<40;i++){
  const distance=Math.abs((i-19.5)/19.5),mask=smooth((density-distance)/.18),b=band(t,i);
  let kickwave=0;for(let j=Math.max(0,kb-3);j<=kb;j++){const age=t-TRK.beats[j]-distance*.22,w=midnight?(j%2===0?1:.5):1;kickwave+=pulse(age)*TRK.kick[j]*w}
  const heightAt=now=>mask*(.3+peak*((2+6*opened+3*drive)*band(now,i)+1.5*build*E.high+1.7*drive*kickwave));
  let level=heightAt(t);for(let k=1;k<=10;k++)level=Math.max(level,heightAt(t-k*.03)-k*1.35); // 상승 즉시 · 하강은 초당 ~45칸(약 0.33s)
  level=Math.min(14.8,level);let cap=level;
  for(let k=1;k<=6;k++)cap=Math.max(cap,heightAt(t-k*.06)-k*.16);
  heights.push(level*9.5);caps.push(cap*9.5);alphas.push(mask*(.88+.12*energy));
  const xx=63+i*27.3;
  for(let j=0;j<15;j++){
   const on=clamp(level-j),col=j>10?P:j>6?V:C;if(on<=.005)continue;
   c.fillStyle=col;c.globalAlpha=alphas[i]*on*.16;c.fillRect(xx-2,398-(j+1)*9.5-2,19,11);c.globalAlpha=alphas[i]*on;c.fillRect(xx,398-(j+1)*9.5,15,7);
   if(j<7){c.globalAlpha=alphas[i]*on*.30*(1-j/7);c.fillRect(xx,402+j*9.5,15,7)}
  }
  if(level>.05){c.fillStyle=cap>10?P:C;c.globalAlpha=alphas[i]*smooth(level/.5);c.fillRect(xx,398-(cap+1)*9.5-1,15,2)}
 }
 c.globalAlpha=1;
 // Read-only diagnostics of the exact geometry used by this render (no influence on output).
 snapshot={t,bp,E,density,drive,build,riser,heights,caps,alphas,lengths,baseR,punch};
}
 if(type===2){for(let layer=2;layer>=0;layer--){const pts=[];for(let i=0;i<=64;i++){let f=i/64,h=0;for(let d=-2;d<=2;d++)h+=spectrum19(Math.max(0,t-layer*.13),Math.max(0,Math.min(63,Math.min(i,64-i)*2+d)),64).height/5;pts.push([45+1110*f,401-h*(.95+layer*.36)])}c.beginPath();c.moveTo(...pts[0]);for(let i=1;i<pts.length-1;i++){let a=pts[i],b=pts[i+1];c.quadraticCurveTo(...a,(a[0]+b[0])/2,(a[1]+b[1])/2)}c.lineTo(...pts.at(-1));let path=new Path2D(); /* paths are rebuilt to keep curves and fills identical */
const stroke=new Path2D();stroke.moveTo(...pts[0]);for(let i=1;i<pts.length-1;i++){let a=pts[i],b=pts[i+1];stroke.quadraticCurveTo(...a,(a[0]+b[0])/2,(a[1]+b[1])/2)}stroke.lineTo(...pts.at(-1));path.addPath(stroke);path.lineTo(1155,404);path.lineTo(45,404);path.closePath();let g=c.createLinearGradient(0,230,0,404);g.addColorStop(0,layer===0?'#8ae3e24d':'#7844ba4d');g.addColorStop(1,'#ff488d05');c.fillStyle=g;c.fill(path);c.strokeStyle=[C,P,V][layer];c.lineWidth=2.4;c.shadowColor=c.strokeStyle;c.shadowBlur=19;c.stroke(stroke);c.shadowBlur=6;c.stroke(stroke);c.shadowBlur=0}}
if(type===3){for(let row=0;row<16;row++){const z=row/15,scale=.22+.78*z,y=411+z*z*290,amp=scale*1.15,hs=past(t-(1-z)*3.6);let pts=hs.map((h,i)=>[600+(i/63-.5)*1170*scale,y-(h-16)*amp]);c.beginPath();c.moveTo(...pts[0]);pts.forEach(p=>c.lineTo(...p));c.lineTo(pts.at(-1)[0],y+8);c.lineTo(pts[0][0],y+8);c.closePath();c.fillStyle='#1c1029';c.fill();line(c,pts,row%4===0?C:P,1.4,.2+.65*z)}}
if(type===4){for(let i=0;i<40;i++){let h=spectrum19(t,Math.min(i,39-i)*2,40),x=63+i*27.3,level=h.height/8,cap=Math.min(14,(h.cap-4)/8);for(let j=0;j<15;j++){c.fillStyle=j>10?P:j>6?V:C;c.globalAlpha=.065+.88*Math.max(0,Math.min(1,level-j));c.fillRect(x,393-j*11,15,6)}c.globalAlpha=.85;c.fillStyle=P;c.fillRect(x,393-cap*11,15,2)}c.globalAlpha=1}
}

// 바닥 세로선 — 지평선 근처에서 화면 좌우 끝까지 닿도록 멀리까지 같은 간격으로 잡는다.
const GRID_X=[];for(let x=-7800;x<=9000;x+=150)GRID_X.push(x);
function groundGrid(c){line(c,[[0,395],[1200,395]],P,1.5,.5);for(const x of GRID_X)line(c,[[600,389],[x,760]],P,1,.22);for(let j=1;j<=12;j++){let y=395+365*(j/12)**2.5;line(c,[[0,y],[1200,y]],P,1,.12+j*.015)}}
const FL={};
function floorWave(c,type,t){
 // Grid Current(D안, 기존 효과 그대로): 지나가는 보라→분홍→시안 띠가 '격자선 위에만' 발광한다.
 // 추가(v2-b): 격자 자체가 느리게 뒤쪽(지평선)으로 이동 · 멀어질수록 투명 · 가장자리는 좌우로 페이드.
 c.save();c.beginPath();c.rect(0,395,1200,groundBottom-395);c.clip();
 let g=c.createLinearGradient(0,395,0,760);g.addColorStop(0,'#250e30');g.addColorStop(1,'#110e20');c.fillStyle=g;c.fillRect(0,395,1200,groundBottom-395);
 const mk=k=>{const cv=FL[k]||(FL[k]=document.createElement('canvas')),h=Math.ceil(groundBottom);if(cv.width!==1200||cv.height!==h){cv.width=1200;cv.height=h}return cv};
 const grid=mk('g'),gc=grid.getContext('2d'),mask=mk('m'),mc=mask.getContext('2d'),bands=mk('b'),w=bands.getContext('2d');
 [gc,mc,w].forEach(x=>{x.globalCompositeOperation='source-over';x.clearRect(0,0,1200,groundBottom)});
 const bp=beatPos(t),beat=1+.03*Math.cos(2*Math.PI*bp);
 const yBeyond=z=>395+365*z**2.5>groundBottom;const N=12,s=Math.max(0,bp)/4;           // 격자 한 칸 = 4박, 지평선 쪽으로(박 위치에 고정)
 const smooth=(a,b,x)=>{x=Math.min(1,Math.max(0,(x-a)/(b-a)));return x*x*(3-2*x)};
 // 가로선: z 가 줄어들며 지평선으로 이동. 거리(z)가 작을수록 크게 투명해진다(z^1.6 · 지평선 근처는 거의 0).
 const lineAlpha=z=>(.03+.34*z**1.6)*smooth(0,.22,z)*beat;
 gc.lineWidth=1;mc.lineWidth=1.8;
 for(let j=0;j<=N*Math.pow((groundBottom-395)/365,.4)+2;j++){
  const z=(j-s%1)/N;if(z<=0||yBeyond(z))continue;
  const y=395+365*z**2.5,al=lineAlpha(z);
  gc.strokeStyle=`rgba(255,72,141,${al})`;gc.beginPath();gc.moveTo(0,y);gc.lineTo(1200,y);gc.stroke();
  mc.strokeStyle=`rgba(255,72,141,${smooth(0,.2,z)})`;mc.beginPath();mc.moveTo(0,y);mc.lineTo(1200,y);mc.stroke();
 }
 // 세로 방사선: 위치 고정, 소실점 근처는 투명 → 앞쪽으로 갈수록 진해짐.
 // 선이 많아 프레임마다 그리지 않는다. 모양은 크기에만 달렸으니 한 번 그려 두고 복사한다.
 for(const [ctx,m,name] of [[gc,1,'radialG'],[mc,3.2,'radialM']]){
  const layer=FL[name]??=document.createElement('canvas'),key=[ctx.canvas.width,ctx.canvas.height,groundBottom,ctx.lineWidth].join(':');
  if(layer.dataset.key!==key||!layer.width){
   layer.width=ctx.canvas.width;layer.height=ctx.canvas.height;layer.dataset.key=key;
   const lc=layer.getContext('2d');lc.setTransform(ctx.getTransform());lc.lineWidth=ctx.lineWidth;lc.lineCap=ctx.lineCap;
   for(const x of GRID_X){
    const ex=600+(x-600)*(groundBottom-389)/371,gr=lc.createLinearGradient(600,389,ex,groundBottom);
    gr.addColorStop(0,'rgba(255,72,141,0)');gr.addColorStop(.18,m>1?'rgba(255,72,141,1)':'rgba(255,72,141,.04)');gr.addColorStop(1,m>1?'rgba(255,72,141,1)':'rgba(255,72,141,.26)');
    lc.strokeStyle=gr;lc.beginPath();lc.moveTo(600,389);lc.lineTo(ex,groundBottom);lc.stroke();
   }
  }
  ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.drawImage(layer,0,0);ctx.restore();
 }
 // 열마다 같은 색 정지점을 다시 만들지 않고 한 프레임의 띠 그라데이션을 공유한다.
 const bandStops=[];
 for(let k=0;k<=8;k++){const f=k/8,d=2*f-1,al=(1-d*d)**2*beat*.72,col=f<.5?[120+(255-120)*f*2,68+4*f*2,186-45*f*2]:[255-117*(f-.5)*2,72+155*(f-.5)*2,141+85*(f-.5)*2];bandStops.push([f,`rgba(${col.map(Math.round)},${al})`])}
 // 발광 띠(Grid Current): 6.8초에 걸쳐 앞으로 다가오는 그라데이션 띠.
 // Arc Tide 와 반대로 '가운데가 앞쪽(아래)으로 튀어나온' 볼록한 굴곡 — 가운데가 가장 먼저 닿고 가장자리가 뒤처진다.
 for(let id=Math.floor(bp/4)-3;id<=Math.floor(bp/4);id++){
  const u=(bp-id*4)/12;   // 4박마다 새 띠 · 12박(3마디)에 걸쳐 앞으로
  if(u<0||u>1.18)continue;
  const y=395+365*u**2.5,width=7+76*u**1.5,bulge=46*Math.min(1,u*1.1);
  const bandGradient=w.createLinearGradient(0,y-width,0,y+width);for(const [stop,color] of bandStops)bandGradient.addColorStop(stop,color);
  for(let x=0;x<1200;x+=10){
   const r=(x+5-600)/600,yc=y+bulge*(1-r*r),y0=yc-width,y1=yc+width;   // 가운데 앞쪽(아래)으로 볼록
   if(y1<395||y0>groundBottom-1)continue;
   w.save();w.translate(0,yc-y);w.fillStyle=bandGradient;
   w.fillRect(x,Math.max(395,y0)-(yc-y),10,Math.min(groundBottom,y1)-Math.max(395,y0));w.restore();
  }
 }
 // 지평선 근처 페이드인(reveal): y 405→450 구간에서 서서히 나타남
 w.globalCompositeOperation='destination-in';const rv=w.createLinearGradient(0,405,0,450);rv.addColorStop(0,'rgba(0,0,0,0)');rv.addColorStop(1,'rgba(0,0,0,1)');w.fillStyle=rv;w.fillRect(0,0,1200,groundBottom); // destination-in 은 그린 영역 밖을 지우므로 전체를 한 번에 채운다
 w.globalCompositeOperation='destination-in';w.drawImage(mask,0,0);
 // 가장자리 페이드: 좌우 끝으로 갈수록 격자·발광이 옅어진다(화면 가장자리에서 선이 뚝 끊겨 보이지 않게).
 const edge=c2=>{c2.globalCompositeOperation='destination-in';const eg=c2.createLinearGradient(0,0,1200,0);eg.addColorStop(0,'rgba(0,0,0,.18)');eg.addColorStop(.22,'rgba(0,0,0,.85)');eg.addColorStop(.5,'rgba(0,0,0,1)');eg.addColorStop(.78,'rgba(0,0,0,.85)');eg.addColorStop(1,'rgba(0,0,0,.18)');c2.fillStyle=eg;c2.fillRect(0,0,1200,groundBottom)};
 edge(gc);edge(w);
 c.drawImage(grid,0,0);c.drawImage(bands,0,0);
 c.strokeStyle='rgba(255,72,141,.5)';c.lineWidth=1.5;c.beginPath();c.moveTo(0,395);c.lineTo(1200,395);c.stroke();
 c.restore();
}

 const canvas=document.createElement('canvas');canvas.draggable=false;canvas.style.cssText='width:100%;height:100%;display:block';host.append(canvas);
 const lightLayer=document.createElement('canvas'),frontLayer=document.createElement('canvas'),spotLayer=document.createElement('canvas');let spotCacheKey=null;
 // 밝기 증폭 뒤 부모에서 다시 감쇠하면 8비트 색이 먼저 클리핑된다. 레이어별 최종 밝기를 합성한다.
 for(const layer of [frontLayer,lightLayer]){layer.draggable=false;layer.style.cssText='position:absolute;left:0;top:0;pointer-events:none;display:none';host.append(layer)}
 lightLayer.style.width=lightLayer.style.height='100%';
 function setBrightness(value){canvas.style.filter=value===1?'':`brightness(${value})`; // 필터가 남아 있으면 전체 화면을 매 프레임 한 번 더 합성한다.
 frontLayer.style.filter=`brightness(${value*(1+effect.spot*1.85)})`}

 const backdrop=createBirthdayBackdrop();
 const c=canvas.getContext('2d');let clock=()=>0,still=false,dead=false,raf=0,visible=true,layout=null,lastT=null,parts=[],lastFrame=0;
 let manual=null,returnAt=-Infinity,pendingFinale=false,grandListener=null;
 const manualEffects=new Map(),toggles={fireworks:null,shower:null},shots=[],pulses=[];let toggleParticles=0,lastShot=-Infinity,pulseHolding=false,holdIndex=-1,pendingBig=null;
 const hasManual=()=>!!manual||manualEffects.size>0,hasToggles=()=>!!toggles.fireworks||!!toggles.shower||shots.length>0||pulses.length>0||pulseHolding||!!pendingBig;
 // 클릭 파는 나올 때 정한 모양으로 끝까지 간다. 많이 겹치면 고리 하나로 시작한다.
 function addPulse(big,wave){const now=performance.now()/1000,lite=!big&&!wave&&pulses.filter(p=>!p.big&&!p.wave&&now-p.start<PULSE_LIFE.small).length>=2;pulses.push({start:now,big,wave,lite});if(pulses.length>16)pulses.shift();lastT=null;resume()}
 // 펄스 버튼을 누르고 있는 동안 곡의 박마다 마디 안 순서대로 한 파씩(1·2박 작게, 3박 안으로 되돌아오게, 4박 중간), 떼면 바로 다음 박에 큰 펄스. 일시정지라 박이 오지 않으면 시간으로 대신한다.
 function stepPulseHold(t,wall){
  if(pulseHolding&&TRK){const j=beatIdx(t);if(holdIndex>=0&&j!==holdIndex)addPulse(false,HOLD_WAVES[j%4]);holdIndex=j}
  if(pendingBig&&(t>=pendingBig.at||wall>=pendingBig.deadline)){pendingBig=null;addPulse(true)}
 }
 function drawToggles(wall){
  toggleParticles=0;
  // 끈 토글은 새로 쏘지 않고 이미 나온 폭죽 · 유성이 끝날 때까지만 남는다.
  for(const kind of ['fireworks','shower'])if(toggles[kind]?.stopAt&&(still||wall-toggles[kind].stopAt>TOGGLE_TAIL))toggles[kind]=null;
  while(shots.length&&wall-shots[0].start>SHELL_LIFE)shots.shift();
  const small=host.clientWidth<700,room=Math.max(0,(small?1900:3200)*quality-parts.length),fire=toggles.fireworks;
  if(fire||shots.length){const frame=fire?fireworkFrame(wall-fire.start,fire.seed,skyViewport,{small,reduced:still,budget:room,until:fire.stopAt?fire.stopAt-fire.start:Infinity}):{particles:[],rockets:[]};
   // 단발은 몇 번을 눌러도 한 발씩 다 보이도록 많을수록 입자만 줄인다.
   const left=room-frame.particles.length-frame.rockets.length,count=Math.max(24,Math.min(small?56:96,Math.floor(left/Math.max(1,shots.length))));
   for(const shot of shots){const one=fireworkShot(wall-shot.start,shot.seed,skyViewport,{small,reduced:still,budget:Math.max(0,room-frame.particles.length-frame.rockets.length),count});frame.particles.push(...one.particles);frame.rockets.push(...one.rockets)}
   toggleParticles=frame.particles.length+frame.rockets.length;c.save();c.beginPath();c.rect(skyViewport.left,skyViewport.top,skyViewport.width,skyViewport.height);c.clip();drawFireworkFrame(c,frame);c.restore()}
  if(toggles.shower){const {start,stopAt}=toggles.shower,t=wall-start,cut=age=>stopAt?age-(wall-stopAt):Infinity,shower=age=>skyExtra('shower',age,{cut:cut(age)});
   shower(still?1:t%1.6);if(!still&&t>=1.6)shower(t%1.6+1.6);if(!still&&t%18<8)skyExtra('comet',t%18,{cut:cut(t%18)})}
 }
 function manualFlight(kind){
  const seed=Math.floor(Math.random()*1000000),sign=kind==='sign',flight=sign?skySign.T+skySign.INTRO:4.25,reveal=flight+.92,fade=sign?5.5:0;
  return {type:1,mode:sign?'sign':'zig',birth:0,end:sign?reveal+fade:4.75,flight,reveal,fade,place:Math.random()<.5?'left':'center',tilt:sign?(Math.random()*2-1)*SIGN_TILT:0,zig:skyMakePath(seed)};
 }
 function startManual(kind){
  // 사인과 YMMT 는 자리가 겹치므로 나중에 누른 쪽으로 바뀐다.
  if(kind==='sign')manualEffects.delete('ymmt');if(kind==='ymmt')manualEffects.delete('sign');
  const f=kind==='ymmt'?null:manualFlight(kind),dur=kind==='ymmt'?9:Math.max(3,kind==='sign'?f.reveal+SIGN_BURST:f.end+SKY_TRAIL_DECAY);
  manualEffects.set(kind,{kind,start:performance.now()/1000,dur,f});lastT=null;resume();
 }
 const costs=[];
 // 프레임이 41fps 아래로 0.6초쯤 이어지면 입자 · 유성 수를 줄인다. 되돌리는 건 6초 동안 느린 프레임이 없을 때만 — 자주 오르내리면 효과가 깜빡여 오히려 끊겨 보인다.
 let quality=1,slow=0,lastDraw=0,lastSlow=0;
 function pace(now){
  const gap=now-lastDraw;lastDraw=now;if(gap>=250)return;
  if(gap>24){lastSlow=now;slow++}else slow=Math.max(0,slow-.5);
  if(slow>=24&&quality>.4){quality=Math.max(.4,quality-.3);slow=0}else if(quality<1&&now-lastSlow>6000){quality=Math.min(1,quality+.3);lastSlow=now}
 }
 // 완주 피날레: 부채꼴로 번지는 1막 → 하늘 전체 2막 → 금빛 대폭발 3막, 약 4.5초.
 function playFinale(){if(dead||still||document.hidden||!visible)return;parts=[];
  const r=host.getBoundingClientRect(),small=r.width<700,density=small?.6:1,reach=Math.max(.85,Math.min(1.6,r.width/900)),colors=['#ff477d','#efb62f','#6ee7f9','#c4a1ff','#ff9f6b','#fff9ec'];
  const burst=(x,y,delay,count,speed,life,color,accent)=>{const n=Math.round(count*density);for(let i=0;i<n;i++){const outer=i%4!==0,a=i*Math.PI*2/n+Math.random()*.06,v=(outer?speed*(.72+Math.random()*.42):speed*(.2+Math.random()*.3))*reach;parts.push({x:r.width*x,y:r.height*y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,age:0,color:i%3===0?accent:color,r:1.1+Math.random()*(outer?1.9:1.2),delay,life:life*(.8+Math.random()*.3)})}};
  [[.5,.3],[.3,.24],[.7,.24],[.14,.32],[.86,.32],[.5,.14]].forEach(([x,y],j)=>burst(x,y,j*.16,84,92,2.6,colors[j%6],'#fff9ec'));
  [[.22,.14],[.78,.14],[.38,.36],[.62,.36],[.08,.18],[.92,.18],[.5,.22],[.3,.08],[.7,.08]].forEach(([x,y],j)=>burst(x,y,1.05+j*.13,96,104,2.7,colors[(j+2)%6],'#ffdc9b'));
  [[.5,.2],[.25,.2],[.75,.2],[.38,.1],[.62,.1],[.12,.28],[.88,.28],[.5,.36],[.32,.34],[.68,.34]].forEach(([x,y],j)=>burst(x,y,2.5+j*.05,140,132,3.1,j%2?'#ffd36b':'#fff1c4',colors[j%6]));
  lastFrame=performance.now();resume()}
 const ymmtShape=ymmtLetters(SKY_SALT),ymmtAngle=ymmtTilt(SKY_SALT);
 // 감사 카드를 닫은 뒤의 큰 장면: UFO 가 사인을 그리는 동안 별자리 · 유성우 · 혜성을 함께 그린다.
 // 사인은 원래 이벤트와 같은 skyUfos 경로이고 자리만 grandLayout 을 따른다. 장면은 사인 완성 뒤 쏟아지는 유성까지 이어진다.
 function skyGrand(age){
  const layout=grandLayout(skyViewport,activeLayout?.portrait);
  skyExtra('comet',age);if(age<12)skyExtra('shower',age%4);skyExtra('rainbow',Math.max(0,age-.3));
  if(still)skyExtra('constellation',4,{box:layout.ymmt});else if(age<manual.f.end)skyExtra('ymmt-sync',age,{box:layout.ymmt,f:manual.f,signScale:layout.sign.scale});
  skyUfos(c,still?manual.f.reveal+.5:age,[{...manual.f,fit:layout.sign}]);signBurst(age-manual.f.reveal);
 }
 // 사인이 완성되는 순간(age=0)부터 YMMT 완성처럼 무지개 유성 · 혜성을 쏟는다. 모션 줄이기에서는 그리지 않는다.
 function signBurst(age){
  if(still||age<0||age>=SIGN_BURST)return;
  skyExtra('rainbow',age,{thin:.7});skyExtra('comet',age);
  if(age<SALVO_LIFE){const frame=fireworkSalvo(age,TRK.bpm+SKY_SALT,skyViewport,{small:host.clientWidth<700,budget:(host.clientWidth<700?700:1400)*quality}),v=skyViewport;c.save();c.beginPath();c.rect(v.left,v.top,v.width,v.height);c.clip();drawFireworkFrame(c,frame);c.restore()}
 }
 // 버튼 태양 펄스. 고정 이벤트를 막지 않고 유노 뒤 하늘에 겹쳐 그린다.
 function drawPulses(wall){
  while(pulses.length&&wall-pulses[0].start>=PULSE_LIFE.big)pulses.shift();
  if(!pulses.length)return;
  const v=skyViewport;c.save();c.beginPath();c.rect(v.left,v.top,v.width,v.height);c.clip();c.lineCap='round';sunTransform(c);
  for(const p of pulses){const age=wall-p.start;if(p.big)sunBigPulse(c,age);else if(p.wave){if(age<p.wave.life)sunWave(c,age,p.wave)}else if(age<PULSE_LIFE.small)sunPulse(c,age,1,p.lite)}
  c.restore();
 }
 // 완성된 YMMT 네온을 한 번만 구워 둔다. 층 구성은 사인(skySign.glow · core)과 같고 색만 파랗다. k = 사인 두께 대비 배율.
 const ymmtLayers={key:0,glow:null,core:null};
 function ymmtNeon(k){
  if(ymmtLayers.key===k)return ymmtLayers;
  const S=2,bake=(paint)=>{const cv=document.createElement('canvas');cv.width=720;cv.height=240;const x=cv.getContext('2d');x.scale(S,S);x.translate(20,20);x.lineCap=x.lineJoin='round';
   const line=(color,width,shadow,blur)=>{x.strokeStyle=color;x.lineWidth=width*k;x.shadowColor=shadow;x.shadowBlur=blur*k*S;for(const {points,path} of ymmtShape){x.beginPath();path.forEach((p,i)=>i?x.lineTo(...points[p]):x.moveTo(...points[p]));x.stroke()}};paint(line,x);return cv};
  ymmtLayers.key=k;
  ymmtLayers.glow=bake(line=>{line('#2b4fc4',9,'#8ae3e2',26);line('#329dff',6,'#329dff',16);line('#329dff',4,'#329dff',8)});
  ymmtLayers.core=bake((line,x)=>{line('#329dff',4.4,'#00000000',0);x.globalAlpha=.55;line('#c3edff',1.6,'#00000000',0)});
  return ymmtLayers;
 }
 function skyExtra(kind,age,opt={}){
  const v=skyViewport,small=host.clientWidth<700;
  c.save();c.beginPath();c.rect(v.left,v.top,v.width,v.height);c.clip();
  const tall=activeLayout?.portrait,x=v.left+v.width*.5,y=v.top+v.height*(tall?.27:.35);
  if(kind==='shower'||kind==='rainbow'){
   // 무지개 유성우 = 별자리가 완성되는 순간부터 쏟아지는 빛깔별 유성. 일반 유성우와 그리기를 공유한다.
   const rainbow=kind==='rainbow',count=rainbow?(small?44:52):(small?5:9),gap=rainbow?(small?.12:.1):(small?.23:.19);
   for(let i=0;i<count;i++){
    const h=k=>skyHash(i*71+k*149+TRK.bpm),delay=i*gap+h(1)*.14,duration=.85+h(2)*.55;
    const a=age-delay;if(a<0||a>duration||delay>(opt.cut??Infinity)||skyHash(i*13+5)>quality*(opt.thin??1))continue;const u=still?.5:a/duration;
    const dx=v.width*(.4+.28*h(3)),dy=v.height*(.22+.19*h(4))*(tall?.6:1),sx=v.left+v.width*(.32+.73*h(5)),sy=v.top+v.height*(.02+.25*h(6));
    const px=sx-dx*u,py=sy+dy*u,tail=(rainbow?.26:.12+.12*h(7))*(small?.75:1),tx=px+dx*tail,ty=py-dy*tail;
    const opacity=Math.sin(u*Math.PI)*(rainbow?.95:.4+.55*h(8)),g=c.createLinearGradient(tx,ty,px,py),hue=Math.round(i*137.5)%360;
    if(rainbow){g.addColorStop(0,`hsla(${hue},100%,62%,0)`);g.addColorStop(.6,`hsla(${hue},100%,68%,.8)`);g.addColorStop(1,`hsl(${hue},100%,88%)`)}else{g.addColorStop(0,'#72aaff00');g.addColorStop(.65,'#7fcfff70');g.addColorStop(1,'#e6fcff')}
    const width=(small?1.1:1.5)+(rainbow?.5:0)+h(9)*(rainbow?1.6:1.1);c.strokeStyle=g;c.lineCap='round';c.beginPath();c.moveTo(tx,ty);c.lineTo(px,py);
    c.globalAlpha=opacity*.12;c.lineWidth=width*2.6;c.stroke();c.globalAlpha=opacity;c.lineWidth=width;c.stroke();
    c.fillStyle=rainbow?`hsl(${hue},100%,92%)`:'#e9fcff';c.beginPath();c.arc(px,py,1+h(11)*.9,0,Math.PI*2);c.fill();
   }
  }else if(kind==='comet'){
   // 혜성 = 긴 꼬리를 끌며 하늘을 가로지르는 큰 빛. 유성보다 크고 느리다.
   for(const [delay,start,dir] of [[.4,.08,1],[3.1,.3,-1],[5.4,.05,1]]){
    const a=age-delay,duration=2.6;if(!still&&(a<0||a>duration||delay>(opt.cut??Infinity)))continue;const u=still?.5:a/duration,w=v.width,h=v.height;
    const px=v.left+w*(dir>0?1.1-1.2*u:-.1+1.2*u),py=v.top+h*(start+(tall?.3:.5)*u),tx=px+dir*w*.36,ty=py-h*(tall?.09:.15);
    const g=c.createLinearGradient(tx,ty,px,py);g.addColorStop(0,'#8ae3e200');g.addColorStop(.6,'#8ae3e288');g.addColorStop(1,'#ffffff');
    c.lineCap='round';c.strokeStyle=g;c.beginPath();c.moveTo(tx,ty);c.lineTo(px,py);c.globalAlpha=Math.sin(u*Math.PI)*.12;c.lineWidth=(small?3.5:5)+7;c.stroke();c.globalAlpha=Math.sin(u*Math.PI);c.lineWidth=small?3.5:5;c.stroke();
    c.fillStyle='#fff';c.beginPath();c.arc(px,py,small?4:6,0,Math.PI*2);c.fill();
   }
  }else if(kind==='ymmt-sync'){
   // 밤 풍경의 YMMT: 별은 먼저 뜨고, 선은 사인 완성 0.9초 전부터 그어져 완성 순간 사인과 같은 곡선으로 번쩍이고 같이 사라진다.
   const box=fitYmmtRotation(opt.box,ymmtAngle),{reveal,fade}=opt.f,rs=age-reveal,pen=djClamp15((rs+.9)/.9);
   const rise=rs<0?0:djEase15(rs/.18),decay=djEase15(djClamp15((fade-rs)/1.1)),pop=1+.9*Math.exp(-Math.max(0,rs-.18)/.35);
   c.translate(box.cx,box.cy);c.rotate(box.angle);c.scale(box.scale,box.scale);c.translate(-157.5,-40);
   if(pen>0&&rise<1){c.strokeStyle='#65baff';c.lineWidth=2;c.lineCap=c.lineJoin='round';c.globalAlpha=1-rise;
    ymmtShape.forEach(({points,path},i)=>{const q=djClamp15(pen*4-i)*(path.length-1);if(q<=0)return;const whole=Math.floor(q),part=q-whole;c.beginPath();c.moveTo(...points[path[0]]);for(let s=1;s<=whole;s++)c.lineTo(...points[path[s]]);
     if(part>0){const a=points[path[whole]],b=points[path[whole+1]];c.lineTo(a[0]+(b[0]-a[0])*part,a[1]+(b[1]-a[1])*part)}c.stroke()})}
   if(rise>0&&rs<fade){const {glow,core}=ymmtNeon(opt.signScale*.88/box.scale);c.globalAlpha=Math.min(1,.95*rise*decay);c.drawImage(glow,-20,-20,360,120);c.globalAlpha=Math.min(1,.5*pop*rise*decay);c.drawImage(glow,-20,-20,360,120);c.globalAlpha=Math.min(1,rise*decay);c.drawImage(core,-20,-20,360,120)}
   // 별은 선과 네온보다 앞에 둔다.
   let n=0;c.fillStyle='#c3edff';
   for(const {points} of ymmtShape)for(const [a,b] of points){const born=n++*.065;if(age>=born&&age<born+.55)skyStar(c,a,b,(age-born)/.55,n+40,.3,'#6fbcff','#e6f5ff');c.globalAlpha=decay*Math.max(0,Math.min(1,(age-born-.2)*8));c.beginPath();c.arc(a,b,3.5,0,Math.PI*2);c.fill()}
  }else if(kind==='constellation'){
   const box=fitYmmtRotation(opt.box||{cx:x,cy:y,scale:Math.min(v.width*.8/355,v.height*.48/120)},ymmtAngle),scale=box.scale,alpha=Math.min(1,(9-age)/1.6),flash=still?0:Math.sin(Math.PI*djClamp15((age-7)/.4));
   c.translate(box.cx,box.cy);c.rotate(box.angle);c.scale(scale,scale);c.translate(-157.5,-40);c.strokeStyle='#65baff';c.fillStyle='#c3edff';c.shadowColor='#329dff';c.shadowBlur=12;c.lineWidth=2;
   let n=0;for(const {points,path} of ymmtShape){if(age>=1.6||still){const pop=still?0:Math.sin(Math.PI*djClamp15((age-1.6)/.4));
     c.globalAlpha=alpha*(still?1:Math.min(1,(age-1.6)/.4));c.beginPath();path.forEach((p,i)=>i?c.lineTo(...points[p]):c.moveTo(...points[p]));c.stroke();
     if(pop>0){c.save();c.globalAlpha=pop*.75;c.strokeStyle='#e6faff';c.shadowColor='#7fcaff';c.shadowBlur=25;c.lineWidth=2+pop*4;c.stroke();c.restore()}
     if(flash>0){c.save();c.lineJoin='round';c.lineCap='round';c.globalAlpha=flash;c.strokeStyle='#1e86ff';c.shadowColor='#1e86ff';c.shadowBlur=40;c.lineWidth=2+flash*9;c.stroke();c.strokeStyle='#62b8ff';c.shadowBlur=14;c.lineWidth=2+flash*3;c.stroke();c.restore()}}
    for(const [a,b] of points){const born=n++*.065;if(!still&&age>=born&&age<born+.55)skyStar(c,a,b,(age-born)/.55,n+40,.3,'#6fbcff','#e6f5ff');c.globalAlpha=alpha*(still?1:Math.max(0,Math.min(1,(age-born-.2)*8)));c.beginPath();c.arc(a,b,3.5+flash*3,0,Math.PI*2);c.fill()}}
  }
  c.restore();
 }
 const images=[...Object.values(YN),skyUFO];
 const whenReady=Promise.all(images.map(i=>i.decode()));
 function draw(t=clock()) {
  if(dead||!TRK)return;
  const start=performance.now();pace(start);const r=host.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,1.5),w=Math.round(r.width*d),h=Math.round(r.height*d);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
  const L=layout||sceneLayout(r.width,r.height),s=L.scale*d,ox=w/2-600*s,oy=L.offsetY*d;activeLayout=L;groundBottom=L.portrait?Math.max(760,(h-oy)/s):760;
  skyViewport={left:-ox/s,top:-oy/s,width:w/s,height:395+oy/s};
  c.setTransform(1,0,0,1,0,0);c.fillStyle='#170725';c.fillRect(0,0,w,h);
  c.setTransform(s,0,0,s,ox,oy);
  // 세로 하늘은 원래 그라데이션의 시작색으로 이어지고 바닥은 아래까지 연장된다.
  if(L.portrait){c.fillStyle='#110e20';c.fillRect(-2000,395,5200,4000);for(let i=0;i<55;i++){c.fillStyle='rgba(138,227,226,.22)';c.fillRect(220+(i*173)%820,-900+(i*71)%900,1.7,1.7)}}
  effect=introScene(t,L,introActive(),still);
  effect.radius=effect.wave*Math.max(...[[0,0],[w,0],[0,h],[w,h]].map(([x,y])=>Math.hypot(x-ox-effect.x*s,y-oy-effect.y*s)))/d;
  setBrightness(introActive()?(t>=17.14&&t<17.64&&!still?.3:introBrightness(t,still)):1);
  const waveActive=introActive()&&!still&&t>=17.14&&t<17.64;
  lightLayer.style.display=waveActive?'block':'none';frontLayer.style.display=effect.spot?'block':'none';
  bg(c);
  backdrop.draw(c,skyViewport,{width:w,height:h},introActive()?.35+.65*effect.rise:1);
  // 하늘의 작은 별은 CSS 픽셀 크기로 그려 모바일에서도 UFO 퇴장 별보다 작고 또렷하다.
  const wall=performance.now()/1000;
  const wasBusy=hasManual();
  if(manual&&wall-manual.start>=manual.dur){const grand=manual.kind==='grand';manual=null;if(grand)grandListener?.(false)}
  for(const [kind,event] of manualEffects)if(wall-event.start>=event.dur)manualEffects.delete(kind);
  if(wasBusy&&!hasManual()){returnAt=wall;if(pendingFinale){pendingFinale=false;playFinale()}}
  const routineAlpha=hasManual()?0:Math.min(1,(wall-returnAt)/.6);
  skyRoutineAlpha=routineAlpha;
  const skyPlanNow=skyPlan(TRK),ambientAlpha=ambientVisibility(t,skyPlanNow.blocked)*routineAlpha;
  if(!still&&ambientAlpha>0){
   c.save();c.setTransform(d,0,0,d,0,0);c.fillStyle='#fff1d5';
   const skyHeight=Math.max(0,Math.min(r.height,(oy+395*s)/d));
   for(const star of backgroundStars(t,skyPlanNow.ambientSeed)){
    const x=star.x*r.width,y=star.y*skyHeight,k=star.radius;
    c.globalAlpha=star.alpha*ambientAlpha;c.beginPath();c.moveTo(x,y-k);c.lineTo(x+k*.25,y-k*.25);c.lineTo(x+k,y);c.lineTo(x+k*.25,y+k*.25);c.lineTo(x,y+k);c.lineTo(x-k*.25,y+k*.25);c.lineTo(x-k,y);c.lineTo(x-k*.25,y-k*.25);c.closePath();c.fill();
   }
   c.lineWidth=1;c.lineCap='round';
   for(const meteor of backgroundMeteors(t,skyPlanNow.ambient)){
    const x=meteor.x*r.width,y=meteor.y*skyHeight,dx=r.width*.16,dy=skyHeight*.0413;
    const glow=c.createLinearGradient(x+dx,y-dy,x,y);glow.addColorStop(0,'#8ae3e200');glow.addColorStop(1,'#fff1d5');
    c.globalAlpha=meteor.alpha*.75*ambientAlpha;c.strokeStyle=glow;c.lineWidth=1.4;c.beginPath();c.moveTo(x+dx,y-dy);c.lineTo(x,y);c.stroke();
    c.fillStyle='#fff1d5';c.beginPath();c.arc(x,y,1.3,0,Math.PI*2);c.fill();
   }
   for(const burst of backgroundFireworks(t,skyPlanNow.ambient)){
    const radius=Math.min(76,r.width*.15)*(1-Math.exp(-burst.age*1.8)),x=burst.x*r.width,y=burst.y*skyHeight+5*burst.age**2;
    c.globalAlpha=burst.alpha*.7*ambientAlpha;c.strokeStyle=burst.color;
    for(let i=0;i<24;i++){
     const angle=i*Math.PI/12,reach=radius*(i%2?.76:1),tail=3+3*(1-burst.age/2.3);
     c.beginPath();c.moveTo(x+Math.cos(angle)*Math.max(0,reach-tail),y+Math.sin(angle)*Math.max(0,reach-tail));c.lineTo(x+Math.cos(angle)*reach,y+Math.sin(angle)*reach);c.stroke();
    }
   }
   c.restore();
  }
  if(introActive()&&t<17.14){
   c.save();c.beginPath();c.rect(-2000,-2000,5200,2395);c.clip();
   const glow=c.createRadialGradient(effect.x,395,0,effect.x,395,260);glow.addColorStop(0,`rgba(255,72,141,${effect.rise*.28})`);glow.addColorStop(1,'#7844ba00');c.fillStyle=glow;c.fillRect(effect.x-260,135,520,260);c.restore();
  }
  c.save();if(routineAlpha<1)c.filter=`opacity(${routineAlpha})`;if(!hasManual())skyProps(c,t);c.restore();stepPulseHold(t,wall);drawPulses(wall);floorWave(c,0,t);if(!introActive()||t>=17.14)visual(c,5,t);
  if(introActive()&&!still&&t>=17.14&&t<17.69){const u=(t-17.14)/.55;c.save();sunTransform(c);for(let j=0;j<3;j++){c.strokeStyle=[P,V,C][j];c.globalAlpha=(1-u)*.9;c.lineWidth=7-j;c.beginPath();c.arc(850,267,100+500*u-j*18,0,Math.PI*2);c.stroke()}c.restore()}
  if(!hasManual()){c.save();if(routineAlpha<1)c.filter=`opacity(${routineAlpha})`;skyUfos(c,t);
   const age=t-skyPlanNow.constellation;if(skyPlanNow.constellation!==null&&age>=0&&age<9){if(age>=1.85&&age<8.3)skyExtra('rainbow',age-1.85);skyExtra('constellation',age)}
   for(const birth of skyPlanNow.showers)if(t>=birth&&t<birth+5)skyExtra('shower',t-birth);
   const fixed=skyPlanNow.ufos[0];if(fixed.mode==='sign')signBurst(t-fixed.birth-fixed.reveal);c.restore();
  }
  if(manual?.kind==='grand')skyGrand(wall-manual.start);
  skyRoutineAlpha=1;
  for(const event of manualEffects.values()){
   if(event.kind==='ymmt'){const a=still?4:wall-event.start;if(!still&&a>=1.85&&a<8.3)skyExtra('rainbow',a-1.85);skyExtra('constellation',a);continue}
   skyUfos(c,still?(event.kind==='sign'?event.f.reveal+.5:event.f.flight*.5):wall-event.start,[event.f]);if(event.kind==='sign')signBurst(wall-event.start-event.f.reveal)
  }
  drawToggles(wall);
  // 조명 원뿔은 유노 중심이며 세로 화면의 확장 하늘에서 내려온다.
  if(effect.spot){
   // 원뿔과 바닥 조명의 모양은 크기가 바뀔 때만 계산하고 알파로 점등한다.
   const spotTop=Math.min(-100,-oy/s),key=`${w}:${h}:${s}:${oy}`;
   if(spotCacheKey!==key){spotCacheKey=key;spotLayer.width=w;spotLayer.height=h;const sc=spotLayer.getContext('2d');sc.setTransform(s,0,0,s,ox,oy);
sc.save();const top=spotTop,g=sc.createLinearGradient(0,top,0,610);g.addColorStop(0,'#8ae3e200');g.addColorStop(.4,`rgba(255,155,192,${.035})`);g.addColorStop(1,`rgba(138,227,226,${.16})`);sc.fillStyle=g;sc.beginPath();sc.moveTo(560,top);sc.lineTo(640,top);sc.lineTo(835,610);sc.quadraticCurveTo(600,655,365,610);sc.closePath();sc.filter="blur(8px)";sc.fill();sc.filter="none";sc.translate(600,607);sc.scale(1,.22);const pool=sc.createRadialGradient(0,0,0,0,0,230);pool.addColorStop(0,`rgba(255,155,192,${.4})`);pool.addColorStop(1,'#8ae3e200');sc.fillStyle=pool;sc.fillRect(-230,-230,460,460);sc.restore();
   }
   c.save();c.setTransform(1,0,0,1,0,0);c.globalAlpha=effect.spot;c.drawImage(spotLayer,0,0);c.restore();
  }
  if(effect.spot){
   // 캐릭터의 개별 그리기에 필터를 걸지 않고 한 번 합성한다.
   const fw=Math.ceil(440*s),fh=Math.ceil(500*s);if(frontLayer.width!==fw||frontLayer.height!==fh){frontLayer.width=fw;frontLayer.height=fh}
   const fc=frontLayer.getContext('2d');fc.setTransform(1,0,0,1,0,0);fc.clearRect(0,0,fw,fh);fc.setTransform(s,0,0,s,-455*s,-160*s);front(fc,t);
   frontLayer.style.left=`${(ox+380*s)/d}px`;frontLayer.style.top=`${(oy+160*s)/d}px`;frontLayer.style.width=`${fw/d}px`;frontLayer.style.height=`${fh/d}px`;
  }else{c.save();c.translate(-75,0);front(c,t);c.restore();}
  if(effect.spot){c.save();c.fillStyle='#b9cfe0';c.globalAlpha=effect.spot*.28;for(let i=0;i<14;i++){const x=465+(i*79)%270,y=180+(i*47-t*9)%380;c.beginPath();c.arc(x,y,1.1,0,7);c.fill()}c.restore();}
  // 장면 색을 보존한 밝기 복사본을 원형 마스크로 합성한다. 흰색 덮개 없음.
  if(introActive()&&!still&&t>=17.14&&t<17.64){
   const copy=lightLayer,lc=copy.getContext('2d');if(copy.width!==w||copy.height!==h){copy.width=w;copy.height=h}
   const x=ox+effect.x*s,y=oy+effect.y*s,max=Math.max(...[[0,0],[w,0],[0,h],[w,h]].map(([a,b])=>Math.hypot(a-x,b-y))),radius=effect.wave*(max+80);
   // 파면 마스크 밖의 픽셀에는 밝기 필터를 계산하지 않는다.
   const left=Math.max(0,Math.floor(x-radius)),top=Math.max(0,Math.floor(y-radius)),right=Math.min(w,Math.ceil(x+radius)),bottom=Math.min(h,Math.ceil(y+radius));
   lc.setTransform(1,0,0,1,0,0);lc.clearRect(0,0,w,h);
   if(right>left&&bottom>top)lc.drawImage(canvas,left,top,right-left,bottom-top,left,top,right-left,bottom-top);
   if(effect.spot)lc.drawImage(frontLayer,ox+380*s,oy+160*s);
   lc.globalCompositeOperation='destination-in';const mask=lc.createRadialGradient(x,y,Math.max(0,radius-80),x,y,Math.max(.01,radius));mask.addColorStop(0,'#000');mask.addColorStop(1,'#0000');lc.fillStyle=mask;lc.fillRect(0,0,w,h);lc.globalCompositeOperation='source-over';lightLayer.style.filter=`brightness(${introBrightness(t)})`;
  }
  // 기존 🎂 전환 폭죽의 수식·색·지연을 유지한다. 음악 장면 자체와는 별도이며 인트로에는 호출하지 않는다.
  const now=performance.now(),dt=lastFrame?Math.min(.05,(now-lastFrame)/1000):0;lastFrame=now;
  if(parts.length){c.save();c.setTransform(d,0,0,d,0,0);for(const p of parts){p.age+=dt;if(p.age<p.delay)continue;const age=p.age-p.delay;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=20*dt;p.vx*=Math.exp(-dt*.35);c.globalAlpha=Math.max(0,1-age/(p.life||2.1))*.85;drawSpark(c,p.color,p.x,p.y,p.r*3.3)}parts=parts.filter(p=>p.age-p.delay<(p.life||2.1));c.restore()}
  costs.push(performance.now()-start);if(costs.length>300)costs.shift();lastT=t;
 }
 function frame(){raf=0;if(dead)return;if(!document.hidden&&visible&&(!still||lastT===null||hasManual()||hasToggles()||performance.now()/1000-returnAt<.6)){const t=still?0:clock();if(t!==lastT||parts.length||hasManual()||hasToggles()||performance.now()/1000-returnAt<.6)draw(t)}if((!still||hasManual()||hasToggles()||performance.now()/1000-returnAt<.6)&&!document.hidden&&visible)raf=requestAnimationFrame(frame)}
 function resume(){if(!dead&&!raf&&!document.hidden&&visible)raf=requestAnimationFrame(frame)}
 function visibility(){if(document.hidden){cancelAnimationFrame(raf);raf=0}else{for(const kind of Object.keys(toggles))if(toggles[kind]?.stopAt)toggles[kind]=null;else if(toggles[kind])toggles[kind].start=performance.now()/1000;lastT=null;resume()}}
 function resize(){layout=null;lastT=null;draw(still?0:clock());resume()}
 const observer=new IntersectionObserver(es=>{visible=es[0].isIntersecting;if(!visible){cancelAnimationFrame(raf);raf=0}else resume()});observer.observe(canvas);
 document.addEventListener('visibilitychange',visibility);window.addEventListener('resize',resize);window.visualViewport?.addEventListener('resize',resize);
 whenReady.then(()=>{if(!dead){draw(0);resume()}}).catch(()=>{});
 return {skyBusy(t){if(!TRK)return false;const plan=skyPlan(TRK),f=plan.ufos[0],a=plan.constellation;return hasManual()||(f.mode==='sign'&&t>=f.birth&&t<f.birth+f.reveal+SIGN_BURST)||(a!==null&&t>=a&&t<a+9)},
  setEyesClosed(value){yunoEyesClosed=!!value;lastT=null;resume()},onGrand(fn){grandListener=fn},
  grandShow(){if(dead||document.hidden)return;grandListener?.(true);pulseHolding=false;pendingBig=null;const f=manualFlight('sign'),preview=grandLayout(skyViewport,activeLayout?.portrait);ymmtNeon(preview.sign.scale*.88/fitYmmtRotation(preview.ymmt,ymmtAngle).scale); // 네온을 미리 구워 번쩍이는 순간에 끊기지 않게 한다.
   manualEffects.delete('sign');manual={kind:'grand',start:performance.now()/1000,dur:f.reveal+SIGN_BURST,f};parts=[];lastT=null;if(!still){const r=host.getBoundingClientRect();[[.5,.28,'#ff477d'],[.42,.2,'#6ee7f9'],[.58,.2,'#ffd36b'],[.5,.14,'#c4a1ff']].forEach(([x,y,color],j)=>{for(let i=0;i<70;i++){const a=i*Math.PI/35,v=(50+Math.random()*90)*Math.max(.8,Math.min(1.4,r.width/900));parts.push({x:r.width*x,y:r.height*y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,age:0,color:i%3?color:'#fff9ec',r:1.1+Math.random()*1.8,delay:j*.08,life:2.2})}});lastFrame=performance.now()}resume()},triggerManual(kind){
   if(dead||document.hidden||!['fireworks','ufo','sign','ymmt','shower','shot','pulse','pulse-big'].includes(kind))return;
   const now=performance.now()/1000;
   // 폭죽 단발 = 쿨타임 0.1초. 고정 이벤트를 막지 않는다.
   if(kind==='shot'){if(now-lastShot<.1)return false;lastShot=now;shots.push({start:now,seed:Math.random()*100000});lastT=null;resume();return true}
   if(kind==='pulse'||kind==='pulse-big'){addPulse(kind==='pulse-big');return true}
   // 끄면 이미 나온 폭죽 · 유성은 끝까지 재생한다. 끝나기 전에 다시 켜면 그대로 이어진다.
   if(kind==='fireworks'||kind==='shower'){const on=toggles[kind];if(on&&!on.stopAt)on.stopAt=now;else if(on)on.stopAt=0;else toggles[kind]={start:now,seed:Math.random()*100000,stopAt:0};lastT=null;resume();return !toggles[kind].stopAt}
   startManual(kind);
  },pulseHold(on,big=true){
   if(dead)return;
   if(on){pulseHolding=true;holdIndex=-1;lastT=null;resume();return}
   pulseHolding=false;if(!big)return;
   if(still||!TRK){addPulse(true);return}
   const t=clock(),B=TRK.beats,at=t<B[0]?B[0]:B[beatIdx(t)+1]??t;
   pendingBig={at,deadline:performance.now()/1000+(at-t)+.3};lastT=null;resume();
  },whenReady,setBrightness,setIntro(fn){introActive=fn},setClock(fn){clock=fn;lastT=null;resume()},setTrack(track){TRK=track;lastT=null;resume()},setLayout(value){layout=value;lastT=null;draw()},
  setStill(value){still=value;if(still)parts=[];cancelAnimationFrame(raf);raf=0;lastT=null;draw(0);resume()},
  celebrate(xRatio,yRatio){if(dead||still||hasManual()||document.hidden||!visible)return;parts=[];const r=host.getBoundingClientRect();const burst=(x,y,delay=0)=>{const colors=['#ff477d','#fff9ec','#efb62f'];for(let i=0;i<40;i++){const a=i*Math.PI*2/40,v=28+Math.random()*50;parts.push({x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,age:0,color:colors[i%3],r:1+Math.random()*1.6,delay})}};if(Number.isFinite(xRatio)&&Number.isFinite(yRatio))burst(r.width*djClamp15(xRatio),r.height*djClamp15(yRatio));else [[.24,.38],[.76,.27],[.54,.17]].forEach(([x,y],i)=>burst(r.width*x,r.height*y,i*.26));lastFrame=performance.now();resume()},
  finale(){if(hasManual()){pendingFinale=true;return}playFinale()},
  renderAt(t){draw(t)},diagnostics(){return {effect:{...effect},snapshot,ambient:TRK?{blocked:skyPlan(TRK).blocked.map(r=>[...r]),events:skyPlan(TRK).ambient.map(e=>({...e}))}:null,costs:[...costs],layout:sceneLayout(host.clientWidth,host.clientHeight),raf,dead,particles:parts.length}},
  destroy(){backdrop.destroy();auroraLayer.key=null;if(auroraLayer.cv){auroraLayer.cv.width=0;auroraLayer.cv=null}ymmtLayers.key=0;if(ymmtLayers.glow)ymmtLayers.glow.width=ymmtLayers.core.width=0;dead=true;yunoEyesClosed=false;grandListener=null;manual=null;manualEffects.clear();toggles.fireworks=toggles.shower=null;shots.length=pulses.length=0;pulseHolding=false;pendingBig=null;pendingFinale=false;parts=[];cancelAnimationFrame(raf);raf=0;observer.disconnect();document.removeEventListener('visibilitychange',visibility);window.removeEventListener('resize',resize);window.visualViewport?.removeEventListener('resize',resize);canvas.remove();frontLayer.remove();lightLayer.remove();spotLayer.width=spotLayer.height=0;lightLayer.width=lightLayer.height=frontLayer.width=frontLayer.height=0;for(const i of images)i.src='';for(const k in FL){FL[k].width=FL[k].height=0}skySign.core.width=skySign.glow.width=0;historyCache.clear();}
 };
}
