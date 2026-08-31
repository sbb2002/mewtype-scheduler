1. 대상과 목적
이 앱의 목적은 무한대 뮤타입(유튜브 방송인)의 방송 예고를 한꺼번에 취합하여 예고 정리를 해주는 정적 웹 서빙 사이트를 제작하는 것이야.
모니터링 대상은 다음과 같아.
    - 仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ (https://www.youtube.com/@arale_yumemita)
    - 千石ユノ -Sengoku Yuno- / 夢限大みゅーたいぷ (https://www.youtube.com/@yuno_yumemita)
    - 宮永ののか -Miyanaga Nonoka- / 夢限大みゅーたいぷ (https://www.youtube.com/@nonoka_yumemita)
    - 峰月律-Minetsuki Ritsu- / 夢限大みゅーたいぷ (https://www.youtube.com/@ritsu_yumemita)
    - 藤都子 -Fuji Miyako- / 夢限大みゅーたいぷ (https://www.youtube.com/@miyako_yumemita)
이용 대상자는 이 방송인들의 컨텐츠를 구독 또는 시청하는 사람들이야. 이들은 우리 앱 웹사이트에 방문하여 이 방송인들의 예고 또는 현재 방송중인 라이브를 확인할 수 있고, 언제 방송하는지 알 수 있으며, 현재 방송 중인 주소로 접속할 수 있어.

2. 핵심 기능
- Youtube RSS를 통해 해당 방송인의 방송 예고시각, 썸네일 이미지, 방송 채널명 등 정보 수집 (RSS로 어려울 경우 youtube-api를 활용 예정.)
- 프론트엔드: vercel을 이용한 배포
- 백엔드: render를 이용한 일정 주기마다 예고있는지 수집 후 새로운 예고가 있다면 프론트엔드에 업데이트. python fastapi 이용 예정.

3. 플랫폼 형태
- 웹사이트(pc, 모바일에서 모두 접속할 수 있음. 따라서 bandori-song-sorter처럼 창 크기를 염두해야함.)

4. 일정 데이터의 출처
- 1번에 상술한 방송인들의 주소에서 RSS 피드 또는 youtube-api를 통해 수집