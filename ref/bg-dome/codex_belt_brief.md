# Codex 의뢰 — 실제 항공기 「좌석벨트 착용」 표시등 디자인 (2026-11-06)

## 배경

배경 「UFO 돔」(모바일 웹)의 조작 패널 중 **워프 기어 패널**(성간 이동 속도를 고르는 패널)에 비행기 좌석벨트 표시등을 넣는다.
레드존(광속의 0.9 · 0.99 배)으로 가속하거나 레드존에서 급제동하면 화면이 흔들리는데, 흔들림이 있는 동안 표시등이 켜지고,
흔들림이 끝나면 1.6초 동안 0.5초 간격으로 깜빡이다 꺼진다. 켜질 때 · 꺼질 때 기내 차임 「띵」이 울린다(소리는 이미 만들어 둠 — 이번 의뢰 범위 밖).

운영자 요구(원문): **「실제 항공기 안전벨트 표시등 디자인이면 좋겠어」** — 지금 Claude 가 그린 것은 운영자가 보기에 실제 같지 않다.
그리고 **「현재 우리 패널 디자인에 맞게 해 달라」** — 실제 표시등임을 한눈에 알아보되, 지금 기어 패널(사이버펑크 HUD: 어두운 남보라 반투명 바탕 ·
모서리를 깎은 테두리 · 시안 / 분홍 네온 · Chakra Petch 계열 숫자 · 옅은 주사선)과 한 몸처럼 보여야 한다. 실물 사진을 그대로 붙인 듯 따로 놀면 안 된다.
패널 전체 코드는 이 폴더의 `Gear.dc.html`(시안 원본 — 읽기만, 고치지 말 것). 표시등 외 패널 요소는 바꾸지 않는다.

## 할 일

실제 여객기 객실 천장(승객 머리 위 PSU 패널)의 좌석벨트 표시등처럼 보이는 표시등을 **인라인 SVG + CSS** 로 디자인한다.

1. 먼저 실제 표시등이 어떻게 생겼는지 정리 — 하우징(테두리 재질 · 색 · 모서리), 렌즈(꺼졌을 때 색 · 질감, 켜졌을 때 빛 색 · 번짐),
   그림(벨트 · 버클 픽토그램의 형태, 글자 유무), 흔히 「금연」 표시와 나란히 붙어 있는지 등. 기종 · 시대마다 다르면 대표적인 것 2 ~ 3 가지를 비교하고,
   이 패널(사이버펑크 · 어두운 남보라 바탕)에 어울리는 것을 하나 골라, **패널 디자인 언어(깎은 모서리 · 네온 테두리 · 색 토큰)로 어떻게 옮겼는지** 근거와 함께 적는다. **확실하지 않은 것은 「확인 필요」로 적는다**(추측을 사실처럼 쓰지 말 것).
2. 고른 안으로 세 상태를 만든다: 꺼짐(평소, 그래도 하우징 · 그림이 희미하게 보임) · 켜짐 · 깜빡임(0.5초 간격, 켜짐 ↔ 꺼짐 계단식).
3. 결과물:
   - `belt_sign.html` — 이 폴더에 단독으로 열리는 확인 페이지. 어두운 바탕(`rgba(10,8,26,.82)` 위)에 세 상태를 나란히 + 실제 크기 · 3배 확대 둘 다.
     **기어 패널 머리글 · 속도계 일부를 함께 그려 넣어** 패널 안에 들어갔을 때 어울리는지 볼 수 있게 한다.
   - `belt_sign_snippet.md` — 기어 패널에 그대로 붙일 마크업 · CSS 조각. 클래스 약속: 바깥 요소 `.belt`, 상태 클래스 `.belt.on` · `.belt.blink`(둘 다 없으면 꺼짐).
   - `belt_sign_report.md` — 1번 조사 결과, 고른 안과 이유, 크기 · 색 값, 확인 필요 항목. **한국어**.

## 제약

- 들어갈 자리: 속도계 왼쪽 위 빈칸, **최대 가로 72px · 세로 44px**(지금은 60 × 40). 폰 화면(390px 폭)에서 실제 크기로 알아볼 수 있어야 한다.
- 외부 이미지 · 폰트 · 이모지 금지. 인라인 SVG + CSS 만. 글자를 넣는다면 시스템 글꼴로 충분히 읽히는 크기여야 한다(8px 미만 금지).
- 특정 항공기 제조사의 상표 · 로고는 넣지 않는다(일반적인 픽토그램 표시등).
- 애니메이션은 `opacity` · `filter` · `background` 정도로 가볍게. `@media (prefers-reduced-motion: reduce)` 에서는 깜빡이지 않고 켜진 채로 있다가 꺼진다.
- 접근성: 바깥 요소는 `role="status"` + `aria-label`(켜짐 = 「좌석벨트를 매 주세요」, 꺼짐 = 「좌석벨트 표시등 꺼짐」), SVG 는 `aria-hidden="true"`.
- 이 폴더 밖의 파일은 고치지 않는다.

## 참고 — 지금 들어가 있는 Claude 시안(바꿀 대상)

```css
.belt{position:absolute;left:0;top:2px;width:60px;height:40px;padding:4px;box-sizing:border-box;background:linear-gradient(180deg,#45454c,#26262b);border-radius:7px;box-shadow:inset 0 1px 0 rgba(255,255,255,.16),inset 0 -1px 0 rgba(0,0,0,.4),0 2px 4px rgba(0,0,0,.6)}
.belt .lens{display:grid;place-items:center;width:100%;height:100%;border-radius:4px;background:#121214;color:#34343b;box-shadow:inset 0 1px 4px rgba(0,0,0,.85)}
.belt.on .lens{background:radial-gradient(ellipse at 50% 55%,#3d3626 0%,#1c1a14 75%);color:#fff5da}
.belt.on .lens svg{filter:drop-shadow(0 0 2px rgba(255,240,200,.95)) drop-shadow(0 0 6px rgba(255,214,140,.6))}
```
```html
<div class="belt on" role="status" aria-label="좌석벨트를 매 주세요">
  <span class="lens">
    <svg width="36" height="20" viewBox="0 0 36 20" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M3 5 Q5.5 13.5 12.5 14" stroke-width="3.2"></path>
      <path d="M33 5 Q30.5 13.5 23.5 14" stroke-width="3.2"></path>
      <rect x="12.5" y="9.6" width="11" height="8.4" rx="1.6" stroke-width="1.8"></rect>
      <rect x="15.6" y="12.2" width="4.8" height="3.2" rx=".6" fill="currentColor" stroke="none"></rect>
    </svg>
  </span>
</div>
```

패널 색 참고: 바탕 `rgba(10,8,26,.82)`, 시안 `#4fe3ff`, 분홍 `#ff6fb5`, 레드존 `#ff3d5a`, 본문 `#eef6ff`, 보조 글자 `#a9bad0`.
