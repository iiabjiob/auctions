<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createComboboxStore, useComboboxStore } from '@affino/combobox-vue'

type ComboboxOption = {
  label: string
  value: string
}

const props = defineProps<{
  id: string
  modelValue: string
  options: ComboboxOption[]
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
}>()

const rootRef = ref<HTMLElement | null>(null)
const store = createComboboxStore({
  context: {
    optionCount: props.options.length,
    mode: 'single',
    loop: true,
    disabled: false,
    isDisabled: () => false,
  },
})
const { state, stop } = useComboboxStore(store)

const selectedOption = computed(() => props.options.find((option) => option.value === props.modelValue) ?? null)
const buttonLabel = computed(() => selectedOption.value?.label ?? props.placeholder ?? 'Выберите значение')

watch(
  () => props.options.length,
  (optionCount) => {
    store.setContext({ ...store.context, optionCount })
  },
)

function toggleOpen() {
  store.setOpen(!state.value.open)
}

function selectOption(option: ComboboxOption, index: number) {
  store.activate(index)
  store.setOpen(false)
  emit('update:modelValue', option.value)
  emit('change', option.value)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!state.value.open) store.setOpen(true)
    store.move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (!state.value.open) store.setOpen(true)
    store.move(-1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!state.value.open) {
      store.setOpen(true)
      return
    }

    const activeOption = props.options[state.value.listbox.activeIndex]
    if (activeOption) selectOption(activeOption, state.value.listbox.activeIndex)
  } else if (event.key === 'Escape') {
    store.setOpen(false)
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!rootRef.value?.contains(event.target as Node)) {
    store.setOpen(false)
  }
}

onMounted(() => window.addEventListener('pointerdown', handleDocumentPointerDown))
onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleDocumentPointerDown)
  stop()
  store.dispose()
})
</script>

<template>
  <div ref="rootRef" class="affino-combobox">
    <button
      :id="id"
      class="affino-combobox__button"
      type="button"
      role="combobox"
      :aria-expanded="state.open"
      :aria-controls="`${id}-listbox`"
      aria-haspopup="listbox"
      @click="toggleOpen"
      @keydown="handleKeydown"
    >
      <span>{{ buttonLabel }}</span>
      <span class="affino-combobox__chevron" aria-hidden="true">⌄</span>
    </button>

    <div v-if="state.open" :id="`${id}-listbox`" class="affino-combobox__list" role="listbox">
      <button
        v-for="(option, index) in options"
        :key="option.value"
        class="affino-combobox__option"
        :class="{
          'affino-combobox__option--active': state.listbox.activeIndex === index,
          'affino-combobox__option--selected': option.value === modelValue,
        }"
        type="button"
        role="option"
        :aria-selected="option.value === modelValue"
        @mouseenter="store.activate(index)"
        @click="selectOption(option, index)"
      >
        {{ option.label }}
      </button>
    </div>
  </div>
</template>