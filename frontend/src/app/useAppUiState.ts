import type { ComponentPublicInstance } from 'vue'
import { computed, ref } from 'vue'
import { UiMenu } from '@affino/menu-vue'
import { createDialogFocusOrchestrator, useDialogController } from '@affino/dialog-vue'

export type PresetDialogMode = 'create' | 'update' | 'delete'

export type InterestProfileDraft = {
  name: string
  minRating: number
  telegramEnabled: boolean
  isActive: boolean
}

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

  const presetsMenuRef = ref<InstanceType<typeof UiMenu> | null>(null)
  const accountMenuRef = ref<InstanceType<typeof UiMenu> | null>(null)
  const presetsMenuOpen = computed(() => presetsMenuRef.value?.controller.state.value.open === true)
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

  const interestProfilesDialogTriggerRef = ref<HTMLElement | null>(null)
  const interestProfilesDialogRef = ref<HTMLDivElement | null>(null)
  const interestProfilesDialogInitialRef = ref<HTMLElement | null>(null)
  const interestProfilesDialogFocus = createDialogFocusOrchestrator({
    dialog: () => interestProfilesDialogRef.value,
    initialFocus: () => interestProfilesDialogInitialRef.value,
    returnFocus: () => interestProfilesDialogTriggerRef.value,
  })
  const interestProfilesDialog = useDialogController({
    focusOrchestrator: interestProfilesDialogFocus,
  })

  const analysisConfigDialogTriggerRef = ref<HTMLElement | null>(null)
  const analysisConfigDialogRef = ref<HTMLDivElement | null>(null)
  const analysisConfigDialogInitialRef = ref<HTMLElement | null>(null)
  const analysisConfigDialogFocus = createDialogFocusOrchestrator({
    dialog: () => analysisConfigDialogRef.value,
    initialFocus: () => analysisConfigDialogInitialRef.value,
    returnFocus: () => analysisConfigDialogTriggerRef.value,
  })
  const analysisConfigDialog = useDialogController({
    focusOrchestrator: analysisConfigDialogFocus,
  })

  function setPresetDialogInitialRef(element: Element | ComponentPublicInstance | null) {
    presetDialogInitialRef.value = element as HTMLElement | null
  }

  function setInterestProfilesDialogInitialRef(element: Element | ComponentPublicInstance | null) {
    interestProfilesDialogInitialRef.value = element as HTMLElement | null
  }

  function setAnalysisConfigDialogInitialRef(element: Element | ComponentPublicInstance | null) {
    analysisConfigDialogInitialRef.value = element as HTMLElement | null
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
    presetsMenuRef,
    accountMenuRef,
    presetsMenuOpen,
    accountMenuOpen,
    presetDialogTriggerRef,
    presetDialogRef,
    presetDialogInitialRef,
    presetDialog,
    interestProfilesDialogTriggerRef,
    interestProfilesDialogRef,
    interestProfilesDialogInitialRef,
    interestProfilesDialog,
    analysisConfigDialogTriggerRef,
    analysisConfigDialogRef,
    analysisConfigDialogInitialRef,
    analysisConfigDialog,
    setPresetDialogInitialRef,
    setInterestProfilesDialogInitialRef,
    setAnalysisConfigDialogInitialRef,
    closeMobileRail,
    toggleMobileRail,
  }
}
