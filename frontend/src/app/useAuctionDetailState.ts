import { computed, ref, watch, type Ref } from 'vue'
import {
  belongsToSelectedLotMedia,
  isImageDocument,
  isLockedTbankrotImageUrl,
  isNoPhotoReason,
  isRelevantDetailImage,
  makeFields,
  normalizeRawFields,
  truncateDetailText,
  uniqueDetailImages,
  uniqueDocuments,
  type DetailImage,
  type DetailField,
} from '@/app/detail'
import {
  formatActionRecommendation,
  formatApiMoney,
  formatApiPercent,
  formatCurrency,
  formatDateTime,
  formatDecisionLevel,
  formatEnrichmentState,
  formatLifecycleStatus,
  formatSourceSyncWindow,
} from '@/app/formatters'

type IdLike = string | number | null | undefined

type SourceSyncStatusLike = {
  code: string
  last_sync_error: string | null
  next_sync_not_before: string | null
  next_sync_not_after: string | null
} | null

export function useAuctionDetailState(deps: {
  selectedLot: Ref<any | null>
  selectedLotDetails: Ref<any | null>
  selectedAuctionDetails: Ref<any | null>
  selectedWorkspace: Ref<any | null>
  selectedDecisionReport: Ref<any | null>
  auctionPipelineHealth: Ref<{ sources: Array<{ code: string; last_sync_error: string | null; next_sync_not_before: string | null; next_sync_not_after: string | null }> } | null>
}) {
  const activeDetailImageIndex = ref(0)

  const detailTitle = computed(() => deps.selectedLotDetails.value?.lot.name || deps.selectedLot.value?.lotName || 'Без названия')
  const liveAuction = computed(() => deps.selectedLotDetails.value?.auction ?? deps.selectedAuctionDetails.value?.auction ?? null)
  const liveLot = computed(() => deps.selectedLotDetails.value?.lot ?? null)
  const liveOrganizer = computed(() => deps.selectedLotDetails.value?.organizer ?? deps.selectedAuctionDetails.value?.organizer ?? null)
  const liveDebtor = computed(() => deps.selectedLotDetails.value?.debtor ?? deps.selectedAuctionDetails.value?.debtor ?? null)
  const detailLotUrl = computed(() => deps.selectedLotDetails.value?.lot.url || deps.selectedLotDetails.value?.url || deps.selectedLot.value?.lotUrl || '')
  const detailAuctionUrl = computed(() => liveAuction.value?.url || deps.selectedAuctionDetails.value?.url || deps.selectedLot.value?.auctionUrl || '')

  const detailFields = computed<DetailField[]>(() => {
    if (!deps.selectedLot.value) return []
    return makeFields([
      ['Аналитический сигнал', deps.selectedLot.value.analysisLabel],
      ['Категория', liveLot.value?.category || deps.selectedLot.value.analysisCategory],
      ['Наименование', deps.selectedLot.value.lotName],
      ['Должник', deps.selectedLot.value.debtorName],
      ['Локация', deps.selectedLot.value.location],
      ['Регион', deps.selectedLot.value.locationRegion],
      ['Город', deps.selectedLot.value.locationCity],
      ['Адрес', deps.selectedLot.value.locationAddress],
      ['Координаты', deps.selectedLot.value.locationCoordinates],
      ['Ручное исключение', deps.selectedLot.value.excludeFromAnalysis ? 'Да' : 'Нет'],
      ['Причина исключения', deps.selectedLot.value.exclusionReason],
      ['Площадка', deps.selectedLot.value.sourceTitle],
      ['Аукцион', liveAuction.value?.number || deps.selectedLot.value.auctionNumber],
      ['Название аукциона', liveAuction.value?.name || deps.selectedLot.value.auctionName],
      ['Публикация', liveAuction.value?.publication_date || formatDateTime(deps.selectedLot.value.publicationDate)],
      ['Лот', liveLot.value?.number || deps.selectedLot.value.lotNumber],
      ['ID лота', deps.selectedLot.value.lotId],
      ['Статус', liveLot.value?.status || deps.selectedLot.value.status],
      ['Начальная цена', liveLot.value?.initial_price || formatCurrency(deps.selectedLot.value.initialPrice)],
      ['Текущая цена', liveLot.value?.current_price || formatCurrency(deps.selectedLot.value.price)],
      ['Минимальная цена', liveLot.value?.minimum_price || formatCurrency(deps.selectedLot.value.minimumPrice)],
      ['Организатор', liveOrganizer.value?.name || deps.selectedLot.value.organizer],
      ['Заявки до', liveAuction.value?.application_deadline || formatDateTime(deps.selectedLot.value.applicationDeadline)],
      ['Торги', liveAuction.value?.auction_date || formatDateTime(deps.selectedLot.value.auctionDate)],
      ['Первое наблюдение', formatDateTime(deps.selectedLot.value.firstSeenAt)],
      ['Последнее наблюдение', formatDateTime(deps.selectedLot.value.lastSeenAt)],
    ])
  })

  const lotInfoFields = computed(() =>
    makeFields([
      ['Локация', liveLot.value?.location],
      ['Регион', liveLot.value?.region],
      ['Город', liveLot.value?.city],
      ['Адрес', liveLot.value?.address],
      ['Координаты', liveLot.value?.coordinates],
      ['Категория', liveLot.value?.category],
      ['Классификатор ЕФРСБ', liveLot.value?.classifier],
      ['Валюта цены по ОКВ', liveLot.value?.currency],
      ['Начальная цена', liveLot.value?.initial_price],
      ['Текущая цена', liveLot.value?.current_price],
      ['Минимальная цена', liveLot.value?.minimum_price],
      ['Шаг, % от начальной цены', liveLot.value?.step_percent],
      ['Шаг, руб.', liveLot.value?.step_amount],
      ['Размер задатка, руб.', liveLot.value?.deposit_amount],
      ['Способ расчета обеспечения', liveLot.value?.deposit_method],
      ['Дата внесения задатка', liveLot.value?.deposit_payment_date],
      ['Дата возврата задатка', liveLot.value?.deposit_return_date],
      ['Всего подано заявок', liveLot.value?.applications_count],
    ]),
  )

  const lotTextFields = computed(() =>
    makeFields([
      ['Описание имущества', liveLot.value?.description || deps.selectedLot.value?.lotDescription],
      ['Порядок ознакомления', liveLot.value?.inspection_order],
      ['Порядок внесения и возврата задатка', liveLot.value?.deposit_order],
    ]),
  )

  const priceScheduleSteps = computed(() => {
    if (deps.selectedLot.value?.priceSchedule?.length) return deps.selectedLot.value.priceSchedule
    if (liveLot.value?.price_schedule?.length) return liveLot.value.price_schedule
    return []
  })

  const priceScheduleFields = computed(() =>
    priceScheduleSteps.value.slice(0, 120).map((step: { starts_at: string; price: string }, index: number) => ({
      label: `${index + 1}. ${step.starts_at}`,
      value: step.price,
    })),
  )

  const organizerFields = computed(() =>
    makeFields([
      ['Сокращенное наименование', liveOrganizer.value?.name],
      ['ИНН', liveOrganizer.value?.inn],
      ['Адрес сайта', liveOrganizer.value?.website],
      ['Контактное лицо', liveOrganizer.value?.contact_name],
      ['Телефон', liveOrganizer.value?.phone],
      ['Факс', liveOrganizer.value?.fax],
    ]),
  )

  const auctionInfoFields = computed(() =>
    makeFields([
      ['Наименование', liveAuction.value?.name],
      ['Форма торга по составу участников', liveAuction.value?.participant_form],
      ['Форма представления предложений о цене', liveAuction.value?.price_offer_form],
      ['Дата проведения', liveAuction.value?.auction_date],
      ['Дата начала представления заявок', liveAuction.value?.application_start],
      ['Дата окончания представления заявок', liveAuction.value?.application_deadline],
      ['Повторные торги', liveAuction.value?.repeat],
      ['Номер сообщения в ЕФРСБ', liveAuction.value?.efrsb_message_number],
      ['Порядок определения победителя', liveAuction.value?.winner_selection_order],
      ['Порядок представления заявок', liveAuction.value?.application_order],
    ]),
  )

  const debtorFields = computed(() =>
    makeFields([
      ['Тип должника', liveDebtor.value?.debtor_type],
      ['ФИО / наименование должника', liveDebtor.value?.name],
      ['ИНН', liveDebtor.value?.inn],
      ['СНИЛС', liveDebtor.value?.snils],
      ['Наименование арбитражного суда', liveDebtor.value?.arbitration_court],
      ['Номер дела о банкротстве', liveDebtor.value?.bankruptcy_case_number],
      ['Арбитражный управляющий', liveDebtor.value?.arbitration_manager],
      ['СРО арбитражных управляющих', liveDebtor.value?.managers_organization],
      ['Регион', liveDebtor.value?.region],
    ]),
  )

  const rawLotFields = computed(() => normalizeRawFields(deps.selectedLotDetails.value?.raw_fields ?? []))
  const rawAuctionFields = computed(() => normalizeRawFields(deps.selectedAuctionDetails.value?.raw_fields ?? []))
  const auctionLots = computed(() => deps.selectedAuctionDetails.value?.lots ?? [])
  const economyFields = computed(() =>
    makeFields([
      ['Текущая цена', formatApiMoney(deps.selectedLot.value?.price ?? deps.selectedWorkspace.value?.economy.current_price)],
      ['Рыночная стоимость', formatApiMoney(deps.selectedLot.value?.marketValue ?? deps.selectedWorkspace.value?.economy.market_value)],
      ['Все расходы', formatApiMoney(deps.selectedLot.value?.totalExpenses ?? deps.selectedWorkspace.value?.economy.total_expenses)],
      ['Целевая прибыль', formatApiMoney(deps.selectedLot.value?.targetProfit ?? deps.selectedWorkspace.value?.economy.target_profit)],
      ['Полная стоимость входа', formatApiMoney(deps.selectedLot.value?.fullEntryCost ?? deps.selectedWorkspace.value?.economy.full_entry_cost)],
      ['Потенциальная прибыль', formatApiMoney(deps.selectedLot.value?.potentialProfit ?? deps.selectedWorkspace.value?.economy.potential_profit)],
      ['ROI', formatApiPercent(deps.selectedLot.value?.roiValue ?? deps.selectedWorkspace.value?.economy.roi)],
      ['Дисконт к рынку', formatApiPercent(deps.selectedLot.value?.marketDiscount ?? deps.selectedWorkspace.value?.economy.market_discount)],
      ['Макс. цена покупки', formatApiMoney(deps.selectedLot.value?.formulaMaxPurchasePrice ?? deps.selectedWorkspace.value?.economy.max_purchase_price)],
    ]),
  )

  const decisionReportSummaryFields = computed(() => {
    const report = deps.selectedDecisionReport.value
    if (!report) return []
    return makeFields([
      ['Решение', formatDecisionLevel(report.decision_level)],
      ['Рекомендация', formatActionRecommendation(report.recommendation)],
      ['Рейтинг', `${report.rating_score} / ${report.rating_level}`],
      ['Макс. цена покупки', formatApiMoney(report.economics?.max_buy_price)],
      ['Сгенерирован', formatDateTime(report.generated_at)],
    ])
  })
  const decisionReportReasons = computed(() => deps.selectedDecisionReport.value?.reasons ?? [])
  const decisionReportRisks = computed(() => deps.selectedDecisionReport.value?.risks ?? [])
  const decisionReportNextActions = computed(() => deps.selectedDecisionReport.value?.next_actions ?? [])
  const analysisReasonItems = computed(() =>
    (deps.selectedLot.value?.analysisReasons ?? []).filter((reason: string) => !(detailImages.value.length && isNoPhotoReason(reason))),
  )
  const detailCachedAt = computed(() => formatDateTime(deps.selectedWorkspace.value?.detail_cached_at ?? null))
  const selectedSourceSyncStatus = computed(() => {
    const sourceCode = deps.selectedLot.value?.source
    if (!sourceCode) return null
    return deps.auctionPipelineHealth.value?.sources.find((source) => source.code === sourceCode) ?? null
  })
  const selectedCurrentEnrichmentState = computed(() => deps.selectedWorkspace.value?.current_enrichment_state ?? null)
  const detailActualityFields = computed(() =>
    makeFields([
      ['Статус актуальности', formatLifecycleStatus(deps.selectedLot.value?.lifecycleStatus)],
      ['Проверка актуальности', formatDateTime(deps.selectedLot.value?.actualityCheckedAt ?? null)],
      ['Последний кэш детали', detailCachedAt.value],
      ['Очередь enrichment', formatEnrichmentState(selectedCurrentEnrichmentState.value)],
      ['Следующий скан источника', formatSourceSyncWindow(selectedSourceSyncStatus.value)],
      ['Ошибка источника', selectedSourceSyncStatus.value?.last_sync_error],
    ]),
  )
  const ratingReasonItems = computed(() => deps.selectedLot.value?.ratingReasons ?? [])
  const ratingBreakdown = computed(() => deps.selectedLot.value?.ratingBreakdown ?? null)
  const changeFields = computed(() =>
    (deps.selectedWorkspace.value?.changes.fields ?? []).slice(0, 40).map((field: { label: string; previous: string | null; current: string | null; change_type: string }) => ({
      ...field,
      previous: field.previous ? truncateDetailText(field.previous) : field.previous,
      current: field.current ? truncateDetailText(field.current) : field.current,
    })),
  )
  const changeSummaryFields = computed(() =>
    makeFields([
      ['Наблюдений списка', deps.selectedWorkspace.value?.changes.observations_count?.toString()],
      ['Наблюдений деталей', deps.selectedWorkspace.value?.changes.detail_observations_count?.toString()],
      ['Последнее наблюдение', formatDateTime(deps.selectedWorkspace.value?.changes.last_observed_at ?? null)],
      ['Предыдущее наблюдение', formatDateTime(deps.selectedWorkspace.value?.changes.previous_observed_at ?? null)],
      ['Последние live-детали', formatDateTime(deps.selectedWorkspace.value?.changes.last_detail_observed_at ?? null)],
      ['Предыдущие live-детали', formatDateTime(deps.selectedWorkspace.value?.changes.previous_detail_observed_at ?? null)],
      ['Изменение статуса', formatDateTime(deps.selectedWorkspace.value?.changes.status_changed_at ?? null)],
    ]),
  )
  const detailDocuments = computed(() =>
    uniqueDocuments([...(deps.selectedLotDetails.value?.documents ?? []), ...(deps.selectedAuctionDetails.value?.documents ?? [])]),
  )
  const detailImages = computed<DetailImage[]>(() => {
    const primaryImage = deps.selectedLot.value?.primaryImageUrl
      ? [
          {
            url: deps.selectedLot.value.primaryImageUrl,
            thumbnail_url: deps.selectedLot.value.primaryImageUrl,
            alt: deps.selectedLot.value.lotName,
            source: deps.selectedLot.value.source,
          },
        ]
      : []
    const selectedRowImages = [...(deps.selectedLot.value?.images ?? []), ...primaryImage]
    const liveDetailImages = liveLot.value?.images ?? []
    const documentImages = detailDocuments.value
      .filter((document) => belongsToSelectedLotMedia(document, deps.selectedLot.value?.lotNumber) && isImageDocument(document) && document.url)
      .map((document) => ({ url: document.url || '', thumbnailUrl: document.url || '', name: document.name }))
    const fallbackImages = [...liveDetailImages, ...selectedRowImages]
    const images = documentImages.length ? documentImages : fallbackImages
    return uniqueDetailImages(images).filter((image) => isRelevantDetailImage(image.url, deps.selectedLot.value?.source) && !isLockedTbankrotImageUrl(image.url))
  })
  const lockedTbankrotImageCount = computed(() => {
    const images = uniqueDetailImages([...(deps.selectedLot.value?.images ?? []), ...(liveLot.value?.images ?? [])])
    return images.filter((image) => isLockedTbankrotImageUrl(image.url)).length
  })
  const mediaDocuments = computed(() =>
    detailDocuments.value.filter((document) => {
      const text = [document.name, document.document_type, document.comment].filter(Boolean).join(' ')
      return (
        belongsToSelectedLotMedia(document, deps.selectedLot.value?.lotNumber) &&
        !isImageDocument(document) &&
        (/фото|photo|изображ/i.test(text) || /\.(rar|zip|7z)(\?|$)/i.test(document.url || document.name || ''))
      )
    }),
  )
  const fileDocuments = computed(() => detailDocuments.value.filter((document) => !isImageDocument(document)))
  const activeDetailImage = computed(() => detailImages.value[activeDetailImageIndex.value] ?? detailImages.value[0] ?? null)

  watch(detailImages, (images) => {
    if (activeDetailImageIndex.value >= images.length) {
      activeDetailImageIndex.value = 0
    }
  })

  watch(
    () => deps.selectedLot.value?.id,
    () => {
      activeDetailImageIndex.value = 0
    },
  )

  function selectDetailImage(index: number) {
    activeDetailImageIndex.value = index
  }

  function showPreviousDetailImage() {
    if (detailImages.value.length < 2) return
    activeDetailImageIndex.value = (activeDetailImageIndex.value - 1 + detailImages.value.length) % detailImages.value.length
  }

  function showNextDetailImage() {
    if (detailImages.value.length < 2) return
    activeDetailImageIndex.value = (activeDetailImageIndex.value + 1) % detailImages.value.length
  }

  return {
    detailTitle,
    liveAuction,
    liveLot,
    liveOrganizer,
    liveDebtor,
    detailLotUrl,
    detailAuctionUrl,
    detailFields,
    lotInfoFields,
    lotTextFields,
    priceScheduleSteps,
    priceScheduleFields,
    organizerFields,
    auctionInfoFields,
    debtorFields,
    rawLotFields,
    rawAuctionFields,
    auctionLots,
    economyFields,
    decisionReportSummaryFields,
    decisionReportReasons,
    decisionReportRisks,
    decisionReportNextActions,
    analysisReasonItems,
    detailCachedAt,
    selectedSourceSyncStatus,
    selectedCurrentEnrichmentState,
    detailActualityFields,
    ratingReasonItems,
    ratingBreakdown,
    changeFields,
    changeSummaryFields,
    detailDocuments,
    detailImages,
    lockedTbankrotImageCount,
    mediaDocuments,
    fileDocuments,
    activeDetailImageIndex,
    activeDetailImage,
    selectDetailImage,
    showPreviousDetailImage,
    showNextDetailImage,
  }
}
