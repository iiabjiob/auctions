import type { ComponentPublicInstance } from 'vue'
import { computed, ref } from 'vue'
import { UiMenu } from '@affino/menu-vue'
import { createDialogFocusOrchestrator, useDialogController } from '@affino/dialog-vue'

export type PresetDialogMode = 'create' | 'update' | 'delete'

export type AnalysisConfigDraftRule = {
  id: number
  category: string
  keywordsText: string
}

export type AnalysisConfigDraft = {
  categoryRules: AnalysisConfigDraftRule[]
  exclusionKeywordsText: string
  highRiskKeywordsText: string
  mediumRiskKeywordsText: string
  mediumRiskCategoriesText: string
}

export function useAppUiState() {
  const selectedPresetId = ref('')
  const presetDialogMode = ref<PresetDialogMode>('create')
  const presetNameDraft = ref('')
  const telegramPresetIdDraft = ref('')
  const mobileRailOpen = ref(false)
  const accountMenuRef = ref<InstanceType<typeof UiMenu> | null>(null)
  const accountMenuOpen = computed(() => accountMenuRef.value?.controller.state.value.open === true)

  const presetDialogTriggerRef = ref<HTMLElement | null>(null)
  const presetDialogRef = ref<HTMLDivElement | null>(null)
  const presetDialogInitialRef = ref<HTMLElement | null>(null)
  const presetDialogFocus = createDialogFocusOrchestrator({
    dialog: () => presetDialogRef.value,
    initialFocus: () => presetDialogInitialRef.value,
    returnFocus: () => presetDialogTriggerRef.value,
  })
  const presetDialog = useDialogController({
    focusOrchestrator: presetDialogFocus,
  })

  const analysisConfigInitialRef = ref<HTMLElement | null>(null)

  function setPresetDialogInitialRef(element: Element | ComponentPublicInstance | null) {
    presetDialogInitialRef.value = element as HTMLElement | null
  }

  function setAnalysisConfigInitialRef(element: Element | ComponentPublicInstance | null) {
    analysisConfigInitialRef.value = element as HTMLElement | null
  }

  function closeMobileRail() {
    mobileRailOpen.value = false
  }

  function toggleMobileRail() {
    mobileRailOpen.value = !mobileRailOpen.value
  }

  return {
    selectedPresetId,
    presetDialogMode,
    presetNameDraft,
    telegramPresetIdDraft,
    mobileRailOpen,
    accountMenuRef,
    accountMenuOpen,
    presetDialogTriggerRef,
    presetDialogRef,
    presetDialogInitialRef,
    presetDialog,
    setPresetDialogInitialRef,
    analysisConfigInitialRef,
    setAnalysisConfigInitialRef,
    closeMobileRail,
    toggleMobileRail,
  }
}
