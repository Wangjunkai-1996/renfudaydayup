<script setup lang="ts">
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { use } from 'echarts/core';
import { computed } from 'vue';
import VChart from 'vue-echarts';

import type { MarketAnnotations, MarketSeriesPoint } from '@/shared/api/types';

const props = defineProps<{
  name: string;
  points: MarketSeriesPoint[];
  annotations?: MarketAnnotations;
}>();

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent]);

const option = computed(() => {
  const points = props.points || [];
  const annotations = props.annotations || {};
  const markLineData = [
    annotations.prev_close ? { yAxis: annotations.prev_close, name: '昨收' } : null,
    annotations.open_price ? { yAxis: annotations.open_price, name: '开盘' } : null,
    annotations.limit_up ? { yAxis: annotations.limit_up, name: '涨停参考' } : null,
    annotations.limit_down ? { yAxis: annotations.limit_down, name: '跌停参考' } : null,
  ].filter(Boolean);

  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' } },
    grid: { left: 24, right: 24, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      axisLabel: { color: '#94a3b8' },
      data: points.map((point) => point.time),
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
    },
    series: [
      {
        name: `${props.name} 价格`,
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#38bdf8', width: 2 },
        areaStyle: { color: 'rgba(56, 189, 248, 0.12)' },
        data: points.map((point) => point.price),
        markLine: markLineData.length > 0 ? {
          symbol: 'none',
          lineStyle: { type: 'dashed', color: 'rgba(226, 232, 240, 0.25)' },
          label: { color: '#cbd5e1' },
          data: markLineData,
        } : undefined,
      },
      {
        name: 'VWAP',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f59e0b', width: 1.5 },
        data: points.map((point) => point.vwap),
      },
    ],
  };
});
</script>

<template>
  <VChart :option="option" autoresize class="h-[360px] w-full" />
</template>
