import assert from 'node:assert/strict';
import { createListenTracker, loadUnlocked, saveUnlocked, REWARD_KEY } from './bdayreward.js';

const D=[214.8,214];
function play(tr,index,from,to,step=.25,silent=false){for(let t=from;t<=to;t+=step)tr.update({index,time:t,duration:D[index],paused:false,silent})}

// 두 곡 자연 재생 = 해제
{const tr=createListenTracker();play(tr,0,0,214.7);play(tr,1,0,213.9);assert.equal(tr.complete(),false,'둘째 곡이 끝나기 전');
 assert.equal(tr.cardReady(),true);play(tr,0,0,1);assert.equal(tr.complete(),true,'자연 전환 후')}

// 탐색으로 끝만 찍으면 해제 안 됨
{const tr=createListenTracker();play(tr,0,0,1);play(tr,0,213,214.7);play(tr,1,0,1);play(tr,1,212,213.9);play(tr,0,0,1);
 assert.equal(tr.complete(),false);assert.equal(tr.cardReady(),false)}

// 다음 곡 버튼(곡 중간 전환) = 끝까지 들은 것이 아님
{const tr=createListenTracker();play(tr,0,0,100);play(tr,1,0,1);assert.equal(tr.coverage(0)<.5,true);play(tr,1,1,213.9);play(tr,0,0,1);assert.equal(tr.complete(),false)}

// 같은 구간 반복은 누적되지 않음
{const tr=createListenTracker();for(let i=0;i<4;i++)play(tr,0,0,60);assert.equal(Math.round(tr.coverage(0)*214.8)<=62,true)}

// 일시정지 동안은 세지 않음
{const tr=createListenTracker();for(let t=0;t<50;t+=.25)tr.update({index:0,time:t,duration:D[0],paused:true});assert.equal(tr.coverage(0),0)}

// 볼륨 0 으로 들은 구간은 세지 않음
{const tr=createListenTracker();play(tr,0,0,214.7,.25,true);play(tr,1,0,213.9);play(tr,0,0,1);assert.equal(tr.coverage(0)<.02,true);assert.equal(tr.complete(),false)}

// 곡을 다 듣고 마무리만 무음이어도 해제 · 카드 없음. 다음 바퀴에 소리를 켜고 마치면 해제.
{const tr=createListenTracker();play(tr,0,0,214.7);play(tr,1,0,211);play(tr,1,211.25,213.9,.25,true);assert.equal(tr.cardReady(),false,'마무리 무음에는 카드 없음');
 play(tr,0,0,1,.25,true);assert.equal(tr.complete(),false);play(tr,0,1.25,214.7);play(tr,1,0,213.9);assert.equal(tr.cardReady(),true);play(tr,0,0,1);assert.equal(tr.complete(),true)}

// 첫 곡을 먼저 완곡했어도 다음 바퀴의 첫 곡 마무리가 무음이면 그 완곡은 무효
{const tr=createListenTracker();play(tr,0,0,214.7);play(tr,1,0,100);play(tr,1,101,102);play(tr,0,0,1);play(tr,0,213,214.7,.25,true);play(tr,1,0,1);assert.equal(tr.complete(),false);assert.equal(tr.cardReady(),false)}

// 저장 — 정상 · 차단
{const m=new Map(),s={getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v)};assert.equal(loadUnlocked(s),false);saveUnlocked(s);assert.equal(m.get(REWARD_KEY),'1');assert.equal(loadUnlocked(s),true);
 const b={getItem(){throw Error('x')},setItem(){throw Error('x')}};assert.equal(loadUnlocked(b),false);saveUnlocked(b)}
console.log('bdayreward selfcheck ok');
