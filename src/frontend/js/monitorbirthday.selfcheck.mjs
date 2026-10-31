import assert from 'node:assert/strict';
import { MONITOR_BIRTHDAY_CODE, advanceMonitorBirthday, dialogExitDirection } from './monitorbirthdaylogic.js';

let progress=0;
for(const [i,value] of MONITOR_BIRTHDAY_CODE.entries()){
  progress=advanceMonitorBirthday(progress,value);assert.equal(progress,i+1);
}
assert.equal(advanceMonitorBirthday(8,'APP'),0);
assert.equal(advanceMonitorBirthday(9,'EXT'),0);
assert.equal(advanceMonitorBirthday(0,'EXT'),0);
assert.equal(advanceMonitorBirthday(2,'U'),2);
assert.equal(advanceMonitorBirthday(7,'U'),1);
assert.equal(advanceMonitorBirthday(10,'APP'),0);
const rect={left:100,top:100,right:300,bottom:300},center={x:200,y:200};
for(const [point,direction] of [[{x:200,y:70},'U'],[{x:200,y:330},'D'],[{x:70,y:200},'L'],[{x:330,y:200},'R']])assert.equal(dialogExitDirection(center,point,rect),direction);
assert.equal(dialogExitDirection(center,{x:200,y:200},rect),null);
assert.equal(dialogExitDirection(center,{x:200,y:95},rect),null);
assert.equal(dialogExitDirection({x:200,y:105},{x:200,y:90},rect),null);
assert.equal(dialogExitDirection({x:90,y:200},{x:70,y:200},rect),null);
assert.equal(dialogExitDirection({x:120,y:200},{x:70,y:70},rect),'L');
assert.equal(dialogExitDirection({x:200,y:120},{x:70,y:70},rect),'U');
console.log('모니터 생일 진입 self-check 통과: 경계·최소 거리·방향 접두사·EXT→APP 순서');
