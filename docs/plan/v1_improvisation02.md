# 보강
docs\plan\v1_improvisation.md와 docs\plan\v1_improvisation_comment.md의 내용을 보완하여 작성.

# 백엔드
- render가 아닌 Google Cloud Scheduler + Github actions 조합을 고려중.

# 관리자 인스턴스
![image](lifespan_overall_clean.png)
위 그림처럼 5명의 live 상태를 관리해야 하므로 백엔드가 필요 시에만 켜서 동작하고 그 외에는 유휴 또는 꺼짐 상태로 들어가기 위함임.

# 의문
- RSS 피드를 수집해서 각 방송인의 상태를 idle -> upcoming으로 업데이트하는데 이 때 GCS의 트리거 타이밍을 변경할 수 있나?
- 아무 문제가 없이 이상적으로 동작한다면 최초 1회에만 수동 디스패칭을 하면 그후 현재 로직에 따라 자동으로 GCS 타이밍을 업데이트하고 GCS가 설정한 타이밍에 따라 백엔드가 적절히 켜지고 꺼져야 함. 이것이 가능한가?