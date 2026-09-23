<script lang="ts">
	// Ticket paper-trading : sizing par risque $, ACHAT/VENTE (SL auto), FLAT et −LOTS en deux temps, BE, statut.
	// [Sol] Ticket et confirmation dans la colonne latérale ; lignes SL/TP sur le graphique.
	import { onMount } from 'svelte';
	import { desk } from '$replay/application/PaperDesk';
	import { market } from '$replay/application/MarketStore';

	let { symbol }: { symbol: string } = $props();
	let flatArmed = $state(false);
	let partArmed = $state(false);
	let psize = $state(1);
	let flatTimer: ReturnType<typeof setTimeout>, partTimer: ReturnType<typeof setTimeout>;
	const positions = market.positions;
	const money = (v: number) => Math.round(v).toLocaleString('fr-FR') + ' $';
	onMount(() => { void desk.start(symbol); return () => { desk.stop(); clearTimeout(flatTimer); clearTimeout(partTimer); }; });
	function flat() { if (flatArmed) { flatArmed = false; void desk.flatten(); } else { flatArmed = true; flatTimer = setTimeout(() => (flatArmed = false), 4000); } }
	function partial() { if (partArmed) { partArmed = false; void desk.partial(psize); } else { partArmed = true; partTimer = setTimeout(() => (partArmed = false), 4000); } }
	const preview = $derived.by(() => {
		const s = $desk.spec; if (!s) return 'SL auto : —';
		const qty = Math.max(1, Math.floor($desk.qty || 1)), ticks = Math.max(s.min_bracket_ticks || 4, Math.floor($desk.budget / (qty * s.tick_value)));
		return `Clique sur le graphique pour poser ton SL · auto : ${(ticks * s.tick_size).toFixed(2)} pts`;
	});
</script>

<div class="ticket">
	<div class="group">
		<label class="field">Contrats <input type="number" min="1" step="1" value={$desk.qty} oninput={(e) => desk.setQty(Number((e.currentTarget as HTMLInputElement).value))} /></label>
		<label class="field">Risque $ <input type="number" min="1" step="25" value={$desk.budget} oninput={(e) => desk.setBudget(Number((e.currentTarget as HTMLInputElement).value))} /></label>
		<label class="field">R:R <select value={String($desk.rr)} onchange={(e) => desk.setRR(Number((e.currentTarget as HTMLSelectElement).value))}><option value="0">sans TP</option><option value="1">1:1</option><option value="1.5">1:1.5</option><option value="2">1:2</option><option value="3">1:3</option></select></label>
	</div>
	<div class="info">{$desk.setup ? 'Setup en cours — glisse les lignes SL/TP, Échap pour annuler' : preview}</div>
	<div class="group">
		<button class="btn buy" disabled={$desk.busy || !$desk.spec} onclick={() => desk.arm('buy')}>Achat</button>
		<button class="btn sell" disabled={$desk.busy || !$desk.spec} onclick={() => desk.arm('sell')}>Vente</button>
		<button class="btn" class:armed={flatArmed} disabled={$desk.busy} onclick={flat} title="Ferme la position simulée">{flatArmed ? 'Confirmer' : 'Tout fermer'}</button>
	</div>
	<div class="group position-actions">
		<button class="btn" disabled={$desk.busy || !$positions.length} onclick={() => desk.breakeven()} title="Déplace le stop au prix d'entrée">Stop à zéro</button>
		<label class="field">Contrats <input type="number" min="1" step="1" bind:value={psize} /></label>
		<button class="btn" class:armed={partArmed} disabled={$desk.busy || !$positions.length} onclick={partial} title="Ferme N contrats">{partArmed ? `Confirmer −${psize}` : 'Réduire'}</button>
	</div>
	{#if $desk.status}<div class="status" class:status-ok={$desk.statusOk} class:status-err={!$desk.statusOk}>{$desk.status}</div>{/if}
	{#if $desk.setup && $desk.sizing}
		{@const z = $desk.sizing}
		<div class="setup" class:buy={$desk.setup.side === 'buy'} class:sell={$desk.setup.side === 'sell'}>
			<div class="sp-head">{$desk.setup.side === 'buy' ? 'ACHAT' : 'VENTE'} — {symbol}</div>
			<div class="sp-grid">
				<div><small>Contrats</small><b>×{z.qty}{z.capped ? ' (max)' : ''}</b></div>
				<div><small>R:R</small><b>{z.rr == null ? '—' : '1:' + z.rr.toFixed(2)}</b></div>
				<div><small>Perte au SL</small><b class="neg">−{money(z.risk)} ({z.slTicks} ticks)</b></div>
				<div><small>Gain au TP</small><b class="pos">{z.gain == null ? '— (sans TP)' : '+' + money(z.gain)}</b></div>
			</div>
			{#if z.reason}<div class="sp-warn" class:err={!z.valid}>{z.reason}</div>{/if}
			<div class="group">
				<button class="btn" class:buy={$desk.setup.side === 'buy'} class:sell={$desk.setup.side === 'sell'} disabled={!z.valid || $desk.sending} onclick={() => desk.confirm()}>{$desk.sending ? 'ENVOI…' : `CONFIRMER ×${z.qty}`}</button>
				<button class="btn" onclick={() => desk.cancel()}>ANNULER</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.ticket{display:flex;flex-direction:column;gap:9px;}
	.group{display:flex;align-items:flex-end;flex-wrap:wrap;gap:8px;}
	.group .btn{flex:1 1 auto;min-width:0;height:34px;font-weight:600;letter-spacing:0;}
	.position-actions{display:grid;grid-template-columns:minmax(0,1fr) 56px minmax(0,1fr)}
	.group.position-actions .field{width:auto}.position-actions .btn{padding:0 5px;font-size:11px}
	.info{color:var(--text-1);font-size:11px;padding:7px 9px;border-radius:7px;border:1px solid var(--border);background:var(--bg-0);}
	.group .field{flex:1;min-width:0;width:0}.group .field input,.group .field select{width:100%;min-width:0}.status{font-size:11px;}
	.setup{border:1px solid var(--border);border-radius:10px;padding:10px;background:var(--bg-0);}
	.setup.buy .sp-head{color:#7dd3fc;} .setup.sell .sp-head{color:var(--warn);}
	.sp-head{font-weight:800;margin-bottom:8px;}
	.sp-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin-bottom:8px;}
	.sp-grid small{display:block;color:var(--text-2);font-size:10px;text-transform:uppercase;} .sp-grid b{font-size:13px;font-variant-numeric:tabular-nums;}
	.sp-warn{color:var(--warn);font-size:11px;margin-bottom:8px;} .sp-warn.err{color:#f4aaa2;}
</style>
