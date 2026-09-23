<script lang="ts">
 // [Sol] PurpleChart V2 visual hierarchy, OXIO replay tools and simulated account only.
 import {onMount} from 'svelte';
 import SortableCards from '$replay/components/layout/SortableCards.svelte';
 import Icon from '$replay/components/ui/Icon.svelte';
 import ReplayBar from '$replay/components/replay/ReplayBar.svelte';
 import ChartToolbar from '$replay/components/chart/ChartToolbar.svelte';
 import Chart from '$replay/components/chart/Chart.svelte';
 import Tape from '$replay/components/tape/Tape.svelte';
 import Dom from '$replay/components/dom/Dom.svelte';
 import Wallet from '$replay/components/wallet/Wallet.svelte';
 import OrderTicket from '$replay/components/orders/OrderTicket.svelte';
 import GexCard from '$replay/components/cards/GexCard.svelte';
 import SessionsCard from '$replay/components/cards/SessionsCard.svelte';
 import Journal from './pages/journal.svelte';
 import Pnl from './pages/pnl.svelte';
 import {replay} from '$replay/application/ReplayStore';
 import {gamma} from '$replay/application/GammaStore';
 const selection=replay.selection;
 let ready=$state(false), view=$state('chart');
 onMount(()=>{gamma.start();let alive=true;void replay.init().then(()=>{if(alive)ready=true;});return()=>{alive=false;gamma.stop();replay.stop();};});
</script>
<div class="workspace">
 <div class="workspace-heading"><div class="workspace-title"><span class="mode-dot"></span><h1>Purple Replay</h1><span class="mode-label">Entraînement</span></div><nav class="feature-nav" aria-label="Vues du replay"><button class="view-tab" class:on={view==='chart'} aria-current={view==='chart'?'page':undefined} onclick={()=>view='chart'}><Icon name="chart"/>Graphique</button><button class="view-tab" class:on={view==='journal'} aria-current={view==='journal'?'page':undefined} onclick={()=>view='journal'}><Icon name="journal"/>Journal</button><button class="view-tab" class:on={view==='pnl'} aria-current={view==='pnl'?'page':undefined} onclick={()=>view='pnl'}><Icon name="performance"/>Performance</button></nav><span class="simulation-badge">Simulation</span></div>
 <ReplayBar />
 {#if !ready}<div class="card">Chargement des séances…</div>
 {:else if view==='journal'}<Journal />
 {:else if view==='pnl'}<Pnl />
 {:else}
 <div class="replay-grid">
  <section class="card chart-card">
   <ChartToolbar />
   <div class="chart-box">
    {#key $selection.symbol+$selection.tf}<Chart symbol={$selection.symbol} timeframe={$selection.tf} />{/key}

   </div>
  </section>
  {#snippet orderCard()}{#key $selection.symbol}<OrderTicket symbol={$selection.symbol}/>{/key}{/snippet}
  {#snippet walletCard()}<Wallet />{/snippet}
  {#snippet gammaCard()}<GexCard />{/snippet}
  {#snippet tapeCard()}<div class="tape-box"><Tape /></div>{/snippet}
  {#snippet domCard()}<details><summary>Afficher les volumes exécutés</summary><div class="dom-box"><Dom /></div></details>{/snippet}
  {#snippet sessionsCard()}<SessionsCard />{/snippet}
  <SortableCards cards={[
   {id:'order',title:`Ordre simulé · ${$selection.symbol}`,content:orderCard},
   {id:'wallet',title:'Compte d’entraînement',content:walletCard},
   {id:'gamma',title:'Gamma historique',content:gammaCard},
   {id:'tape',title:`Tape — ${$selection.symbol}`,content:tapeCard},
   {id:'dom',title:'DOM · volumes exécutés',content:domCard},
   {id:'sessions',title:'Sessions d’entraînement',content:sessionsCard}
  ]} />
 </div>
 {/if}
</div>
<style>
 .workspace{display:flex;flex-direction:column;gap:12px;height:100%;min-height:0;}
 .workspace-heading{display:flex;align-items:center;gap:24px;min-height:34px;flex-shrink:0}.workspace-title{display:flex;align-items:center;gap:9px}.workspace-title h1{font-size:17px;font-weight:600;letter-spacing:-.02em}.mode-dot{width:6px;height:6px;background:var(--accent);border-radius:50%}.mode-label{color:var(--text-2);font-size:11px;margin-left:3px}
 .feature-nav{display:flex;align-items:center;gap:2px;padding:3px;background:var(--bg-1);border:1px solid var(--border-soft);border-radius:8px}.view-tab{display:flex;align-items:center;gap:7px;padding:6px 12px;background:transparent;border:0;border-radius:5px;font:inherit;font-size:11px;color:var(--text-2);cursor:pointer}.view-tab:hover{color:var(--text-0)}.view-tab.on{background:var(--bg-3);color:var(--text-0)}
 .simulation-badge{margin-left:auto;text-transform:uppercase;letter-spacing:.12em;font-size:9px;color:var(--text-2)}
 .replay-grid{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:14px;flex:1;min-height:280px;}
 .chart-card{min-width:0;display:flex;flex-direction:column;min-height:0;padding:0;overflow:visible;}.chart-box{position:relative;flex:1;min-height:180px;overflow:hidden;border-radius:0 0 12px 12px;}
 .tape-box{height:230px;overflow:hidden}.dom-box{height:320px;position:relative;}summary{color:var(--text-1);cursor:pointer;font-size:12px}
 @media(max-width:1400px){.replay-grid{grid-template-columns:minmax(0,1fr) 285px;gap:12px}.mode-label{display:none}.workspace-heading{gap:18px}.view-tab{padding:6px 10px}}
 @media(max-width:850px){.replay-grid{grid-template-columns:minmax(0,1fr)}.chart-card{height:480px;min-height:480px}.workspace{height:auto}.workspace-heading{gap:8px;flex-wrap:wrap}.simulation-badge{display:none}.workspace-title{margin-right:auto}}
</style>
