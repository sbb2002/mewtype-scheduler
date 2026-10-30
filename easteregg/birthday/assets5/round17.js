// One deterministic 100 BPM clock: two scratch bursts, fader cuts, knob touch, rare cue.
let dj15=null;
const DJ15_BPM=100;
const djClamp15=x=>Math.max(0,Math.min(1,x));
const djFrac15=x=>x-Math.floor(x);
const djTri15=u=>u<.25?4*u:u<.75?2-4*u:4*u-4;
const djEase15=x=>{x=djClamp15(x);return x*x*(3-2*x)};
function djContact15(shoulder,paw,degrees,bounce){
 const a=degrees*Math.PI/180,x=paw[0]-shoulder[0],y=paw[1]-shoulder[1];
 const rx=shoulder[0]+x*Math.cos(a)-y*Math.sin(a),ry=shoulder[1]+x*Math.sin(a)+y*Math.cos(a);
 return {rig:[rx,ry],scene:[675+(rx-120)*1.55,585+(ry-229+bounce)*1.55]};
}
function djPose15(seconds){
 const beats=Math.max(0,seconds)*DJ15_BPM/60,bar=Math.floor(beats/4),b=beats-bar*4,k=Math.floor(b),p=djFrac15(b);
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
 if(k===1)right=5*djTri15(djFrac15(swung*2));
 if(k===2){
  mode='knob';
  if(p<.18)right=9*djEase15(p/.18);
  else if(p<.72){const u=(p-.18)/.54;right=9+1.4*djTri15(u);knob=26*djTri15(u)}
  else right=9*(1-djEase15((p-.72)/.28));
 }
 if(k===3&&p>=.62)right=6*djTri15((p-.62)/.38);
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
 const tail=5*accent*Math.sin(Math.PI*follow*2)*Math.exp(-follow*3);
 const bodyRoll=.65*Math.sin(Math.PI*beats); 
 return {bodyRoll,swung,swingRatio:.62,accent,seconds,bar,beat:k+1,phase:p,pattern:scattered?'single-per-beat':'paired-1-and-3',scratch,left,right,mode,knob,bounce,nod,tail,
  leftCoast:bar*32+32*idle,leftRecord:bar*32+32*idle+26*scratch,rightRecord:seconds*45*DJ15_BPM/120,
  headY:1.8*nod,headAngle:(Math.floor(beats)%2?1:-1)*.5*nod,
  ear:.9*accent*Math.sin(follow*Math.PI*2)*Math.exp(-follow*3),mic:1.2*accent*Math.sin(follow*Math.PI*2)*Math.exp(-follow*3),
  leftContact,rightContact,fader:mode==='fader'?rightContact.scene[0]-675:2.9,energy:Math.min(1, (.55+.3*(k%2))*Math.exp(-p*5.5)+.12*Math.exp(-Math.abs(p-.62)*22))};
}
function setupYuno15(){
 dj15=null;if(current!==1)return;
 dj15={body:svg.querySelector('.rig-yuno .rig-body'),roots:[...svg.querySelectorAll('.rig-yuno')],head:svg.querySelector('.rig-yuno .rig-head'),left:svg.querySelector('.rig-arm8_l'),right:svg.querySelector('.rig-arm8_r'),tail:svg.querySelector('.rig-yuno .rig-tail'),earL:svg.querySelector('.rig-yuno .rig-ear-l'),earR:svg.querySelector('.rig-yuno .rig-ear-r'),mic:svg.querySelector('.rig-yuno .rig-headset'),recordL:svg.querySelector('[data-dj-record="left"]'),recordR:svg.querySelector('[data-dj-record="right"]'),fader:svg.querySelector('[data-dj-fader]'),knob:svg.querySelector('[data-dj-knob]')};
 renderYuno15(0);
}
function renderYuno15(seconds){
 if(current!==1||!dj15)return;
 const q=djPose15(seconds),d=dj15;
 const rotate=(e,a)=>{if(e)e.style.transform='rotate('+a.toFixed(4)+'deg)'};
 d.roots.forEach(e=>e.style.transform='translateY('+q.bounce.toFixed(4)+'px)');
 if(d.head)d.head.style.transform='translateY('+q.headY.toFixed(4)+'px) rotate('+q.headAngle.toFixed(4)+'deg)';
 if(d.body)d.body.style.transformOrigin='120px 170px';
 rotate(d.body,q.bodyRoll);rotate(d.left,q.left);rotate(d.right,q.right);rotate(d.tail,q.tail);rotate(d.earL,-q.ear);rotate(d.earR,q.ear);rotate(d.mic,q.mic);
 if(d.recordL)d.recordL.setAttribute('transform','rotate('+q.leftRecord.toFixed(4)+')');
 if(d.recordR)d.recordR.setAttribute('transform','rotate('+q.rightRecord.toFixed(4)+')');
 if(d.fader)d.fader.setAttribute('transform','translate('+q.fader.toFixed(4)+' 0)');
 if(d.knob)d.knob.setAttribute('transform','rotate('+q.knob.toFixed(4)+')');
 eq.forEach((e,i)=>{const profile=.45+.55*(.5+.5*Math.sin(i*.73+q.bar*.37));const h=24+62*(.22+.78*q.energy)*profile;e.setAttribute('height',h.toFixed(2));e.setAttribute('y',(405-h).toFixed(2))});
 d.last=seconds;return q;
}
// Test-only deterministic seeking is enabled before load by Chrome QA, never by the UI.
if(window.__BIRTHDAY_QA__)window.__birthdayDj15={bpm:DJ15_BPM,sample:djPose15,now(){return dj15&&dj15.last},seek(seconds){if(current!==1)choose(1);return renderYuno15(seconds)}};
