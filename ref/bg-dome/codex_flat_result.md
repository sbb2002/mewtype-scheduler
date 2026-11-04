`bgdomegl.js`만 수정했고, 커밋하지 않았습니다.

- **변경:** 고도 5° 아래에서 서서히 눌려 지평선에서는 세로/가로 비율 약 **0.826**이 됩니다. 아래쪽을 조금 더 압축했고, 달 위상·표면·지구 반사광에도 같은 변형을 적용했습니다. 빛 번짐도 가로로 조금 퍼집니다. 반복문 추가는 없습니다.
- **확인:** localhost:8102, 서울 좌표에서 지정한 해넘이·달뜨기 시각과 지평선 가림을 비교했습니다. 실내 4조합과 높이 뜬 해·달은 이전 코드와 **픽셀 차이 0**입니다. 보름·반달·초승달 위상, JS·WebGL 검사도 통과했습니다.
- **미확인:** 실제 폰의 FPS·발열·소비전력.

비교 이미지 — 왼쪽 이전, 오른쪽 수정 후:

[해넘이](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/refraction-review/sun-comparison.png) · [달뜨기](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/refraction-review/moon-comparison.png) · [높이 뜬 해·달](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/refraction-review/high-comparison.png) · [위상 검사](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/refraction-review/phase-comparison.png)