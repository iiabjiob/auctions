import { h } from 'vue'
import {
  defineDataGridColumnMenu,
  defineDataGridColumns,
  type DataGridAppColumnFilterOptions,
  type DataGridAppFilterValueNormalizationContext,
} from '@affino/datagrid-vue-app'
import AnalysisSignalTooltip from '@/components/AnalysisSignalTooltip.vue'
import LotNameCell from '@/components/LotNameCell.vue'
import { catalogColumnMenuOptions } from '@/datagrid/auctionGridUiConfig'
import {
  buildLifecycleStatusTooltip,
  formatApiPercent,
  formatCurrency,
  formatLifecycleStatus,
  lifecycleStatusTone,
} from '@/app/formatters'

const predicateFilterOnly = { valueSet: false } satisfies DataGridAppColumnFilterOptions
const percentPredicateFilter = {
  valueSet: false,
  normalizeValue: normalizePercentFilterValue,
} satisfies DataGridAppColumnFilterOptions

export function normalizePercentFilterValue(context: DataGridAppFilterValueNormalizationContext) {
  const value = context.value
  if (value === null || value === undefined || value === '') return value

  const parsed = Number(String(value).trim().replace(/\s+/g, '').replace('%', '').replace(',', '.'))
  if (!Number.isFinite(parsed)) return value
  return String(parsed / 100)
}

export function createAuctionGridColumns(openLotDetails: (row: any) => void) {
  return defineDataGridColumns<any>()([
    {
      key: 'ratingScore',
      label: 'Рейтинг',
      dataType: 'number',
      initialState: { width: 96 },
      presentation: { align: 'right', headerAlign: 'right' },
      capabilities: { sortable: true, filterable: true, aggregatable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'analysisLabel',
      label: 'Сигнал',
      initialState: { width: 176 },
      capabilities: { sortable: true, filterable: true },
      cellRenderer: ({ row }) => {
        if (!row) return ''

        const reasons = Array.isArray(row.analysisReasons) ? row.analysisReasons : []
        const pill = h(
          'span',
          {
            class: ['analysis-pill', `analysis-pill--${row.analysisColor || 'yellow'}`],
          },
          row.analysisLabel,
        )
        return reasons.length
          ? h(
              AnalysisSignalTooltip,
              {
                reasons,
              },
              {
                default: () => pill,
              },
            )
          : pill
      },
    },
    { key: 'analysisCategory', label: 'Категория', initialState: { width: 168 } },
    {
      key: 'isNew',
      label: 'Новый',
      dataType: 'boolean',
      initialState: { width: 88 },
      capabilities: { sortable: true, filterable: true },
    },
    {
      key: 'sourceTitle',
      label: 'Площадка',
      initialState: { width: 120 },
      filter: predicateFilterOnly,
    },
    {
      key: 'auctionNumber',
      label: 'Аукцион',
      initialState: { width: 120 },
      filter: predicateFilterOnly,
    },
    {
      key: 'publicationDate',
      label: 'Дата публикации',
      dataType: 'datetime',
      initialState: { width: 160 },
      presentation: {
        format: {
          dateTime: {
            locale: 'ru-RU',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
    },
    { key: 'lotNumber', label: 'Лот', initialState: { width: 76 }, filter: predicateFilterOnly },
    {
      key: 'lotName',
      label: 'Наименование',
      initialState: { width: 430 },
      filter: predicateFilterOnly,
      cellInteraction: {
        click: true,
        keyboard: ['enter'],
        role: 'button',
        label: ({ row }) => (row ? `Открыть ${row.lotName}` : 'Открыть лот'),
        onInvoke: ({ row }) => {
          if (row) void openLotDetails(row)
        },
      },
      cellRenderer: ({ displayValue, row }) =>
        row
          ? h(LotNameCell, {
              row,
              label: String(displayValue || 'Без названия'),
              onOpen: (lot: unknown) => void openLotDetails(lot),
            })
          : String(displayValue || 'Без названия'),
    },
    {
      key: 'location',
      label: 'Локация',
      initialState: { width: 220 },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'initialPrice',
      label: 'Начальная цена',
      dataType: 'currency',
      initialState: { width: 150 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: {
            locale: 'ru-RU',
            style: 'currency',
            currency: 'RUB',
            maximumFractionDigits: 2,
          },
        },
      },
      capabilities: { sortable: true, filterable: true, aggregatable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.initialPrice ?? null),
    },
    {
      key: 'price',
      label: 'Текущая цена',
      dataType: 'currency',
      initialState: { width: 150 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: {
            locale: 'ru-RU',
            style: 'currency',
            currency: 'RUB',
            maximumFractionDigits: 2,
          },
        },
      },
      capabilities: { sortable: true, filterable: true, aggregatable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.price ?? null),
    },
    {
      key: 'minimumPrice',
      label: 'Мин. цена',
      dataType: 'currency',
      initialState: { width: 150 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: {
            locale: 'ru-RU',
            style: 'currency',
            currency: 'RUB',
            maximumFractionDigits: 2,
          },
        },
      },
      capabilities: { sortable: true, filterable: true, aggregatable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.minimumPrice ?? null),
    },
    {
      key: 'marketValue',
      label: 'Рынок',
      dataType: 'currency',
      initialState: { width: 150 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.marketValue ?? null),
    },
    {
      key: 'platformFee',
      label: 'Комиссия ЭТП',
      dataType: 'currency',
      initialState: { width: 150 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.platformFee ?? null),
    },
    {
      key: 'deliveryCost',
      label: 'Доставка',
      dataType: 'currency',
      initialState: { width: 132 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.deliveryCost ?? null),
    },
    {
      key: 'dismantlingCost',
      label: 'Демонтаж',
      dataType: 'currency',
      initialState: { width: 138 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.dismantlingCost ?? null),
    },
    {
      key: 'repairCost',
      label: 'Ремонт',
      dataType: 'currency',
      initialState: { width: 132 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.repairCost ?? null),
    },
    {
      key: 'storageCost',
      label: 'Хранение',
      dataType: 'currency',
      initialState: { width: 138 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.storageCost ?? null),
    },
    {
      key: 'legalCost',
      label: 'Юрист',
      dataType: 'currency',
      initialState: { width: 124 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.legalCost ?? null),
    },
    {
      key: 'otherCosts',
      label: 'Прочие',
      dataType: 'currency',
      initialState: { width: 124 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.otherCosts ?? null),
    },
    {
      key: 'targetProfit',
      label: 'Целевая прибыль',
      dataType: 'currency',
      initialState: { width: 168 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.targetProfit ?? null),
    },
    {
      key: 'totalExpenses',
      label: 'Все расходы',
      dataType: 'currency',
      formula:
        'platformFee + deliveryCost + dismantlingCost + repairCost + storageCost + legalCost + otherCosts',
      initialState: { width: 152 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.totalExpenses ?? null),
    },
    {
      key: 'fullEntryCost',
      label: 'Полная стоимость входа',
      dataType: 'currency',
      formula: 'price + totalExpenses',
      initialState: { width: 198 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.fullEntryCost ?? null),
    },
    {
      key: 'potentialProfit',
      label: 'Потенциальная прибыль',
      dataType: 'currency',
      formula: 'marketValue - fullEntryCost',
      initialState: { width: 188 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.potentialProfit ?? null),
    },
    {
      key: 'roiValue',
      label: 'ROI',
      dataType: 'number',
      formula: 'potentialProfit / fullEntryCost',
      initialState: { width: 100 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: { number: { locale: 'ru-RU', style: 'percent', maximumFractionDigits: 1 } },
      },
      capabilities: { sortable: true, filterable: true },
      filter: percentPredicateFilter,
      cellRenderer: ({ row }) => formatApiPercent(row?.roiValue),
    },
    {
      key: 'marketDiscount',
      label: 'Дисконт к рынку',
      dataType: 'number',
      formula: '1 - price / marketValue',
      initialState: { width: 146 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: { number: { locale: 'ru-RU', style: 'percent', maximumFractionDigits: 1 } },
      },
      capabilities: { sortable: true, filterable: true },
      filter: percentPredicateFilter,
      cellRenderer: ({ row }) => formatApiPercent(row?.marketDiscount),
    },
    {
      key: 'formulaMaxPurchasePrice',
      label: 'Макс. цена покупки',
      dataType: 'currency',
      formula: 'marketValue - totalExpenses - targetProfit',
      initialState: { width: 176 },
      presentation: {
        align: 'right',
        headerAlign: 'right',
        format: {
          number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
      cellRenderer: ({ row }) => formatCurrency(row?.formulaMaxPurchasePrice ?? null),
    },
    {
      key: 'excludeFromAnalysis',
      label: 'Исключить',
      dataType: 'boolean',
      initialState: { width: 112 },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'exclusionReason',
      label: 'Причина исключения',
      initialState: { width: 188 },
      capabilities: { sortable: true, filterable: true, editable: true },
      filter: predicateFilterOnly,
    },
    { key: 'status', label: 'Статус', initialState: { width: 170 }, filter: predicateFilterOnly },
    {
      key: 'organizer',
      label: 'Организатор',
      initialState: { width: 240 },
      filter: predicateFilterOnly,
    },
    {
      key: 'applicationDeadline',
      label: 'Прием заявок до',
      dataType: 'datetime',
      initialState: { width: 180 },
      presentation: {
        format: {
          dateTime: {
            locale: 'ru-RU',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'auctionDate',
      label: 'Дата торгов',
      dataType: 'datetime',
      initialState: { width: 170 },
      presentation: {
        format: {
          dateTime: {
            locale: 'ru-RU',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'lastSeenAt',
      label: 'Последнее наблюдение',
      dataType: 'datetime',
      initialState: { width: 190 },
      presentation: {
        format: {
          dateTime: {
            locale: 'ru-RU',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          },
        },
      },
      capabilities: { sortable: true, filterable: true },
      filter: predicateFilterOnly,
    },
    {
      key: 'lifecycleStatus',
      label: 'Актуальность',
      initialState: { width: 148 },
      capabilities: { sortable: true, filterable: true },
      cellRenderer: ({ row }) =>
        row
          ? h(
              'span',
              {
                class: ['status-chip', `status-chip--${lifecycleStatusTone(row.lifecycleStatus)}`],
                title: buildLifecycleStatusTooltip(row),
              },
              formatLifecycleStatus(row.lifecycleStatus),
            )
          : '',
    },
  ])
}

export function createAuctionColumnMenuOptions(
  columns: ReturnType<typeof createAuctionGridColumns>,
) {
  return defineDataGridColumnMenu({
    ...catalogColumnMenuOptions,
    columns: Object.fromEntries(
      columns
        .filter((column) => 'filter' in column && column.filter?.valueSet === false)
        .map((column) => [String(column.key), { hide: ['filter'] }]),
    ),
  })
}
