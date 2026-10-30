const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const read=n=>fs.readFileSync(path.join(__dirname,n),'utf8');
const old=read('round18.js'),now=read('round19.js');
const pose=s=>s.slice(s.indexOf('function djPose15('),s.indexOf('\n}',s.indexOf('function djPose15('))+2);
assert.strictEqual(pose(old),pose(now));
const ctx={window:{}};vm.createContext(ctx);vm.runInContext(now,ctx);
const result=vm.runInContext(`(()=>{const mean=Array(40).fill(0);let independent=0,capGap=0;for(let n=0;n<384;n++){const t=n*.1;const values=Array.from({length:40},(_,i)=>spectrum19(t,i,40));values.forEach((v,i)=>{mean[i]+=v.height/384;capGap=Math.max(capGap,v.cap-v.height)});if(values.some((v,i)=>i&&Math.abs(v.height-values[i-1].height)>.5))independent++;}return {meanByBand:mean,lowMean:mean.slice(0,13).reduce((a,b)=>a+b)/13,highMean:mean.slice(27).reduce((a,b)=>a+b)/13,nonflatFrames:independent,frames:384,maxCapGap:capGap}})()`,ctx);
assert(result.lowMean>result.highMean&&result.maxCapGap>5&&result.nonflatFrames>=383);
result.yunoPoseIdentical=true;result.seedPeriodBeats=64;result.attackMS=40;result.releaseMSRange=[139.2,519.8];
fs.writeFileSync(path.join(__dirname,'spectrum_stats19.json'),JSON.stringify(result,null,2));console.log(result);

