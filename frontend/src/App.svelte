<script lang="ts">
import {onMount} from 'svelte';
let ready=$state(false),error=$state('');
onMount(()=>{fetch('/api/replay/status').then(r=>{if(!r.ok)throw Error('Espace temporairement indisponible');ready=true;}).catch(e=>error=e.message);});
import Workspace from '$replay-ui/Workspace.svelte';
import '$replay-ui/replay.css';
import './app.css';
</script>
<svelte:head><title>Purple Replay — Entraînement futures</title></svelte:head>
<div class="shell"><header class="brandbar"><a href="/">P<span>R</span> <strong>Purple Replay</strong></a><span>Marchés historiques · compte simulé</span><a href="/guide.html" target="_blank" rel="noopener">Guide & installation ↗</a></header><main class="replay-root">{#if ready}<Workspace />{:else}<section class="card">{error||'Ouverture de ton espace de replay…'}</section>{/if}</main></div>
