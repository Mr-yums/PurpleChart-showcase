<script lang="ts">
	// Présentation du graphique : crée lightweight-charts, délègue les données au ChartController, monte les overlays.
	import { onMount } from 'svelte';
	import { createChart, type IChartApi } from 'lightweight-charts';
	import { ChartController } from './ChartController';
	import ProfileOverlay from './overlays/ProfileOverlay.svelte';
	import VpRangeOverlay from './overlays/VpRangeOverlay.svelte';
	import GexOverlay from './overlays/GexOverlay.svelte';
	import OrderOverlay from '$replay/components/orders/OrderOverlay.svelte';
	import { chartSettings } from '$replay/application/ChartSettings';
	import './chart.css';

	let { symbol, timeframe, tz = 'Europe/Paris' }: { symbol: string; timeframe: string; tz?: string } = $props();
	let container = $state<HTMLDivElement>(null!);
	let message = $state('');
	let api = $state.raw<{ chart: IChartApi; controller: ChartController } | null>(null);

	function format(t: number, date = false): string {
		return new Date(t * 1000).toLocaleString('fr-FR', {
			timeZone: tz,
			...(/D$/.test(timeframe) ? { day: '2-digit', month: '2-digit', year: 'numeric' } : { hour: '2-digit', minute: '2-digit' }),
			...(timeframe.endsWith('s') ? { second: '2-digit' } : {}),
			...(date ? { day: '2-digit', month: '2-digit' } : {})
		});
	}

	onMount(() => {
		const chart = createChart(container, {
			autoSize: true,
			layout: { background: { color: '#12121a' }, textColor: '#a0a0b0', fontFamily: 'Inter, sans-serif' },
			grid: { vertLines: { color: '#1e1e2a' }, horzLines: { color: '#1e1e2a' } },
			rightPriceScale: { borderColor: '#2a2a38', minimumWidth: 84 },
			timeScale: { borderColor: '#2a2a38', timeVisible: true, secondsVisible: timeframe.endsWith('s'), tickMarkFormatter: (t: number) => format(t) },
			crosshair: { mode: 0 }, localization: { locale: 'fr-FR', timeFormatter: (t: number) => format(t, true) }
		});
		const controller = new ChartController(chart, symbol, timeframe, { state: (t) => { message = t; } });
		const offSettings = chartSettings.subscribe((s) => { controller.setStyle(s.style); controller.setEma(s.ema); controller.setVwap(s.vwap, s.bands); });
		controller.start();
		api = { chart, controller };
		return () => { api = null; offSettings(); controller.dispose(); queueMicrotask(() => chart.remove()); /* [Sol] Overlays detach first, before destroying the chart model. */ };
	});
</script>

<div class="market-chart" data-testid="market-chart" data-timeframe={timeframe}>
	<div class="market-chart__canvas" bind:this={container}></div>
	{#if message}<div class="market-chart__message" role="status">{message}</div>{/if}
	{#if api}
		<div class="study-legend">
			<button style="color:#ffb020;border-color:#ffb02055" class:off={!$chartSettings.ema} onclick={() => chartSettings.update({ ema: !$chartSettings.ema })}>EMA 20 · 50</button>
			<button style="color:#00e5ff;border-color:#00e5ff55" class:off={$chartSettings.vwap === 'off'} onclick={() => chartSettings.update({ vwap: $chartSettings.vwap === 'globex' ? 'rth' : $chartSettings.vwap === 'rth' ? 'off' : 'globex' })}>VWAP {$chartSettings.vwap === 'off' ? 'off' : $chartSettings.vwap === 'rth' ? 'RTH' : 'Globex'}</button>
			<button style="color:#00e5ff;border-color:#00e5ff55" class:off={!$chartSettings.bands} onclick={() => chartSettings.update({ bands: !$chartSettings.bands })}>±σ</button>
		</div>
		<ProfileOverlay chart={api.chart} host={container} controller={api.controller} />
		<VpRangeOverlay chart={api.chart} host={container} controller={api.controller} />
		<GexOverlay chart={api.chart} controller={api.controller} />
		<OrderOverlay chart={api.chart} series={api.controller.candle} host={container} />
	{/if}
	<span class="market-chart__timezone">{tz} · archive replay</span>
</div>
