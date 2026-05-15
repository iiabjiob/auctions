<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
const buttonRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLDivElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
const searchQuery = ref('')
const panelStyle = ref<Record<string, string>>({})
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
const filteredOptions = computed(() => {
  const normalizedQuery = searchQuery.value.trim().toLowerCase()
  if (!normalizedQuery) return props.options
  return props.options.filter((option) => {
    const haystack = `${option.label} ${option.value}`.toLowerCase()
    return haystack.includes(normalizedQuery)
  })
})

watch(
  () => filteredOptions.value.length,
  (optionCount) => {
    store.setContext({ ...store.context, optionCount })
    if (!state.value.open || optionCount <= 0 || state.value.listbox.activeIndex < optionCount) return
    store.activate(0)
  },
  { immediate: true },
)

watch(
  () => state.value.open,
  async (open) => {
    if (!open) {
      searchQuery.value = ''
      panelStyle.value = {}
      return
    }

    updatePanelPosition()
    await nextTick()
    searchInputRef.value?.focus()
  },
)

function getPanelHost() {
  return document.getElementById('affino-overlay-host') ?? document.body
}

function updatePanelPosition() {
  if (!buttonRef.value || !state.value.open) return

  const rect = buttonRef.value.getBoundingClientRect()
  const viewportPadding = 12
  const preferredWidth = Math.max(rect.width, 280)
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const top = Math.min(rect.bottom + 6, Math.max(viewportPadding, viewportHeight - 180))
  const left = Math.min(Math.max(viewportPadding, rect.left), Math.max(viewportPadding, viewportWidth - preferredWidth - viewportPadding))

  panelStyle.value = {
    position: 'fixed',
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    width: `${Math.round(preferredWidth)}px`,
    maxWidth: `calc(100vw - ${viewportPadding * 2}px)`,
    zIndex: '1450',
  }
}

function handleViewportChange() {
  if (state.value.open) updatePanelPosition()
}

function open() {
  store.setOpen(true)
}

function close() {
  store.setOpen(false)
  searchQuery.value = ''
}

function toggleOpen() {
  if (state.value.open) {
    close()
    return
  }

  open()
}

function selectOption(option: ComboboxOption, index: number) {
  store.activate(index)
  close()
  emit('update:modelValue', option.value)
  emit('change', option.value)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!state.value.open) open()
    store.move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (!state.value.open) open()
    store.move(-1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!state.value.open) {
      open()
      return
    }

    const activeOption = filteredOptions.value[state.value.listbox.activeIndex]
    if (activeOption) selectOption(activeOption, state.value.listbox.activeIndex)
  } else if (event.key === 'Escape') {
    close()
  }
}

function handleSearchInput(event: Event) {
  searchQuery.value = (event.target as HTMLInputElement).value
}

function handleSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    store.move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    store.move(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const activeOption = filteredOptions.value[state.value.listbox.activeIndex]
    if (activeOption) selectOption(activeOption, state.value.listbox.activeIndex)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target as Node
  if (!rootRef.value?.contains(target) && !panelRef.value?.contains(target)) {
    close()
  }
}

onMounted(() => window.addEventListener('pointerdown', handleDocumentPointerDown))
onMounted(() => {
  window.addEventListener('resize', handleViewportChange)
  window.addEventListener('scroll', handleViewportChange, true)
})
onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleDocumentPointerDown)
  window.removeEventListener('resize', handleViewportChange)
  window.removeEventListener('scroll', handleViewportChange, true)
  stop()
  store.dispose()
})
</script>

<template>
  <div ref="rootRef" class="affino-combobox">
    <button
      ref="buttonRef"
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

    <Teleport :to="getPanelHost()">
      <div
        v-if="state.open"
        :id="`${id}-listbox`"
        ref="panelRef"
        class="affino-combobox__list"
        :style="panelStyle"
        role="listbox"
      >
        <label class="affino-combobox__search">
          <span class="sr-only">Поиск</span>
          <input
            ref="searchInputRef"
            type="text"
            class="affino-combobox__search-input"
            :value="searchQuery"
            placeholder="Найти срез"
            autocomplete="off"
            spellcheck="false"
            @input="handleSearchInput"
            @keydown="handleSearchKeydown"
          />
        </label>
        <div v-if="filteredOptions.length === 0" class="affino-combobox__empty">Ничего не найдено</div>
        <button
          v-for="(option, index) in filteredOptions"
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
    </Teleport>
  </div>
</template>
