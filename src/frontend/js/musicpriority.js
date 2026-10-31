// 유메미타 플레이어가 재생/버퍼링 중이면 생일 BGM보다 우선한다.
let active=false;
const listeners=new Set();
export const mainMusicActive=()=>active;
export function setMainMusicActive(value){
  value=!!value;if(active===value)return;active=value;
  for(const listener of listeners)listener(active);
}
export function subscribeMainMusic(listener){listeners.add(listener);return()=>listeners.delete(listener)}
