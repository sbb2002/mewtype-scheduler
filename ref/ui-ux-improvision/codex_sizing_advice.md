**우선은 색이나 장식을 더하기보다, 조작 요소의 높이와 여백을 역할별로 정리하는 편이 효과가 큽니다.** 현재 24·26·27·28px 조작부가 혼재합니다. 다만 작은 외형에도 터치 영역을 확장한 요소가 있으므로, 보이는 크기와 누르는 범위를 구분해야 합니다. [playerpop.css:393](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:393), [layout.css:269](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:269)

지정한 CSS 9개, 제품 문서, 실측표와 첨부 화면을 대조했습니다. 아래는 **구현 전 자문**이며 파일 수정·커밋은 하지 않았습니다. 수치는 CSS px이고, `≈`는 계산상 추정치입니다. 시각적 효과의 순위는 디자인 판단입니다.

**1. 기능 요소 크기 체계**

기본 높이는 **폰 28 / 36 / 44 / 56px**, **PC 28 / 32 / 40 / 56px**로 제안합니다. 순서대로 밀집 칩, 보조 선택, 일반 조작, 두 줄 목록입니다. 원형 아이콘·배지·미디어에는 이 단계를 강제하지 않습니다.

패딩은 아래 표처럼 역할별로 묶고, 반경은 일반 조작부 8px·카드 12px·독립 칩 999px를 기준으로 삼으면 됩니다. 현재 기본 글자는 14px이고 `rem` 값이 다양하므로, 전역 글자 크기를 바꾸기보다 해당 선택자에서 조정하는 편이 안전합니다. [layout.css:74](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:74)

표의 패딩은 **상하 / 좌우**, `연동`은 다른 배치 계산도 함께 수정해야 한다는 뜻입니다.

| 역할·대상 | 폰: 현재 → 제안 | PC: 현재 → 제안 | 패딩·반경·글자 제안 | 근거·주의 |
|---|---|---|---|---|
| 상단 소식 칩 `.ntc__cchip` | 높이 26 → **28** | 26 → **28** | `0 / 6`, 반경 999, 글자 13 유지. 폭·아이콘 14 유지 | [notices.css:113](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:113). **폭 확대 주의** |
| 상단 막대·펼침·테마 | 막대 35.2 → **44**, 버튼 약 36×33 → **36×42** | 막대 35.2 → **36**, 버튼 약 46×33 → **40×34** | 버튼 패딩 0·반경 0 유지. 막대 반경 6→8. 테마 아이콘 폰 16→18, PC 16 유지 | [notices.css:67](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:67), [theme.css:137](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/theme.css:137). **연동** |
| 플레이어 필터·정렬 | 높이 24 → **36** | 24 → **32** | 필터 `0 / 10`, 반경 999. 정렬 `0 / 8`, 반경 6→8. 글자 12→13 | [playerpop.css:393](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:393). 폰 가로 스크롤 유지 |
| 언어·보기 전환의 내부 버튼 | 소식 27·트윗 28 → **36** | 소식 27·트윗 28·보기 27 → **32** | 좌우 10~12, 글자 13. 트윗·보기 내부 반경 8, 소식 알약형 유지 | [notices.css:237](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:237), [tweets.css:245](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:245), [timetable.css:33](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:33). **트윗 헤더 폭 주의** |
| 플레이어 탭 | 41 → **44** | 43 → **40** | `0 / 8`, 반경 0·밑줄 유지, 글자 13.6→14 | [playerpop.css:340](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:340), [playerpop.css:588](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:588) |
| 플레이어 검색창 **외곽** | ≈35 → **44** | ≈41 → **40** | 외곽 `0 / 12`, 반경 8 유지. 입력 글자 **16 유지**, 줄높이 24 | [playerpop.css:368](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:368), [playerpop.css:601](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:601). 실측표의 33·39는 입력 요소 자체 높이 |
| 이후 예고 펼치기 | 42 → **최소 44** | 42 → **최소 40** | `0 / 14`, 반경 10→8, 글자 13.6→14. 줄바꿈 시 높이 증가 허용 | [timetable.css:438](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:438) |
| 멤버 헤더 YouTube·X | 26×26 → **32×32** | **22×22 유지** | 패딩 0, 폰 반경 5→8·아이콘 17→18. 폰 두 버튼 간격 6→4 | [tweets.css:28](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:28). **헤더 폭·높이 주의** |
| 하단 플레이어·표 버튼 | 47×26 → **47×32** | 해당 없음 | `0 / 7`, 반경 999·아이콘 31×18 유지. 기존 세로 터치 범위 44 유지 | [player.css:57](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/player.css:57), [timetable.css:855](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:855), [layout.css:275](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:275) |
| 곡 목록의 재생 버튼 | 48 → **최소 56**, 내용 높이 허용 | 실측 54·70 **유지** | 폰 패딩 `0 / 6`→`8 / 8`, 제목 14 유지·보조 글자 약 11.5→12. PC 패딩 8 유지 | [playerpop.css:409](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:409), [playerpop.css:609](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:609). **화면당 곡 수 감소** |
| 행사 배너 선택 탭 | 53 → **최소 56** | 53 → **최소 56** | 패딩 `7 / 12`→`8 / 12`, 반경 10→12. 상태 12/줄높이16, 제목14/줄높이20 | [banners.css:155](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:155), [banners.css:195](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:195). 탭 폭·다음 탭 노출 유지 |

세 가지는 특히 연동해서 봐야 합니다.

- **상단 높이:** `--ntc-item-h`를 바꾸면 폰의 `--m-notice`도 높이 차이만큼 조정해야 합니다. 레인 높이가 이 값을 빼고 계산됩니다. 제안대로라면 폰에서 차이는 **+8.8px**입니다. [notices.css:30](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:30), [layout.css:427](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:427), [layout.css:457](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:457)
- **상단 가로폭:** 칩의 좌우 패딩까지 늘리면 390px에서 먼저 밀립니다. 아이콘+숫자 구성과 현재 가로 스크롤을 유지하고, 두 자리 숫자도 확인해야 합니다. [notices.css:122](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:122), [notices.css:366](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:366)
- **헤더 아이콘:** 폰 버튼을 32px로 바꾸면 기존 투명 확장 영역도 다시 계산해야 합니다. 현재 규칙을 그대로 두면 가로 50px까지 넓어집니다. 제안은 **누름 영역 44×36**, 두 버튼 간격 4px입니다. [layout.css:277](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:277)

**2. 세련돼 보이는 효과가 큰 순서 — 상위 8개**

1. **상단 소식 막대의 세로 여백 정리.** 폰 막대 44px·칩 28px로 만들면 가장 자주 보이는 조작부가 덜 눌려 보입니다. 지금은 확장한 터치 영역까지 막대에서 잘립니다. 칩 폭은 유지하는 것이 핵심입니다. [notices.css:67](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:67), [layout.css:282](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:282)

2. **플레이어 검색·필터·정렬을 한 묶음으로 정돈.** 폰 검색 44px, 필터·정렬 36px로 맞추면 첨부 플레이어에서 크기 차이가 큰 조작부들이 안정됩니다. PC는 검색 40px·필터 32px로 밀도를 유지합니다. [playerpop.css:367](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:367), [playerpop.css:598](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:598)

3. **언어·보기 전환 버튼의 내부 높이 통일.** 현재 27~28px인 버튼을 폰 36px·PC 32px로 묶습니다. 트윗 시트의 멤버 얼굴과 번역 버튼 사이에서 느껴지는 크기 불균형도 완화됩니다. 멤버 칩 자체는 유지합니다. [notices.css:241](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/notices.css:241), [tweets.css:249](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:249), [timetable.css:42](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:42)

4. **하단 플레이어·표 버튼의 외형 높이만 32px로.** 멤버 아이콘과 시각적 무게가 가까워집니다. 이미 44px 터치 범위가 있으므로, 폭과 하단 띠 높이까지 키울 이유는 적습니다. [player.css:59](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/player.css:59), [layout.css:275](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:275)

5. **폰 멤버 헤더의 YouTube·X를 32px 사각 영역으로 정리.** 아이콘을 크게 만드는 것보다 주변 여백을 확보하는 효과가 큽니다. 두 버튼 간격은 4px로 줄여 헤더가 과도하게 길어지지 않게 합니다. [tweets.css:28](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:28)

6. **펼치기 버튼을 폰 44px·PC 40px로 명확히 구분.** 폰은 누르는 행동에 여유를 주고, PC의 긴 가로 막대는 조금 가볍게 만듭니다. 삼각형과 문구 사이 간격도 현재 12→8px로 줄이는 편을 권합니다. [timetable.css:438](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:438)

7. **배너 선택 탭을 56px 기준의 일정한 두 줄로.** 상태 줄과 제목 줄의 높이를 명시하고 패딩을 8px로 정리합니다. 배너 본문보다 적은 변경으로 상단 선택부의 완성도를 올릴 수 있습니다. [banners.css:155](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:155), [banners.css:166](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:166)

8. **폰 곡 목록의 두 줄을 최소 56px 안에 배치.** 현재 48px에서 제목·독음·분류가 밀집해 있습니다. 좌우 8px·상하 8px로 정리하면 읽기 편해집니다. 다만 한 화면의 곡 수가 줄어드는 교환이 있어 마지막 순위입니다. [playerpop.css:609](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:609)

**3. 디자인 자체를 바꾸는 별도 제안 — 최대 3개**

아래는 필수 수정이 아니라 **선택 가능한 디자인 방향**입니다.

| 제안 | 필요한 이유·변경 방향 | 바꾸지 않을 때 남는 인상 | 근거 |
|---|---|---|---|
| **어두운 패널에 아주 약한 청보라 기운** | 기본 패널 `#1a1a1a`를 예컨대 `#1b1b22` 부근으로 검토. 분홍→파랑 배경과 패널의 색 연결을 조금 강화합니다. 밝은 테마의 흰 패널은 유지 | 배경은 개성 있고 내부 판은 중성 검정인 현재의 분리가 남음. 대비가 분명하다는 장점도 있음 | [layout.css:3](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:3), [theme.css:12](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/theme.css:12) |
| **배너의 재질 표현을 한 단계 절제** | 원본 이미지는 유지하고, 뒤쪽 흐린 이미지의 불투명도 `0.6→0.25` 정도를 검토. 종료 박스의 배경 흐림도 줄여 분홍·파랑 종류색과 실제 이미지가 중심이 되게 함 | 흐린 이미지·그라데이션·유리 박스·색 테두리가 함께 보이는 현재의 풍부하지만 복잡한 재질감이 남음 | [banners.css:61](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:61), [banners.css:104](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:104), [banners.css:114](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/banners.css:114) |
| **폰 하단 조작부 뒤에서만 도형을 약하게** | 떠다니는 로고 도형과 움직임은 유지하면서 하단 44px 띠 뒤의 도형만 추가로 감쇠. 멤버 얼굴과 버튼 윤곽을 더 선명하게 만듦 | 하단에서도 도형의 존재감이 강한 현재의 활기찬 구성이 남음 | [bgdeco.css:5](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/bgdeco.css:5), [bgdeco.css:29](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/bgdeco.css:29), [layout.css:469](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:469) |

**4. 건드리면 위험하거나 현재가 더 나은 것**

- **폰 보드의 큰 빈 공간을 ‘과한 패딩’으로 판단하지 않는 것이 좋습니다.** 레인은 화면 높이에서 상단·하단 영역을 뺀 높이로 고정됩니다. 이를 내용 높이로 줄이면 하단 멤버 전환부와 레인의 관계까지 달라집니다. 빈 상태 패딩만 줄여도 큰 빈 공간은 해결되지 않습니다. [layout.css:457](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:457), [timetable.css:655](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:655)

- **PC 타임테이블의 행·블록 크기는 유지하십시오.** 멤버 행과 시간 트랙이 각각 78px, 블록은 위 여백 7px·높이 64px로 맞물립니다. 블록 폭은 시간 정보이므로 일반 버튼의 최소 폭을 적용하면 의미가 변합니다. [timetable.css:189](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:189), [timetable.css:212](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:212), [timetable.css:294](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:294)

- **하단 멤버 얼굴을 전부 40~44px로 키우는 것은 피하십시오.** 현재 기본 26px·선택 시 1.2배이고, 애니메이션까지 44px 띠 안에 들어가도록 조정돼 있습니다. 지금 크기는 양끝 버튼과 5명을 함께 담는 데 유리합니다. [timetable.css:803](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:803)

- **트윗 본문의 패딩과 큰 여백은 단독 축소하지 마십시오.** 번역 면은 X 원문과 사진·시각 위치를 맞추는 구조입니다. CSS뿐 아니라 JS의 치수 상수와 높이 계산에도 연결됩니다. 제안 범위는 헤더의 전환 버튼까지가 적절합니다. [tweets.css:353](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:353), [tweets.css:366](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/tweets.css:366), [tweetlogic.js:175](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/js/tweetlogic.js:175)

- **남은 시간 링 46·54px는 유지하십시오.** 카드 본문과 짝을 이루며, 좁은 PC 카드에서는 이미 40·44px로 줄이는 별도 규칙이 있습니다. 일반 버튼 체계에 편입할 대상이 아닙니다. [timetable.css:640](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:640), [timetable.css:732](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:732), [timetable.css:777](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:777)

- **모든 카드를 같은 패딩으로 통일하지 마십시오.** PC 카드 보기의 본문은 78px, 좁은 구간은 72px 높이를 전제로 합니다. 이후 예고의 `.card`도 별도 구조입니다. 일괄 패딩 확대는 제목·메타 잘림 위험이 있습니다. [timetable.css:621](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/timetable.css:621), [card.css:101](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/card.css:101)

- **푸터와 버전 버튼은 이번 우선순위에서 유지하십시오.** 버전 버튼은 28px이지만 음수 여백으로 푸터 높이 증가를 막고 있습니다. 푸터의 45px 전제는 폰 보드와 플로팅 플레이어 위치에도 사용됩니다. [layout.css:287](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:287), [layout.css:430](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/layout.css:430), [playerpop.css:625](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/patch-ui-ux-improvision/src/frontend/css/playerpop.css:625)