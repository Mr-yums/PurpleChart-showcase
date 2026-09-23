<script lang="ts">
 // [Sol] Shared, lightweight interface icons; no additional library or font.
 let {name,size=16}:{name:'play'|'pause'|'calendar'|'arrow'|'resume'|'sliders'|'close'|'eye'|'eyeOff'|'chart'|'journal'|'performance'|'measure';size?:number}=$props();
 const paths={play:'m8 5 11 7-11 7V5Z',pause:'M8 5v14M16 5v14',calendar:'M8 3v4M16 3v4M4 10h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',arrow:'M4 12h15m-6-6 6 6-6 6',resume:'M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2',sliders:'M4 7h6m4 0h6M4 17h10m4 0h2M10 4v6m4 4v6',close:'m6 6 12 12M6 18 18 6',eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm7 0a3 3 0 1 0 6 0 3 3 0 0 0-6 0',eyeOff:'m3 3 18 18M10 5a12 12 0 0 1 2 0c6 0 10 7 10 7a20 20 0 0 1-3 4M6 6a22 22 0 0 0-4 6s4 7 10 7a12 12 0 0 0 5-1',chart:'M4 4v16h16M7 14l4-5 4 3 5-7',journal:'M5 4h14v17H5V4Zm4 4h6m-6 4h6m-6 4h3',performance:'M5 19v-5m7 5V9m7 10V4',measure:'m4 16 12-12 4 4L8 20l-4-4Zm6-6 2 2m2-6 2 2M6 14l2 2'};
</script>
<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>
<style>svg{flex-shrink:0;vertical-align:middle}</style>
