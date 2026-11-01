// 태양과 LED horizon 사이의 신스웨이브 폴리곤 산. 정적 그림이라 크기가 바뀔 때만 캐시를 다시 만든다.
export function createBirthdayBackdrop(){
 let cache=null,key='';
 const poly=(c,points,fill,edge)=>{c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fillStyle=fill;c.fill();if(edge){c.strokeStyle=edge;c.lineWidth=.8;c.stroke()}};
 function build(view,size){
  cache??=document.createElement('canvas');
  const density=Math.min(2,size.width/view.width),height=185;
  cache.width=Math.ceil(view.width*density);cache.height=Math.ceil(height*density);
  const c=cache.getContext('2d');c.setTransform(cache.width/view.width,0,0,cache.height/height,-view.left*cache.width/view.width,-210*cache.height/height);
  const x=u=>view.left+view.width*u,y=h=>395-h;
  const ridge=[[x(0),y(28)],[x(.10),y(64)],[x(.22),y(150)],[x(.34),y(82)],[x(.46),y(103)],[x(.61),y(35)],[x(.73),y(31)],[x(.84),y(22)],[x(.96),y(89)],[x(1),y(44)]];
  poly(c,[[x(0),395],...ridge,[x(1),395]],'#261b40');
  for(let i=0;i<ridge.length-1;i++){
   const a=ridge[i],b=ridge[i+1],foot=[(a[0]+b[0])/2+view.width*.025,395];
   poly(c,[a,b,foot],['#34214c','#382345','#252340','#3c2454'][i%4],'#8a559b45');
   poly(c,[a,foot,[a[0],395]],i%2?'#211d35':'#2c193e');
  }
  c.beginPath();ridge.forEach(([a,b],i)=>i?c.lineTo(a,b):c.moveTo(a,b));c.strokeStyle='#8ae3e270';c.lineWidth=1.1;c.stroke();
  poly(c,[[x(0),395],[x(.16),y(33)],[x(.32),y(6)],[x(.48),y(37)],[x(.65),y(4)],[x(.83),y(20)],[x(1),y(7)],[x(1),395]],'#27132c','#ff488d35');
 }
 return {
  draw(c,view,size,alpha=1){
   const next=[size.width,size.height,view.left,view.width].join(':');if(next!==key){key=next;build(view,size)}
   c.save();c.globalAlpha*=alpha;c.drawImage(cache,view.left,210,view.width,185);c.restore();
  },
  destroy(){if(cache)cache.width=cache.height=0;cache=null;key=''},
 };
}
