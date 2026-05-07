• Да, текущая логика действительно больше похожа на “скрапим, потом как-то достраиваем аналитику”, а не на целевой enterprise-анализатор. Я бы развернул
  архитектуру вокруг другого принципа:

  локальная БД является основным источником правды, внешний сайт используется только для controlled ingestion/enrichment.

  То есть приложение должно не “ходить на площадку, когда пользователь смотрит”, а заранее построить качественный локальный слой данных и рейтингов.

  Целевая Модель

  Нужно разделить систему на 5 слоёв:

  1. Source ingestion
     Забирает данные с площадок по расписанию. Минимум повторных запросов. Все входящие данные сохраняются как raw snapshot + normalized snapshot.
  2. Enrichment
     Дозагружает только данные, которые реально нужны для принятия решения и рейтинга. Не “полную карточку для UI”, а именно rating-critical evidence.
  3. Canonical auction lot
     Нормализованная локальная модель лота, независимая от TBankrot/Utender/etc.
  4. Scoring / ranking
     Версионированный расчёт привлекательности под профиль пользователя/компании.
  5. Presentation grid
     Только читает локальную БД, datasetVersion и change feed. Никакой бизнес-логики и внешних запросов.

  Ключевая Идея

  Когда появляется новый лот, мы не должны просто сохранить list-card и ждать, пока пользователь откроет карточку.

  Правильный flow:

  new external lot discovered
  → save raw list snapshot
  → normalize base fields
  → decide whether rating-critical details are missing
  → fetch only required detail fields once
  → save raw detail snapshot
  → normalize detail evidence
  → calculate score
  → expose in grid

  Открытие детальной карточки в UI должно быть вторичным. Оно может показывать уже закешированную детальную информацию. Live refresh карточки допустим, но это не
  должно быть основой анализа.

  Что Нужно Хранить Локально

  Для каждого лота:

  - source identity: площадка, auction id, lot id
  - raw list payload
  - raw detail payload, если загружался
  - normalized item
  - normalized detail/evidence
  - price facts
  - location facts
  - category facts
  - legal/risk facts
  - deadlines
  - media/document availability
  - parsed constraints
  - current status
  - freshness: first_seen, last_seen, status_changed_at
  - content_hash для list данных
  - detail_hash для detail данных
  - scoring_version
  - score_input_hash
  - score result
  - score explanation

  Особенно важно: всё, что участвует в рейтинге, должно быть сохранено как нормализованные локальные поля, а не вычисляться из HTML/source на лету.

  Scoring Должен Быть Отдельным Контрактом

  Сейчас rating частично живёт внутри datagrid_row. Для enterprise-логики лучше думать так:

  lot facts + user/company profile + scoring config + scoring version
  → score result

  Результат должен быть объяснимым:

  {
    "score": 87,
    "level": "high",
    "dimensions": {
      "economics": 31,
      "risk": 18,
      "urgency": 12,
      "data_quality": 9,
      "owner_fit": 17
    },
    "reasons": [
      "Цена на 42% ниже рыночной оценки",
      "Регион входит в целевой список",
      "До окончания приема заявок 3 дня",
      "Есть риск неполных документов"
    ],
    "caps": [
      "Юридический риск ограничил максимум рейтинга до 90"
    ]
  }

  Это важно для пользователя: не просто “87”, а почему.

  Профиль Пользователя Должен Быть В Центре

  Основная ценность приложения не “показать все лоты”, а “показать подходящие”.

  Профиль должен включать:

  - целевые регионы
  - категории
  - бюджет min/max
  - минимальный ROI
  - минимальный дисконт
  - допустимые юридические риски
  - готовность к демонтажу/доставке
  - ограничения по расстоянию
  - стоп-слова
  - желательные ключевые слова
  - весовые коэффициенты
  - стратегия: conservative / balanced / aggressive

  Тогда рейтинг становится не глобальным, а профильным.

  Sync Policy

  Нужно перестать думать “синхронизировать всё одинаково”.

  Я бы ввёл state machine:

  discovered
  → list_synced
  → needs_enrichment
  → enriched
  → scored
  → active
  → stale
  → archived

  И отдельно причины пересчёта:

  source_content_changed
  detail_content_changed
  profile_changed
  scoring_config_changed
  manual_economics_changed
  source_status_changed
  ttl_expired

  Внешний сайт трогаем только если:

  - новый лот;
  - изменился list content hash;
  - detail данных нет, а они нужны для scoring;
  - detail TTL истёк для активного привлекательного лота;
  - пользователь явно запросил live refresh;
  - лот high-potential и нужно уточнить недостающие факты.

  Enrichment Не Должен Быть “Полная Карточка Всегда”

  Лучше ввести понятие evidence requirements.

  Например scoring engine говорит:

  Для первичного рейтинга нужны:
  - current price
  - minimum price
  - region
  - category
  - deadline
  - debtor
  - documents availability
  - description keywords

  Если list-card уже даёт 80% этих данных, detail fetch не нужен.

  Если данных не хватает, enrichment job догружает только нужный detail payload и сохраняет его.

  Рекомендуемая Архитектура Worker-ов

  Я бы разделил:

  source_sync_worker

  Отвечает только за discovery/list updates.

  enrichment_worker

  Дозагружает detail/evidence по очереди и policy.

  scoring_worker

  Пересчитывает рейтинг, когда изменились входы.

  change_publisher

  Единый слой, который bump-ает datasetVersion и пишет grid change events.

  Сейчас auction_sync_worker частично делает sync, scoring и иногда detail sync. Это смешение бизнес-ролей. Работает, но плохо масштабируется и сложно
  контролировать нагрузку на источники.

  Главное Изменение В Логике

  Текущий подход:

  sync list
  → maybe score
  → maybe fetch details later when user opens card

  Целевой подход:

  sync list
  → determine business relevance
  → fetch required evidence if missing
  → score locally
  → user sees already-ranked actionable grid

  Практический Roadmap

  1. Описать LotEvidence контракт: какие поля нужны рейтингу.
  2. Разделить “detail for UI” и “detail for scoring”.
  3. Добавить enrichment_status / scoring_status / hashes.
  4. Сделать enrichment queue с policy.
  5. Сделать scoring полностью hash/version driven.
  6. Перестать пересчитывать/скрапить без причины.
  7. Сделать рейтинг профильным, а не просто глобальным.
  8. Grid оставить read-only consumer локальной аналитической модели.

  Самая важная архитектурная правка: внешний источник должен быть dependency ingestion layer, а не часть пользовательского workflow. Пользователь должен работать
  почти полностью с локальной аналитической БД.