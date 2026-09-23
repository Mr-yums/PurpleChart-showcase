<script lang="ts">
 // [Sol] Keep the chart controls compact; expose the full existing studies in a dedicated panel.
 import {replay} from '$replay/application/ReplayStore';
 import {chartSettings} from '$replay/application/ChartSettings';
 import {vpTool} from '$replay/application/VpTool';
 import Icon from '$replay/components/ui/Icon.svelte';
 const sel=replay.selection,instruments=replay.instruments,timeframes=replay.timeframes,armed=vpTool.armed;
 let expanded=$state(false);
</script>
<svelte:window onkeydown={e=>{if(e.key==='Escape')expanded=false;}}/>
<div class="toolbar">
 <div class="chart-controls">
  <label class="symbol-control"><span class="symbol-dot"></span><select aria-label="Symbole du graphique" value={$sel.symbol} onchange={e=>replay.select(e.currentTarget.value,$sel.tf)}>{#each $instruments as i (i.symbol)}<option value={i.symbol}>{i.symbol}</option>{/each}</select></label>
  <div class="tfs" aria-label="Période du graphique">{#each $timeframes as tf (tf)}<button class="tf" class:on={$sel.tf===tf} aria-pressed={$sel.tf===tf} onclick={()=>replay.select($sel.symbol,tf)}>{tf}</button>{/each}</div>
  <div class="study-actions"><button class="btn measure" class:on={$armed} onclick={()=>vpTool.arm()} title="Tracer un profil de volume de mesure"><Icon name="measure"/><span>{$armed?'Tracer sur le cours':'VP mesure'}</span></button><button class="btn studies" class:on={expanded} aria-expanded={expanded} aria-controls="replay-study-settings" onclick={()=>expanded=!expanded}><Icon name="sliders"/> Indicateurs</button></div>
 </div>
 {#if expanded}
 <section class="study-panel" id="replay-study-settings" aria-label="Réglages du graphique">
  <div class="panel-heading"><div><strong>Indicateurs & affichage</strong><p>Adapte la lecture du marché à ton exercice.</p></div><button class="btn icon-button" aria-label="Fermer les indicateurs" onclick={()=>expanded=false}><Icon name="close"/></button></div>
  <div class="filter-grid">
   <fieldset class="wide"><legend>Études sur le graphique</legend><div class="options"><label><input type="checkbox" checked={$chartSettings.profile} onchange={()=>chartSettings.update({profile:!$chartSettings.profile})}/> Profil de séance</label><label><input type="checkbox" checked={$chartSettings.gexLines} onchange={()=>chartSettings.update({gexLines:!$chartSettings.gexLines})}/> Niveaux GEX</label></div></fieldset>
  </div>
  <div class="panel-footer"><label class="field">Représentation<select value={$chartSettings.style} onchange={e=>chartSettings.update({style:e.currentTarget.value as 'candles'|'line'})}><option value="candles">Bougies</option><option value="line">Ligne</option></select></label><button class="btn quiet clear-vp" onclick={()=>vpTool.clear()}>Effacer les VP de mesure</button></div>
 </section>
 {/if}
</div>
<style>
 .toolbar{position:relative;z-index:22;flex-shrink:0;border-bottom:1px solid var(--border-soft);padding:10px 12px;}
 .chart-controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-width:0;}
 .symbol-control{display:flex;align-items:center;gap:8px;min-width:100px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding-left:10px;}.symbol-control select{height:32px;background:transparent;color:var(--text-0);font-size:12px;font-weight:600;border:0;max-width:110px;padding-right:7px;cursor:pointer}.symbol-dot{width:5px;height:5px;background:var(--accent);border-radius:50%;}
 .tfs{display:flex;gap:2px;align-items:center;flex-wrap:wrap}.tf{height:28px;min-width:30px;padding:0 6px;background:transparent;border:1px solid transparent;color:var(--text-2);border-radius:6px;font-size:11px;font-weight:500;cursor:pointer}.tf:hover{color:var(--text-0);background:var(--bg-2)}.tf.on{color:#d6c3fa;background:#a06bff20;border-color:#a06bff35}
 .study-actions{display:flex;align-items:center;gap:6px;margin-left:auto}.study-actions .btn{height:32px;padding:0 9px;font-size:11px;}
 .study-panel{position:absolute;right:10px;top:calc(100% + 6px);width:min(620px,calc(100% - 20px));max-height:min(540px,70vh);overflow:auto;padding:20px;background:var(--bg-1);border:1px solid #484055;border-radius:12px;box-shadow:0 18px 60px #0008;}
 .panel-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:20px}.panel-heading strong{font-size:14px;font-weight:600}.panel-heading p{font-size:11px;color:var(--text-2);margin:5px 0 0}
 .filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px 24px}.wide{grid-column:1/-1}fieldset{margin:0;padding:0;border:0;min-width:0}legend{padding:0;margin-bottom:10px;font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--text-2)}.options{display:flex;gap:12px 16px;flex-wrap:wrap}.options label{display:flex;align-items:center;gap:6px;color:var(--text-1);font-size:12px;cursor:pointer}.options input{accent-color:var(--accent);width:14px;height:14px;margin:0}
 .panel-footer{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;padding-top:18px;margin-top:20px;border-top:1px solid var(--border-soft)}.panel-footer .field{flex:1}.panel-footer .field select{width:100%}.clear-vp{width:100%;justify-content:flex-start!important;padding-left:0!important}
 @media(max-width:1400px){.measure span{display:none}.chart-controls{gap:8px}.study-actions{gap:5px}}
 @media(max-width:1050px){.tfs{order:3;flex-basis:100%}.study-panel{padding:16px}.filter-grid{gap:18px}}
</style>
