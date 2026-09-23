<script lang="ts">
 import {onMount} from 'svelte';
 import {get} from 'svelte/store';
 import {LineStyle,type IChartApi,type IPriceLine} from 'lightweight-charts';
 import type {ChartController} from '../ChartController';
 import type {GexLevel} from '$replay/domain/market/types';
 import {gamma} from '$replay/application/GammaStore';
 import {chartSettings} from '$replay/application/ChartSettings';
 let {chart,controller}:{chart:IChartApi;controller:ChartController}=$props();
 onMount(()=>{
  let lines:IPriceLine[]=[],level:GexLevel|null=null;
  const clear=()=>{for(const line of lines){try{controller.candle.removePriceLine(line);}catch{}}lines=[];};
  const draw=()=>{clear();if(!get(chartSettings).gexLines||!level)return;
   for(const [key,label,color] of [['cw_d','CW','#ef7777'],['pw_d','PW','#44c89d'],['fl_d','FL','#e8c14a']] as const){
    const distance=level[key];if(distance==null)continue;
    const price=level.spot*(1+distance);if(!Number.isFinite(price)||price<=0)continue;
    lines.push(controller.candle.createPriceLine({price,color,lineWidth:1,lineStyle:LineStyle.Dashed,axisLabelVisible:true,title:label+' ≈'}));
   }
  };
  const offGamma=gamma.subscribe(state=>{level=state.symbol===controller.symbol ? state.level : null;draw();});
  const offSettings=chartSettings.subscribe(draw);
  return()=>{offGamma();offSettings();clear();};
 });
</script>
