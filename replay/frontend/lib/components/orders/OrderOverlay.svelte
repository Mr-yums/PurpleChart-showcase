<script lang="ts">
	// Lignes d'ordre sur le graphique (patron PurpleChart v2) : setup pré-ordre (entrée marché, SL/TP glissables,
	// recalcul live du sizing), position simulée (entrée + PnL latent, SL/TP glissables -> modify au relâchement).
	// Clic simple hors ligne = armement (sous le cours : achat, au-dessus : vente). Échap = annuler.
	import { onMount } from 'svelte';
	import type { IChartApi, ISeriesApi } from 'lightweight-charts';
	import { desk } from '$replay/application/PaperDesk';
	import { market } from '$replay/application/MarketStore';
	import { vpTool } from '$replay/application/VpTool';
	import { get } from 'svelte/store';
	import './orders.css';

	let { chart, series, host }: { chart: IChartApi; series: ISeriesApi<'Candlestick'>; host: HTMLElement } = $props();
	interface Line { kind: string; price: number; y: number; labelY: number; outside: boolean; label: string; drag: boolean; cls: string; }
	let layer: HTMLDivElement;
	let lines = $state<Line[]>([]);
	let dragging: { kind: 'sl' | 'tp'; owner: 'setup' | 'position'; startY: number; startPrice: number; ppp: number; id: number; el: HTMLElement; last: number } | null = null;
	let press: { x: number; y: number; t: number } | null = null;
	const money = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(2) + ' $';

	onMount(() => {
		let raf = 0;
		const draw = () => {
			const d = get(desk), pos = get(market.positions)[0], last = get(market.lastPrice);
			const h = layer?.clientHeight ?? 0, out: Line[] = [];
			const add = (kind: string, price: number, label: string, drag: boolean, cls: string) => {
				const y = series.priceToCoordinate(price) ?? -100;
				out.push({ kind, price, y: Math.max(14, Math.min(h - 30, y)), labelY: Math.max(14, Math.min(h - 30, y)), outside: y < 14 || y > h - 30, label, drag, cls });
			};
			if (d.setup && d.sizing) {
				const z = d.sizing, lbl = d.setup.side === 'buy' ? 'ACHAT' : 'VENTE';
				add('entry', z.entry, `${lbl} ×${z.qty} @ marché ${z.entry.toFixed(2)}`, false, d.setup.side === 'buy' ? 'setup-buy' : 'setup-sell');
				add('sl', d.setup.sl, z.badSL ? 'SL invalide' : `SL ${d.setup.sl.toFixed(2)} · −${Math.round(z.risk)} $ · ${z.slTicks} ticks`, true, 'stop');
				if (d.setup.tp != null) add('tp', d.setup.tp, z.badTP ? 'TP invalide' : `TP ${d.setup.tp.toFixed(2)} · +${Math.round(z.gain ?? 0)} $ · R ${z.rr?.toFixed(2)}`, true, 'target');
			} else if (d.pendingPrice != null) add('pending', d.pendingPrice, 'envoi…', false, 'pending');
			if (pos) {
				const dir = pos.side === 'LONG' ? 1 : -1;
				let pnl = '';
				let pnlCls = '';
				if (last != null) { const pts = (last - pos.entry) * dir, usd = pts * pos.point_value * pos.size; pnl = ` · ${money(usd)} (${pts >= 0 ? '+' : ''}${pts.toFixed(2)} pts)`; pnlCls = usd >= 0 ? 'pnl-profit' : 'pnl-loss'; }
				add('pentry', pos.entry, `${pos.side} ×${pos.size} @ ${pos.entry}${pnl}`, false, 'entry ' + pnlCls);
				if (pos.sl != null) add('psl', pos.sl, `SL ${pos.sl}`, true, 'stop');
				if (pos.tp != null) add('ptp', pos.tp, `TP ${pos.tp}`, true, 'target');
			}
			const packed = [...out].sort((a, b) => a.y - b.y);
			for (let i = 1; i < packed.length; i++) packed[i].labelY = Math.max(packed[i].labelY, packed[i - 1].labelY + 26);
			if (out.length) { const overflow = Math.max(0, packed[packed.length - 1].labelY - (h - 30)); for (const l of out) l.labelY -= overflow; }
			lines = out;
			raf = requestAnimationFrame(draw);
		};
		draw();
		const yOf = (e: MouseEvent) => e.clientY - host.getBoundingClientRect().top;
		const onDown = (e: MouseEvent) => {
			if (e.button !== 0) return;
			if (dragging || vpTool.isArmed) return;
			if ((e.target as HTMLElement | null)?.closest?.('.order-price-label, .order-ticket, button')) return;
			press = { x: e.clientX, y: e.clientY, t: Date.now() };
		};
		const onUp = (e: MouseEvent) => {
			if (!press) return;
			const still = Math.abs(e.clientX - press.x) < 5 && Math.abs(e.clientY - press.y) < 5 && Date.now() - press.t < 600;
			press = null;
			if (!still || vpTool.isArmed) return;
			const r = host.getBoundingClientRect();
			if (vpTool.blocks(e.clientX - r.left, e.clientY - r.top)) return;
			const raw = series.coordinateToPrice(yOf(e));
			if (raw != null) desk.clickAt(raw);
		};
		const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') desk.cancel(); };
		host.addEventListener('mousedown', onDown, true);
		window.addEventListener('mouseup', onUp);
		window.addEventListener('keydown', onKey);
		return () => { cancelAnimationFrame(raf); host.removeEventListener('mousedown', onDown, true); window.removeEventListener('mouseup', onUp); window.removeEventListener('keydown', onKey); end(true); };
	});

	function down(e: PointerEvent, line: Line) {
		if (e.button !== 0 || !line.drag || dragging) return;
		const p0 = series.coordinateToPrice(100), p1 = series.coordinateToPrice(101);
		if (p0 == null || p1 == null) return;
		e.preventDefault(); e.stopPropagation();
		const owner = line.kind.startsWith('p') ? 'position' : 'setup';
		const kind = (line.kind === 'psl' || line.kind === 'sl') ? 'sl' : 'tp';
		const el = e.currentTarget as HTMLElement;
		dragging = { kind, owner, startY: e.clientY, startPrice: line.price, ppp: p1 - p0, id: e.pointerId, el, last: line.price };
		chart.applyOptions({ handleScroll: false, handleScale: false });
		el.setPointerCapture(e.pointerId);
		window.addEventListener('pointermove', move, true); window.addEventListener('pointerup', up, true); window.addEventListener('pointercancel', cancel, true); window.addEventListener('blur', cancel);
	}
	function move(e: PointerEvent) {
		if (!dragging || e.pointerId !== dragging.id) return;
		if (!(e.buttons & 1)) { end(false); return; }
		e.preventDefault(); e.stopPropagation();
		const price = dragging.startPrice + (e.clientY - dragging.startY) * dragging.ppp;
		const snapped = desk.calc ? desk.calc.snap(price) : price;
		dragging.last = snapped;
		if (dragging.owner === 'setup') desk.move(dragging.kind, snapped);
		else lines = lines.map((l) => (l.kind === 'p' + dragging!.kind ? { ...l, price: snapped, y: series.priceToCoordinate(snapped) ?? l.y, labelY: series.priceToCoordinate(snapped) ?? l.labelY, label: `${dragging!.kind.toUpperCase()} → ${snapped}` } : l));
	}
	function up(e: PointerEvent) { if (!dragging || e.pointerId !== dragging.id) return; e.preventDefault(); e.stopPropagation(); end(false); }
	function cancel() { end(true); }
	function end(cancelled: boolean) {
		if (!dragging) return;
		const d = dragging; dragging = null;
		window.removeEventListener('pointermove', move, true); window.removeEventListener('pointerup', up, true); window.removeEventListener('pointercancel', cancel, true); window.removeEventListener('blur', cancel);
		if (d.el.hasPointerCapture(d.id)) d.el.releasePointerCapture(d.id);
		chart.applyOptions({ handleScroll: true, handleScale: true });
		if (d.owner === 'position' && !cancelled && d.last !== d.startPrice) void desk.modify(d.kind, d.last);
	}
</script>

<div class="order-overlay" bind:this={layer}>
	{#each lines as line (line.kind)}
		<div class="order-price-line {line.cls}" class:outside={line.outside} style:top={`${line.y}px`}>
			<button class="order-price-label" class:draggable={line.drag} style:top={`${line.labelY - line.y}px`} title={line.label} aria-label={`${line.kind} ${line.price}`} onpointerdown={(e) => down(e, line)} onlostpointercapture={cancel} onclick={(e) => e.stopPropagation()}>{line.label}{line.outside ? ' · hors cadre' : ''}</button>
		</div>
	{/each}
</div>
