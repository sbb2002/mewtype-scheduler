// 지속 폭죽은 현재 주기만 계산한다. 입자·발사 대기열이나 별도 시계는 저장하지 않는다.
const hash=n=>{const x=Math.sin(n*127.1+19.73)*43758.5453;return x-Math.floor(x)};
const palettes=[['#ff70b6','#85f9ff'],['#c99cff','#ffda7a'],['#ff997c','#fff1ce']];
export function fireworkFrame(time,seed,view,{small=false,reduced=false,budget=small?420:720}={}){
 const cycle=Math.floor(time/4),particles=[],rockets=[];
 budget=Math.max(0,Math.min(budget,small?420:720));
 for(let k=Math.max(0,cycle-1);k<=cycle;k++){
  const salvo=k%5===4?6:1;
  for(let j=0;j<salvo;j++){
   const age=time-k*4-j*.16;if(age<0||age>3.35)continue;
   const h=n=>hash(seed+k*701+j*97+n*31),style=Math.floor(h(1)*3),colors=palettes[Math.floor(h(2)*3)];
   const radius=Math.min(view.width*.14,view.height*.22)*(style===1?.85:1),margin=radius+12;
   const x=view.left+margin+Math.max(0,view.width-2*margin)*h(3),y=view.top+margin+Math.max(0,view.height-2*margin)*h(4);
   if(!reduced&&age<.65&&particles.length+rockets.length<budget){
    const u=age/.65,floor=view.top+view.height,bend=(h(5)-.5)*radius;
    rockets.push({x:x+bend*Math.sin(u*Math.PI),y:floor+(y-floor)*u,tailX:x+bend*Math.sin(Math.max(0,u-.17)*Math.PI),tailY:floor+(y-floor)*Math.max(0,u-.17),alpha:Math.sin(u*Math.PI)});continue;
   }
   const t=Math.max(0,age-.65),count=reduced?18:small?56:96,alpha=Math.max(0,1-t/2.7);
   for(let i=0;i<count&&particles.length+rockets.length<budget;i++){
    const a=i*Math.PI*2/count+h(6)*6.28,ring=i%3===0?.53:1,speed=ring*(.78+.22*hash(i+j*71+k*17));
    const r=reduced?radius*.24:radius*(1-Math.exp(-t*(style===1?1.5:2.5)))*speed;
    const fall=reduced?0:radius*t*t*(style===1?.16:.07),px=x+Math.cos(a)*r,py=y+Math.sin(a)*r*(style===1?.75:1)+fall;
    const tail=radius*(.12+.1*t)*alpha;
    particles.push({x:px,y:py,tx:reduced?px:px-Math.cos(a)*tail,ty:reduced?py:py-Math.sin(a)*tail-fall*.18,
     color:i%7===0?'#fff9ed':colors[style===2?i%2:i%5===0?1:0],alpha:reduced?Math.sin(age/3.35*Math.PI)*.55:alpha*.95,radius:reduced?1.6:1.2+hash(i+seed)*1.1});
   }
  }
 }
 return {particles,rockets};
}
export function drawFireworkFrame(c,frame){
 c.save();c.lineCap='round';
 for(const r of frame.rockets){c.globalAlpha=r.alpha;c.strokeStyle='#ffdb94';c.lineWidth=1.6;c.shadowColor='#ffc97e';c.shadowBlur=6;c.beginPath();c.moveTo(r.tailX,r.tailY);c.lineTo(r.x,r.y);c.stroke()}
 c.shadowBlur=0;c.lineWidth=1.1;
 for(const p of frame.particles){c.globalAlpha=p.alpha*.55;c.strokeStyle=p.color;c.beginPath();c.moveTo(p.tx,p.ty);c.lineTo(p.x,p.y);c.stroke();c.fillStyle=p.color;c.globalAlpha=p.alpha*.13;c.beginPath();c.arc(p.x,p.y,p.radius*2.8,0,Math.PI*2);c.fill();c.globalAlpha=p.alpha;c.beginPath();c.arc(p.x,p.y,p.radius,0,Math.PI*2);c.fill()}
 c.restore();
}
