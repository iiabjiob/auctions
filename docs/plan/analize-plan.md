Предлагаемый пайплайн

  1. Нормализовать даты в БД

     Добавить в auction_lot_records реальные datetime-колонки:
      - publication_at
      - application_start_at
      - application_deadline_at
      - auction_at
      - finished_at
      - lifecycle_status: active | expired | stale | archived
      - archived_at
      - archive_reason
      - actuality_checked_at
      - detail_stale_after

     JSON оставить для отображения, но вся фильтрация/сортировка/актуальность должны идти по колонкам.
  2. Actuality classifier после каждого sync и отдельным sweep-job’ом

     Правило простое:
      - статус содержит архив, заверш, состоял, подвед, отмен → archived
      - application_deadline_at < now - grace и auction_at < now - grace → expired/archived
      - лот не видели в источнике N синков или N дней → stale
      - есть будущий дедлайн/торги и источник активен → active

     Default grid должен показывать только lifecycle_status = active. Архив открыть отдельным фильтром.
  3. Рейтинг считать только для активного каталога

     Старый лот вообще не должен иметь шанс попасть в топ. Даже если score 99, если дедлайн прошел, он либо скрыт, либо score принудительно capped до 0/archived.
  4. Enrichment должен идти не “кто раньше попросился”, а по SLA

     Ввести priority policy:
      - top-30 active lots по рейтингу: detail TTL 6-24 часа
      - top-100: TTL 1-3 дня
      - near deadline, например до 72 часов: повышенный приоритет
      - user-requested refresh: высокий приоритет, но через rate-limit
      - low-score/non-active: не обогащать автоматически

     То есть отдельный scheduler регулярно делает: “найти активные топ-лоты, у которых detail cache старее TTL, поставить enrichment_requested_at”. Тогда топ не будет
     неделю лежать без мониторинга.
  5. Очередь enrichment лучше сделать явной

     Минимальный вариант: добавить поля enrichment_priority, enrichment_reason, next_enrichment_due_at.

     Более чистый вариант: таблица lot_refresh_jobs:
      - lot_record_id
      - job_type: detail_refresh | reanalyze | actuality_check
      - priority
      - reason
      - requested_by
      - run_after
      - attempt_count
      - status

     Воркер берет WHERE run_after <= now AND status='pending' ORDER BY priority DESC, run_after ASC FOR UPDATE SKIP LOCKED.
  6. Manual refresh для пользователя

     Разделить две кнопки:
      - Пересчитать локально - не ходит во внешний источник, можно почти без лимита.
      - Обновить с источника - ставит refresh-job в очередь.

     Лимиты:
      - per-user: например 5 live refresh / час, 30 / день
      - per-lot: не чаще 1 раза в 30-60 минут
      - per-source global: concurrency 1-2, pause 1-3 секунды, backoff на 403/429
      - если лимит превышен, UI показывает “запланировано” или “можно через X минут”, а не бьет источник напрямую.
  7. Показать пользователю расписание

     Добавить worker_runs или source_scan_state:
      - source_code
      - last_started_at
      - last_completed_at
      - last_result
      - next_run_at
      - next_run_window_start
      - next_run_window_end
      - last_error

     Так как jitter уже вычисляется в worker, его надо не только логировать, а сохранять. UI показывает: “Следующий scan: 14:10-14:55”, “Последнее обогащение: 7 дней
     назад”, “Следующее обновление detail: через 3 часа”.

  MVP порядок внедрения

  1. Миграция lifecycle + нормализованные даты + индексы.
  2. Парсер дат из datagrid_row/normalized_item/detail_cache и backfill.
  3. Default grid: скрыть expired/stale/archived.
  4. Sweep-job актуальности: архивирует прошедшие/невидимые лоты.
  5. Top-N enrichment scheduler: гарантированно ставит в очередь топ-30/top-100.
  6. Manual refresh endpoint с rate-limit.
  7. UI badges: актуальность, last seen, last enriched, next scan window.

  Самое важное: актуальность должна стать отдельной первой стадией пайплайна, до рейтинга и enrichment. Тогда старые торги не попадут в топ, а дорогие активные лоты
  будут обновляться по SLA, а не случайно “когда воркер до них доберется”.

  Да. Я бы шел такими [x] слайсами, каждый можно давать Codex отдельным промтом и закрывать PR/коммитом.

  Общий Контекст
  Этот блок можно вставлять перед каждым промтом:

  Работаем в репозитории /workspace. Система аукционных лотов: FastAPI backend, SQLAlchemy async, Alembic, frontend Vue.
  Цель: сделать каталог актуальным: прошедшие/устаревшие лоты не должны попадать в default grid/top rating, а top-ranked активные лоты должны обогащаться приоритетно.
  Не ломай существующий lifecycle/enrichment pipeline. Используй существующие паттерны: AuctionLotRecord, auction_sync, auction_catalog, lot_enrichment,
  auction_pipeline_observability, tests.
  После изменений добавь/обнови focused tests и запусти релевантные тесты.

  [x] Слайс 1: Lifecycle И Нормализованные Даты

  Добавь в AuctionLotRecord нормализованные поля актуальности.

  Нужно:
  - Alembic migration:
    - publication_at DateTime(timezone=True), nullable
    - application_start_at DateTime(timezone=True), nullable
    - application_deadline_at DateTime(timezone=True), nullable
    - auction_at DateTime(timezone=True), nullable
    - finished_at DateTime(timezone=True), nullable
    - lifecycle_status String(32), nullable=False, default='active', index
    - archived_at DateTime(timezone=True), nullable
    - archive_reason Text, nullable
    - actuality_checked_at DateTime(timezone=True), nullable
  - Обновить backend/app/models/auction.py.
  - Добавить индексы под default catalog:
    - lifecycle_status
    - application_deadline_at
    - auction_at
    - rating_score + lifecycle_status, если удобно для Postgres.
  - Не менять пока поведение grid/enrichment.

  Acceptance:
  - Миграция проходит.
  - Модель импортируется.
  - Есть тест или проверка migration/model, если в проекте есть подходящий паттерн.

  [x] Слайс 2: Парсер Дат И Классификатор Актуальности

  Реализуй сервис, который извлекает даты лота из record.datagrid_row, record.normalized_item и detail_cache.

  Нужно:
  - Новый сервис, например backend/app/services/lot_actuality.py.
  - Функции:
    - parse_lot_datetime(value: str | None) -> datetime | None
    - extract_lot_actuality_dates(record, detail_cache=None) -> объект/модель с publication_at, application_start_at, application_deadline_at, auction_at
    - classify_lot_actuality(record, detail_cache=None, current_time=None) -> результат:
      - lifecycle_status: active | expired | stale | archived
      - finished_at
      - archive_reason
  - Правила:
    - терминальные статусы: архив, archived, заверш, закончен, состоял, состоялись, подвед, отмен.
    - если статус терминальный -> archived.
    - если application_deadline_at и auction_at в прошлом с grace, например 24 часа -> expired.
    - если есть только application_deadline_at в прошлом с grace -> expired.
    - если last_seen_at слишком старый, например configurable threshold, пока константа 30 дней -> stale.
    - иначе active.
  - Пока не подключать к grid, только сервис и тесты.
  - Не дублируй парсинг грубо: можно переиспользовать/аккуратно вынести форматы из lot_enrichment/lot_evidence, но не делай большой рефактор.

  Acceptance:
  - Unit tests на разные форматы дат.
  - Unit tests на active/expired/archived/stale.

  [x] Слайс 3: Интеграция Actuality В Sync

  Подключи нормализованные даты и lifecycle_status в source sync.

  Нужно:
  - В backend/app/services/auction_sync.py при create/update record:
    - извлекать publication_at/application_start_at/application_deadline_at/auction_at
    - записывать эти колонки в AuctionLotRecord
    - вызывать classify_lot_actuality
    - обновлять lifecycle_status, finished_at, archived_at, archive_reason, actuality_checked_at
  - Если лот стал archived/expired/stale:
    - не ставить его на enrichment
    - очистить enrichment_requested_at/claim/retry поля или минимум исключить его из будущего enrichment
  - Если лот снова активен после sync:
    - lifecycle_status должен вернуться в active
    - archived_at/archive_reason очистить
  - Сохранять текущий behavior scoring/search насколько возможно.
  - Добавить tests в backend/tests/test_auction_sync.py или новый focused test.

  Acceptance:
  - Новые лоты получают нормализованные даты.
  - Прошедший лот получает expired/archived.
  - Активный лот остается active.
  - Archived lot не получает enrichment_requested_at.

  [x] Слайс 4: Default Grid Показывает Только Active

  Сделай так, чтобы default persisted grid не показывал expired/stale/archived лоты.

  Нужно:
  - В backend/app/services/auction_catalog.py:
    - default query должен фильтровать AuctionLotRecord.lifecycle_status == 'active'.
    - Добавить явный фильтр lifecycle_status/include_archived, чтобы можно было открыть архив.
  - Обновить схемы фильтров, API router и frontend datasource, если фильтр прокидывается через request.
  - Summary/histograms должны использовать тот же default active scope.
  - Старый period по last_seen_at оставить, но lifecycle фильтр должен быть обязательным default.
  - Tests:
    - SQL test, что default query содержит lifecycle_status active.
    - expired/archived лоты не попадают в grid.
    - при явном archived filter попадают.

  Acceptance:
  - Top rating/grid больше не может вернуть прошедший лот по умолчанию.
  - Архив доступен явно, а не потерян.

  [x] Слайс 5: Actuality Sweep Worker

  Добавь локальный sweep, который без похода во внешний источник регулярно переоценивает актуальность лотов.

  Нужно:
  - Сервисная функция, например run_lot_actuality_sweep(session, limit, current_time=None).
  - Она выбирает non-archived или recently seen records, у которых:
    - actuality_checked_at is null
    - или ближайший deadline/auction уже прошел
    - или last_seen_at старше stale threshold
  - Обновляет lifecycle_status/finished_at/archived_at/archive_reason.
  - Для строк, ушедших из active, bump dataset version с event_type row_deleted или invalidation по существующему паттерну.
  - Добавить worker module или встроить в existing analysis/enrichment cycle минимально безопасно.
  - Добавить настройки в config:
    - AUCTION_ACTUALITY_SWEEP_ENABLED
    - AUCTION_ACTUALITY_SWEEP_INTERVAL_SECONDS
    - AUCTION_ACTUALITY_SWEEP_BATCH_SIZE
  - Tests на sweep.

  Acceptance:
  - Лот с прошедшим дедлайном исчезает из default grid после sweep даже без нового source sync.
  - Sweep не ходит во внешние источники.

  [x] Слайс 6: Top-N Enrichment Scheduler

  Сделай scheduler, который гарантированно ставит активные top-ranked лоты на detail refresh по TTL.

  Нужно:
  - Не переписывать enrichment worker полностью.
  - Добавить функцию schedule_priority_lot_enrichment(session, current_time=None).
  - Выбирает только lifecycle_status='active'.
  - Политика:
    - top 30 по rating_score: detail TTL 24 часа
    - top 100: detail TTL 72 часа
    - near deadline <= 72 часа: TTL 12-24 часа
    - low score не трогаем автоматически
  - Если detail_cache отсутствует или fetched_at старше TTL -> set enrichment_requested_at, reason/priority если такие поля уже есть или добавить минимально.
  - Не ставить job, если active claim есть или retry backoff еще не прошел.
  - Подключить scheduler перед run_enrichment_batch или отдельным шагом worker-а.
  - Tests:
    - top-30 stale cache попадает в enrichment.
    - archived/expired не попадает.
    - fresh cache не попадает.
    - near deadline получает приоритет.

  Acceptance:
  - Топовые активные лоты не могут лежать неделю без enrichment_requested_at.

  [x] Слайс 7: SQL Priority В Enrichment Claim

  Улучши выбор enrichment candidates, чтобы БД сразу отдавала лучшие кандидаты, а не огромный хвост по enrichment_requested_at.

  Нужно:
  - Сейчас build_lot_enrichment_candidate_statement сортирует по enrichment_requested_at/id, а priority применяется в Python.
  - Перенести максимум priority в SQL:
    - active lifecycle first/only
    - rating_score desc
    - application_deadline_at asc nulls last
    - last_seen_at desc
    - enrichment_requested_at asc
  - Если application_deadline_at еще нет в старых строках, fallback можно оставить в Python, но новые колонки должны использоваться.
  - Не сломать FOR UPDATE SKIP LOCKED.
  - Tests:
    - high score выбирается раньше старого low score.
    - near deadline при равном score раньше far deadline.
    - expired/archived не выбираются.

  Acceptance:
  - claim path масштабируется без загрузки всех requested records в память.

  [x] Слайс 8: Next Scan Window И Pipeline Status Для UI

  Сохраняй next scan window и отдай его в API observability.

  Нужно:
  - Добавить модель/таблицу или расширить AuctionSourceState sync_cursor, если так проще:
    - last_sync_started_at
    - last_sync_completed_at
    - next_sync_not_before
    - next_sync_not_after
    - last_sync_error
  - В auction_sync_worker.py после расчета delay сохранять next window.
  - Учитывать interval + jitter:
    - если delay уже выбран, next_sync_not_before = now + delay
    - next_sync_not_after = now + delay + jitter или точное окно по выбранной модели.
  - Расширить /api/v1/health/auction-pipeline или добавить endpoint source sync status.
  - Tests на расчет/serialization.

  Acceptance:
  - UI/API может показать “следующий scan примерно с X до Y”.

  [x] Слайс 9: Manual Refresh С Rate Limit

  Добавь безопасный manual refresh для пользователя.

  Нужно:
  - Backend endpoint для lot refresh:
    - local reanalyze: только локальный пересчет scoring/report, без внешнего источника.
    - live refresh: ставит lot в enrichment queue, не ходит напрямую в источник из request handler.
  - Rate limits:
    - per lot cooldown, например 30 минут.
    - per user/day или per user/hour, можно начать с простой DB/Redis-free проверки по existing timestamps, если нет инфраструктуры.
    - source global safety остается в worker через item_pause/backoff.
  - Response должен возвращать:
    - status: queued | rate_limited | already_pending
    - next_allowed_at
    - current enrichment state
  - Frontend: кнопка/действие в detail/grid, без auto-refresh при открытии.
  - Tests endpoint/service.

  Acceptance:
  - Пользователь может запросить обновление важного лота.
  - Запрос не бьет внешний источник синхронно.
  - Повторные клики не создают шторм.

  [x] Слайс 10: UI Видимость Актуальности

  Добавь в UI понятные поля актуальности и мониторинга.

  Нужно:
  - В grid/detail показать:
    - lifecycle_status
    - last_seen_at
    - last enriched/fetched_at
    - next enrichment due/pending state
    - next source scan window
  - Default grid остается active-only.
  - Добавить фильтр “Архив/Неактуальные”.
  - Не перегружать интерфейс: достаточно badges/columns/tooltips.
  - Проверить frontend build/tests.

  Acceptance:
  - Пользователь видит почему лот активен/неактуален.
  - Понятно, когда был последний мониторинг и когда ожидается следующий scan.

  Я бы закрывал в порядке: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. Минимальный полезный результат появится после слайса 4: старые торги исчезнут из default top/grid.
  После слайса 6 решится проблема “топ неделю не мониторился”.

  Главные остаточные риски сейчас такие:

  - Полноценной runtime-проверки на живой БД/Redis я не делал, поэтому остаётся риск скрытой логики на стыке sync / actuality / enrichment.
  - Окно следующего source scan хранится в sync_cursor, а не в отдельной таблице. Это рабочее решение, но оно менее структурно и может потребовать отдельной нормализации
    позже.
  - Логика actuality и приоритизации enrichment сейчас сделана как практичный MVP. Если каталог сильно вырастет, вероятно, придётся ужесточать SQL-предикаты и индексы.
  - Риск лишних обращений во внешний источник всё ещё есть при частом manual refresh и при агрессивных настройках sync interval. Код уже ограничивает это, но
    эксплуатационно это нужно держать под контролем.
  - UI-зависимость от фоновых воркеров осталась: если actuality/sync воркеры выключены или отстают, статус в гриде и detail будет временно устаревать.