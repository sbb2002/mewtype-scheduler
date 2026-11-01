// 수동 선곡·탐색을 제한하지 않고 곡 시각으로 현재 문구를 고른다.
// 문구는 게임 스토리 번역에서 확인한 유노의 말투(반말·단문·말줄임표·감정 받아넘기기)에 맞춘 창작이며 실제 대사가 아니다.
// 문구 사이 공백은 곡마다 STORY_MAX_GAP 초 이하로 유지한다 — 정지 화면에 이탈이 시작된다는 업계 경험치(12~15초)를 따른 값이며 연구로 확정된 수치는 아니다.
export const STORY_MAX_GAP=15;
export const STORY_CUES=[
 // intro = 첫 인트로에서만. 곡이 돌아와도 다시 나오지 않는다. 17.14초 드럼 직전에 끝난다.
 {id:'welcome',track:0,start:.8,end:7.2,intro:true,text:'......왔네.\nYUNO\'s party Lv. 3, 와 줘서 고마워.'},
 {id:'listen',track:0,start:7.4,end:12,intro:true,text:'그럼 내 노래도 들어줘.'},
 {id:'prepared',track:0,start:12.2,end:16.9,intro:true,text:'2곡을 준비했어.'},
 {id:'invitation',track:0,start:30,end:38,text:'가지 말라는 건 아니고......\n끝까지 들어 보라는 거야.',stars:0},
 {id:'floor',track:0,start:52,end:59,text:'손님이 몇 명이든 상관없어.\n판은 끝까지 돌릴 거니까.'},
 {id:'night',track:0,start:74,end:81,text:'이 곡, 밤에 듣기 좋잖아.\n......그냥 그렇다고.'},
 {id:'volume',track:0,start:96,end:103,text:'아, 볼륨은 네 마음대로 해.\n......너무 줄이지만 마.'},
 {id:'early',track:0,start:114,end:121,text:'벌써 가려는 건 아니지?\n아직 초반이거든.'},
 {id:'one',track:0,start:134,end:142,text:'별빛 하나.\n아직 듣고 있었어? ......그래그래.',stars:1},
 {id:'count',track:0,start:156,end:163,text:'왜 별을 세냐고?\n......끝까지 들으면 알아.'},
 {id:'talk',track:0,start:174,end:181,text:'파티라더니 말이 많아졌네.\n......신경 쓰지 마.'},
 {id:'ending',track:0,start:192,end:199,text:'이제 곧 이 곡 끝나.\n그렇다고 나가면 안 돼.'},
 {id:'next',track:0,start:203.8,end:212.8,text:'아직 끝 아니야.\n한 곡 더 남았잖아.'},
 {id:'second',track:1,start:8,end:15,text:'두 번째 곡.\n......이것도 끝까지 듣고 가.'},
 {id:'two',track:1,start:26,end:34,text:'별빛 둘.\n여기까지 왔으면, 나도 좀 기대할게.',stars:2},
 {id:'birthday',track:1,start:48,end:55,text:'생일이라고 특별한 건 없어.\n......그런 줄 알았는데.'},
 {id:'late',track:1,start:70,end:77,text:'이 시간까지 있는 사람이\n있을 줄은 몰랐어.'},
 {id:'mood',track:1,start:92,end:99,text:'그래그래, 알았어.\n기분 좋은 건 티 안 낼게.'},
 {id:'level',track:1,start:114,end:121,text:'Lv. 3까지 왔네.\n의외로 오래 가잖아, 이 파티.'},
 {id:'focus',track:1,start:136,end:143,text:'딴짓 안 하고 듣고 있는 거지?\n......보이는 건 아니지만.'},
 {id:'last',track:1,start:156,end:163,text:'슬슬 마지막이 보이네.\n아쉬운 건...... 너만은 아니야.'},
 {id:'three',track:1,start:175,end:184,text:'별빛 셋.\n......다음 말, 두 번은 안 해.',stars:3},
 {id:'stay',track:1,start:198,end:205,text:'곧 끝나.\n......끝까지 있어.'}
];
export function birthdayStoryCue(track,time,intro=false){return STORY_CUES.find(c=>c.track===track&&time>=c.start&&time<c.end&&(!c.intro||intro))||null}
