// [Sol] Entirely synthetic data; no network calls, persistence, broker or private logic.
'use strict';
const $ = id => document.getElementById(id);
const state = { symbol:'NQ', cursor:120, running:!matchMedia('(prefers-reduced-motion: reduce)').matches, average:true, speed:1, replay:false };
const fmt = n => n.toLocaleString('fr-FR', {minimumFractionDigits:2,maximumFractionDigits:2});
function series(symbol) {
  let seed = symbol==='NQ'?42:93;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  let price=symbol==='NQ'?20400:5600;
  const scale=symbol==='NQ'?5:1.2;
  return Array.from({length:240},(_,i)=>{const open=price;price+=(random()-.46)*scale*6+Math.sin(i/11)*scale*.8;return {open,close:price,high:Math.max(open,price)+random()*scale*3,low:Math.min(open,price)-random()*scale*3,volume:Math.round(70+random()*800),time:`${String(9+Math.floor(i/60)).padStart(2,'0')}:${String(i%60).padStart(2,'0')}`};});
}
let data=series(state.symbol);
function view(name) {
 document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==name);
 document.querySelectorAll('.nav').forEach(el=>{el.classList.toggle('active',el.dataset.view===name);if(el.dataset.view===name)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 $('page-name').textContent={market:'Exploration du marché',journal:'Journal de démonstration',about:'À propos du projet'}[name];
 if(name==='market')requestAnimationFrame(render);
}
document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>view(el.dataset.view));
$('journal-link').onclick=()=>view('journal');
$('symbol').onchange=e=>{state.symbol=e.target.value;data=series(state.symbol);render();};
$('average').onclick=()=>{state.average=!state.average;$('average').classList.toggle('selected',state.average);$('average').setAttribute('aria-pressed',String(state.average));render();};
$('pause').onclick=()=>{state.running=!state.running;render();};
$('timeline').oninput=e=>{state.cursor=Number(e.target.value);state.running=false;state.replay=true;render();};
function reset(){state.cursor=25;state.replay=true;state.running=false;render();}
$('reset').onclick=reset;
$('replay-start').onclick=()=>{reset();$('timeline').focus();};
$('speed').onchange=e=>state.speed=Number(e.target.value);
const canvas=$('chart'),ctx=canvas.getContext('2d');
function render(){
 const shown=data.slice(0,state.cursor),last=shown.at(-1),first=data[0];
 $('price').textContent=fmt(last.close);
 const pct=(last.close/first.open-1)*100;
 $('change').textContent=`${pct>=0?'+':''}${fmt(pct)} % depuis l’ouverture fictive`;
 $('change').className=pct>=0?'up':'down';
 $('volume').textContent=shown.reduce((a,b)=>a+b.volume,0).toLocaleString('fr-FR');
 $('range').textContent=fmt(Math.max(...shown.map(c=>c.high))-Math.min(...shown.map(c=>c.low)));
 $('mode').textContent=state.replay?'Replay':'Simulation';
 $('chart-caption').textContent=`Session synthétique · ${last.time}`;
 $('timeline').value=state.cursor;$('position').textContent=`${state.cursor} / 240`;
 $('pause').textContent=state.running?'Ⅱ Pause':'▶ Lecture';
 $('pause').setAttribute('aria-label',state.running?'Mettre l’animation en pause':'Reprendre l’animation');
 $('play-label').textContent=state.running?'Lecture':'Pause';
 $('tape').replaceChildren(...shown.slice(-5).reverse().map(c=>{const row=document.createElement('div');row.className='tape-row '+(c.close>=c.open?'up':'down');for(const text of [c.time,fmt(c.close),String(c.volume)]){const el=document.createElement('span');el.textContent=text;row.append(el);}return row;}));
 const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;
 const w=rect.width,h=rect.height,dpr=devicePixelRatio||1;
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 const visible=shown.slice(-70),left=16,right=w-66,top=23,bottom=h-85;
 const low=Math.min(...visible.map(c=>c.low)),high=Math.max(...visible.map(c=>c.high)),pad=(high-low)*.12;
 const y=p=>bottom-(p-low+pad)/(high-low+pad*2)*(bottom-top);
 ctx.font='9px ui-monospace, monospace';ctx.strokeStyle='#252430';ctx.fillStyle='#767185';ctx.lineWidth=.7;
 for(let i=0;i<5;i++){const yy=top+i*(bottom-top)/4;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.fillText(fmt(high+pad-i*(high-low+2*pad)/4),right+7,yy+3);}
 const step=(right-left)/visible.length;
 visible.forEach((c,i)=>{const x=left+(i+.5)*step,color=c.close>=c.open?'#5bd3b0':'#ed8297';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y(c.high));ctx.lineTo(x,y(c.low));ctx.stroke();ctx.fillRect(x-step*.29,Math.min(y(c.open),y(c.close)),Math.max(1,step*.58),Math.max(1,Math.abs(y(c.open)-y(c.close))));ctx.globalAlpha=.22;ctx.fillRect(x-step*.29,h-30-c.volume/900*40,Math.max(1,step*.58),c.volume/900*40);ctx.globalAlpha=1;if(i%14===0){ctx.fillStyle='#767185';ctx.fillText(c.time,x-12,h-10);}});
 if(state.average){ctx.strokeStyle='#b399ef';ctx.lineWidth=1.6;ctx.beginPath();const offset=shown.length-visible.length;visible.forEach((c,i)=>{const index=offset+i,chunk=data.slice(Math.max(0,index-11),index+1),avg=chunk.reduce((s,b)=>s+b.close,0)/chunk.length,x=left+(i+.5)*step;if(i===0)ctx.moveTo(x,y(avg));else ctx.lineTo(x,y(avg));});ctx.stroke();}
 ctx.setLineDash([3,4]);ctx.strokeStyle='#a58ac766';ctx.beginPath();ctx.moveTo(left,y(last.close));ctx.lineTo(right,y(last.close));ctx.stroke();ctx.setLineDash([]);
}
new ResizeObserver(()=>render()).observe(canvas.parentElement);
setInterval(()=>{if(state.running&&!document.hidden&&!$('market').hidden){state.cursor=Math.min(240,state.cursor+state.speed);if(state.cursor===240)state.running=false;render();}},1000);
const trades=[['Session 04','NQ','Achat','+ 125,00','Attendre la confirmation'],['Session 03','ES','Vente','− 45,00','Revoir le contexte'],['Session 02','NQ','Vente','+ 80,00','Documenter la sortie'],['Session 01','ES','Achat','− 30,00','Respecter le plan']];
function journal(){ $('trades').replaceChildren(...trades.filter(t=>$('filter').value==='all'||t[1]===$('filter').value).map(t=>{const row=document.createElement('tr');t.forEach((value,i)=>{const td=document.createElement('td');td.textContent=value;if(i===3)td.className=value.startsWith('+')?'up':'down';row.append(td);});return row;})); }
$('filter').onchange=journal;
$('note').oninput=()=>{$('note-count').textContent=`${$('note').value.length} / 600 · rien n’est envoyé ni enregistré`;};
journal();render();
