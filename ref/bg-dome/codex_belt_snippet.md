# 좌석벨트 표시등 삽입 조각

기존 `.belt` 마크업과 관련 CSS를 전부 교체합니다. 부모 속도계의 `position:relative`를 유지합니다. 크기 64 × 40px, 위치 left:0 / top:2px입니다.

```html
<div class="belt" role="status" aria-label="좌석벨트 표시등 꺼짐"><span class="belt-lens"><svg class="belt-symbol" width="54" height="28" viewBox="0 0 54 28" aria-hidden="true" focusable="false"><g fill="currentColor">
<path d="M1 5 13 9 11 15 0 12zM53 5 41 9 43 15 54 12z"/>
<path fill-rule="evenodd" d="M13 8h13v13H13z M16 11v7h7v-7z"/>
<path d="M31 12h10v6H31v-2h-3v-2h3z"/>
<path d="M3 16 8 14 12 16 14 21 20 23 19 26 11 24 7 20 3 20zM51 16 46 14 42 16 40 21 34 23 35 26 43 24 47 20 51 20z"/>
<path d="M22 3h9V1l5 4-5 4V7h-9z"/>
</g></svg><span class="belt-lit"><svg class="belt-symbol" width="54" height="28" viewBox="0 0 54 28" aria-hidden="true" focusable="false"><g fill="currentColor">
<path d="M1 5 13 9 11 15 0 12zM53 5 41 9 43 15 54 12z"/>
<path fill-rule="evenodd" d="M13 8h13v13H13z M16 11v7h7v-7z"/>
<path d="M31 12h10v6H31v-2h-3v-2h3z"/>
<path d="M3 16 8 14 12 16 14 21 20 23 19 26 11 24 7 20 3 20zM51 16 46 14 42 16 40 21 34 23 35 26 43 24 47 20 51 20z"/>
<path d="M22 3h9V1l5 4-5 4V7h-9z"/>
</g></svg></span></span></div>
```

```css

.belt{position:absolute;left:0;top:2px;width:64px;height:40px;box-sizing:border-box;padding:3px;isolation:isolate;background:linear-gradient(150deg,#516070,#263044 48%,#141526);clip-path:polygon(0 0,calc(100% - 6px) 0,100% 6px,100% 100%,6px 100%,0 calc(100% - 6px));box-shadow:inset 0 1px 0 #7692a1,inset 0 -1px 0 #4fe3ff40}
.belt::before{content:"";position:absolute;inset:1px;background:#111023;z-index:-1;clip-path:polygon(0 0,calc(100% - 5px) 0,100% 5px,100% 100%,5px 100%,0 calc(100% - 5px))}
.belt .belt-lens{position:relative;display:grid;place-items:center;width:100%;height:100%;overflow:hidden;background:#0b0c14;border:1px solid #4fe3ff30;box-sizing:border-box;box-shadow:inset 0 2px 4px #000a;clip-path:polygon(0 0,calc(100% - 3px) 0,100% 3px,100% 100%,3px 100%,0 calc(100% - 3px))}
.belt .belt-lens::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(170deg,#eef6ff09,transparent 48%),repeating-linear-gradient(0deg,#eef6ff03 0 1px,transparent 1px 3px)}
.belt .belt-symbol{position:absolute;width:54px;height:28px;color:#677078}
.belt .belt-lit{position:absolute;inset:0;display:grid;place-items:center;opacity:0;background:radial-gradient(ellipse,#ffd27a20,transparent 80%)}
.belt .belt-lit .belt-symbol{color:#ffe4a3;filter:drop-shadow(0 0 1px #ffd27a) drop-shadow(0 0 3px #ffb84d70)}
.belt.on .belt-lit{opacity:1}

.belt.blink .belt-lit{animation:belt-sign-pulse 1s steps(1,end) infinite}
@keyframes belt-sign-pulse{0%,100%{opacity:1}50%{opacity:0}}
@media(prefers-reduced-motion:reduce){.belt.blink .belt-lit{animation:none;opacity:1}}

```

| 상태 | 바깥 class | aria-label |
|---|---|---|
| 꺼짐 | belt | 좌석벨트 표시등 꺼짐 |
| 켜짐 | belt on | 좌석벨트를 매 주세요 |
| 깜빡임 | belt blink | 좌석벨트를 매 주세요 |

원본의 `{{beltCls}}`, `{{beltAria}}`를 마크업의 class/aria-label에 연결하세요. blink가 on보다 우선합니다. 프레임마다 접근성 문구를 바꾸지 않습니다.

흔들림 중 on → 종료 시 blink → 1600ms 뒤 상태 클래스 제거와 꺼짐 aria-label 설정. 재가속 시 타이머를 취소하고 on으로 복귀합니다. 기존 Gear.dc.html 상태 제어기가 이 순서를 수행하므로 타이머나 차임을 추가하지 않습니다.

CSS의 한 주기는 1초이며 0.5초마다 켜짐/꺼짐을 전환합니다. CSS 자체는 1.6초 타이머를 대체하지 않습니다. reduced-motion에서는 blink 동안 계속 켜지고 기존 상태 제어기가 1.6초 뒤 끕니다. 확인 페이지의 상단 비교 표본만 계속 반복하며 하단 버튼에서 유한 시퀀스를 확인합니다.
