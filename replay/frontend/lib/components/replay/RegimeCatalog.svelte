<script lang="ts">
	// Catalogue des régimes de séance (regimes.json) : phases DIRECTIONNEL / RANGE / RANGE PIÉGEUX par jour,
	// mini profil de volume (POC jaune, value area violette). Clic = charge le replay au début de la phase.
	import { onMount } from 'svelte';
    import VolumeProfile from './VolumeProfile.svelte';
    import Icon from '$replay/components/ui/Icon.svelte'; // [Sol]
	import { ReplayApi } from '$replay/api/replay';
	import type { RegimeCatalogue } from '$replay/domain/market/types';

	let { onpick, onclose }: { onpick: (symbol: string, ts: number, source?: string) => void; onclose: () => void } = $props();
	const LABELS: Record<string, { txt: string; col: string }> = {
		DIR_UP: { txt: 'HAUSSE ↑', col: '#22c55e' }, DIR_DOWN: { txt: 'BAISSE ↓', col: '#ef4444' },
		RANGE: { txt: 'RANGE', col: '#94a3b8' }, BATARD: { txt: 'AMBIGU', col: '#f59e0b' }
	};
	let data = $state<RegimeCatalogue | null>(null);
	let error = $state('');
	let sym = $state('');
	const symbols = $derived(data ? Object.keys(data.symbols) : []);
	const days = $derived(data && sym && data.symbols[sym] ? Object.keys(data.symbols[sym]).sort().reverse() : []);

	onMount(async () => {
		try {
			data = await ReplayApi.regimes();
			if (!data.ok) error = data.message || 'catalogue absent';
			sym = symbols.includes('US100.cash') ? 'US100.cash' : symbols[0] ?? '';
		} catch (e) { error = 'erreur de chargement du catalogue : ' + (e as Error).message; }
	});

</script>

<div class="rg-panel" role="dialog" aria-label="Catalogue des séances">
    <div class="rg-head"><div><b>Séances & régimes</b><p>Profils de volume des journées UTC et des régimes horaires. Vue rétrospective complète : ces profils incluent la suite de la séance. Clique sur un régime pour rejouer.</p></div><button class="btn icon-button" aria-label="Fermer le catalogue" onclick={onclose}><Icon name="close"/></button></div>
    <div class="rg-legend"><span style="color:#79c3a0">HAUSSE / BAISSE</span><span style="color:#b3b6c5">RANGE</span><span style="color:#d8b576">MIXTE</span><span style="color:#e8c14a">POC jaune</span><span style="color:#a47cec">Zone de valeur 70 %</span><span>Heures UTC · données enregistrées uniquement</span></div>
	{#if error}<div class="rg-info">{error}</div>
	{:else if !data}<div class="rg-info">chargement du catalogue…</div>
	{:else}
		<div class="rg-sym">Symbole <select bind:value={sym}>{#each symbols as s}<option value={s}>{s}</option>{/each}</select></div>
		{#each days as day (day)}
			{@const d = data.symbols[sym][day]}
			{#if d.segments?.length}
				<h3>{d.jour} {day} <span class="rg-meta">net {d.day_net > 0 ? '+' : ''}{d.day_net} pts · range {d.day_range} pts</span></h3>
				<div class="day-profile"><b>Profil de la journée</b><VolumeProfile profile={d.vp} label={`Profil du ${day} ${sym}`} /></div>
				{#each d.segments as g (g.debut_s)}
					<div class="rg-row" role="button" tabindex="0" onclick={() => onpick(sym, g.debut_s, d.source)} onkeydown={(e) => e.key === 'Enter' && onpick(sym, g.debut_s, d.source)}>
						<span class="rg-t">{g.debut} → {g.fin}</span>
						<span class="rg-cl" style:color={(LABELS[g.classe] ?? { col: '#fff' }).col}>{(LABELS[g.classe] ?? { txt: g.classe }).txt}</span>
						<span class="rg-net" style:color={g.net >= 0 ? '#22c55e' : '#ef4444'}>{g.net > 0 ? '+' : ''}{g.net}</span>
						<span class="rg-meta">{g.duree_min} min · ER {g.er}</span>
						<div class="segment-profile"><VolumeProfile profile={g.vp} label={`Profil ${sym} ${g.debut} à ${g.fin}`} /></div>
					</div>
				{/each}
			{/if}
		{/each}
	{/if}
</div>

<style>
 .rg-panel{position:absolute;top:calc(100% + 8px);right:0;z-index:200;background:var(--bg-1);border:1px solid #484055;border-radius:12px;box-shadow:0 18px 60px #0008;max-height:min(580px,70vh);overflow:auto;width:min(710px,100%);padding:20px;font-size:12px;line-height:1.5;color:var(--text-1);}
 .rg-head{display:flex;align-items:flex-start;gap:14px;margin-bottom:14px}.rg-head b{font-size:15px;font-weight:600;color:var(--text-0)}.rg-head p{margin:5px 0 0;font-size:11px;color:var(--text-2)}.rg-head .btn{margin-left:auto;flex-shrink:0}
 .rg-legend{display:flex;align-items:center;gap:16px;font-size:10px;flex-wrap:wrap;padding-bottom:15px;border-bottom:1px solid var(--border-soft);margin-bottom:14px}.rg-legend span:last-child{margin-left:auto;color:var(--text-2)}
 h3{margin:20px 0 7px;font-size:12px;font-weight:600;color:var(--text-0);padding-bottom:7px;border-bottom:1px solid var(--border-soft)}h3 .rg-meta{font-size:10px;font-weight:400;margin-left:8px;}
 .rg-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;min-height:38px;padding:8px;border-radius:7px;cursor:pointer;border:1px solid transparent;}.rg-row:hover,.rg-row:focus-visible{background:var(--bg-2);border-color:var(--border)}
 .rg-cl{font-weight:600;min-width:88px;font-size:11px}.rg-t{font-variant-numeric:tabular-nums;color:var(--text-1);min-width:100px;font-size:11px}.rg-net{min-width:60px;text-align:right;font-variant-numeric:tabular-nums}.rg-meta{color:var(--text-2);font-size:11px}
 .day-profile{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--bg-2);padding:10px;border-radius:7px}.day-profile>b{font-size:11px;font-weight:500}.segment-profile{margin-left:auto;}.rg-sym{font-size:11px;display:flex;gap:10px;align-items:center}.rg-sym select{background:var(--bg-0);color:var(--text-0);border:1px solid var(--border);border-radius:7px;padding:6px 10px;min-width:110px}.rg-info{color:var(--text-1);padding:18px 0}
 @media(max-width:650px){.rg-panel{padding:14px}.rg-row{gap:8px}.rg-cl{min-width:76px}.rg-net{min-width:45px}.segment-profile{width:100%;margin-left:0}.day-profile{align-items:flex-start;flex-direction:column}}
</style>
