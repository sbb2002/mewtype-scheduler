`bgdomegl.js`만 수정했고, 커밋하지 않았습니다.

흰금색 중심·따뜻한 가장자리·넓은 금빛 글로우를 추가했습니다. 빛을 사진에 가산한 뒤 톤 매핑해 하늘·구름 결과 섞고, 구름 알파로 원반을 흐리게 했습니다. 여명/노을 차이와 지평선 눌림·가림은 유지했습니다.

| 확인 시각 | 고도 | 해 표현 |
|---|---:|---|
| 17:00 / 17:15 | 5.07° / 2.32° | 밝은 흰금색 핵, 넓은 금빛 산란 |
| 17:25 | 0.46° | 눌린 원반 아래쪽 가림 |
| 17:30 | -0.47° | 원반 일부와 잔광 |
| 12:20 | 37.21° | 흰빛 해와 은은한 광륜 |
| 다음 날 06:55 | -1.89° | 원반 없이 여명광 |
| 다음 날 07:10 | 0.91° | 연한 금빛과 밝은 중심 |
| 13:30, 구름 방향 | 34.41° | 원반 대비 감소, 부드러운 번짐 |

실내는 폰·데스크톱 크기와 두 테마 모두 **픽셀 차이 0**입니다. PC GPU 비용은 **+2.3~6.3%**, 반복문·텍스처 조회 추가는 없습니다. WebGL 오류와 실행 예외도 없었습니다. **삼성 인터넷·안드로이드 10 실기기 외관과 성능은 미확인**입니다.

비교 이미지: [지정 시각](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/sun-review/comparison.png) · [구름 방향](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/sun-review/clouds-comparison.png)  
상세 결과·재현 자료: [_local/sun-review/REPORT.md](C:/Users/user/Documents/myprojects/mewtype-scheduler-worktrees/v4/feat-bg-dome/_local/sun-review/REPORT.md)