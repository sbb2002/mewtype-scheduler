// 수동 선곡·탐색을 제한하지 않고 곡 시각으로 현재 문구를 고른다.
// 문구는 게임 스토리 번역에서 확인한 유노의 말투(반말·단문·말줄임표·감정 받아넘기기)에 맞춘 창작이며 실제 대사가 아니다.
// v4.11.9 에서 1곡 0:30 ~ 2곡 3:25 를 곡 구조(시작 · 사인 · 가장 센 구간 · 끝)에 맞춰 다시 배치했다. 서사 = 축하는 받아 두고 대답은 노래로 → 곡마다 별 하나 → 곡은 둘인데 별은 셋 → 셋째는 끝까지 있어 준 사람의 몫 → 「이 순간」 → 감사 카드. 대부분 운영자 지정 문구다 — 고칠 때는 운영자에게 먼저 묻는다.
// 사인이 나오는 곡의 1곡 109.9~125.3 · 2곡 134.5~149.9 에는 다른 문구가 쉬고, sign 문구가 있는 early · focus 만 사인을 피해 유노 위(세로) · 왼쪽(가로)에 낮게 뜬다.
// 문구 안의 「 // 」 = 좁은 화면에서만 줄을 나눌 자리(운영자 지정, 3줄까지 허용). 넓으면 한 줄로 이어진다.
// 문구 사이 공백은 곡마다 STORY_MAX_GAP 초 이하로 유지한다 — 정지 화면에 이탈이 시작된다는 업계 경험치(12~15초)를 따른 값이며 연구로 확정된 수치는 아니다.
export const STORY_MAX_GAP=15;
export const STORY_CUES=[
 // intro = 첫 인트로에서만. 곡이 돌아와도 다시 나오지 않는다. 17.14초 드럼 직전에 끝난다.
 {id:'welcome',track:0,start:.8,end:7.2,intro:true,text:'......왔네.\n내 생일 파티, 와 줘서 고마워.'},
 {id:'listen',track:0,start:7.4,end:12,intro:true,text:'그럼 내 노래도 들어줘.'},
 {id:'prepared',track:0,start:12.2,end:16.9,intro:true,text:'2곡을 준비했어.'},
 {id:'invitation',track:0,start:30,end:38,text:'축하는...... 일단 받아 둘게.\n대답은 노래로 할 거니까.',stars:0},
 {id:'floor',track:0,start:52,end:60,text:'그루브에 몸을 맡겨봐.\n오늘 밤, 턴테이블은 내가 돌리니까.'},
 {id:'night',track:0,start:74,end:82,text:'잠깐 쉬었지.\n......곡 얘기야.'},
 // 볼륨 대사 = 음소거 · 볼륨 0 으로 두지 않게 하는 무언의 힌트. 조건을 설명하지 않는다.
 {id:'volume',track:0,start:96,end:104,text:'볼륨은 네 마음대로 해.\n......그렇다고 끄지는 마.'},
 {id:'early',track:0,start:110,end:118,text:'오늘도 요란하네, // 저 UFO......\n난 여기 있을 거지만.',sign:'오늘도 요란하네, // 저 UFO......\n난 여기 있을 거지만.'},
 {id:'still',track:0,start:133,end:141,text:'듣고...... 있는 거지?\n......그래.'},
 {id:'wait',track:0,start:145,end:152,text:'밤하늘을 수놓는 별.\n......좋은 악상이 떠올랐어.'},
 {id:'one',track:0,start:166,end:173,text:'첫 곡의 몫. 별빛 하나.\n......여기 남겨 두자.',stars:1},
 {id:'talk',track:0,start:174,end:181,text:'파티라더니 말이 많아졌네.\n......신경 쓰지 마.'},
 {id:'next',track:0,start:203.8,end:212.8,text:'이번 곡은 여기서 끝.\n그래도 한 곡 더 남아있어.'},
 {id:'second',track:1,start:8,end:15,text:'두 번째 곡.\n......이건 아껴 둔 거야.'},
 {id:'moving',track:1,start:26,end:34,text:'손이 먼저 움직이네.\n플로우를 느껴볼까.'},
 {id:'birthday',track:1,start:48,end:55,text:'이 곡, 네가 좋아할까 꽤 고민했어.\n......못 들은 걸로 해.'},
 {id:'late',track:1,start:70,end:77,text:'아직 안 갔구나.\n이 시간까지 내 노래를 들어 줄 줄 몰랐어......'},
 {id:'mood',track:1,start:92,end:99,text:'기분이 좋아 보인다고......?\n......뭐, 나도 싫진 않아.'},
 {id:'level',track:1,start:114,end:121,text:'생각보다 잘 따라오는걸.\n그루브가 살아있잖아.'},
 {id:'focus',track:1,start:136,end:143,text:'쟤 또 왔네.\n......UFO 말야.',sign:'저 녀석들...... 또 왔네.\n......그래도 싫지는 않아.'},
 {id:'back',track:1,start:153,end:161,text:'잠깐 조용했지.\n......이제 다시 간다.'},
 {id:'two',track:1,start:162,end:169,text:'별빛 둘.\n......곡 몫은 이걸로 끝.',stars:2},
 {id:'count',track:1,start:170,end:177,text:'곡은 둘인데 별은 셋.\n......이상하지?'},
 {id:'last',track:1,start:178,end:185,text:'셋째는 네 몫.\n......기억하려고. 됐어.'},
 {id:'three',track:1,start:186,end:194,text:'별빛 셋.\n네가 있어 준 덕분에 다 모을 수 있었어.',stars:3},
 {id:'stay',track:1,start:198,end:205,text:'지금 이 순간은 두 번 다시 안 오지만......\n부디 간직해 줘.'}
];
// 문구가 쉬는 하늘 장면 중 곡마다 시각이 고정된 것 — YMMT 별자리 9초(bdayscene-yuno.js skyPlan 의 plan.constellation).
// 이 구간에는 문구를 두지 않고(두면 skyBusy 에 가려 나오지 않는다), 공백 계산에서는 화면이 비지 않은 시간으로 친다.
// 별자리 시각은 박 지도와 고정 해시로 정해진다 — 박 지도 · 장면 예약 규칙을 바꾸면 다시 재서 이 값을 고칠 것.
export const STORY_SKY_SHOWS=[{id:'constellation',track:0,start:156,end:165},{id:'constellation',track:1,start:37,end:46}];
// 곡 시각과 상관없이 한 번씩 나오는 대사. 해금 뒤 마지막 말 · 무음이 1분 이어질 때.
export const STORY_TURN='자, 이제 너의 음악을 들려줘.\n너의 턴이야.',STORY_NUDGE='......안 듣고 있는 거.\n알고 있거든?',SILENT_NUDGE_MS=60000;
export function birthdayStoryCue(track,time,intro=false){return STORY_CUES.find(c=>c.track===track&&time>=c.start&&time<c.end&&(!c.intro||intro))||null}
// 사인 중 낮게 띄울 위치(px). 장면은 설계 좌표 x=600 을 화면 가운데에 두고 sceneLayout 의 scale · offsetY 로 그린다.
// 유노 머리 꼭대기(더듬이 포함) ≈ 설계 y 232, 데크 왼쪽 끝 ≈ 설계 x 404 — 1440×900 · 390×844 캡처로 잰 값.
export function lowStoryBox(w,h,L){
 const X=x=>w/2+(x-600)*L.scale,Y=y=>L.offsetY+y*L.scale,head=Y(232);
 if(!L.portrait){const right=X(404)-24;if(right>=220)return {mode:'side',left:20,width:right-20,centerY:Math.max(90,Math.min(h-180,Y(330)))}}
 return {mode:'above',bottom:Math.max(0,h-head+14)};
}
