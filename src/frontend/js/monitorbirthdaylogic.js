// 초기화 확인창의 바깥으로 밀어내는 방향과 숨은 진입 순서를 계산한다.
export const MONITOR_BIRTHDAY_CODE = ['U','U','D','D','L','R','L','R','EXT','APP'];

export function advanceMonitorBirthday(progress, input) {
  const code=MONITOR_BIRTHDAY_CODE;
  if(progress<0||progress>=code.length)return 0;
  if(code[progress]===input)return progress+1;
  // 방향 입력 중에는 잘못 누른 뒤에도 새 ↑↑ 시작을 인식한다.
  if(progress>=8)return 0;
  const seen=code.slice(0,progress).concat(input);
  for(let n=Math.min(8,seen.length);n>0;n--){
    if(code.slice(0,n).every((v,i)=>v===seen[seen.length-n+i]))return n;
  }
  return 0;
}

export function dialogExitDirection(start, point, rect) {
  if(start.x<rect.left||start.x>rect.right||start.y<rect.top||start.y>rect.bottom)return null;
  const dx=point.x-start.x,dy=point.y-start.y;
  if(Math.hypot(dx,dy)<24)return null;
  const exits=[];
  if(point.y<rect.top-12)exits.push(['U',(rect.top-start.y)/dy]);
  if(point.y>rect.bottom+12)exits.push(['D',(rect.bottom-start.y)/dy]);
  if(point.x<rect.left-12)exits.push(['L',(rect.left-start.x)/dx]);
  if(point.x>rect.right+12)exits.push(['R',(rect.right-start.x)/dx]);
  // 모서리로 나가도 출발점에서 가장 먼저 통과한 변을 한 번만 센다.
  exits.sort((a,b)=>a[1]-b[1]);
  return exits[0]?.[0]||null;
}

// 모바일은 화면 끝까지 밀지 않아도 창 안에서 짧게 한 방향으로 밀면 인식한다.
export function dialogDirection(start, point, rect, pointerType='mouse') {
  if(pointerType==='mouse')return dialogExitDirection(start,point,rect);
  if(start.x<rect.left||start.x>rect.right||start.y<rect.top||start.y>rect.bottom)return null;
  const dx=point.x-start.x,dy=point.y-start.y,x=Math.abs(dx),y=Math.abs(dy);
  if(Math.max(x,y)<36)return null;
  if(x>=y*1.25)return dx<0?'L':'R';
  if(y>=x*1.25)return dy<0?'U':'D';
  return null;
}
