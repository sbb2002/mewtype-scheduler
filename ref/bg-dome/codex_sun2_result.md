`bgdomegl.js`만 수정했습니다. `bggyro.js`·`bgview.js`는 건드리지 않았고 commit도 하지 않았습니다.

- 흰금색 핵·노란 테와 약 20°까지 퍼지는 금빛 광륜을 적용했습니다.
- 해 쪽 하늘과 구름을 호박빛으로 연결하고, 지평선의 광륜 경계를 없앴습니다. 여명은 더 옅은 복숭아·연금빛입니다.
- 지정한 다섯 시각을 **390×760, 요청한 센서·카메라 조건**으로 확인했습니다.
- 실내 픽셀 차이 **0**, 반복·텍스처 추가 없음, PC GPU 비용 **+0.89~2.75%**입니다.

캡처는 `_local/sun-review2/`에 저장했습니다. [17:10 비교](_local/sun-review2/sun-1710-comparison.png) · [17:20 비교](_local/sun-review2/sun-1720-comparison.png) · [전체 검증 보고서](_local/sun-review2/REPORT.md)

못 한 것: 실제 폰에서 외관·발열·GPU 비용은 확인하지 못했습니다.