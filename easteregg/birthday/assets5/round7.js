// Focusable SVG hit area follows the actual puppet at every viewport size.
const originalFox7=fox;
fox=function(){return '<g class="arale-interactive">'+originalFox7()+'<rect class="arale-trigger" role="button" tabindex="0" aria-label="아라레와 폭죽 놀이" x="-117" y="-225" width="234" height="235" rx="32"/></g>'};
function aralePlay7(target){
 if(stopped())return;
 const puppet=target.parentElement.querySelector('.raster-character');
 puppet.classList.remove('arale-jump');void puppet.getBoundingClientRect();puppet.classList.add('arale-jump');
 const a=target.getBoundingClientRect(),s=stage.getBoundingClientRect();burst(a.left+a.width/2-s.left,a.top+a.height*.55-s.top);
}
stage.addEventListener('click',e=>{if(e.target.matches('.arale-trigger')){e.stopImmediatePropagation();aralePlay7(e.target)}},true);
stage.addEventListener('keydown',e=>{if(e.target.matches('.arale-trigger')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();aralePlay7(e.target)}});
