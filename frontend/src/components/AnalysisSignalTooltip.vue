<script setup lang="ts">
import AppTooltip from './AppTooltip.vue'

defineProps<{
  reasons: string[]
}>()
</script>

<template>
  <AppTooltip
    id="lot-analysis-tooltip"
    trigger-class="signal-tooltip-trigger"
    :trigger-attrs="{
      tabindex: 0,
      'aria-label': 'Показать причины сигнала',
    }"
    surface-class="rating-info-tooltip signal-info-tooltip"
  >
    <template #trigger>
      <slot />
    </template>

    <section>
      <strong>Почему такой сигнал</strong>
      <ul v-if="reasons.length">
        <li v-for="reason in reasons" :key="reason">{{ reason }}</li>
      </ul>
      <p v-else>Нет пояснений от модели.</p>
    </section>
  </AppTooltip>
</template>
