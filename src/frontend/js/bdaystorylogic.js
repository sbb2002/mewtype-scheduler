// 수동 선곡·탐색을 제한하지 않고 곡 시각으로 현재 문구를 고른다.
// 문구는 게임 스토리 번역에서 확인한 유노의 말투(반말·단문·말줄임표·감정 받아넘기기)에 맞춘 창작이며 실제 대사가 아니다.
// v4.11.8 에서 1곡 0:30 ~ 2곡 3:25 문구를 서사(축하 → 별 세기 → 아껴 둔 곡 → 별 셋 → 「이 순간」 → 감사 카드)에 맞춰 다시 짰다. 16~18 · 22~23 번(birthday · late · mood · three · stay)은 운영자 지정 문구.
// 문구 사이 공백은 곡마다 STORY_MAX_GAP 초 이하로 유지한다 — 정지 화면에 이탈이 시작된다는 업계 경험치(12~15초)를 따른 값이며 연구로 확정된 수치는 아니다.
export const STORY_MAX_GAP=15;
export const STORY_CUES=[
 // intro = 첫 인트로에서만. 곡이 돌아와도 다시 나오지 않는다. 17.14초 드럼 직전에 끝난다.
 {id:'welcome',track:0,start:.8,end:7.2,intro:true,text:'......왔네.\n내 생일 파티, 와 줘서 고마워.'},
 {id:'listen',track:0,start:7.4,end:12,intro:true,text:'그럼 내 노래도 들어줘.'},
 {id:'prepared',track:0,start:12.2,end:16.9,intro:true,text:'2곡을 준비했어.'},
 {id:'invitation',track:0,start:30,end:38,text:'축하는...... 일단 받아 둘게.\n대답은 노래로 할 거니까.',stars:0},
 {id:'floor',track:0,start:52,end:59,text:'손님이 몇 명이든 상관없어.\n오늘 판은 내가 돌리니까.'},
 {id:'night',track:0,start:74,end:81,text:'이 곡, 밤에 달리는 느낌이지?\n......그냥 그렇다고.'},
 {id:'volume',track:0,start:96,end:103,text:'아, 볼륨은 네 마음대로 해.\n......너무 줄이지만 마.'},
 {id:'early',track:0,start:114,end:121,text:'벌써 가려는 건 아니지?\n아직 초반이거든.'},
 {id:'one',track:0,start:134,end:142,text:'별빛 하나.\n아직 듣고 있었어? ......그래그래.',stars:1},
 {id:'count',track:0,start:144,end:151,text:'왜 별을 세냐고?\n......다 모이면 알려 줄게.'},
 {id:'talk',track:0,start:174,end:181,text:'파티라더니 말이 많아졌네.\n......신경 쓰지 마.'},
 {id:'ending',track:0,start:192,end:199,text:'이제 곧 이 곡 끝나.\n그렇다고 나가면 안 돼.'},
 {id:'next',track:0,start:203.8,end:212.8,text:'아직 끝 아니야.\n한 곡 더 남았잖아.'},
 {id:'second',track:1,start:8,end:15,text:'두 번째 곡.\n......이건 아껴 둔 거야.'},
 {id:'two',track:1,start:26,end:34,text:'별빛 둘.\n하나 남았어. ......나도 좀 기대할게.',stars:2},
 {id:'birthday',track:1,start:48,end:55,text:'이 곡, 네가 좋아할까 꽤 고민했어.\n......못 들은 걸로 해.'},
 {id:'late',track:1,start:70,end:77,text:'아직 안 갔구나.\n이 시간까지 내 노래를\n들어 줄 줄 몰랐어......'},
 {id:'mood',track:1,start:92,end:99,text:'기분이 좋아 보인다고......?\n......뭐, 나도 싫진 않아.'},
 {id:'level',track:1,start:114,end:121,text:'생각보다 잘 따라오는걸.\n그루브가 살아있잖아.'},
 {id:'focus',track:1,start:136,end:143,text:'딴짓 안 하고 듣고 있는 거지?\n......보이는 건 아니지만.'},
 {id:'last',track:1,start:156,end:163,text:'슬슬 마지막이 보이네.\n아쉬운 건...... 너만은 아니야.'},
 {id:'three',track:1,start:175,end:184,text:'별빛 셋.\n네가 있어 준 덕분에 다 모을 수 있었어.',stars:3},
 {id:'stay',track:1,start:198,end:205,text:'지금 이 순간은\n두 번 다시 안 오지만......\n부디 간직해 줘.'}
];
// 문구가 쉬는 하늘 장면 중 곡마다 시각이 고정된 것 — YMMT 별자리 9초(bdayscene-yuno.js skyPlan 의 plan.constellation).
// 이 구간에는 문구를 두지 않고(두면 skyBusy 에 가려 나오지 않는다), 공백 계산에서는 화면이 비지 않은 시간으로 친다.
// 별자리 시각은 박 지도와 고정 해시로 정해진다 — 박 지도 · 장면 예약 규칙을 바꾸면 다시 재서 이 값을 고칠 것.
export const STORY_SKY_SHOWS=[{id:'constellation',track:0,start:156,end:165},{id:'constellation',track:1,start:37,end:46}];
// 곡 시각과 상관없이 한 번씩 나오는 대사. 해금 뒤 마지막 말 · 무음이 1분 이어질 때.
export const STORY_TURN='자, 이제 너의 음악을 들려줘.\n너의 턴이야.',STORY_NUDGE='......안 듣고 있는 거.\n알고 있거든?',SILENT_NUDGE_MS=60000;
export function birthdayStoryCue(track,time,intro=false){return STORY_CUES.find(c=>c.track===track&&time>=c.start&&time<c.end&&(!c.intro||intro))||null}
