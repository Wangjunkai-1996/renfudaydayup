<script setup lang="ts">
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { use } from 'echarts/core';
import { computed } from 'vue';
import VChart from 'vue-echarts';

const props = defineProps<{ items: Array<{ symbol: string; change_pct: number }> }>();

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

const option = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  grid: { left: 24, right: 12, top: 16, bottom: 24 },
  xAxis: {
    type: 'category',
    axisLabel: { color: '#94a3b8' },
    data: props.items.map((item) => item.symbol),
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#94a3b8', formatter: '{value}%' },
    splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } },
  },
  series: [
    {
      type: 'bar',
      data: props.items.map((item) => ({
        value: item.change_pct,
        itemStyle: { color: item.change_pct >= 0 ? '#34d399' : '#fb7185' },
      })),
      barWidth: 20,
      borderRadius: [8, 8, 0, 0],
    },
  ],
}));
</script>

<template>
  <VChart :option="option" autoresize class="h-72 w-full" />
</template>
