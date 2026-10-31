import { advanceMonitorBirthday, dialogDirection } from './monitorbirthdaylogic.js';

export function mountMonitorBirthday() {
  const dialog=document.getElementById('reset-dlg'),open=document.getElementById('reset-open');
  const area=dialog.querySelector('.dlg-in'),frame=document.getElementById('f');
  const events=new AbortController(),signal=events.signal;
  let progress=0,gesture=null,expiry=0,edgeTimer=0,closeTimer=0,suppressClick=false,frameEvents=null;
  let tabHints=[],hintStyle=null;

  function restoreTabHints(){
    for(const saved of tabHints){
      saved.node.textContent=saved.label;saved.node.style.minWidth=saved.minWidth;
      saved.node.classList.remove('mon-bday-key','mon-bday-next');
      if(saved.aria===null)saved.node.removeAttribute('aria-label');else saved.node.setAttribute('aria-label',saved.aria);
    }
    tabHints=[];hintStyle?.remove();hintStyle=null;
  }
  function updateTabHints(){
    if(progress<8||progress>=10){restoreTabHints();return}
    try{
      const doc=frame.contentDocument;if(!doc)return;
      const app=doc.getElementById('tabBtnApp'),ext=doc.getElementById('tabBtnExt');if(!app||!ext)return;
      if(tabHints.length&&(tabHints[0].node!==app||tabHints[1].node!==ext))restoreTabHints();
      if(!tabHints.length){
        hintStyle=doc.createElement('style');hintStyle.id='mon-bday-key-style';
        hintStyle.textContent=`.tab-btn.mon-bday-key{color:#ffc1da;background:#39142a;outline:1px solid #ff488d88;outline-offset:3px;border-radius:5px;box-shadow:0 0 10px #ff488d99;text-shadow:0 0 8px #ff488d;font-weight:800}
          .tab-btn.mon-bday-next{color:#fff;outline-color:#8ae3e2;box-shadow:0 0 13px #8ae3e2aa,0 0 22px #ff488d88;animation:mon-bday-next 1.3s ease-in-out infinite alternate}
          @keyframes mon-bday-next{to{box-shadow:0 0 19px #8ae3e2cc,0 0 28px #ff488d99}}
          @media(prefers-reduced-motion:reduce){.tab-btn.mon-bday-next{animation:none}}`;
        doc.head.append(hintStyle);
        tabHints=[app,ext].map(node=>({node,label:node.textContent,minWidth:node.style.minWidth,aria:node.getAttribute('aria-label'),width:node.getBoundingClientRect().width}));
      }
      for(const saved of tabHints){
        const isApp=saved.node===app,key=isApp?'A':'B',next=progress===(isApp?9:8);
        saved.node.style.minWidth=saved.width+'px';saved.node.textContent=key;
        saved.node.classList.add('mon-bday-key');saved.node.classList.toggle('mon-bday-next',next);
        saved.node.setAttribute('aria-label',`${key} (${saved.label} 탭)${next?' · 다음 입력':''}`);
      }
    }catch{/* 같은 출처의 리포트에서만 임시 이름과 강조를 적용한다. */}
  }

  function clearEdge(){clearTimeout(edgeTimer);edgeTimer=0;dialog.removeAttribute('data-bday-edge')}
  function showEdge(direction){clearTimeout(edgeTimer);edgeTimer=0;dialog.dataset.bdayEdge=direction}
  function cancelGesture(){
    const active=gesture;gesture=null;
    if(active&&area.hasPointerCapture(active.id))area.releasePointerCapture(active.id);
  }
  function reset(){
    progress=0;clearTimeout(expiry);expiry=0;clearTimeout(closeTimer);closeTimer=0;
    open.classList.remove('bday-armed');cancelGesture();clearEdge();restoreTabHints();
  }
  function input(value){
    progress=advanceMonitorBirthday(progress,value);
    clearTimeout(expiry);expiry=0;
    open.classList.toggle('bday-armed',progress>=8&&progress<10);
    updateTabHints();
    if(progress===10){
      const url=new URL('./',location.href);url.searchParams.set('bday','yuno');
      const va=new URLSearchParams(location.search).get('va');if(va)url.searchParams.set('va',va);
      reset();location.assign(url.href);return;
    }
    if(progress)expiry=setTimeout(reset,30000);
    if(progress===8){
      // pointerup 뒤 호환 click이 먼저 소모되도록 확인창은 다음 이벤트 턴에 닫는다.
      closeTimer=setTimeout(()=>{closeTimer=0;if(dialog.open&&progress>=8)dialog.close()},0);
    }
  }
  dialog.addEventListener('pointerdown',e=>{
    if(!gesture)suppressClick=false;
    if(!e.isPrimary){cancelGesture();return}
    if(!dialog.open||e.button!==0||!area.contains(e.target)||e.target.closest('button,a,input,select,textarea'))return;
    cancelGesture();clearEdge();suppressClick=false;
    gesture={id:e.pointerId,pointerType:e.pointerType,start:{x:e.clientX,y:e.clientY},rect:dialog.getBoundingClientRect(),direction:null,moved:false};
    area.setPointerCapture(e.pointerId);e.preventDefault();
  },{signal});
  function move(e){
    if(!gesture||gesture.id!==e.pointerId)return;
    if(Math.hypot(e.clientX-gesture.start.x,e.clientY-gesture.start.y)>=8)gesture.moved=true;
    const direction=gesture.direction||dialogDirection(gesture.start,{x:e.clientX,y:e.clientY},gesture.rect,gesture.pointerType);
    if(direction&&!gesture.direction){gesture.direction=direction;showEdge(direction)}
    if(gesture.moved)e.preventDefault();
  }
  document.addEventListener('pointermove',move,{signal,passive:false});
  document.addEventListener('pointerup',e=>{
    if(!gesture||gesture.id!==e.pointerId)return;
    move(e);const active=gesture;cancelGesture();
    suppressClick=active.moved;
    if(active.direction){
      e.preventDefault();input(active.direction);
      edgeTimer=setTimeout(clearEdge,450);
    }
  },{signal});
  document.addEventListener('pointercancel',()=>{cancelGesture();clearEdge()},{signal});
  area.addEventListener('lostpointercapture',e=>{if(e.target===area&&gesture?.id===e.pointerId&&!area.hasPointerCapture(e.pointerId)){gesture=null;clearEdge()}},{signal});
  // 드래그 뒤의 호환 클릭이 되돌리기나 바깥 클릭으로 해석되지 않게 한다.
  dialog.addEventListener('click',e=>{if(suppressClick){suppressClick=false;if(e.detail){e.preventDefault();e.stopImmediatePropagation()}}},{signal,capture:true});
  open.addEventListener('click',()=>{suppressClick=false;reset()},{signal});
  document.getElementById('reset-cancel').addEventListener('click',reset,{signal});
  document.getElementById('reset-ok').addEventListener('click',reset,{signal});
  dialog.addEventListener('cancel',reset,{signal});
  dialog.addEventListener('close',()=>{cancelGesture();clearEdge();if(progress<8)reset()},{signal});
  window.addEventListener('resize',()=>{cancelGesture();clearEdge()},{signal});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)reset()},{signal});
  window.addEventListener('pagehide',reset,{signal});

  function attachFrame(){
    restoreTabHints();frameEvents?.abort();frameEvents=null;
    // srcdoc은 부모와 같은 출처이므로 라이브·스냅샷 모두 같은 탭 클릭 위임을 붙인다.
    try{
      const doc=frame.contentDocument;if(!doc)return;
      frameEvents=new AbortController();
      doc.addEventListener('click',e=>{
        if(progress<8||!e.target.closest)return;
        const tab=e.target.closest('#tabBtnExt,#tabBtnApp');
        if(tab)input(tab.id==='tabBtnExt'?'EXT':'APP');
      },{signal:frameEvents.signal});
      updateTabHints();
    }catch{/* 외부 출처 iframe으로 바뀌면 숨은 진입만 비활성화한다. */}
  }
  frame.addEventListener('load',attachFrame,{signal});attachFrame();
  return {destroy(){reset();frameEvents?.abort();events.abort()}};
}
