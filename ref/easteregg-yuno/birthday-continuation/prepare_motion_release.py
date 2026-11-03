from pathlib import Path
root=Path(__file__).resolve().parents[2]
work=root.parent/'mewtype-scheduler-worktrees/v4/hotfix-birthday-greeting-motion'
for source,target in [('check_greeting_motion.py','verify_birthday_greeting.py'),('check_birthday_sky.py','verify_birthday_sky.py')]:
 s=(Path(__file__).parent/source).read_text(encoding='utf8')
 s=s.replace("Path(__file__).resolve().parents[2].parent/'mewtype-scheduler-worktrees/v4/hotfix-birthday-greeting-motion'",'Path(__file__).resolve().parents[1]')
 (work/'scripts'/target).write_text(s,encoding='utf8')
for name in ['README.md','CLAUDE.md','src/frontend/js/config.js']:
 p=work/name;s=p.read_text(encoding='utf8').replace('4.11.1','4.11.2');p.write_text(s,encoding='utf8')
for name in ['docs/BIRTHDAY_SKIN.md','docs/SPEC.md']:
 p=work/name;s=p.read_text(encoding='utf8').replace('모바일 곡 제목은 위를 따라간다.','모바일 곡 제목은 우하단에 고정하며 플레이바가 제목·하단 안내 위에서 멈춘다(v4.11.2).').replace('모바일의 곡 제목은 옮긴 플레이바 위를 따라간다.','모바일 곡 제목은 우하단에 고정하고 플레이바가 제목·하단 안내 위에서 멈추도록 제한한다(v4.11.2).').replace('기존 인트로 공개·퇴장 시각은 유지한다.','인트로 공개는 19초로 유지하고, 인사말은 시차 등장·빛 연출 후 4.8초부터 2.8초 동안 사라진다(v4.11.2).');p.write_text(s,encoding='utf8')
p=work/'docs/BIRTHDAY_MUSIC_SCENE_SPEC.md';s=p.read_text(encoding='utf8').replace('모바일은 컨트롤 바로 위 우측.','모바일도 화면 우하단에 고정하며 하단 SUNO 안내 위에 여백을 둔다. 이동 플레이바는 제목 위에서 멈춘다(v4.11.2).');p.write_text(s,encoding='utf8')
description='''
### 인사말·모바일 배치·음악 우선권 보완 (v4.11.2, 운영자 지정 핫픽스)

- 19초 공개 후 영문/아래 문구가 0.3초 시차로 1.4초 동안 떠오르고 금빛·분홍빛으로 빛난다. 4.8초 후 2.8초 동안 함께 서서히 사라진다. 모션 줄이기는 이동·빛 애니메이션 없이 등장하고 페이드만 유지한다.
- 모바일 BGM 제목은 우하단 고정(안전영역 + 아래 64px), SUNO 안내는 아래 38px이다. 플레이바 기본 아래 여백은 110px이며 이동 시 제목 위 12px까지 제한한다. 긴 제목은 줄바꿈한다.
- 배경의 작은 네 갈래 별은 반경 1.2~2.6 CSS px, 여러 개가 서로 다른 주기로 반짝인다. 19초 이후 9초 주기마다 작은 폭죽 두 발이 0.55초 시차로 터진 뒤 약 6초 쉰다. 별·폭죽 모두 곡 시각에 종속되어 정지하면 멈추며 모션 줄이기에서는 생략한다. 별도 타이머/리스너/이미지 로드는 없다.
- 태양 펄스의 하늘 클립을 모바일 확장 하늘까지 늘리고 실제 태양 위치·크기에 맞췄다. 지평선 아래를 가리지 않는다. 유성의 원래 영역은 유지한다.
- 모바일 UFO/궤적/퇴장 별은 실제 보이는 하늘 영역으로 좌표를 매핑한다. 사인 경로는 원래 모바일 사인 배치를 유지한다. PC 경로는 유지한다.
- 유메미타 플레이어가 PLAYING/BUFFERING이면 생일 BGM을 즉시 일시정지하고 재생을 막는다. 유메미타가 멈춰도 BGM은 자동 재개하지 않고 생일 제어 버튼으로 재개한다. 대기 중인 BGM 재생도 취소하며, 생일 오디오 정리 시 구독을 해제한다.
'''
for name in ['docs/BIRTHDAY_SKIN.md','docs/BIRTHDAY_MUSIC_SCENE_SPEC.md']:
 p=work/name;p.write_text(p.read_text(encoding='utf8')+description,encoding='utf8')
p=work/'docs/SPEC.md';s=p.read_text(encoding='utf8');s=s.replace('- **생일 플레이바 보완', '- **생일 연출 후속(v4.11.2)**: 19초 공개 뒤 두 줄 시차 등장·금빛/분홍빛 글로우, 4.8초 후 2.8초 페이드아웃. 배경의 작은 별과 간헐적 폭죽은 곡 시각을 따르고 모션 줄이기에서는 생략한다. 모바일 태양 펄스는 확장 하늘까지 퍼지고 UFO·궤적은 실제 모바일 하늘에 매핑한다. 유메미타 플레이어가 재생/버퍼링하면 생일 BGM을 정지하고 수동 재개 전까지 유지한다. 상세 = `docs/BIRTHDAY_SKIN.md` v4.11.2 절.\n- **생일 플레이바 보완',1);p.write_text(s,encoding='utf8')
p=work/'docs/VERSION.md';s=p.read_text(encoding='utf8');i=s.index('- **v4.11.1**');s=s[:i]+'''- **v4.11.2** (일반 패치·핫픽스, 2026-11-01 — 브랜치 `hotfix/birthday-greeting-motion`, 프론트만): **생일 인사말 등장·느린 퇴장, 모바일 배치와 하늘 효과, 유메미타 재생 우선권 보완.** 운영자 지정 핫픽스.
  - 영문/이름·날짜의 시차 등장과 금빛·분홍빛 글로우, 2.8초 페이드아웃. 모바일 BGM 제목 우하단 고정·안내/이동 플레이바와 겹침 방지.
  - 곡 시각에 따라 작은 별 여러 개와 간헐적 폭죽. 모션 줄이기에서 생략. 모바일 태양 펄스 상단 잘림과 UFO 경로 개선.
  - 유메미타 플레이어 재생/버퍼링 우선, 생일 BGM 일시정지·재시작 차단, 자동 재개 없음. 생일 제어 버튼으로 수동 재개.
  - 검증 결과는 `docs/BIRTHDAY_GREETING_HOTFIX_VERIFICATION.md`. 배포 진행: 검증 후 병합·배포. 롤백 = `d77667b`(v4.11.1 완료 main). 백엔드·음원 자산 변경 없음.

'''+s[i:];p.write_text(s,encoding='utf8')
