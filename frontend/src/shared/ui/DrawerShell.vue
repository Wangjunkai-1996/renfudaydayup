<script setup lang="ts">
defineProps<{ open: boolean; title: string; subtitle?: string }>();
defineEmits<{ (event: 'close'): void }>();
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm" @click.self="$emit('close')">
      <div class="h-full w-full max-w-2xl overflow-y-auto border-l border-slate-800 bg-slate-950 p-6 shadow-2xl">
        <div class="flex items-start justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <div class="text-xl font-semibold text-white">{{ title }}</div>
            <div v-if="subtitle" class="mt-1 text-sm text-slate-400">{{ subtitle }}</div>
          </div>
          <button class="rounded-2xl border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" @click="$emit('close')">关闭</button>
        </div>
        <div class="pt-5">
          <slot />
        </div>
      </div>
    </div>
  </teleport>
</template>
