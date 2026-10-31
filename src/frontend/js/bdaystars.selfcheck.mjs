import assert from 'node:assert/strict';
import {createAmbientTimeline,ambientVisibility,backgroundStars,backgroundFireworks,backgroundMeteors} from './bdaystars.js';
const blocked=[[0,19],[45,60],[120,140]];
for(let seed=0;seed<100;seed++){
  const events=createAmbientTimeline(180,blocked,seed);
  assert(events.length>=5&&events.length<=16);
  assert.deepEqual(events,createAmbientTimeline(180,blocked,seed));
  assert.notDeepEqual(events,createAmbientTimeline(180,blocked,seed+100));
  assert(events.some(e=>e.kind==='meteor')&&events.some(e=>e.kind==='fireworks'));
  for(const [i,event] of events.entries()){
    assert(event.start>=19&&event.end<=180);
    assert(!blocked.some(([a,b])=>event.start<b+.8&&event.end>a-.8));
    if(i)assert(event.start-events[i-1].end>=5);
    const sample=event.start+.75;
    assert((event.kind==='meteor'?backgroundMeteors(sample,events):backgroundFireworks(sample,events)).length>0);
  }
  for(const [a,b] of blocked){
    assert.equal(ambientVisibility((a+b)/2,blocked),0);
    assert.equal(backgroundFireworks((a+b)/2,events).length,0);
    assert.equal(backgroundMeteors((a+b)/2,events).length,0);
  }
}
assert.equal(ambientVisibility(30,blocked),1);
assert(ambientVisibility(19.4,blocked)>0&&ambientVisibility(19.4,blocked)<1);
const sample=backgroundStars(35,99);backgroundStars(400,99);
assert.deepEqual(sample,backgroundStars(35,99));
assert(sample.every(s=>s.radius<=2.6&&s.x>0&&s.x<1&&s.y>0&&s.y<1));
console.log('Ambient sky: 100 random plans; fixed-scene exclusion, spacing, replay determinism and both event types passed.');
