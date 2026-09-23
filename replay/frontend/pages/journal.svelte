<script lang="ts">
	// Journal des exercices de replay et sessions enregistrées.
	import { onMount } from 'svelte';
	import { JournalApi } from '$replay/api/journal';
	import type { JournalPayload, SessionsPayload, TradeStats } from '$replay/domain/market/types';
	const SRC = { replay: { lbl: 'Replay historique', cls: 'replay' } } as const;
	let data = $state<JournalPayload | null>(null);
	let sessions = $state<SessionsPayload | null>(null);
	let filter = $state<'all' | 'replay'>('all');
	let q = $state('');
	let since = $state('2026-07-15');
	let all = $state(false);
	let error = $state('');
	const usd = (v: number | null | undefined) => (v == null ? '—' : ((v > 0 ? '+' : '') + v.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' $'));
	const cls = (v: number) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
	const px = (v: number | null) => (v == null ? '—' : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 }));
	const date = (ts: number | null) => (!ts ? '—' : new Date(ts * 1000).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }));
	const pf = (st: TradeStats) => (!st.count ? '—' : st.profit_factor_inf ? '∞' : st.profit_factor == null ? '—' : st.profit_factor.toFixed(2));
	const rows = $derived((data?.trades ?? []).filter((t) => (filter === 'all' || t.source === filter) && (!q || (t.symbol || '').toLowerCase().includes(q.toLowerCase()))));
	async function load() {
		error = '';
		try {
			const [j, s] = await Promise.all([JournalApi.unified({ since: all ? undefined : Date.parse(since + 'T00:00:00') / 1000, all }), JournalApi.sessions().catch(() => null)]);
			data = j; sessions = s;
		} catch (e) { error = (e as Error).message; }
	}
	onMount(() => { void load(); });
</script>

<div class="wrap">
	<div class="ctrls">
		<h1>📓 Journal de trading</h1>
		<label class="field">Depuis <input type="date" bind:value={since} onchange={() => { all = false; void load(); }} /></label>
		<button class="btn" class:on={all} onclick={() => { all = !all; void load(); }}>Tout l'historique</button>
		<input class="search" type="search" placeholder="filtrer symbole…" bind:value={q} />
		<button class="btn" onclick={load}>↻ Rafraîchir</button>
	</div>
	<div class="chips">
		<button class="chip" class:on={filter === 'all'} onclick={() => (filter = 'all')}>Tout</button>
		<button class="chip" class:on={filter === 'replay'} onclick={() => (filter = 'replay')}>🎬 Replay</button>
	</div>
	{#if error}<div class="warn">Erreur de chargement : {error}</div>{/if}
	{#if data}
		<div class="cards">
			{#each [['Compte d’entraînement', data.overall]] as [title, st]}
				{@const s = st as TradeStats}
				<div class="card">
					<div class="ttl">{title}</div>
					<div class="pnl {cls(s.total_pnl)}">{usd(s.total_pnl)}</div>
					<div class="grid"><span class="k">Trades</span><span class="v">{s.count}</span><span class="k">Win rate</span><span class="v">{s.count ? s.win_rate + ' %' : '—'}</span><span class="k">Profit factor</span><span class="v">{pf(s)}</span><span class="k">Gagnants</span><span class="v pos">{s.wins}</span><span class="k">Perdants</span><span class="v neg">{s.losses}</span><span class="k">Avg gain</span><span class="v pos">{s.avg_win ? usd(s.avg_win) : '—'}</span><span class="k">Avg perte</span><span class="v neg">{s.avg_loss ? usd(s.avg_loss) : '—'}</span><span class="k">Frais</span><span class="v neg">{s.total_fees ? usd(-s.total_fees) : '—'}</span><span class="k">PnL net</span><span class="v {cls(s.total_pnl_net)}">{usd(s.total_pnl_net)}</span></div>
				</div>
			{/each}
		</div>
		<h2>Sessions enregistrées <span class="muted">· {sessions?.sessions.length ?? 0}</span></h2>
		<div class="tbox"><table class="tbl"><thead><tr><th class="l">#</th><th class="l">Libellé</th><th class="l">Mode</th><th>Période</th><th>Trades</th><th>Win%</th><th>PF</th><th>PnL</th></tr></thead><tbody>
			{#if !sessions?.sessions.length}<tr><td colspan="8" class="empty">Aucune session enregistrée.</td></tr>{/if}
			{#each [...(sessions?.sessions ?? [])].reverse() as s (s.session_id)}<tr><td class="l">{s.session_id}</td><td class="l">{s.label || '(sans nom)'}</td><td class="l"><span class="pill" class:live={s.mode === 'live'} class:replay={s.mode !== 'live'}>Replay</span></td><td>{date(s.first_trade_wall)} → {date(s.last_trade_wall)}</td><td>{s.count}</td><td>{s.win_rate} %</td><td>{pf(s)}</td><td class={cls(s.total_pnl)}>{usd(s.total_pnl)}</td></tr>{/each}
		</tbody></table></div>
		<h2>Tous les trades <span class="muted">· {rows.length} affichés</span></h2>
		<div class="tbox"><table class="tbl"><thead><tr><th class="l">Date</th><th class="l">Source</th><th class="l">Symbole</th><th class="l">Sens</th><th>Taille</th><th>Entrée</th><th>Sortie</th><th>PnL</th><th class="l">Motif</th></tr></thead><tbody>
			{#if !rows.length}<tr><td colspan="9" class="empty">Aucun trade sur ce filtre.</td></tr>{/if}
			{#each rows as t, i (t.source + t.ts + i)}<tr><td class="l">{date(t.ts)}</td><td class="l"><span class="pill {SRC[t.source].cls}">{SRC[t.source].lbl}</span></td><td class="l">{t.symbol || '—'}</td><td class="l" class:pos={t.side === 'LONG'} class:neg={t.side === 'SHORT'}>{t.side || '—'}</td><td>{t.size ?? '—'}</td><td>{px(t.entry)}</td><td>{px(t.exit)}</td><td class={cls(t.pnl)}>{usd(t.pnl)}</td><td class="l">{t.reason || '—'}</td></tr>{/each}
		</tbody></table></div>
		<div class="foot muted">Généré {new Date(data.generated_at * 1000).toLocaleString('fr-FR')} · borne : {data.since ? date(data.since) : 'tout l’historique'} · {data.trades.length} trades chargés.</div>
	{:else if !error}<div class="muted">chargement…</div>{/if}
</div>

<style>
	.wrap{max-width:1180px;margin:0 auto;padding:18px 20px 60px;}
	.ctrls{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap;margin-bottom:10px;} h1{font-size:18px;margin-right:auto;}
	.search{height:30px;background:var(--bg-1);border:1px solid var(--border);color:var(--text-0);border-radius:8px;padding:0 10px;min-width:150px;}
	.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 16px;}
	.cards{display:grid;grid-template-columns:repeat(1,1fr);gap:12px;margin-bottom:22px;} @media(max-width:860px){.cards{grid-template-columns:1fr 1fr;}}
	.ttl{font-size:12px;color:var(--text-1);text-transform:uppercase;letter-spacing:.6px;margin-bottom:10px;} .pnl{font-size:24px;font-weight:700;}
	.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;margin-top:11px;font-size:12px;} .k{color:var(--text-2);} .v{text-align:right;font-variant-numeric:tabular-nums;font-weight:600;}
	h2{font-size:14px;margin:26px 0 10px;color:#cfd6e6;}
	.warn{background:rgba(232,193,74,.09);border:1px solid rgba(232,193,74,.3);color:#e8c14a;border-radius:8px;padding:8px 12px;font-size:12px;margin:10px 0;}
	.pill.real{color:#7fe0b0;border-color:rgba(46,194,126,.5);} .foot{margin-top:24px;border-top:1px solid var(--border);padding-top:12px;font-size:11px;}
</style>
