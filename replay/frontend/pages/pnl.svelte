<script lang="ts">
	// PnL paper-trading : KPIs, courbe d'équité (net cumulé), stats d'edge par régime / tag / GEX, table des trades.
	import { onMount } from 'svelte';
	import { EdgeApi } from '$replay/api/edge';
	import type { EdgeGroup, EdgeTrade, GexGroup } from '$replay/domain/market/types';
	let trades = $state<EdgeTrade[]>([]);
	let groups = $state<EdgeGroup[]>([]);
	let gex = $state<GexGroup[]>([]);
	let mode = $state<'all' | 'replay' | 'live'>('all');
	let period = $state<'all' | 'today' | '7d' | '30d'>('all');
	let canvas: HTMLCanvasElement;
	const usd = (v: number | null | undefined) => (v == null ? '—' : (v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ','));
	const filtered = $derived.by(() => {
		let list = trades;
		if (mode !== 'all') list = list.filter((t) => (t.mode || 'replay') === mode);
		if (period !== 'all') { const now = Date.now() / 1000, cut = { today: now - 86400, '7d': now - 7 * 86400, '30d': now - 30 * 86400 }[period]; list = list.filter((t) => (t.ts_wall || 0) > cut); }
		return list;
	});
	const net = (t: EdgeTrade) => (t.pnl_net != null ? t.pnl_net : (t.pnl || 0) - (t.fees || 0));
	const kpis = $derived.by(() => {
		const l = filtered, n = l.length, wins = l.filter((t) => (t.pnl || 0) > 0), losses = l.filter((t) => (t.pnl || 0) < 0);
		const gross = l.reduce((s, t) => s + (t.pnl || 0), 0), fees = l.reduce((s, t) => s + (t.fees || 0), 0), tot = l.reduce((s, t) => s + net(t), 0);
		const gw = wins.reduce((s, t) => s + (t.pnl || 0), 0), gl = Math.abs(losses.reduce((s, t) => s + (t.pnl || 0), 0)), pf = gl > 0 ? gw / gl : gw > 0 ? Infinity : 0;
		const rs = l.filter((t) => t.result_r != null).map((t) => t.result_r as number);
		return [
			{ l: 'PnL net', v: usd(tot), c: tot >= 0 ? 'pos' : 'neg' }, { l: 'PnL brut', v: usd(gross), c: gross >= 0 ? 'pos' : 'neg' }, { l: 'Fees', v: usd(-fees), c: 'neg' },
			{ l: 'Trades', v: String(n), c: '' }, { l: 'Win rate', v: (n ? (wins.length / n) * 100 : 0).toFixed(1) + '%', c: n && wins.length / n >= 0.5 ? 'pos' : 'neg' },
			{ l: 'Profit factor', v: pf === Infinity ? '∞' : pf.toFixed(2), c: pf >= 1 ? 'pos' : 'neg' },
			{ l: 'Σ R', v: rs.length ? rs.reduce((a, b) => a + b, 0).toFixed(2) : '—', c: '' }, { l: 'R moyen', v: rs.length ? (rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2) : '—', c: '' },
			{ l: 'Avg win', v: usd(wins.length ? gw / wins.length : 0), c: 'pos' }, { l: 'Avg loss', v: usd(losses.length ? -gl / losses.length : 0), c: 'neg' }
		];
	});
	function equity() {
		if (!canvas) return;
		const ctx = canvas.getContext('2d')!, dpr = window.devicePixelRatio || 1, rect = canvas.getBoundingClientRect();
		canvas.width = rect.width * dpr; canvas.height = rect.height * dpr; ctx.scale(dpr, dpr);
		const W = rect.width, H = rect.height; ctx.clearRect(0, 0, W, H);
		const sorted = [...filtered].sort((a, b) => (a.ts_wall || 0) - (b.ts_wall || 0));
		if (!sorted.length) { ctx.fillStyle = '#8a95ad'; ctx.textAlign = 'center'; ctx.font = '13px sans-serif'; ctx.fillText('Aucun trade', W / 2, H / 2); return; }
		const eq = [0]; for (const t of sorted) eq.push(eq[eq.length - 1] + net(t));
		const mn = Math.min(...eq), mx = Math.max(...eq), range = mx - mn || 1, pad = { t: 12, b: 24, l: 56, r: 12 }, cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;
		const zy = pad.t + ch * (1 - (0 - mn) / range);
		ctx.strokeStyle = '#232b3d'; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(pad.l, zy); ctx.lineTo(W - pad.r, zy); ctx.stroke(); ctx.setLineDash([]);
		ctx.beginPath(); eq.forEach((v, i) => { const x = pad.l + (i / (eq.length - 1)) * cw, y = pad.t + ch * (1 - (v - mn) / range); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
		const last = eq[eq.length - 1]; ctx.strokeStyle = last >= 0 ? '#2ec27e' : '#e5484d'; ctx.lineWidth = 2; ctx.stroke();
		ctx.lineTo(pad.l + cw, zy); ctx.lineTo(pad.l, zy); ctx.closePath(); ctx.fillStyle = last >= 0 ? 'rgba(46,194,126,.08)' : 'rgba(229,72,77,.08)'; ctx.fill();
		ctx.fillStyle = '#8a95ad'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right'; ctx.fillText(usd(mx), pad.l - 6, pad.t + 8); ctx.fillText(usd(mn), pad.l - 6, H - pad.b); ctx.fillText('0', pad.l - 6, zy + 4);
		ctx.fillStyle = last >= 0 ? '#2ec27e' : '#e5484d'; ctx.textAlign = 'left'; ctx.font = 'bold 12px sans-serif'; ctx.fillText(usd(last), pad.l + cw + 4, pad.t + ch * (1 - (last - mn) / range) + 4);
	}
	$effect(() => { filtered; requestAnimationFrame(equity); });
	const byKey = (key: 'regime' | 'entry_tag') => { const m = new Map<string, { n: number; wins: number; sum: number; r: number }>(); for (const g of groups) { const k = g[key] || '—'; const e = m.get(k) || { n: 0, wins: 0, sum: 0, r: 0 }; e.n += g.n; e.wins += g.wins || 0; e.sum += g.sum_usd || 0; e.r += g.sum_r || 0; m.set(k, e); } return [...m.entries()].sort((a, b) => b[1].n - a[1].n); };
	const tables = $derived([{ title: 'Stats par régime', rows: byKey('regime') }, { title: 'Stats par tag', rows: byKey('entry_tag') }]);
	onMount(() => {
		void (async () => {
			try { const [j, s, g] = await Promise.all([EdgeApi.journal(5000), EdgeApi.stats(), EdgeApi.gexStats()]); trades = j.trades.sort((a, b) => (b.ts_wall || 0) - (a.ts_wall || 0)); groups = s.groups; gex = g.groups; } catch { /* page vide */ }
		})();
		window.addEventListener('resize', equity);
		return () => window.removeEventListener('resize', equity);
	});
</script>

<div class="wrap">
	<div class="filters">
		{#each [['all', 'Tous'], ['replay', 'Replay'], ['live', 'Démo live']] as [m, l]}<button class="chip" class:on={mode === m} onclick={() => (mode = m as never)}>{l}</button>{/each}
		<span class="sep"></span>
		<select class="field" bind:value={period}><option value="all">Toute la période</option><option value="today">Aujourd'hui</option><option value="7d">7 derniers jours</option><option value="30d">30 derniers jours</option></select>
	</div>
	<div class="kpis">{#each kpis as k}<div class="kpi"><div class="label">{k.l}</div><div class="val {k.c}">{k.v}</div></div>{/each}</div>
	<div class="card"><h3 class="muted">Equity curve (PnL net cumulé)</h3><canvas class="equity" bind:this={canvas}></canvas></div>
	<div class="edge">
		{#each tables as tb (tb.title)}
			<div class="card"><h3 class="muted">{tb.title}</h3><table class="tbl"><thead><tr><th class="l">Clé</th><th>N</th><th>WR%</th><th>PnL $</th><th>Σ R</th></tr></thead><tbody>
				{#each tb.rows as [k, v] (k)}<tr><td class="l"><b>{k}</b></td><td>{v.n}</td><td class={v.n && v.wins / v.n >= 0.5 ? 'pos' : 'neg'}>{v.n ? ((v.wins / v.n) * 100).toFixed(0) : 0}%</td><td class={v.sum >= 0 ? 'pos' : 'neg'}>{usd(v.sum)}</td><td class={v.r >= 0 ? 'pos' : 'neg'}>{v.r.toFixed(1)}</td></tr>{/each}
			</tbody></table></div>
		{/each}
		<div class="card"><h3 class="muted">Stats GEX (régime × position vs flip × sens)</h3><table class="tbl"><thead><tr><th class="l">GEX</th><th class="l">Flip</th><th class="l">Sens</th><th>N</th><th>WR%</th><th>PnL $</th><th>R moy</th></tr></thead><tbody>
			{#each gex as g (g.gex_regime + g.above_flip + g.side)}<tr><td class="l">{g.gex_regime}</td><td class="l">{g.above_flip}</td><td class="l">{g.side}</td><td>{g.n}</td><td>{g.winrate}%</td><td class={g.sum_usd >= 0 ? 'pos' : 'neg'}>{usd(g.sum_usd)}</td><td>{g.avg_r ?? '—'}</td></tr>{/each}
		</tbody></table></div>
	</div>
	<div class="tbox"><table class="tbl"><thead><tr><th class="l">Date</th><th class="l">Mode</th><th class="l">Symbole</th><th class="l">Side</th><th>Qté</th><th>Entrée</th><th>Sortie</th><th>PnL</th><th>Fees</th><th>Net</th><th>R</th><th class="l">Raison</th><th class="l">Régime</th><th class="l">Tag</th><th class="l">Setup</th></tr></thead><tbody>
		{#if !filtered.length}<tr><td colspan="15" class="empty">Aucun trade trouvé</td></tr>{/if}
		{#each filtered as t (t.id)}
			<tr><td class="l">{new Date((t.ts_wall || 0) * 1000).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}</td><td class="l"><span class="pill" class:live={t.mode === 'live'} class:replay={t.mode !== 'live'}>{t.mode || 'replay'}</span></td><td class="l">{t.symbol}</td><td class="l" class:pos={t.side === 'LONG'} class:neg={t.side === 'SHORT'}>{t.side}</td><td>{t.size}</td><td>{t.entry?.toFixed(2)}</td><td>{t.exit?.toFixed(2)}</td><td class={(t.pnl || 0) >= 0 ? 'pos' : 'neg'}>{usd(t.pnl)}</td><td class="muted">{usd(t.fees || 0)}</td><td class={net(t) >= 0 ? 'pos' : 'neg'}><b>{usd(net(t))}</b></td><td>{t.result_r ?? '—'}</td><td class="l">{t.reason}</td><td class="l">{t.regime || '—'}</td><td class="l">{t.entry_tag || '—'}</td><td class="l">{t.ctx_setup || '—'}{t.ctx_coherence ? ' · ' + t.ctx_coherence : ''}</td></tr>
		{/each}
	</tbody></table></div>
</div>

<style>
	.wrap{max-width:1300px;margin:0 auto;padding:20px 16px;display:flex;flex-direction:column;gap:16px;}
	.filters{display:flex;gap:8px;align-items:center;flex-wrap:wrap;} .sep{width:1px;height:20px;background:var(--border);}
	.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}
	.kpi{background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:12px 14px;text-align:center;} .label{font-size:10px;color:var(--text-2);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;} .val{font-size:20px;font-weight:700;}
	.equity{width:100%;height:180px;display:block;} h3{margin-bottom:8px;font-size:12px;}
	.edge{display:grid;grid-template-columns:1fr 1fr;gap:16px;} @media(max-width:900px){.edge{grid-template-columns:1fr;}}
</style>
