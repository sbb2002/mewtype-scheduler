// 수동 선곡·탐색을 제한하지 않고 곡 시각으로 현재 문구를 고른다.
export const STORY_CUES=[
 {id:'invitation',track:0,start:30,end:39,text:'오늘 밤의 마지막 선물까지,\n함께 있어 줘.'},
 {id:'one',track:0,start:134,end:142,text:'별빛 하나,\n마음을 담아서.',stars:1},
 {id:'next',track:0,start:203.8,end:212.8,text:'아직 전하지 못한 선물이 있어.'},
 {id:'two',track:1,start:26,end:34,text:'별빛 둘,\n조금 더 가까이.',stars:2},
 {id:'three',track:1,start:175,end:184,text:'별빛 셋,\n이제 마음을 전할 시간이야.',stars:3}
];
export function birthdayStoryCue(track,time){return STORY_CUES.find(c=>c.track===track&&time>=c.start&&time<c.end)||null}
