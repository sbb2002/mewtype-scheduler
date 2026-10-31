// 개발자 도구·스크린샷·음원 다운로드를 막는 보안 기능이 아닌 가벼운 억제.
export function mountBirthdayGuard(hosts) {
  let active=false,restore=[];const abort=new AbortController();
  const stop=e=>{if(active)e.preventDefault()};
  // 배경 Canvas는 pointer-events:none이므로 실제 빈 곳 우클릭은 body로 전달된다.
  for(const type of ['contextmenu','dragstart'])document.addEventListener(type,stop,{signal:abort.signal,capture:true});
  for(const host of hosts){host.draggable=false;for(const type of ['contextmenu','dragstart'])host.addEventListener(type,stop,{signal:abort.signal})}
  document.addEventListener('keydown',e=>{if(active&&(e.key==='F12'||((e.ctrlKey||e.metaKey)&&(['u','s'].includes(e.key.toLowerCase())||(e.shiftKey&&['i','j','c'].includes(e.key.toLowerCase()))))))e.preventDefault()},{signal:abort.signal});
  function setActive(value){
    if(active===value)return;active=value;
    for(const fn of restore)fn();restore=[];
    if(value)for(const host of hosts)for(const cv of host.querySelectorAll('canvas')){
      const ctx=cv.getContext('2d');
      for(const [obj,key,replacement] of [[cv,'toDataURL',()=> ''],[cv,'toBlob',cb=>cb(null)],[ctx,'getImageData',()=>new ImageData(1,1)]]){
        const desc=Object.getOwnPropertyDescriptor(obj,key);Object.defineProperty(obj,key,{configurable:true,value:replacement});restore.push(()=>{if(desc)Object.defineProperty(obj,key,desc);else delete obj[key]});
      }
    }
  }
  return {setActive,destroy(){setActive(false);abort.abort()}};
}
