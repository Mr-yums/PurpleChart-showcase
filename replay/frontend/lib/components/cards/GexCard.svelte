<script lang="ts">
 import {gamma} from '$replay/application/GammaStore';
 const level = $derived($gamma.level);
 const when = $derived(level ? new Date(level.time * 1000).toISOString().slice(0,16).replace('T',' ') + ' UTC' : '');
</script>
<div class="gx" aria-live="polite">
 <div class="regime" style:color={level?.regime === 'RANGE' ? '#26a66a' : level ? '#e0524b' : '#888'}>{level?.regime ?? '—'}</div>
 <div class="detail">
 {#if $gamma.phase === 'idle'}Choisis et charge une séance.
 {:else if $gamma.phase === 'unsupported'}Gamma disponible sur NQ et MNQ, pas sur {$gamma.symbol}.
 {:else if $gamma.phase === 'error'}Impossible de charger le gamma. <button class="btn" onclick={() => gamma.refresh(true)}>Réessayer</button>
 {:else if $gamma.phase === 'loading' && !level}Chargement du gamma {$gamma.symbol}…
 {:else if !level}Aucun relevé gamma exploitable avant cette heure pour {$gamma.symbol}.
 {:else}{$gamma.symbol} · {level.netGamma >= 0 ? 'Gamma net positif' : 'Gamma net négatif'} · niveaux projetés sur le future
 {/if}
 </div>
 {#if level}<div class="when mono">{$gamma.stale ? 'Dernier relevé antérieur' : 'Relevé'} · {when}</div>{/if}
</div>
<style>
	.gx{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:6px 0;}
	.regime{font-size:30px;font-weight:700;letter-spacing:2px;font-family:var(--mono);}
	.detail{font-size:11px;color:var(--text-1);text-align:center;} .when{font-size:10px;color:var(--text-2);}
</style>
