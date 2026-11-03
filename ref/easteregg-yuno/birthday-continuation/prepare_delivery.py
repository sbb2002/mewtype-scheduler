from pathlib import Path
import json,hashlib
BASE=Path(__file__).parent
ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
def save(name,text):
 p=BASE/'delivery'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf8',newline='\n')
def read(name):return (ROOT/name).read_text(encoding='utf-8-sig')
logic=(BASE/'bdaylogic.js').read_text(encoding='utf-8-sig')
a=logic.index('  const points=');z=logic.index('\n}',a)
logic=logic[:a]+'''  const ease=x=>1-(1-Math.min(1,Math.max(0,x)))**2;
  if(t<3)return .03+.27*ease(t/3);
  if(t<DROP)return .30;
  return 2.4-1.4*ease((t-DROP)/1.5);'''+logic[z:]
logic=logic.replace('정본 표의 밝기 표본을 연속 선형 보간한다.','인계에서 확정한 양 끝 값과 ease-out 곡선을 따른다.')
save('src/frontend/js/bdaylogic.js',logic)
check=(BASE/'bdaymusic.selfcheck.mjs').read_text(encoding='utf-8-sig').replace('[.03,.17,.3,.3,.3,2.4,1.7,1.45,1]','[.03,.2325,.3,.3,.3,2.29024,1.34073,1.12046,1]')
check=check.replace('assert.equal(introBrightness(17.139)', '''assert.equal(introBrightness(18.64),1);
for(let t=0;t<3;t+=.01)assert(introBrightness(t+.01)>=introBrightness(t));
for(let t=DROP;t<18.64;t+=.01)assert(introBrightness(t+.01)<=introBrightness(t));
assert.equal(introBrightness(17.139)''')
save('src/frontend/js/bdaymusic.selfcheck.mjs',check)
save('src/frontend/js/bdayscene-yuno.js',(BASE/'bdayscene-yuno.js').read_text(encoding='utf8'))
audio=(BASE/'bdayaudio-next.js').read_text(encoding='utf8')
audio=audio.replace('volume=.3,revision=0;', 'volume=.3,revision=0,playRevision=0;')
audio=audio.replace('if(dead)return;ensureContext();const resume=', 'if(dead)return;const rev=++playRevision;ensureContext();const resume=')
audio=audio.replace('await resume;if(dead)return;', 'await resume;if(dead||rev!==playRevision)return;')
audio=audio.replace('    if(dead){for(const a of audios)a.pause();return}', '    if(dead||rev!==playRevision)return;')
audio=audio.replace('function pause(){if(dead)return;', 'function pause(){if(dead)return;playRevision++;')
audio=audio.replace('next(){return select(index+1)},previous(){return select(index-1)}', 'next(){return select(api.index+1)},previous(){return select(api.index-1)}')
audio=audio.replace('dead=true;revision++;playing=false;', 'dead=true;revision++;playRevision++;playing=false;')
save('src/frontend/js/bdayaudio.js',audio)
spec=read('docs/SPEC.md')
spec=spec.replace('이 Canvas 버전에서는 별도 폭죽을 추가하지 않는다.', '기존 전환 폭죽의 색·수식·지연을 유지한다.')
spec=spec.replace('곡 시각 0/1.5/3/17/17.14/17.2/17.9/18.2/18.64초의 밝기는 .03/.17/.30/.30/2.4/2.4/1.7/1.45/1.0이다. 정본 §9의 실측 표본을 우선해 구간별 선형 보간한다.', '인계의 곡선 충돌 해결 지시에 따라 밝기는 0→3초에 .03→.30, 17.14→18.64초에 2.4→1.0으로 quadratic ease-out한다. 3~17.14초는 .30이다. 따라서 1.5초 .2325, 17.2초 2.29024이며 기존 선형 표본은 현재 곡선의 검증 기준으로 쓰지 않는다.')
spec=spec.replace('실제 `audio.currentTime`에 LAT=.02 평활화를 적용한다. 첫 곡은 스트리밍, 다음 곡은 blob 선로딩, 임의 탐색은 blob을 사용한다.', '최초에는 `audio.currentTime`, 버퍼 전환 뒤에는 `AudioContext.currentTime`에 LAT=.02 평활화를 적용한다. 첫 곡을 스트리밍하면서 두 곡의 blob·박 지도를 선로딩·디코드하고 같은 컨텍스트 시각에 스트림 Gain과 버퍼 출력을 교체한다. 이후 현재 곡과 다음 두 곡의 AudioBufferSource를 종료 시각에 이어 예약하므로 메인 스레드의 ended 처리 지연이 곡 경계에 공백을 만들지 않는다. 제목·박 지도·장면 시계도 같은 예약 시각에서 바뀐다. 일시정지·탐색·곡 선택은 예약을 취소하고 다시 잡는다. Web Audio/디코드 불가 시 스트리밍으로 대체하며 이 경로는 무공백을 보장하지 않는다.')
spec=spec.replace('곡 종료 후 다음 요소를 재생하는 방식이므로 샘플 단위 무공백 연결은 보장하지 않는다. ', '')
spec=spec.replace('PC 프레임 CPU 8ms 목표는 현재 로컬 headless 검증에서 미달(바닥 합성이 병목)이며 출시 완료로 판정하지 않는다. 실기기 Safari·음향 무공백도 추가 확인이 필요하다.', '그라데이션 재사용·조명 캐시·캐릭터/파면 필터 영역 제한으로 프레임 비용을 줄였다. GPU 가속과 SwiftShader를 구분한 측정은 `scripts/verify_birthday_performance.py`, 실제 출력 샘플의 곡 경계 검증은 `scripts/verify_birthday_gapless.py`로 실행한다. 성능 수치는 CPU에서 Canvas 명령을 제출한 비용이며 GPU 완료 시각을 뜻하지 않는다. 실제 iPhone Safari 음향·자동재생·안전영역·주소창 검증은 남아 있다.')
spec=spec.replace('결과·성능 미통과 내역은 handoff REPORT.md를 따른다.', '후속 최적화·검증 결과는 handoff REPORT.md의 「3차 결과」를 따른다.')
save('docs/SPEC.md',spec)
skin=read('docs/BIRTHDAY_SKIN.md')
skin='\n'.join('**출시 전 확인**: 곡 전환은 Web Audio 예약 재생으로 개선했고 실제 경계 출력 샘플을 검사했다. GPU/소프트웨어 성능과 정본 픽셀 차이는 REPORT.md 「3차 결과」를 따른다. 실제 iPhone Safari 음향·주소창·안전영역·길게 누르기는 미확인이다. 복사 억제는 우연한 가져가기를 어렵게 하는 장벽이며 완전한 차단이 아니다. v4.11.0은 제안이며 번호 확정·병합·배포는 운영자 결정이다.' if line.startswith('**미완료 조건**:') else line for line in skin.split('\n'))
skin=skin.replace('결과·성능 미통과 내역은 handoff REPORT.md를 따른다.', '후속 최적화·검증 결과는 handoff REPORT.md의 「3차 결과」를 따른다.')
skin+='\n### 음악 장면 3차 인계\n\n바닥 띠는 열마다 그라데이션을 만들지 않고 파면별 그라데이션을 공유한다. 오로라는 두 색 그라데이션을 좌표 변환으로 재사용한다. 조명은 화면 크기가 바뀔 때만 캐시하고 캐릭터 밝기·점등 파면은 필요한 영역만 필터링한다. 밝기 곡선은 인계 지시에 따라 양 끝 값과 quadratic ease-out으로 통일했다. 성능 검사는 `verify_birthday_performance.py --headed`, 출력 샘플 검사는 `verify_birthday_gapless.py`. 두 곡 디코드는 48kHz·스테레오에서 약 157MiB의 PCM 메모리를 사용하며 destroy 시 예약 소스·타이머·버퍼·blob을 해제한다. 메모리 부족/디코드 실패 시 스트리밍을 유지한다.\n'
save('docs/BIRTHDAY_SKIN.md',skin)
version=read('docs/VERSION.md').replace('성능 8ms는 미통과이며 별도 캡처·계측 결과를 보고서에 덧붙였다.', '그라데이션 재사용·조명 캐시·필터 영역 제한으로 최적화하고 GPU/소프트웨어 환경을 구분해 측정했다.')
version=version.replace('프레임 CPU 8ms 목표 미달, 샘플 단위 무공백 전환 미확인, 실제 iOS Safari 확인이 남아 출시 완료로 판정하지 않는다.', '곡 경계는 AudioBufferSource를 같은 컨텍스트 시각에 예약하고 실제 출력 샘플로 검사했다. CPU 제출 비용과 픽셀 차이의 최종 수치는 REPORT.md 「3차 결과」를 따른다. 실제 iOS Safari 확인이 남아 출시 완료로 판정하지 않는다.')
save('docs/VERSION.md',version)
claude=read('CLAUDE.md').replace('player.js playerbtn.js songs.js', 'player.js playerbtn.js songs.js')
claude=claude.replace('bdayaudio.js bdayplayer.js bdayguard.js', 'bdayaudio.js bdayplayer.js bdayguard.js')
claude+='\n생일 음악 후속 구현은 `docs/BIRTHDAY_MUSIC_SCENE_SPEC.md`와 `docs/BIRTHDAY_SKIN.md`를 따른다. 첫 스트리밍 뒤 Web Audio 예약 재생으로 전환한다. 성능은 GPU/소프트웨어를 구분하고 실제 iPhone Safari는 별도 확인한다. 현재 버전 상수는 운영자 확정 전 바꾸지 않는다.\n'
save('CLAUDE.md',claude)
lifecycle=read('scripts/verify_birthday_lifecycle.py')
lifecycle=lifecycle.replace("    page.evaluate('()=>{window.transfer={};for(const a of testAudios){a.onended=()=>transfer.ended=performance.now();a.onplaying=()=>{if(transfer.ended)transfer.playing=performance.now()}}}')", "    page.wait_for_function('__birthday.audio.diagnostics().engine===\"buffer\"')")
lifecycle=lifecycle.replace('# 실제 ended 이벤트까지 재생(합성 이벤트로 대체하지 않는다).','# 예약한 실제 곡 경계까지 재생한다(합성 ended 이벤트 없음).')
lifecycle=lifecycle.replace("result['real_ended']", "result['natural_boundary']")
lifecycle=lifecycle.replace("    result['transition_event_gap_ms']=page.evaluate('()=>transfer.playing-transfer.ended')", "    result['scheduled_transitions']=page.evaluate('()=>__birthday.audio.diagnostics().transitions')\n    assert result['scheduled_transitions'] and all(t['gap']==0 for t in result['scheduled_transitions'])")
save('scripts/verify_birthday_lifecycle.py',lifecycle)
for name,out in [('profile.py','verify_birthday_performance.py'),('audio_verify.py','verify_birthday_gapless.py')]:
 s=(BASE/name).read_text(encoding='utf8')
 s=s.replace("ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')", "ROOT=Path(__file__).resolve().parents[1]\nimport os,tempfile\nOUT=Path(os.environ.get('BIRTHDAY_VERIFY_OUT',str(Path(tempfile.gettempdir())/'birthday-verify-third')))\nOUT.mkdir(parents=True,exist_ok=True)")
 if name=='profile.py':s=s.replace("Path(__file__).with_name('profile-headed.json' if '--headed' in sys.argv else 'profile.json')", "(OUT/('performance-headed.json' if '--headed' in sys.argv else 'performance-software.json'))")
 else:s=s.replace("Path(__file__).with_name('audio-results.json')", "(OUT/'gapless.json')")
 save('scripts/'+out,s)
files=[str(p.relative_to(BASE/'delivery')).replace('\\','/') for p in (BASE/'delivery').rglob('*') if p.is_file()]
manifest={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() if (ROOT/f).exists() else None for f in files}
(BASE/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('\n'.join(files))

