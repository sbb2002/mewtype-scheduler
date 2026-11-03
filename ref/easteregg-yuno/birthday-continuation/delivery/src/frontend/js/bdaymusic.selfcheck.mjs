import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { introScene, introBrightness, sceneLayout, smoothClock, decodeTrack, DROP } from './bdaylogic.js';
import { decodeSign } from './bdaysign.js';
assert.equal(DROP,17.14);
const times=[0,1.5,3,10,17,17.2,17.9,18.2,18.7];
assert.deepEqual(times.map(t=>+introBrightness(t).toFixed(5)),[.03,.2325,.3,.3,.3,2.29024,1.34073,1.12046,1]);
assert.equal(introBrightness(18.64),1);
for(let t=0;t<3;t+=.01)assert(introBrightness(t+.01)>=introBrightness(t)-1e-12);
for(let t=DROP;t<18.64;t+=.01)assert(introBrightness(t+.01)<=introBrightness(t)+1e-12);
assert.equal(introBrightness(17.139),.3);assert.equal(introBrightness(17.14),2.4);
for(let t=0;t<25;t+=.01){const b=introBrightness(t,true);assert(b>=.03&&b<=1)}
for(const [w,h] of [[1440,900],[390,844],[412,915],[360,800],[844,390]]){const L=sceneLayout(w,h);assert(Number.isFinite(L.offsetY));assert.equal(L.portrait,h/w>=1.25);if(L.portrait)assert.equal((395*L.scale+L.offsetY)/h,.68)}
const [strokes,widths]=decodeSign();assert.equal(strokes.length,20);assert.equal(widths.length,20);assert(strokes.flat().every(p=>p.length===2&&p.every(n=>n>=0&&n<=1)));
const state={};assert.equal(smoothClock(state,0,0,false),.02);assert.equal(smoothClock(state,90,1,false),90.02);assert.equal(smoothClock(state,4,2,true),4);assert.equal(state.value,null);
for(const key of ['noctural','midnight']){const T=decodeTrack(JSON.parse(await readFile(new URL(`../assets/birthday/beat/${key}.json`,import.meta.url))),await readFile(new URL(`../assets/birthday/beat/${key}.bin`,import.meta.url)));assert(T.beats.every((v,i,a)=>!i||v>a[i-1]));assert.equal(T.q.length,T.frames*T.nb);assert.equal(T.nb,24);assert(T.duration>150)}

for(const L of [sceneLayout(1440,900),sceneLayout(390,844)]){
 for(const t of [0,5,9.9,10])assert(introScene(t,L).y-102*L.sunScale>395);
 assert(introScene(10.1,L).y<introScene(10,L).y);
 assert.equal(introScene(16.9,L).y,267);assert.equal(introScene(17,L).y,267);
 assert.equal(introScene(6.3,L).spot,0);assert.equal(introScene(7.5,L).spot,1);assert.equal(introScene(18.14,L).spot,0);
 assert(introScene(17.3,L).wave<introScene(17.6,L).wave);
 assert.equal(introScene(12,L,false).y,267);assert.equal(introScene(12,L,true,true).spot,0);
}
console.log('생일 음악 self-check 통과: 기존 계약 + 일출 위치·조명 수명·파면·모션 줄이기');
