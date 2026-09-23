<script lang="ts">
	// Sessions d'entraînement : tally cumulé, session en cours (trades non sauvegardés), clôture avec libellé.
	import { onMount } from 'svelte';
	import { JournalApi } from '$replay/api/journal';
	import { market } from '$replay/application/MarketStore';
	import type { SessionsPayload } from '$replay/domain/market/types';
	let data = $state<SessionsPayload | null>(null);
	let label = $state('');
	let busy = $state(false);
	let msg = $state('');
	const money = (v: number | null | undefined) => v == null || Number.isNaN(v) ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(0) + ' $';
	const col = (v: number) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
	async function refresh() { try { data = await JournalApi.sessions(); } catch { /* silencieux */ } }
	async function save() {
		busy = true; msg = '';
		try { const r = await JournalApi.save(label); msg = r.ok && r.session ? `✅ Session #${r.session.session_id} : ${money(r.session.total_pnl)} · ${r.session.count} trades · ${r.session.win_rate}% WR` : '⚠️ ' + (r.message || 'rien à sauvegarder'); label = ''; }
		catch (e) { msg = 'Erreur : ' + (e as Error).message; }
		busy = false; await refresh();
	}
	onMount(() => { void refresh(); const off = market.positions.subscribe(() => { void refresh(); }); return off; });
</script>

<div class="sc">
	{#if data}
		<div class="big {col(data.aggregate.total_pnl)}">{money(data.aggregate.total_pnl)}</div>
		<div class="muted">{data.aggregate.sessions} session(s) · {data.aggregate.total_trades} trades cumulés</div>
		<div class="row"><span>Win rate global</span><b>{data.aggregate.win_rate}% ({data.aggregate.wins}W/{data.aggregate.losses}L)</b></div>
		<div class="row"><span>Sessions gagnantes</span><b>{data.aggregate.winning_sessions} / {data.aggregate.sessions}</b></div>
		<div class="pend">{#if data.pending.count && data.pending.stats}Session en cours : <b class={col(data.pending.stats.total_pnl)}>{money(data.pending.stats.total_pnl)}</b> · {data.pending.count} trades · {data.pending.stats.win_rate}% WR{:else}Session en cours : aucun trade non sauvegardé.{/if}</div>
		<div class="save"><input placeholder="libellé (optionnel)" bind:value={label} /><button class="btn primary" disabled={busy || !data.pending.count} onclick={save}>💾 Clôturer</button></div>
		{#if msg}<div class="muted">{msg}</div>{/if}
		<div class="hist">{#each [...data.sessions].reverse().slice(0, 8) as s (s.session_id)}<div class="hi"><span>#{s.session_id} {new Date(s.saved_at_wall * 1000).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })} ({s.count}t){s.label ? ' · ' + s.label : ''}</span><b class={col(s.total_pnl)}>{money(s.total_pnl)}</b></div>{/each}</div>
	{:else}<div class="muted">chargement…</div>{/if}
</div>

<style>
	.sc{display:flex;flex-direction:column;gap:6px;font-size:12px;}
	.big{font-size:24px;font-weight:800;} .row{display:flex;justify-content:space-between;color:var(--text-1);} .row b{color:var(--text-0);}
	.pend{padding:7px 9px;background:rgba(90,110,150,.12);border:1px solid var(--border);border-radius:8px;font-size:11.5px;color:var(--text-1);}
	.save{display:flex;gap:6px;} .save input{flex:1;min-width:0;background:var(--bg-0);color:var(--text-0);border:1px solid var(--border);border-radius:7px;padding:0 8px;height:30px;}
	.hist{max-height:118px;overflow:auto;font-size:11px;} .hi{display:flex;justify-content:space-between;padding:3px 0;border-top:1px solid var(--border-soft);color:var(--text-1);}
</style>
