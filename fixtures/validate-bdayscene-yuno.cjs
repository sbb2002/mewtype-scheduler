// v16 DOM 검증을 대체하는 실제 음악 장면 검증 진입점. 결과 이미지는 저장소 밖에 쓴다.
const {spawnSync}=require('node:child_process');
const path=require('node:path');
for(const script of ['verify_birthday_music.py','verify_birthday_lifecycle.py','compare_birthday_pixels.py']){
  const r=spawnSync('python',[path.join('scripts',script)],{cwd:path.resolve(__dirname,'..'),stdio:'inherit',windowsHide:true});
  if(r.status!==0)process.exit(r.status||1);
}
console.log('실행 완료. 성능/무공백 판정은 handoff/verify 결과를 확인하세요.');
