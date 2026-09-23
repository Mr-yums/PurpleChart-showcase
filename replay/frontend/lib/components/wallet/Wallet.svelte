<script lang="ts">
 import {onDestroy} from 'svelte';
 import {market} from '$replay/application/MarketStore';
 import {replay} from '$replay/application/ReplayStore';
 import {desk} from '$replay/application/PaperDesk';
 import {accountValue} from '$replay/domain/account/valuation';
 const account=market.account, positions=market.positions, last=market.lastPrice, selection=replay.selection;
 const value=$derived(accountValue($account,$positions,$last,$selection.symbol));
 const fmt=(n:number|null|undefined)=>n==null||!Number.isFinite(n)?'—':n.toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' $';
 const signed=(n:number|null|undefined)=>n==null?'—':(n>=0?'+':'')+fmt(n);
 let confirming=$state(false);
 let confirmTimer:ReturnType<typeof setTimeout>;
 onDestroy(()=>clearTimeout(confirmTimer));
 async function reset(){if(!confirming){confirming=true;confirmTimer=setTimeout(()=>confirming=false,4000);return;}confirming=false;await desk.reset();}
</script>
<div class="wallet">
 <div class="wc-head"><span class="muted">Compte simulé</span><button class="btn" class:armed={confirming} onclick={reset} title="Réinitialiser le compte simulé">{confirming?'Confirmer ?':'↻ Réinitialiser'}</button></div>
 <div class="wc-total"><small>{value.hasPosition?'Valeur actuelle estimée':'Solde du compte'}</small><strong>{fmt(value.equity)}</strong><span>{value.hasPosition?'Solde + gain/perte de la position ouverte':'Aucune position ouverte'}</span></div>
 <div class="wc-grid">
  {#if value.hasPosition}
   <div><small>Solde après clôtures</small><b>{fmt($account?.balance)}</b></div>
   <div><small>Gain/perte en cours</small><b class:pos={value.unrealized!=null&&value.unrealized>=0} class:neg={value.unrealized!=null&&value.unrealized<0}>{signed(value.unrealized)}</b>{#if value.unrealized===null}<span>Prix indisponible</span>{/if}</div>
  {/if}
  <div><small>Résultat clôturé net</small><b class:pos={($account?.realized_net??0)>=0} class:neg={($account?.realized_net??0)<0}>{signed($account?.realized_net)}</b></div>
  <div><small>Frais déjà comptabilisés</small><b>{fmt($account?.fees_total)}</b></div>
 </div>
 <details class="wc-help"><summary>Comprendre les montants</summary><p>Départ : {fmt($account?.starting_balance)}. Le solde intègre les trades clôturés et leurs frais. La valeur actuelle, aussi appelée équité, ajoute le gain ou la perte provisoire de la position ouverte. Sans position, elle est égale au solde. Les frais affichés sont déjà déduits du résultat clôturé.</p></details>
</div>
<style>
 .wallet{display:flex;flex-direction:column;gap:10px}.wc-head{display:flex;align-items:center;gap:8px;font-size:11px}.wc-head .btn{margin-left:auto;padding:4px 8px;font-size:11px}.wc-total{padding:12px;border:1px solid var(--border);border-radius:9px;background:var(--bg-0)}.wc-total strong{display:block;font-size:24px;margin:5px 0;font-variant-numeric:tabular-nums}.wc-total small,.wc-grid small{display:block;color:var(--text-2);font-size:10px}.wc-total span,.wc-grid span{display:block;font-size:11px;color:var(--text-1)}.wc-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.wc-grid>div{border:1px solid var(--border);border-radius:8px;padding:7px 9px;background:var(--bg-0);min-width:0}.wc-grid b{display:block;margin-top:4px;font-size:14px;font-variant-numeric:tabular-nums}.wc-help{font-size:11px;color:var(--text-2)}.wc-help summary{cursor:pointer}.wc-help p{padding-top:8px;line-height:1.5}
</style>
