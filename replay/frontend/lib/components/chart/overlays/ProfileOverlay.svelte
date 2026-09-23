<script lang="ts">
	// Profil de volume de séance (volume réellement traité par prix, payload dom.profile), ancré au bord droit, POC doré.
	import { onMount } from 'svelte';
	import type { IChartApi } from 'lightweight-charts';
	import type { ChartController } from '../ChartController';
	import { OverlayCanvas } from './canvas';
	import { market } from '$replay/application/MarketStore';
	import { chartSettings } from '$replay/application/ChartSettings';
	import type { DomBook } from '$replay/domain/market/types';
	import { get } from 'svelte/store';

	let { chart, host, controller }: { chart: IChartApi; host: HTMLElement; controller: ChartController } = $props();

	onMount(() => {
		let book: DomBook | null = null;
		const canvas = new OverlayCanvas(host, chart, (ctx, W, H) => {
			if (!book || !get(chartSettings).profile) return;
			const src = book.profile?.length ? book.profile.map((pv) => ({ price: pv[0], vol: pv[1] })) : [...(book.bids || []), ...(book.asks || [])];
			const levels = src.filter((l) => l && l.vol > 0);
			if (!levels.length) return;
			const series = controller.candle, right = W - controller.axisWidth(), maxBarW = Math.min(220, right * 0.3);
			const tick = book.tick || 0.25;
			const yA = series.priceToCoordinate(levels[0].price), yB = series.priceToCoordinate(levels[0].price + tick);
			if (yA == null || yB == null) return;
			const tickPx = Math.max(Math.abs(yB - yA), 0.0001), binTicks = Math.max(1, Math.ceil(2 / tickPx)), binSize = tick * binTicks;
			const bidMax = book.bids?.length ? book.bids[0].price : book.bid ?? -Infinity;
			const bins = new Map<number, { vol: number; bid: number; ask: number }>();
			for (const l of levels) {
				const k = Math.round(l.price / binSize);
				const e = bins.get(k) || { vol: 0, bid: 0, ask: 0 };
				e.vol += l.vol; if (l.price <= bidMax) e.bid += l.vol; else e.ask += l.vol;
				bins.set(k, e);
			}
			let maxVol = 0, pocKey: number | null = null;
			for (const [k, e] of bins) if (e.vol > maxVol) { maxVol = e.vol; pocKey = k; }
			if (!maxVol || pocKey == null) return;
			const barH = Math.max(1, tickPx * binTicks - 1);
			for (const [k, e] of bins) {
				const y = series.priceToCoordinate(k * binSize);
				if (y == null || y < -barH || y > H + barH) continue;
				const w = Math.max(1, (e.vol / maxVol) * maxBarW);
				ctx.fillStyle = k === pocKey ? 'rgba(232,193,74,.60)' : e.bid >= e.ask ? 'rgba(38,166,106,.30)' : 'rgba(224,82,75,.30)';
				ctx.fillRect(right - w, y - barH / 2, w, barH);
			}
			const pocY = series.priceToCoordinate(pocKey * binSize);
			if (pocY != null) {
				const poc = bins.get(pocKey)!;
				ctx.font = '10px system-ui, sans-serif'; ctx.fillStyle = 'rgba(232,193,74,.9)'; ctx.textAlign = 'right';
				ctx.fillText(`POC ${(pocKey * binSize).toFixed(book.digits ?? 2)} · ${poc.vol}`, right - Math.max(1, (poc.vol / maxVol) * maxBarW) - 6, pocY + 3);
			}
		}, 3);
		const offs = [market.dom.subscribe((b) => { book = b; canvas.schedule(); }), chartSettings.subscribe(() => canvas.schedule()), controller.onBars(() => canvas.schedule())];
		return () => { offs.forEach((f) => f()); canvas.dispose(); };
	});
</script>
