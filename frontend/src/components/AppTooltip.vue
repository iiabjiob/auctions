<script setup lang="ts">
import { computed, type ComponentPublicInstance, type PropType } from 'vue'
import { useFloatingTooltip, useTooltipController } from '@affino/tooltip-vue'

const props = defineProps({
  id: {
    type: String,
    required: true,
  },
  openDelay: {
    type: Number,
    default: 120,
  },
  placement: {
    type: String as PropType<'top' | 'right' | 'bottom' | 'left'>,
    default: 'top',
  },
  align: {
    type: String as PropType<'start' | 'center' | 'end'>,
    default: 'start',
  },
  gutter: {
    type: Number,
    default: 10,
  },
  viewportPadding: {
    type: Number,
    default: 12,
  },
  triggerTag: {
    type: String,
    default: 'span',
  },
  triggerClass: {
    type: [String, Array, Object] as PropType<string | string[] | Record<string, boolean>>,
    default: '',
  },
  triggerAttrs: {
    type: Object as PropType<Record<string, unknown>>,
    default: () => ({}),
  },
  surfaceClass: {
    type: [String, Array, Object] as PropType<string | string[] | Record<string, boolean>>,
    default: '',
  },
})

const tooltip = useTooltipController({ id: props.id, openDelay: props.openDelay })
const floating = useFloatingTooltip(tooltip, {
  placement: props.placement,
  align: props.align,
  gutter: props.gutter,
  viewportPadding: props.viewportPadding,
})

const triggerProps = computed(() => {
  const tooltipProps = tooltip.getTriggerProps() as Record<string, unknown>
  const customAttrs = props.triggerAttrs ?? {}

  return {
    ...tooltipProps,
    ...customAttrs,
    class: [tooltipProps.class, customAttrs.class, props.triggerClass],
  }
})

function setTriggerRef(element: Element | ComponentPublicInstance | null) {
  floating.triggerRef.value = element instanceof HTMLElement ? element : null
}

function setTooltipRef(element: Element | ComponentPublicInstance | null) {
  floating.tooltipRef.value = element instanceof HTMLElement ? element : null
}
</script>

<template>
  <component
    :is="triggerTag"
    :ref="setTriggerRef"
    v-bind="triggerProps"
  >
    <slot name="trigger" />
  </component>

  <Teleport :to="floating.teleportTarget.value || 'body'">
    <div
      v-if="tooltip.state.value.open"
      :ref="setTooltipRef"
      v-bind="tooltip.getTooltipProps()"
      :class="['app-tooltip', surfaceClass]"
      :style="floating.tooltipStyle.value"
    >
      <slot />
    </div>
  </Teleport>
</template>
