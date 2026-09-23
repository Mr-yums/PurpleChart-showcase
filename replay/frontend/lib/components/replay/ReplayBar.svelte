<script lang="ts">
	// Barre de contrôle du replay : séance + heure UTC, charger, lecture/pause, vitesse,
	// démo live, tag d'edge, horloge marché et état. Le statut vient du WebSocket (aucun sondage).
    import { onMount } from 'svelte';
    import Icon from '$replay/components/ui/Icon.svelte'; // [Sol]
    import { api } from '$replay/api/client';
	import { replay } from '$replay/application/ReplayStore';
	import { desk } from '$replay/application/PaperDesk';
	import RegimeCatalog from './RegimeCatalog.svelte';
	import type { SessionInfo } from '$replay/domain/market/types';

	const status = replay.status;
    const selection = replay.selection; // [Sol] Seed the session selector from the current symbol.
    let seeded = false, loadedKey = "";
	const sessionsStore = replay.sessions;
	const message = replay.message;
	let sessionIdx = $state(0);
	let time = $state('15:30');
	let speed = $state(5);
	let catalog = $state(false);
    let loading = $state(false);
    let checkpoint = $state<{symbol:string;cursor:number}|null>(null);
    onMount(()=>{void api.get<{checkpoint:{symbol:string;cursor:number}|null}>('/replay/checkpoint').then(r=>checkpoint=r.checkpoint).catch(()=>{});});
    async function resume(){loading=true;try{await api.post('/replay/resume');}catch(e){replay.message.set(String(e));}finally{loading=false;}}

	const sessions = $derived([...$sessionsStore].reverse());
	const clock = $derived($status.loaded ? new Date($status.cursor_ts * 1000) : null);
	const stateLabel = $derived(!$status.loaded ? 'aucune séance chargée' : $status.ended ? 'fin des données' : $status.buffering ? 'lecture… (chargement)' : $status.playing ? `lecture ×${$status.speed}` : 'pause');
	const stateColor = $derived(!$status.loaded ? 'var(--text-2)' : $status.ended ? '#ff8080' : $status.playing ? '#7fdc9a' : '#ffd479');

	async function load() {
		const s: SessionInfo | undefined = sessions[sessionIdx];
		if (!s) return;
		const [hh, mm] = (time || '15:30').split(':').map(Number);
        loading=true;
        try { await replay.load(s, hh, mm, speed); } finally { loading=false; }
	}
	async function onSpeed() { await replay.speed(speed); }
	function pickSession(symbol: string, ts: number, source?: string) {
		const i = sessions.findIndex((s) => s.symbol === symbol && (!source || s.source === source) && ts >= Math.floor(s.first_ts / 300) * 300 && ts <= s.last_ts);
		if (i < 0) { replay.message.set('séance absente de l’archive'); return; }
		sessionIdx = i;
		time = new Date(ts * 1000).toISOString().slice(11, 16);
		catalog = false;
		void load();
	}
	$effect(() => { if ($status.loaded && $status.speed) speed = $status.speed; });
    // [Sol] Follow a newly loaded session, without overwriting the user's next choice on every heartbeat.
    $effect(()=>{
        if(!seeded&&sessions.length){
            const i=sessions.findIndex(s=>s.symbol===(checkpoint?.symbol??$selection.symbol));
            sessionIdx=Math.max(0,i);seeded=true;
        }
        if(!$status.loaded)return;
        const key=$status.symbol+':'+$status.context_start;
        if(key===loadedKey)return;
        loadedKey=key;
        const i=sessions.findIndex(s=>s.symbol===$status.symbol&&$status.cursor_ts>=s.first_ts&&$status.cursor_ts<=s.last_ts+1);
        if(i>=0)sessionIdx=i;
        time=new Date($status.cursor_ts*1000).toISOString().slice(11,16);
    });

</script>

<svelte:window onkeydown={(e)=>{if(e.key==='Escape')catalog=false;}} />
<div class="replay-bar">
 <div class="session-row">
  <label class="field session-field">Séance
   <select bind:value={sessionIdx} aria-label="Séance à charger">
    {#each sessions as s,i (s.symbol+s.session_start+s.source)}<option value={i}>{s.symbol} · {s.date} · {s.source==='v2'?'V2':'Archive'}</option>{/each}
   </select>
  </label>
  <label class="field time-field">Départ · UTC <input type="time" bind:value={time} step="60" /></label>
  <button class="btn primary load" onclick={load} disabled={loading||!sessions.length} aria-busy={loading}>{loading?'Préparation…':'Charger'}</button>
  {#if checkpoint&&!$status.loaded}<button class="btn resume" disabled={loading} onclick={resume}><Icon name="resume"/> Reprendre {checkpoint.symbol}</button>{/if}
  <div class="session-actions">
   <button class="btn" class:on={catalog} aria-expanded={catalog} onclick={()=>catalog=!catalog}><Icon name="calendar"/> Séances & régimes</button>
  </div>
 </div>
 <div class="transport-row">
  <div class="transport">
   <button class="btn play" class:playing={$status.playing&&!$status.ended} disabled={loading||!$status.loaded||$status.ended} onclick={()=>replay.toggle()} title="Lecture / pause"><Icon name={$status.playing&&!$status.ended?'pause':'play'}/><span>{$status.playing&&!$status.ended?'Pause':'Lecture'}</span></button>
   <select class="speed" bind:value={speed} onchange={onSpeed} aria-label="Vitesse de lecture" disabled={loading}>{#each [0.5,1,2,5,10,25,50] as v}<option value={v}>{v}×</option>{/each}</select>
  </div>
  <div class="market-time"><span class="clock mono">{clock?clock.toLocaleTimeString('fr-FR'):'— : — : —'}</span><span class="market-date">{clock?clock.toLocaleDateString('fr-FR'):'Choisis une séance'}</span></div>
  <span class="state" class:active={$status.playing} style:color={stateColor}><span class="state-dot"></span>{loading?'Préparation':stateLabel}</span>
  <div class="context-actions">
   <label class="tag-field"><span>Setup</span><select value={$desk.tag??''} aria-label="Tag du setup" onchange={e=>desk.setTag(e.currentTarget.value.toLowerCase()||null)}><option value="">Aucun</option><option value="FIGURE">Figure</option><option value="VP">Volume profile</option></select></label>
  </div>
 </div>
 {#if $message}<div class="feedback" role="status">{$message}</div>{/if}
 {#if catalog}<RegimeCatalog onpick={pickSession} onclose={()=>catalog=false}/>{/if}
</div>
<style>
 .replay-bar{position:relative;border:1px solid var(--border);border-radius:12px;background:var(--bg-1);z-index:25;flex-shrink:0;}
 .session-row{display:flex;align-items:flex-end;gap:10px;padding:12px 16px;flex-wrap:wrap;}
 .session-field{flex:1;min-width:200px;max-width:330px}.time-field{width:116px}.field select,.field input{width:100%;min-width:0}
 .session-actions{margin-left:auto;display:flex;align-items:center;gap:8px}
 .transport-row{display:flex;align-items:center;gap:18px;flex-wrap:wrap;border-top:1px solid var(--border-soft);padding:9px 16px;background:color-mix(in srgb,var(--bg-0) 40%,transparent);border-radius:0 0 12px 12px;}
 .transport{display:flex;align-items:center;padding:3px;border:1px solid var(--border);border-radius:9px;background:var(--bg-0);gap:3px}.transport .play{height:30px;min-width:96px;border-color:transparent;background:var(--bg-3);color:var(--text-0)}.transport .play.playing{color:#c5adf3;background:#a06bff20;}
 .speed{height:30px;min-width:61px;background:transparent;border:0;border-left:1px solid var(--border);color:var(--text-1);padding:0 7px;cursor:pointer;font-size:12px;}
 .market-time{display:flex;align-items:baseline;gap:10px}.clock{font-size:16px;font-weight:600;letter-spacing:.03em;color:var(--text-0)}.market-date{font-size:11px;color:var(--text-2)}
 .state{display:flex;align-items:center;gap:6px;font-size:11px;white-space:nowrap}.state-dot{width:5px;height:5px;background:currentColor;border-radius:50%;opacity:.8}
 .context-actions{display:flex;align-items:center;gap:14px;margin-left:auto}.tag-field{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-2)}.tag-field select{max-width:104px;background:var(--bg-1);color:var(--text-1);border:1px solid var(--border);border-radius:7px;height:30px;padding:0 7px;font-size:11px}
 .feedback{padding:9px 16px;font-size:12px;color:var(--text-1);border-top:1px solid var(--border-soft)}
 @media(max-width:1350px){.session-row{gap:8px;padding:10px 12px}.transport-row{gap:12px;padding:8px 12px}.market-date{display:none}.session-field{max-width:280px}}
 @media(max-width:1050px){.resume{order:3}.session-actions{flex:1;justify-content:flex-end}.state{display:none}.context-actions{gap:8px}.tag-field>span{display:none}}
 @media(max-width:650px){.session-actions{width:100%;justify-content:space-between}.session-field{max-width:none}.context-actions{width:100%;justify-content:space-between}.market-date{display:inline}.transport-row{gap:10px}.session-row .resume{order:0}}
</style>
