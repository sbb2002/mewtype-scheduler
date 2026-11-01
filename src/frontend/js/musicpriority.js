// 유메미타 플레이어가 재생/버퍼링 중이면 생일 BGM보다 우선한다.
let active=false;
const listeners=new Set();
export const mainMusicActive=()=>active;
export function setMainMusicActive(value){
  value=!!value;if(active===value)return;active=value;
  for(const listener of listeners)listener(active);
}
export function subscribeMainMusic(listener){listeners.add(listener);return()=>listeners.delete(listener)}
// 생일 장면이 자정에 켜질 때 유메미타 플레이어에게 자리를 넘겨받는다. 플레이어가 안 떠 있으면 할 일이 없다.
let handOff=null;
export function setMainMusicHandOff(fn){handOff=fn}
export function handOffMainMusic(ms){handOff?.(ms)}
