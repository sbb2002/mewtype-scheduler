from pathlib import Path
import json,hashlib,shutil,subprocess,tempfile
from PIL import Image
B=Path(__file__).parent
R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
H=Path(r'C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Documents-pyworks-mewtype-scheduler/cd557148-9ec6-47cb-b90f-a459b94aa233/scratchpad/handoff')
V=Path(tempfile.gettempdir())/'birthday-verify-third';O=H/'verify'/'third';O.mkdir(parents=True,exist_ok=True)
def git(*a):return subprocess.check_output(['git',*a],cwd=R,text=True,encoding='utf8').strip()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
assert git('branch','--show-current')=='feat/birthday-music-scene'
assert not git('status','--porcelain'),'워크트리가 깨끗하지 않음'
assert not git('diff','9dc7783','HEAD','--','src/frontend/js/config.js')
g=read(V/'performance-headed.json');c=read(V/'performance-software.json');a=read(V/'gapless.json')
m=read(V/'monitor/results.json');p=read(H/'verify/pixels.json');life=read(H/'verify/lifecycle.json');app=read(H/'verify/results.json');intro=read(H/'verify/addendum.json')
times=['7.5','14','17.3','25','110']
assert g['gpu_features']['2d_canvas']=='enabled' and g['gpu_features']['gpu_compositing']=='enabled'
assert all(g[t]['max']<=8 and g[t]['samples']==120 for t in times)
assert all(x['normalized']['changed_pixels_percent']==0 and x['normalized']['max_channel_difference']<=1 for x in p)
assert len(p)==7
for k in ['boundary-0','boundary-1','boundary-2']:
 assert a[k]['channels']==[0,1] and a[k]['bad']==0 and a[k]['count']>10000
assert a['seek']==110.125 and not a['destroy']['scheduled'] and not a['destroy']['timer'] and not a['destroy']['autoplayTimer']
assert not app['ordinary_birthday_requests'] and not app['errors'] and not life['errors'] and not intro['errors']
assert life['blocked']['paused'] and life['blocked']['prompt'] and not life['tap']['paused']
assert life['paused_seek_error_seconds']==0
assert all(life['after_midnight']['audit'][k]==0 for k in ['audios','contexts','urls','raf'])
assert life['after_destroyBirthday']['birthdayListeners']==0
assert intro['reduced']['raf']==0 and intro['spotlight_color'][0]>150
for name in ['pc-mouse','android-touch']:
 assert not m[name]['errors'] and m[name]['armed_glow'] and m[name]['storage_preserved_on_entry'] and m[name]['normal_reset']
 assert m[name]['wrong_direction'] and m[name]['wrong_tab'] and m[name]['timeout'] and m[name]['snapshot_reload']>0
commits=read(B/'commits.json')+[read(B/'monitor-commit.json')]
assert git('rev-parse','HEAD')==commits[-1]['commit']
for item in commits:assert 'Co-Authored-By: Codex <noreply@openai.com>' in git('show','-s','--format=%B',item['commit'])
for name in ['performance-headed.json','performance-software.json','gapless.json','selfchecks.txt']:shutil.copyfile(V/name,O/name)
for name in ['results.json','lifecycle.json','pixels.json','addendum.json']:shutil.copyfile(H/'verify'/name,O/name)
for pattern in ['addendum-*.png','mobile-*.png','pixels-*.png','diff-*.png','pc-app.png','intro-*.png']:
 for f in list((H/'verify').glob(pattern)):shutil.copyfile(f,O/f.name)
shutil.copytree(V/'monitor',O/'monitor',dirs_exist_ok=True)
dump(O/'commits.json',commits)
assets={}
refs=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/devpapers/ref/bgm_easteregg_birthday')
for title,key in [('Noctural Run','noctural'),('Midnight Groove','midnight')]:
 src=refs/(title+'.mp3');dest=R/f'src/frontend/assets/birthday/bgm/{key}.mp3'
 original=hashlib.sha256(src.read_bytes()).hexdigest();actual=hashlib.sha256(dest.read_bytes()).hexdigest();assert original==actual
 assets[key]={'sha256':actual,'bytes':dest.stat().st_size,'original_matches':True}
dump(O/'assets-sha256.json',assets)
summary={'date':'2026-11-01','branch':git('branch','--show-current'),'head':git('rev-parse','HEAD'),'clean_worktree':True,'selfchecks':len(list((R/'src/frontend/js').glob('*.selfcheck.mjs'))),'gpu_max_ms':max(g[t]['max'] for t in times),'gpu_frames':600,'pixel_changed_percent':0,'stereo_boundaries':3,'audio_bad_samples':0,'monitor_pc_and_android_emulation':'pass','real_Samsung_Browser':'unverified','real_iPhone_Safari':'unverified','software_8ms':'fail','pushed':False,'merged':False,'deployed':False,'version_constants_changed':False}
dump(O/'summary.json',summary)
(O/'changed-files.txt').write_text(git('diff','--name-status','9dc7783','HEAD')+'\n',encoding='utf8')
rows='\n'.join(f"| {t} | {g[t]['mean']:.2f} | {g[t]['p95']:.2f} | {g[t]['max']:.2f} | {c[t]['mean']:.2f} | {c[t]['p95']:.2f} |" for t in times)
commit_text='\n'.join(f"- `{x['commit'][:7]}` {x['subject']}" for x in commits)
boundary_text='\n'.join(f"- {k}: 두 채널 합 {a[k]['count']}샘플, 오차 1e-5 초과 {a[k]['bad']}개, 최대 오차 {a[k]['maxError']:.3g}." for k in ['boundary-0','boundary-1','boundary-2'])
legacy_means='/'.join(f"{intro['cpu'][t]['mean']:.2f}" for t in ['7.5','14','17.3'])
report=f'''

## 3차 결과 (2026-11-01, Codex)

인계 문서 §2 작업과 후속 모니터 진입 요청을 같은 `feat/birthday-music-scene` 워크트리에서 구현·검증하고 4개 커밋으로 저장했다. **GPU 가속 데스크톱의 8ms CPU 목표와 스테레오 무공백 예약 재생은 통과했다. 실제 삼성 브라우저·iPhone Safari는 미확인이며 출시·배포 승인으로 판정하지 않는다.** 소프트웨어 렌더링은 8ms를 넘는다. 앞 절의 커밋 0개·무공백 미통과 기록은 당시 상태이며 현재 결과는 이 절을 따른다.

### 구현과 확인한 오류 수정

- 바닥은 열별 색 정지점 계산을 한 프레임에 모으고 파면별 그라데이션을 좌표 이동으로 재사용한다. 오로라는 두 색 그라데이션을 공유한다. 조명 원뿔/바닥 풀은 화면 크기별 캐시로 바꾸고 유노는 작은 캔버스에 그린다. 픽셀 차이가 생겼던 바닥 잘라내기·클리핑·CPU 캔버스 후보는 채택하지 않았다.
- 최종 캡처에서 유노가 회색으로 눌리는 기존 합성 오류를 발견했다. 밝게 만든 8비트 캔버스를 부모 brightness .3에서 다시 어둡게 하면 색이 먼저 잘렸다. 기본 장면·유노·점등 파면을 별도 Canvas로 나누고 각각 최종 CSS 밝기를 적용해 해결했다. PC 7.5초 실제 이마 픽셀은 {tuple(intro['spotlight_color'])}이며 밝기/색 회귀 단언도 추가했다. 태양 점등도 실제 밝은 색으로 전파된다.
- 인계의 곡선 충돌 해결 지시에 따라 .03→.30@3초, 2.4→1.0@1.5초의 양 끝 값과 quadratic ease-out으로 통일했다. 1.5초 .2325, 17.2초 2.29024, 17.9초 1.34073, 18.2초 1.12046이다. 전파 중 기본 Canvas는 .30이고 별도 파면 레이어가 밝기를 합성한다. 이전 선형 표본을 현재 검사 기준으로 쓰지 않는다.
- 첫 곡은 스트리밍하면서 두 곡을 blob/PCM으로 준비한다. 이후 동일 AudioContext의 샘플 경계에 현재 곡과 다음 두 곡을 미리 예약한다. 처음 출력 교체는 Gain을 같은 시각에 바꿔 중복 재생을 피하고, 조작 재시작은 80ms 예약 여유를 둔다. 제목·박 지도·장면 시계도 같은 컨텍스트 시각을 사용한다. 종료 이벤트 처리 지연은 다음 곡의 실제 출력 시각을 결정하지 않는다.
- 초기 로딩 중 멈춘 미디어의 탐색이 0초로 돌아가는 경합을 재현해 수정했다. blob 메타데이터와 진행 중 디코드를 기다리고 준비된 버퍼 시계에서 정확히 탐색한다. 재생·일시정지·곡 선택·destroy의 비동기 경합과 자동재생 대기 타이머도 취소한다.

### 프레임 비용: 직접 계측, 환경과 한계

Chromium {g['browser_version']}, Windows, 1440×900, DPR 1. 실제 화면을 표시하고 테스트 응답에만 주입한 RAF 취소 함수로 기존 루프를 멈춘 뒤 시각별 120회, 프레임 사이 requestAnimationFrame 대기로 측정했다. 별도 브라우저 검사는 동시에 실행하지 않았다. **CPU가 Canvas 명령과 CSS 갱신을 제출한 비용이며 GPU 완료/디스플레이 표시 지연을 포함하지 않는다.** 워밍업 이후 비용이며 첫 캐시 생성 비용은 이 표에 포함하지 않는다.

- GPU: {g['renderer']}. CDP SystemInfo에서 2D Canvas·GPU 합성 enabled 확인.
- 소프트웨어: {c['renderer']}. 2D Canvas/GPU 합성 software 상태를 별도로 확인.

| 곡 시각(s) | GPU 평균(ms) | GPU p95(ms) | GPU 최대(ms) | 소프트웨어 평균(ms) | 소프트웨어 p95(ms) |
|---|---:|---:|---:|---:|---:|
{rows}

**통과: 이 GPU 환경에서 600프레임 모두 8ms 이하(최대 4.8ms). 미통과: 소프트웨어의 8ms 기준.** 소프트웨어는 평균 17.38~32.81ms로 느리며 바닥 합성이 남은 병목이다. 인계의 같은 추가 연출 검사(쉬지 않고 draw 120회)도 다시 실행해 평균 {legacy_means}ms 수준으로 개선됐지만 새 실제 프레임 간격 검사와 동일한 방법으로 혼동하지 않는다. 과거 44~72ms와는 세션 부하가 통제된 A/B 비교가 아니다.

검사 후보 중 Canvas를 화면 밖으로 옮겨 RAF를 정지시켰을 때는 소비되지 않은 GPU 명령의 일괄 처리 지연이 p95에 섞였다. 최종 검사는 화면을 표시해 이 방법 오류를 제거했다. 최종 원본 JSON만 위 수치의 근거로 사용한다. 이 데스크톱 GPU 결과로 모바일/모든 기기의 8ms를 보증하지 않는다.

### 직접 검증 결과

- 전체 self-check **11개 통과**(음악 장면 기존 10개 + 모니터 명령 1개). 최종 git diff/cached 공백 검사도 통과. 신규 파일 EOF 빈 줄도 커밋 전 검사에서 정리했다.
- PC 정본 비교 7시점: 의도된 유노 위치·사인 폭·드롭 보정 후 RGB 최대 차이 2 초과 변경 픽셀 **0%**, 전체 최대 채널 차이 **1/255**. 완전한 비트 동일이라고 쓰지 않는다. 수식·색·일정 변경은 없다.
- `verify_birthday_music.py`: 평일 장면/음원 요청 0, 강제 생일에서만 자원 요청, PC/모바일 390×844·412×915·360×800 컨트롤/안내 배치, 키보드, 기존 전환 폭죽 640/40개, 복사 억제와 복구, 숨김/화면 밖/모션 감소 RAF 0, 정리 후 UI/Canvas/AudioContext/blob/예약 소스/타이머 0, pageerror 0.
- `verify_birthday_lifecycle.py`: 실제 정책 차단→암전·0초·탭 안내, 실제 터치 시작, 모바일 슬라이더 숨김·Gain .3/음소거 0·저장 .64 복원, 자연 곡 경계, 정지 110.125초 탐색 오차 0, 자정 재판정 뒤 Audio·AudioContext·blob·RAF 0, destroyBirthday 뒤 생일 소유 리스너 0. 자동재생 판정 전에 locator/evaluate를 실행하면 도구가 사용자 활성화에 영향을 주므로 이 구간은 브라우저 시간 대기로 관찰했다. 재생 거부를 모의로 주입하지 않았다.
- `verify_birthday_addendum.py`: PC/모바일 각 16시점, 일출·스포트라이트·동심원 전파, 실제 RGB 색 단언, reduced-motion RAF 0, pageerror 0. 모바일 표본은 scene 인트로를 다시 켜 고정한 장면 검증이며 화면에 남은 인사/플레이어 UI를 최초 방문 UI 수명 증거로 쓰지 않는다.
- `verify_birthday_gapless.py`: 실제 AudioWorklet 입력을 캡처해 경계 전후 80ms의 양 채널 출력과 원본 PCM을 샘플별 비교했다. 세 번째 경계는 메인 스레드를 1초 막은 상태로 검사했다. 예약 사이 gap 0, 원본에 앱이 추가한 공백 없음. 원본 음원 자체의 침묵/페이드를 없앤 것은 아니다. OS 스피커 녹음이나 실물 Safari 출력 검사는 아니다.
{boundary_text}

음원 원본 SHA256 일치를 다시 검사했다(원본 2개 합 약 10MB 그대로). 디코드된 두 곡은 48kHz 스테레오에서 약 157MiB의 PCM을 사용한다. Web Audio 미지원/디코드 실패의 스트리밍 대체 경로는 무공백을 보장하지 않는다. 제품 소스에 전역 디버그 훅은 없으며 테스트에서만 응답을 계측한다.

### 후속 모니터 진입 요청과 가장자리 표시

초기화 확인창의 버튼을 제외한 안쪽에서 시작해 창 밖으로 **↑↑↓↓←→←→**를 각각 드래그/터치한다. 입력한 변이 즉시 시안/분홍빛으로 빛나고 손을 뗀 뒤 450ms 유지된다. 8방향 완료 시 상단 초기화 버튼이 빛나고 팝업이 닫힌다. 이후 같은 리포트의 **EXT → APP**으로 `./?bday=yuno`에 이동한다(`va`가 있으면 보존). 진입으로 localStorage를 지우지 않는다. 정상 되돌리기는 기존처럼 명시 클릭할 때만 지운다.

`verify_monitor_birthday.py`에서 제품의 실제 monitor_report 렌더러에 빈 테스트 이벤트를 넣어 리포트를 생성하고 PC 마우스와 Android(SamsungBrowser UA) 터치로 검사했다. JS 합성 pointer 이벤트가 아니라 CDP touchStart/Move/End를 사용했다. 네 가장자리의 실제 CSS 빛, 버튼 빛, 팝업 닫힘, 생일 페이지 도착, 잘못된 방향/탭, 30초 만료, 라이브 실패→스냅샷 iframe 교체 뒤 연결, 진입 전 생일 자원 요청 0, 저장값 보존과 정상 초기화를 모두 확인했다. pageerror 0. 터치 이동은 브라우저 프레임에서 합쳐질 수 있어 마지막 이동 직후 즉시 속성을 읽는 검사 오류를 프레임 대기로 수정했다. 백엔드는 변경하지 않았다.

**미확인**: 실제 삼성 브라우저 터치·성능·음향, 실제 iPhone Safari 자동재생·Gain·안전영역·주소창 높이·백그라운드 복귀·길게 누르기·메모리/프레임 비용. 에뮬레이션을 실기기 통과로 간주하지 않는다. 복사 억제는 우연한 가져가기를 어렵게 하는 장벽이며 다운로드/개발 도구/화면 캡처 완전 차단이 아니다.

### 커밋과 운영 상태

{commit_text}

4개 모두 한국어 메시지와 `Co-Authored-By: Codex <noreply@openai.com>`을 포함한다. 브랜치 HEAD `{git('rev-parse','HEAD')}`, 워크트리 깨끗함. **푸시·PR·병합·배포 없음, APP_VERSION/APP_DATE 변경 없음.** v4.11.0은 제안만 유지했다. 모니터의 새 진입도 아직 운영 사이트에는 반영되지 않았다. 사용자 수동 테스트를 위한 운영/프리뷰 반영은 별도 지시 대상이다.

저장소에 유지되는 요약: `docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`, 사용 순서: `docs/BIRTHDAY_SKIN.md` 「모니터에서 시험 화면 열기」. 재실행: 기존 명세의 4개 브라우저 검사 + `python scripts/verify_birthday_gapless.py`, `python scripts/verify_birthday_performance.py --headed`, `python scripts/verify_birthday_performance.py`, `python scripts/verify_monitor_birthday.py`. 성능 검사는 단독 실행한다.

고정한 3차 증거 폴더: `{O}`. GPU/소프트웨어 JSON, 스테레오 샘플 비교, 기존 브라우저 JSON·캡처, 모니터 캡처/결과, selfchecks, commits/summary/assets-sha256/manifest를 포함한다. `DONE3.flag`는 구현·검증·보고·커밋 완료 표시이고 전체 실기기 승인/배포 완료 표시가 아니다.
'''
report_path=H/'REPORT.md';existing=report_path.read_text(encoding='utf8')
assert '## 3차 결과 (2026-11-01, Codex)' not in existing,'이미 3차 결과가 있어 중복 작성하지 않음'
report_path.write_text(existing.rstrip()+report+'\n',encoding='utf8')
manifest={f.relative_to(O).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in O.rglob('*') if f.is_file() and f.name!='manifest.json'}
dump(O/'manifest.json',manifest)
(H/'DONE3.flag').write_text('구현·로컬 검증·4개 커밋·보고 완료. 실제 삼성/iPhone 검증과 운영/프리뷰 배포는 별도. HEAD '+git('rev-parse','HEAD')+'\n',encoding='utf8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
