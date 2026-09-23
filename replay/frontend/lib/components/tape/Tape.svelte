<script lang="ts">
	// Time & sales : prints accumulés puis insérés en un passage par rAF (un reflow max par frame),
	// gros lots surlignés au seuil adaptatif serveur, marques classifiées annotées. CVD et compteurs de séance.
	import { onMount } from 'svelte';
	import { market } from '$replay/application/MarketStore';
	import type { Trade } from '$replay/domain/market/types';
	import './tape.css';

	let list: HTMLDivElement;
	const stats = market.stats;
	const MAX = 200;
	let digits = 2;
	let big = 10;
	let last = $state('—');

	onMount(() => {
		let queue: Trade[] = [], raf = 0;
		const time = (t: Trade) => { const d = new Date(t.t * 1000); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('fr-FR', { hour12: false, timeZone: 'Europe/Paris' }); };
		const row = (t: Trade) => {
			const div = document.createElement('div');
			const side = t.side === 'buy' ? 'buy' : t.side === 'sell' ? 'sell' : 'unk';
			const kind = t.kind === 'block' || t.kind === 'sweep' || t.kind === 'absorb' ? t.kind : '';
			div.className = `tape-row ${side}${(t.volume || 0) >= big ? ' big' : ''}${kind ? ' k-' + kind : ''}`;
			if (kind) div.title = kind === 'block' ? 'Gros lot individuel' : kind === 'sweep' ? 'Sweep : rafale agressive fragmentée' : 'Absorption : agression massive, prix figé';
			const arrow = kind === 'block' ? '●' : kind === 'sweep' ? '◎' : kind === 'absorb' ? '■' : side === 'buy' ? '▲' : side === 'sell' ? '▼' : '•';
			div.innerHTML = `<span class="tp-time">${time(t)}</span><span class="tp-px">${t.price == null ? '—' : Number(t.price).toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}</span><span class="tp-sz">${t.volume ?? '—'}</span><span class="tp-side">${arrow}</span>`;
			return div;
		};
		const append = (trades: Trade[]) => {
			if (!trades.length) return;
			if (trades.length > MAX) trades = trades.slice(-MAX);
			const frag = document.createDocumentFragment();
			for (let i = trades.length - 1; i >= 0; i--) frag.appendChild(row(trades[i]));
			list.insertBefore(frag, list.firstChild);
			while (list.children.length > MAX) list.removeChild(list.lastChild!);
			last = time(trades[trades.length - 1]);
		};
		const offs = [
			market.onTrades((trades, snapshot) => {
				if (snapshot) { list.innerHTML = ''; queue = []; append(trades.slice(-MAX)); return; }
				queue.push(...trades);
				if (!raf) raf = requestAnimationFrame(() => { raf = 0; const q = queue; queue = []; append(q); });
			}),
			market.stats.subscribe((s) => { if (Number.isFinite(s.big_threshold) && s.big_threshold >= 1) big = s.big_threshold; }),
			market.dom.subscribe((d) => { if (d && d.digits != null) digits = d.digits; })
		];
		return () => { offs.forEach((f) => f()); if (raf) cancelAnimationFrame(raf); };
	});
</script>

<div class="tape">
	<div class="tape-stats mono">
		<span>CVD <b class:pos={$stats.cvd > 0} class:neg={$stats.cvd < 0}>{($stats.cvd > 0 ? '+' : '') + $stats.cvd.toLocaleString('fr-FR')}</b></span>
		<span class="buy">▲ <b>{$stats.buys.toLocaleString('fr-FR')}</b></span>
		<span class="sell">▼ <b>{$stats.sells.toLocaleString('fr-FR')}</b></span>
		<span class="muted">{last}</span>
	</div>
	<div class="tape-head"><span>Heure</span><span>Prix</span><span>Taille</span><span></span></div>
	<div class="tape-list" bind:this={list}></div>
	<div class="note">▲ achat · ▼ vente au marché (agresseur). CVD = delta cumulé de séance. Gros lots ≥ seuil adaptatif.</div>
</div>
