// 지속 폭죽은 현재 주기만 계산한다. 입자·발사 대기열이나 별도 시계는 저장하지 않는다.
const hash=n=>{const x=Math.sin(n*127.1+19.73)*43758.5453;return x-Math.floor(x)};
const palettes=[['#ff70b6','#85f9ff'],['#c99cff','#ffda7a'],['#ff997c','#fff1ce']];
export const SHELL_LIFE=3.35; // 발사(0.65초) + 폭발 2.7초.
// 폭죽 한 발. out 에 입자를 더한다. age = 발사 뒤 시간.
function addShell(out,age,h,view,{seed,salt,small,reduced,budget,count}){
 const {particles,rockets}=out,style=Math.floor(h(1)*3),colors=palettes[Math.floor(h(2)*3)];
 const radius=Math.min(view.width*.14,view.height*.22)*(style===1?.85:1),margin=radius+12;
 const x=view.left+margin+Math.max(0,view.width-2*margin)*h(3),y=view.top+margin+Math.max(0,view.height-2*margin)*h(4);
 if(!reduced&&age<.65&&particles.length+rockets.length<budget){
  const u=age/.65,floor=view.top+view.height,bend=(h(5)-.5)*radius;
  rockets.push({x:x+bend*Math.sin(u*Math.PI),y:floor+(y-floor)*u,tailX:x+bend*Math.sin(Math.max(0,u-.17)*Math.PI),tailY:floor+(y-floor)*Math.max(0,u-.17),alpha:Math.sin(u*Math.PI)});return;
 }
 const t=Math.max(0,age-.65),alpha=Math.max(0,1-t/2.7);count=reduced?18:count??(small?56:96);
 for(let i=0;i<count&&particles.length+rockets.length<budget;i++){
  const a=i*Math.PI*2/count+h(6)*6.28,ring=i%3===0?.53:1,speed=ring*(.78+.22*hash(i+salt));
  const r=reduced?radius*.24:radius*(1-Math.exp(-t*(style===1?1.5:2.5)))*speed;
  const fall=reduced?0:radius*t*t*(style===1?.16:.07),px=x+Math.cos(a)*r,py=y+Math.sin(a)*r*(style===1?.75:1)+fall;
  const tail=radius*(.12+.1*t)*alpha;
  particles.push({x:px,y:py,tx:reduced?px:px-Math.cos(a)*tail,ty:reduced?py:py-Math.sin(a)*tail-fall*.18,
   color:i%7===0?'#fff9ed':colors[style===2?i%2:i%5===0?1:0],alpha:reduced?Math.sin(age/SHELL_LIFE*Math.PI)*.55:alpha*.95,radius:reduced?1.6:1.2+hash(i+seed)*1.1});
 }
}
// until = 토글을 끈 시각. 그 뒤로는 새로 쏘지 않고 이미 쏜 폭죽만 끝까지 그린다.
export function fireworkFrame(time,seed,view,{small=false,reduced=false,budget=small?420:720,until=Infinity}={}){
 const cycle=Math.floor(time/4),out={particles:[],rockets:[]};
 budget=Math.max(0,Math.min(budget,small?420:720));
 for(let k=Math.max(0,cycle-1);k<=cycle;k++){
  const salvo=k%5===4?6:1;
  for(let j=0;j<salvo;j++){
   const launch=k*4+j*.16,age=time-launch;if(age<0||age>SHELL_LIFE||launch>until)continue;
   addShell(out,age,n=>hash(seed+k*701+j*97+n*31),view,{seed,salt:j*71+k*17,small,reduced,budget});
  }
 }
 return out;
}
// 단발 폭죽. 버튼을 누를 때마다 하나씩 쌓이므로 저장하지 않고 발사 시각 · 시드로만 그린다.
export function fireworkShot(age,seed,view,{small=false,reduced=false,budget=small?420:720,count}={}){
 const out={particles:[],rockets:[]};
 if(age>=0&&age<=SHELL_LIFE)addShell(out,age,n=>hash(seed+n*31),view,{seed,salt:seed%1000,small,reduced,budget,count});
 return out;
}
// 사인 완성 때 한꺼번에 터지는 폭죽. 발사 없이 바로 터진다. age = 완성 뒤 시간(결정적이라 탐색해도 같다).
export const SALVO_LIFE=4.2;
export function fireworkSalvo(age,seed,view,{small=false,budget=small?700:1400}={}){
 const out={particles:[],rockets:[]},shells=small?8:14;
 for(let j=0;j<shells;j++){
  const shell=age-j*.1+.65;if(shell<.65||shell>SHELL_LIFE)continue;
  addShell(out,shell,n=>hash(seed+j*97+n*31),view,{seed,salt:j*71,small,budget});
 }
 return out;
}
// 입자마다 호 · 그림자를 그리면 GPU 가 밀린다. 꼬리는 색 · 밝기 칸별로 묶어 한 번에 긋고, 머리는 미리 구운 빛점을 복사한다.
const sprites=new Map(),ALPHA_BINS=6;
function sprite(color){
 let cv=sprites.get(color);if(cv)return cv;
 cv=document.createElement('canvas');cv.width=cv.height=32;
 const x=cv.getContext('2d'),g=x.createRadialGradient(16,16,0,16,16,16);
 g.addColorStop(0,color);g.addColorStop(.3,color);g.addColorStop(.36,color+'26');g.addColorStop(1,color+'00');
 x.fillStyle=g;x.fillRect(0,0,32,32);sprites.set(color,cv);return cv;
}
// 빛점 하나. r = 빛무리까지 포함한 반지름. 색은 #rrggbb 만 받는다.
export function drawSpark(c,color,x,y,r){c.drawImage(sprite(color),x-r,y-r,r*2,r*2)}
export function drawFireworkFrame(c,frame){
 c.save();c.lineCap='round';
 c.strokeStyle='#ffdb94';
 for(const r of frame.rockets){c.globalAlpha=r.alpha*.3;c.lineWidth=4;c.beginPath();c.moveTo(r.tailX,r.tailY);c.lineTo(r.x,r.y);c.stroke();c.globalAlpha=r.alpha;c.lineWidth=1.6;c.stroke()}
 const tails=new Map();
 for(const p of frame.particles){const bin=Math.ceil(p.alpha*ALPHA_BINS),key=p.color+bin;let t=tails.get(key);if(!t)tails.set(key,t={color:p.color,bin,list:[]});t.list.push(p)}
 c.lineWidth=1.1;
 for(const {color,bin,list} of tails.values()){c.globalAlpha=bin/ALPHA_BINS*.55;c.strokeStyle=color;c.beginPath();for(const p of list){c.moveTo(p.tx,p.ty);c.lineTo(p.x,p.y)}c.stroke()}
 for(const p of frame.particles){const r=p.radius*2.8;c.globalAlpha=p.alpha;c.drawImage(sprite(p.color),p.x-r,p.y-r,r*2,r*2)}
 c.restore();
}
