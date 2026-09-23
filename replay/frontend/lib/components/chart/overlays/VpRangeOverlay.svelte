<script lang="ts">
	// Overlay du VP de mesure : canvas + souris (armement « Tracer », drag, suppression par la croix).
	import { onMount } from 'svelte';
	import type { IChartApi } from 'lightweight-charts';
	import type { ChartController } from '../ChartController';
	import { OverlayCanvas } from './canvas';
	import { VpRange } from './VpRange';
	import { market } from '$replay/application/MarketStore';
	import { vpTool } from '$replay/application/VpTool';

	let { chart, host, controller }: { chart: IChartApi; host: HTMLElement; controller: ChartController } = $props();

	onMount(() => {
		const vp = new VpRange(chart, controller.candle);
		vpTool.bind(vp);
		const canvas = new OverlayCanvas(host, chart, (ctx, W, H) => vp.draw(ctx, W, H, controller.axisWidth()), 5);
		vp.onChange = () => canvas.schedule();
		vp.setContext(controller.symbol);
		vp.setCandles(controller.candles);
		vp.seed(market.trades);
		const rel = (e: MouseEvent) => { const r = host.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
		const down = (e: MouseEvent) => {
			if (!vp.armed || e.button !== 0) return;
			e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
			chart.applyOptions({ handleScroll: false, handleScale: false });
			vp.beginDrag(rel(e).x);
		};
		const move = (e: MouseEvent) => { if (vp.drag) vp.moveDrag(rel(e).x); };
		const up = () => { if (!vp.drag) return; chart.applyOptions({ handleScroll: true, handleScale: true }); vp.endDrag(); host.style.cursor = ''; vpTool.disarmed(); };
		const click = (e: MouseEvent) => { if (vp.armed) return; const p = rel(e); if (vp.clickAt(p.x, p.y)) e.stopPropagation(); };
		host.addEventListener('mousedown', down, true);
		window.addEventListener('mousemove', move);
		window.addEventListener('mouseup', up);
		host.addEventListener('click', click);
		const offs = [
			controller.onBars(() => { vp.setCandles(controller.candles); }),
			market.onTrades((trades, snapshot) => { if (snapshot) vp.seed(trades); else vp.push(trades); }),
			market.onCandle((c) => vp.pushCandle(c))
		];
		return () => {
			vpTool.unbind(); offs.forEach((f) => f());
			host.removeEventListener('mousedown', down, true); window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); host.removeEventListener('click', click);
			canvas.dispose();
		};
	});
</script>
