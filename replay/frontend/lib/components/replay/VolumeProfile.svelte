<script lang="ts">
 import type {VolumeProfile} from '$replay/domain/market/types';
 let {profile, label}: {profile: VolumeProfile | null | undefined; label: string} = $props();
 const max = $derived(Math.max(1, ...(profile?.bins ?? [])));
 const span = $derived(profile ? profile.high - profile.low : 0);
 const price = (v: number) => v.toLocaleString('fr-FR', {maximumFractionDigits: 2});
</script>
{#if profile && profile.bins.length}
 {@const y = span ? Math.max(1,Math.min(63,64 - (profile.poc-profile.low)/span*64)) : 32}
 <figure class="profile">
  <svg viewBox="0 0 120 64" role="img" aria-label={`${label} : POC ${price(profile.poc)}, zone de valeur ${price(profile.val)} à ${price(profile.vah)}`}>
   <title>{label} · volumes enregistrés · zone de valeur 70 %</title>
   {#each profile.bins as volume, i}
    {@const mid = profile.low + (i + 0.5) * span / profile.bins.length}
    <rect x="0" y={64 - (i + 1) * 64 / profile.bins.length} width={volume / max * 118} height={Math.max(0.5,64 / profile.bins.length - 0.4)} fill={mid >= profile.val && mid <= profile.vah ? '#a47cec' : '#555b71'} />
   {/each}
   <line x1="0" x2="120" y1={y} y2={y} stroke="#e8c14a" stroke-width="1.5" />
  </svg>
  <figcaption><span>POC {price(profile.poc)}</span><span>VA {price(profile.val)} – {price(profile.vah)}</span></figcaption>
 </figure>
{:else}<span class="missing">Profil indisponible</span>{/if}
<style>
 .profile{display:flex;align-items:center;gap:10px;margin:0;min-width:0;}.profile svg{width:100px;height:54px;flex-shrink:0;border-left:1px solid var(--border);}.profile figcaption{display:flex;flex-direction:column;font-size:10px;color:var(--text-2);font-variant-numeric:tabular-nums;}.profile figcaption span:first-child{color:#e8c14a}.missing{font-size:10px;color:var(--text-2);}
 @media(max-width:650px){.profile svg{width:85px;height:46px;}}
</style>
