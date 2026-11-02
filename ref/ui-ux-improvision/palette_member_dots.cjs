// 멤버 점 색 시안 계산 — OKLCH 로 종료색을 만들고 구분도를 잰다.
const toLin = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const toSrgb = v => { v = Math.min(1, Math.max(0, v)); return Math.round(255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055)); };
const hex2 = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const rgbHex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
const lin2lab = ([r, g, b]) => { const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b, s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b; const [a, c, d] = [l, m, s].map(Math.cbrt); return [0.2104542553 * a + 0.793617785 * c - 0.0040720468 * d, 1.9779984951 * a - 2.428592205 * c + 0.4505937099 * d, 0.0259040371 * a + 0.7827717662 * c - 0.808675766 * d]; };
const lab2lin = ([L, a, b]) => { const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3; return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]; };
const lch = h => { const [L, a, b] = lin2lab(hex2(h).map(toLin)); return [L, Math.hypot(a, b), Math.atan2(b, a)]; };
const fromLch = ([L, C, H]) => rgbHex(lab2lin([L, C * Math.cos(H), C * Math.sin(H)]).map(toSrgb));
const M = { 정상: null, 녹색약: [[0.498864, 0.674741, -0.173605], [0.205199, 0.754488, 0.040313], [-0.011131, 0.030969, 0.980162]], 적색약: [[0.38545, 0.769005, -0.154455], [0.100526, 0.829802, 0.069673], [-0.007442, -0.02219, 1.029632]] };
const lab = (h, m) => { const x = hex2(h).map(toLin); return lin2lab(m ? m.map(r => Math.max(0, r[0] * x[0] + r[1] * x[1] + r[2] * x[2])) : x); };
const d = (a, b, m) => { const p = lab(a, m), q = lab(b, m); return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };
const contrast = (a, b) => { const Y = h => { const [r, g, b] = hex2(h).map(toLin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }; const [x, y] = [Y(a), Y(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const names=['arale','yuno','nonoka','ritsu','miyako'];
const off={arale:'#FFDD33',yuno:'#FF6688',nonoka:'#FFAACC',ritsu:'#5588DD',miyako:'#9977DD'};
const DB='#0f0f0f',LB='#f5f4fb';
const out={};
const dk={ritsu:0.045,miyako:-0.045},de={ritsu:0.06,miyako:-0.03},lo={ritsu:0.03,miyako:-0.06,yuno:-0.05,nonoka:0.05},le={ritsu:-0.02,miyako:-0.07,yuno:-0.06,nonoka:0.05};
for(const n of names){const [L,C,H]=lch(off[n]);
 const dark=(dk[n]?fromLch([L+dk[n],C,H]):off[n]);
 const darkEnded=fromLch([L*0.66+(de[n]||0),C*0.8,H]);
 const lightL=Math.min(L,0.62);
 const light=fromLch([lightL+(lo[n]||0),C*1.05,H]);
 const lightEnded=fromLch([lightL+(0.86-lightL)*0.5+(le[n]||0),C*0.75,H]);
 out[n]={dark,darkEnded,light,lightEnded};}
console.log(JSON.stringify(out,null,0));
const rep=(k,lbl,bg)=>{for(const [nm,m] of Object.entries(M)){const o=[];for(let i=0;i<5;i++)for(let j=i+1;j<5;j++)o.push([names[i]+'-'+names[j],d(out[names[i]][k],out[names[j]][k],m)]);o.sort((a,b)=>a[1]-b[1]);console.log(lbl,nm,'최소',o[0][0],o[0][1].toFixed(3),o[1][0],o[1][1].toFixed(3));}console.log(lbl,'바탕 대비',names.map(n=>n+' '+contrast(out[n][k],bg).toFixed(1)).join(' '));};
rep('dark','어둡게 예고',DB);rep('darkEnded','어둡게 종료',DB);rep('light','밝게 예고',LB);rep('lightEnded','밝게 종료',LB);
for(const [nm,m] of Object.entries(M))console.log(nm,'같은 멤버 예고↔종료 어둡게',Math.min(...names.map(n=>d(out[n].dark,out[n].darkEnded,m))).toFixed(3),'밝게',Math.min(...names.map(n=>d(out[n].light,out[n].lightEnded,m))).toFixed(3));
