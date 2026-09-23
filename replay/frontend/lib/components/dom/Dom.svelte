<script lang="ts">
	// DOM synthétique (volume réellement traité par prix, pas de L2 en archive) : réglette continue au pas
	// d'affichage adaptatif, barres proportionnelles, best bid/ask, imbalance. Rendu incrémental : le pool de lignes
	// est créé une fois, seules les cellules qui changent sont écrites, une frame max par rAF.
	import { onMount } from 'svelte';
	import { market } from '$replay/application/MarketStore';
	import type { DomBook } from '$replay/domain/market/types';
	import './dom.css';

	let ladder: HTMLDivElement;
	let imb = $state<{ pct: number; txt: string; bid: string; ask: string } | null>(null);
	let spread = $state('—');
	let ts = $state('—');
	const ROW_H = 20, MAX_ROWS = 80, DESIRED = 44, PAD = 3;
	const fmt = (n: number | null | undefined, d = 0) => n == null || Number.isNaN(Number(n)) ? '—' : Number(n).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });

	onMount(() => {
		type Row = { root: HTMLDivElement; bidBar: HTMLDivElement; bidSz: HTMLSpanElement; px: HTMLDivElement; askSz: HTMLSpanElement; askBar: HTMLDivElement; c: { cls: string; px: string; bid: string; ask: string; bw: string; aw: string; vis: boolean } };
		const rows: Row[] = [];
		let raf = 0, book: DomBook | null = null, lastHi: number | null = null, lastStep: number | null = null, centered = false, empty: HTMLDivElement | null = null;
		const ensure = (n: number) => {
			if (empty) { empty.remove(); empty = null; }
			while (rows.length < n) {
				const root = document.createElement('div'); root.className = 'lad-row';
				const bid = document.createElement('div'); bid.className = 'lad-bid';
				const bidBar = document.createElement('div'); bidBar.className = 'bar'; const bidSz = document.createElement('span'); bidSz.className = 'sz'; bid.append(bidBar, bidSz);
				const px = document.createElement('div'); px.className = 'lad-px';
				const ask = document.createElement('div'); ask.className = 'lad-ask';
				const askSz = document.createElement('span'); askSz.className = 'sz'; const askBar = document.createElement('div'); askBar.className = 'bar'; ask.append(askSz, askBar);
				root.append(bid, px, ask); ladder.appendChild(root);
				rows.push({ root, bidBar, bidSz, px, askSz, askBar, c: { cls: 'lad-row', px: '', bid: '', ask: '', bw: '', aw: '', vis: true } });
			}
			rows.forEach((r, i) => { const want = i < n; if (r.c.vis !== want) { r.root.style.display = want ? '' : 'none'; r.c.vis = want; } });
		};
		const set = (r: Row, cls: string, pxTxt: string, bidTxt: string, bw: string, askTxt: string, aw: string) => {
			const c = r.c;
			if (c.cls !== cls) { r.root.className = cls; c.cls = cls; }
			if (c.px !== pxTxt) { r.px.textContent = pxTxt; c.px = pxTxt; }
			if (c.bid !== bidTxt) { r.bidSz.textContent = bidTxt; c.bid = bidTxt; }
			if (c.bw !== bw) { r.bidBar.style.width = bw; c.bw = bw; }
			if (c.ask !== askTxt) { r.askSz.textContent = askTxt; c.ask = askTxt; }
			if (c.aw !== aw) { r.askBar.style.width = aw; c.aw = aw; }
		};
		const niceStep = (range: number, tick: number) => {
			if (!(range > 0)) return tick;
			const raw = range / DESIRED;
			for (const m of [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000]) if (tick * m >= raw) return tick * m;
			return tick * 10000;
		};
		const render = () => {
			const b = book; if (!b) return;
			const f = b.features || ({} as DomBook['features']);
			imb = { pct: f.imbalance != null ? f.imbalance * 100 : 50, txt: f.imbalance != null ? (f.imbalance * 100).toFixed(0) + '% bid' : '—', bid: 'bid ' + fmt(f.bid_vol), ask: 'ask ' + fmt(f.ask_vol) };
			ts = b.ts ? new Date(b.ts * 1000).toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' }) : '—';
			const digits = Number.isInteger(b.digits) ? b.digits : 2;
			spread = 'spread ' + fmt(b.spread, b.spread != null && b.spread % 1 ? digits : 0);
			const bids = b.bids || [], asks = b.asks || [];
			if (!bids.length && !asks.length) { rows.forEach((r) => { if (r.c.vis) { r.root.style.display = 'none'; r.c.vis = false; } }); if (!empty) { empty = document.createElement('div'); empty.className = 'dom-empty'; empty.textContent = 'carnet vide'; ladder.appendChild(empty); } lastHi = null; return; }
			const bestBid = bids.length ? bids[0].price : b.bid, bestAsk = asks.length ? asks[0].price : b.ask;
			const sorted = [...bids, ...asks].map((x) => x.price).sort((x, y) => x - y);
			const minP = sorted[0], maxP = sorted[sorted.length - 1];
			let tick = b.tick && b.tick > 0 ? b.tick : 0.25;
			if (!(b.tick > 0)) { let best: number | null = null; for (let i = 1; i < sorted.length; i++) { const d = Math.abs(sorted[i] - sorted[i - 1]); if (d > 1e-9 && (best === null || d < best)) best = d; } tick = best || 0.25; }
			const midRaw = f.mid ? f.mid : bestBid != null && bestAsk != null ? (bestBid + bestAsk) / 2 : (minP + maxP) / 2;
			const step = niceStep(maxP - minP, tick), snap = (p: number) => Math.round(p / step) * step, key = (p: number) => snap(p).toFixed(digits);
			const bidMap = new Map<string, number>(), askMap = new Map<string, number>();
			for (const x of bids) { const k = key(x.price); bidMap.set(k, (bidMap.get(k) || 0) + x.vol); }
			for (const x of asks) { const k = key(x.price); askMap.set(k, (askMap.get(k) || 0) + x.vol); }
			const bestBidKey = bestBid != null ? key(bestBid) : null, bestAskKey = bestAsk != null ? key(bestAsk) : null, midKey = key(midRaw);
			let hi = snap(maxP) + PAD * step, lo = snap(minP) - PAD * step, nRows = Math.round((hi - lo) / step) + 1;
			if (nRows > MAX_ROWS) { hi = snap(midRaw) + Math.floor(MAX_ROWS / 2) * step; nRows = MAX_ROWS; }
			const maxVol = Math.max(1, ...bidMap.values(), ...askMap.values()), prevScroll = ladder.scrollTop;
			ensure(nRows);
			let midIdx = 0;
			for (let i = 0; i < nRows; i++) {
				const price = hi - i * step, pk = price.toFixed(digits), bv = bidMap.get(pk), av = askMap.get(pk);
				let cls = 'lad-row';
				if (pk === bestAskKey) cls += ' best-ask'; else if (pk === bestBidKey) cls += ' best-bid';
				if (pk === midKey) { cls += ' mid'; midIdx = i; }
				set(rows[i], cls, fmt(price, digits), bv ? fmt(bv) : '', bv ? Math.max(4, (bv / maxVol) * 100).toFixed(1) + '%' : '0%', av ? fmt(av) : '', av ? Math.max(4, (av / maxVol) * 100).toFixed(1) + '%' : '0%');
			}
			const stepChanged = lastStep !== null && Math.abs(step - lastStep) > 1e-9;
			if (!centered || stepChanged) { ladder.scrollTop = Math.max(0, midIdx * ROW_H - ladder.clientHeight / 2 + ROW_H / 2); centered = true; }
			else if (lastHi !== null) { const dRows = Math.round((hi - lastHi) / step); if (dRows) ladder.scrollTop = prevScroll + dRows * ROW_H; }
			lastHi = hi; lastStep = step;
		};
		const off = market.dom.subscribe((b) => { book = b; if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); }); });
		return () => { off(); if (raf) cancelAnimationFrame(raf); };
	});
</script>

<div class="dom">
	<div class="dom-imbalance">
		<div class="imb-bar"><div class="imb-fill" style:width={`${imb?.pct ?? 50}%`}></div></div>
		<div class="imb-legend"><span>{imb?.bid ?? 'bid —'}</span><b>{imb?.txt ?? '—'}</b><span>{imb?.ask ?? 'ask —'}</span></div>
	</div>
	<div class="dom-meta mono"><span>{spread}</span><span>{ts}</span></div>
	<div class="lad-head"><span>Bid</span><span>Prix</span><span>Ask</span></div>
	<div class="dom-ladder" bind:this={ladder}></div>
	<div class="note">Volume réellement traité par prix (flux CME rejoué) — pas de carnet L2 en archive.</div>
</div>
