// 플레이바의 왼쪽 손잡이만 이동을 시작한다. 위치는 이번 방문 동안만 유지한다.
export function mountBirthdayPlayerDrag({bar,grip,shell,title,disc}) {
  const events=new AbortController(),signal=events.signal,root=document.documentElement;
  const mobile=matchMedia('(max-width:700px), (pointer:coarse)');
  let position=null,drag=null,dead=false;
  function limits(){
    const view=window.visualViewport,x=view?.offsetLeft||0,y=view?.offsetTop||0;
    const width=view?.width||innerWidth,height=view?.height||innerHeight,r=bar.getBoundingClientRect();
    const style=getComputedStyle(shell),safe=side=>parseFloat(style.getPropertyValue('--bday-safe-'+side))||0;
    const top=y+safe('top')+12+(mobile.matches?title.offsetHeight+8:0);
    const floor=Math.min(y+height-safe('bottom')-12,disc.getBoundingClientRect().top-12);
    const left=x+safe('left')+12;
    return {left,right:Math.max(left,x+width-safe('right')-r.width-12),top,bottom:Math.max(top,floor-r.height),width:r.width};
  }
  function place(x,y){
    const b=limits();position={x:Math.min(b.right,Math.max(b.left,x)),y:Math.min(b.bottom,Math.max(b.top,y))};
    shell.style.setProperty('--bday-player-x',position.x+'px');shell.style.setProperty('--bday-player-y',position.y+'px');
    shell.style.setProperty('--bday-player-width',b.width+'px');shell.style.setProperty('--bday-title-height',title.offsetHeight+'px');
    bar.classList.add('is-positioned');shell.classList.add('is-positioned');
  }
  function finish(){
    const active=drag;drag=null;bar.classList.remove('is-dragging');
    if(active&&grip.hasPointerCapture(active.id))grip.releasePointerCapture(active.id);
  }
  function layout(){if(!dead&&position&&root.hasAttribute('data-bday-full'))place(position.x,position.y)}
  function reset(){
    finish();position=null;bar.classList.remove('is-positioned');shell.classList.remove('is-positioned');
    for(const key of ['x','y','width'])shell.style.removeProperty('--bday-player-'+key);
    shell.style.removeProperty('--bday-title-height');
  }
  grip.addEventListener('pointerdown',e=>{
    if(!e.isPrimary||e.button!==0||!root.hasAttribute('data-bday-full')||!root.hasAttribute('data-bday-revealed'))return;
    finish();const rect=bar.getBoundingClientRect();
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:rect.left,top:rect.top,moved:false};
    grip.focus({preventScroll:true});grip.setPointerCapture(e.pointerId);e.preventDefault();
  },{signal});
  grip.addEventListener('pointermove',e=>{
    if(!drag||drag.id!==e.pointerId)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.moved&&Math.hypot(dx,dy)<4)return;
    drag.moved=true;bar.classList.add('is-dragging');place(drag.left+dx,drag.top+dy);e.preventDefault();
  },{signal});
  for(const type of ['pointerup','pointercancel','lostpointercapture'])grip.addEventListener(type,e=>{if(drag?.id===e.pointerId)finish()},{signal});
  grip.addEventListener('click',e=>e.stopPropagation(),{signal});
  grip.addEventListener('keydown',e=>{
    if(!root.hasAttribute('data-bday-full')||!root.hasAttribute('data-bday-revealed'))return;
    if(e.key==='Home'){e.preventDefault();e.stopPropagation();reset();return}
    const directions={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]},d=directions[e.key];
    if(!d||e.ctrlKey||e.altKey||e.metaKey)return;
    e.preventDefault();e.stopPropagation();const r=bar.getBoundingClientRect(),step=e.shiftKey?32:8;place(r.left+d[0]*step,r.top+d[1]*step);
  },{signal});
  window.addEventListener('resize',()=>{finish();layout()},{signal});
  window.visualViewport?.addEventListener('resize',()=>{finish();layout()},{signal});
  window.visualViewport?.addEventListener('scroll',layout,{signal});
  const observer=new MutationObserver(()=>{if(root.hasAttribute('data-bday-full'))layout();else finish()});
  observer.observe(root,{attributes:true,attributeFilter:['data-bday-full']});
  return {destroy(){dead=true;finish();observer.disconnect();events.abort()}};
}
