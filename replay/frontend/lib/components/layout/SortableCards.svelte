<script lang="ts">
 import {onMount, type Snippet} from 'svelte';
 type Card = {id: string; title: string; content: Snippet};
 let {cards}: {cards: Card[]} = $props();
 const storageKey = 'purple-replay.sidebar-order.v1';
 let order = $state<string[]>([]);
 const sorted = $derived([...cards].sort((a,b) => order.indexOf(a.id) - order.indexOf(b.id)));
 let host: HTMLElement;
 let dragged = $state<string | null>(null);
 let target = $state<string | null>(null);
 let after = $state(false);
 let announcement = $state('');
 let startY = 0, pointerY = 0, pointerX = 0, moved = false, frame = 0;
 onMount(() => {
  try {
   const saved: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]');
   if (Array.isArray(saved)) order = [...new Set(saved.filter((id): id is string => typeof id === 'string' && cards.some(c => c.id === id)))];
  } catch { /* Storage may be unavailable. Ordering still works for this visit. */ }
  order = [...order, ...cards.map(c => c.id).filter(id => !order.includes(id))];
  return () => cancelAnimationFrame(frame);
 });
 function save(next: string[], id: string) {
  order = next;
  try { localStorage.setItem(storageKey, JSON.stringify(order)); } catch { /* Keep the in-memory order. */ }
  announcement = `${cards.find(c => c.id === id)?.title}, position ${order.indexOf(id) + 1} sur ${cards.length}`;
 }
 function keyboard(event: KeyboardEvent, id: string) {
  if (event.key === 'Escape') { cancel(); return; }
  if (!['ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const next = sorted.map(c => c.id), index = next.indexOf(id);
  const destination = event.key === 'Home' ? 0 : event.key === 'End' ? next.length - 1 : Math.max(0, Math.min(next.length - 1, index + (event.key === 'ArrowUp' ? -1 : 1)));
  next.splice(index, 1); next.splice(destination, 0, id); save(next, id);
 }
 function locate() {
  const bounds = host.getBoundingClientRect();
  if (pointerX < bounds.left - 30 || pointerX > bounds.right + 30) { target = null; return; }
  const elements = Array.from(host.querySelectorAll<HTMLElement>('[data-card-id]')).filter(el => el.dataset.cardId !== dragged);
  const candidate = elements.find(el => pointerY < el.getBoundingClientRect().bottom) ?? elements.at(-1);
  if (candidate) {
   const rect = candidate.getBoundingClientRect();
   target = candidate.dataset.cardId!;
   after = pointerY > rect.top + rect.height / 2;
  }
 }
 function scroll() {
  if (!dragged) return;
  if (moved) {
   const rect = host.getBoundingClientRect();
   const top = Math.max(0, rect.top), bottom = Math.min(window.innerHeight, rect.bottom);
   const delta = pointerY < top + 55 ? -12 : pointerY > bottom - 55 ? 12 : 0;
   if (delta) {
    if (host.scrollHeight > host.clientHeight) host.scrollTop += delta;
    else window.scrollBy(0, delta);
   }
   locate();
  }
  frame = requestAnimationFrame(scroll);
 }
 function start(event: PointerEvent, id: string) {
  if (event.button !== 0 || dragged) return;
  const handle = event.currentTarget as HTMLElement;
  handle.setPointerCapture(event.pointerId);
  dragged = id; target = null; moved = false; startY = pointerY = event.clientY; pointerX = event.clientX;
  frame = requestAnimationFrame(scroll);
 }
 function move(event: PointerEvent) {
  if (!dragged) return;
  pointerY = event.clientY; pointerX = event.clientX;
  moved ||= Math.abs(pointerY - startY) > 5;
  if (moved) locate();
 }
 function finish() {
  if (dragged && target && moved) {
   const next = sorted.map(c => c.id).filter(id => id !== dragged);
   next.splice(next.indexOf(target) + (after ? 1 : 0), 0, dragged);
   save(next, dragged);
  }
  cancel();
 }
 function cancel() { cancelAnimationFrame(frame); dragged = null; target = null; moved = false; }
</script>
<aside class="side" bind:this={host} aria-label="Cartes personnalisables">
 <p class="hint">Déplace les cartes avec la poignée ⠿</p>
 {#each sorted as card (card.id)}
  <section class="card sortable" data-card-id={card.id} class:dragging={dragged === card.id} class:before={target === card.id && !after} class:after={target === card.id && after}>
   <div class="card-head">
    <h3>{card.title}</h3>
    <button class="handle" aria-label={`Déplacer ${card.title}`} title="Glisser pour déplacer · au clavier : flèches haut/bas" onpointerdown={e => start(e, card.id)} onpointermove={move} onpointerup={finish} onpointercancel={cancel} onlostpointercapture={cancel} onkeydown={e => keyboard(e, card.id)}>⠿</button>
   </div>
   {@render card.content()}
  </section>
 {/each}
 <span class="sr-only" aria-live="polite">{announcement}</span>
</aside>
<style>
 .side{display:flex;flex-direction:column;gap:12px;overflow-y:auto;min-height:0;scrollbar-width:thin;padding:3px 3px 3px 1px;}
 .hint{font-size:10px;color:var(--text-2);margin:0;flex-shrink:0;}
 .sortable{flex-shrink:0;padding:14px;position:relative;min-width:0;}
 .card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;}
 h3{font-size:10px;letter-spacing:.09em;font-weight:600;color:var(--text-2);}
 .handle{touch-action:none;user-select:none;cursor:grab;background:transparent;border:1px solid transparent;border-radius:5px;color:var(--text-2);font-size:22px;line-height:1;width:32px;height:32px;flex-shrink:0;}
 .handle:hover,.handle:focus-visible{color:var(--text-0);border-color:var(--accent);background:var(--bg-3);}
 .dragging{opacity:.55;outline:1px dashed var(--accent);}.dragging .handle{cursor:grabbing;}
 .before::before,.after::after{content:'';position:absolute;left:0;right:0;height:3px;background:var(--accent);border-radius:3px;pointer-events:none;}
 .before::before{top:-8px;}.after::after{bottom:-8px;}
 .sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);}
 @media(max-width:1400px){.sortable{padding:12px;}}
 @media(max-width:850px){.side{overflow:visible;}.handle{width:40px;height:40px;}}
</style>
