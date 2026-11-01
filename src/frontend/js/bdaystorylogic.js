// 수동 선곡·탐색을 제한하지 않고 곡 시각으로 현재 문구를 고른다.
// 문구는 게임 스토리 번역에서 확인한 유노의 말투(반말·단문·말줄임표·감정 받아넘기기)에 맞춘 창작이며 실제 대사가 아니다.
export const STORY_CUES=[
 {id:'invitation',track:0,start:30,end:39,text:'가지 말라는 건 아니고......\n끝까지 들어 보라는 거야.',stars:0},
 {id:'one',track:0,start:134,end:142,text:'별빛 하나.\n아직 듣고 있었어? ......그래그래.',stars:1},
 {id:'next',track:0,start:203.8,end:212.8,text:'아직 끝 아니야.\n한 곡 더 남았잖아.'},
 {id:'two',track:1,start:26,end:34,text:'별빛 둘.\n여기까지 왔으면, 나도 좀 기대할게.',stars:2},
 {id:'three',track:1,start:175,end:184,text:'별빛 셋.\n......다음 말, 두 번은 안 해.',stars:3}
];
export function birthdayStoryCue(track,time){return STORY_CUES.find(c=>c.track===track&&time>=c.start&&time<c.end)||null}
