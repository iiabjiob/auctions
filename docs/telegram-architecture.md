• Да, тогда архитектуру лучше строить не как “один канал для всех”, а как приложение управляет доступом, бот только доставляет уведомления.

  Базовая модель:

  1. Приложение остается источником прав
      - пользователи;
      - тарифы/подписки;
      - доступные регионы/категории/порог рейтинга;
      - лимиты уведомлений;
      - включенные Telegram-уведомления.
  2. Telegram-бот привязывается к пользователю
     Пользователь в приложении нажимает “Подключить Telegram”, получает код или deep-link:

     https://t.me/TorgiRadarBot?start=connect_<token>

     Потом бот пишет в личку этому пользователю, а backend сохраняет:

     user_id -> telegram_chat_id

  3. Уведомления уходят персонально
     Не в общий канал, а каждому пользователю в личный чат с ботом:

     telegram_chat_id = конкретный пользователь

     Тогда можно фильтровать сообщения по подписке.

  4. Канал можно оставить как публичную витрину
     Например:
      - бесплатные редкие сигналы;
      - задержанные уведомления;
      - только топ-лоты без деталей;
      - маркетинговая лента.
  5. Outbox должен стать user-scoped
     Сейчас у нас логика ближе к глобальному уведомлению. Для подписок понадобится примерно:

     telegram_notification_outbox
     - user_id
     - telegram_chat_id
     - lot_record_id
     - decision_report_id
     - message_payload
     - dedupe_key
     - cooldown_key
     - status

  6. Eligibility тоже станет персональной
     Сейчас:

     evaluate_lot_notification_eligibility(report, profile=None)

     Позже должно быть ближе к:

     evaluate_lot_notification_eligibility(report, user_profile, subscription)

     Где учитывается:
      - тариф;
      - профиль интересов;
      - регионы;
      - категории;
      - минимальный рейтинг;
      - лимит сообщений;
      - cooldown;
      - доступ к деталям/max buy/economics.

  Итого: для MVP канал нормален, чтобы быстро проверить формат и пользу уведомлений. Но для платного доступа основной путь — личные сообщения от бота каждому
  пользователю, а backend решает, кому что можно отправить.

## Профили интересов пользователя

Одного рейтинга недостаточно для Telegram-уведомлений. Рейтинг отвечает на вопрос "лот объективно сильный?", а профиль интересов отвечает на вопрос "нужен ли этот лот конкретному пользователю?". Например:

- пользователь A получает только спецтехнику от 2 млн рублей;
- пользователь B получает только авто BMW;
- пользователь C получает только лоты в конкретных регионах и без юридических стоп-сигналов.

Базовая сущность должна быть не "Telegram-фильтр", а пользовательский профиль интересов, который можно использовать и в анализе, и в уведомлениях. В текущем коде для этого уже подходит доменная база `LotScoringProfile`: регионы, категории, бюджет, ROI/discount, желательные слова, стоп-слова, юридический риск и веса.

Фильтр datagrid и сохраненный preset остаются UI-представлением. Профиль интересов должен быть операционным правилом, которое backend может применить в фоне без открытого браузера пользователя.

Минимальная модель:

```text
user_interest_profiles
- id
- owner_user_id
- name
- profile_payload
- min_rating
- notification_priority_threshold
- telegram_enabled
- is_active
- created_at
- updated_at
```

`profile_payload` может хранить канонический payload `LotScoringProfile`, чтобы не плодить вторую несовместимую модель правил.

Eligibility для уведомлений должна стать персональной:

```python
evaluate_lot_notification_eligibility(report, user_profile, subscription)
```

Она должна учитывать:

- текущий deterministic score и decision level;
- совпадение с `evaluate_lot_profile_fit`;
- минимальный рейтинг профиля;
- бюджет/цену;
- желательные и стоп-слова;
- тариф и лимиты;
- cooldown по пользователю/профилю/лоту;
- включен ли Telegram у пользователя.

Важное правило: несовпадение с профилем должно быть блокером отправки пользователю, а не просто небольшим штрафом к рейтингу. Иначе высокорейтинговый BMW будет прилетать пользователю, которому нужна только спецтехника.

Outbox тоже должен стать персональным:

```text
telegram_notification_outbox
- user_id
- telegram_chat_id
- interest_profile_id
- lot_record_id
- decision_report_id
- message_payload
- dedupe_key
- cooldown_key
- status
- priority
```

`dedupe_key` должен включать пользователя и профиль:

```text
telegram:{user_id}:{interest_profile_id}:{lot_record_id}:{report_hash}
```

Тогда один и тот же лот можно отправить пользователю A и не отправить пользователю B.

MVP-срез:

1. Добавить persistent user interest profiles на базе `LotScoringProfile`.
2. Добавить привязку Telegram chat к пользователю.
3. Добавить `user_id` и `interest_profile_id` в outbox.
4. В enqueue-flow проходить по активным профилям пользователей и создавать outbox-записи только при совпадении.
5. Во frontend дать действие "создать профиль интересов из текущих фильтров".


Ниже слайсы в порядке реализации. Каждый промт можно давать Codex отдельно.

  Slice 1: Backend Model

  Добавь persistent user interest profiles.

  Контекст:
  - Монорепо auctions platform.
  - Backend FastAPI + async SQLAlchemy + Alembic.
  - Есть LotScoringProfile в backend/app/schemas/scoring_profile.py.
  - Есть filter_presets как пример user-owned CRUD.
  - Архитектура описана в docs/telegram-architecture.md.

  Задача:
  1. Создать SQLAlchemy model UserInterestProfileModel:
     - id: string primary key
     - owner_user_id: FK users.id cascade
     - name: string 160
     - profile_payload: JSONB
     - min_rating: int default 0
     - notification_priority_threshold: string nullable/default medium
     - telegram_enabled: bool default true
     - is_active: bool default true
     - created_at / updated_at
     - unique(owner_user_id, name)
  2. Добавить Alembic migration.
  3. Добавить Pydantic schemas create/update/response.
  4. Добавить model export в backend/app/models/__init__.py.
  5. Добавить focused tests for model/schema validation if existing patterns allow.

  Не трогай frontend. Не меняй Telegram behavior в этом слайсе.
  Запусти минимальные backend tests/migration checks.

  Slice 2: Backend CRUD API

  Реализуй CRUD API для user interest profiles.

  Контекст:
  - UserInterestProfileModel уже добавлен.
  - Смотри pattern filter_presets:
    - backend/app/api/v1/filter_presets/router.py
    - backend/app/services/filter_presets.py
    - backend/app/schemas/filter_presets.py

  Задача:
  1. Добавить service user_interest_profiles:
     - list_for_user
     - create
     - update
     - delete
     - enforce owner_user_id
     - trim/validate name
     - unique name conflict
  2. Добавить router:
     - GET /api/v1/user-interest-profiles
     - POST /api/v1/user-interest-profiles
     - PATCH /api/v1/user-interest-profiles/{profile_id}
     - DELETE /api/v1/user-interest-profiles/{profile_id}
  3. Подключить router в app/main.py или текущий v1 router setup.
  4. Tests:
     - user sees only own profiles
     - duplicate name returns conflict
     - update/delete requires ownership
     - create stores profile_payload and min_rating

  Не меняй Telegram enqueue logic в этом слайсе.

  Slice 3: Profile Matching Service

  Добавь backend service для проверки, подходит ли lot/report под user interest profile.

  Контекст:
  - Есть evaluate_lot_profile_fit в backend/app/services/scoring_profile_fit.py.
  - Есть LotScoringProfile.
  - Есть build_lot_decision_report/evaluate_lot_notification_eligibility в backend/app/services/lot_decision_report.py.
  - UserInterestProfileModel хранит profile_payload и min_rating.

  Задача:
  1. Создать service, например backend/app/services/user_interest_matching.py.
  2. Реализовать функцию:
     - build_lot_scoring_profile_from_interest(profile_model)
     - evaluate_user_interest_match(record/detail_cache/work_item/report, interest_profile)
  3. Правила:
     - inactive profile = blocker
     - rating_score < min_rating = blocker
     - telegram_enabled false = blocker для notification path
     - evaluate_lot_profile_fit blockers = blocker
     - matches_profile true = match
  4. Вернуть структурированный result:
     - matches: bool
     - reasons: list[str]
     - blockers: list[str]
     - profile_hash
  5. Tests:
     - BMW keyword profile matches BMW lot
     - спецтехника + budget_min 2M blocks cheap lot
     - stop_words block notification
     - min_rating blocks low rating

  Не меняй outbox schema в этом слайсе.

  Slice 4: User-Scoped Telegram Outbox Schema

  Сделай Telegram outbox user-scoped без изменения отправки сообщений.

  Контекст:
  - Current model: TelegramNotificationOutbox in backend/app/models/auction.py.
  - Current migration: backend/alembic/versions/202605080002_telegram_notification_outbox.py.
  - Current sender reads pending outbox and sends to global chat_id.

  Задача:
  1. Добавить nullable columns:
     - user_id FK users.id ondelete CASCADE, nullable for backward compatibility
     - telegram_chat_id string nullable
     - interest_profile_id FK user_interest_profiles.id ondelete SET NULL nullable
  2. Добавить индексы:
     - user_id
     - interest_profile_id
     - status/user_id/priority if useful
  3. Обновить SQLAlchemy model.
  4. Обновить tests/snapshots для outbox model.
  5. Не ломать текущие глобальные outbox записи.

  Не меняй sender routing в этом слайсе, только schema/model compatibility.

  Slice 5: Personal Eligibility And Enqueue

  Обнови Telegram enqueue flow, чтобы создавать персональные outbox entries по user interest profiles.

  Контекст:
  - UserInterestProfileModel существует.
  - User-scoped columns in TelegramNotificationOutbox существуют.
  - Есть user_interest_matching service.
  - Current enqueue function: enqueue_lot_telegram_notification_outbox in backend/app/services/lot_decision_report.py.

  Задача:
  1. Не удаляй старую глобальную функцию сразу. Добавь новую функцию, например:
     - enqueue_user_scoped_lot_telegram_notifications(session, snapshot, report, ...)
  2. Найти активные user interest profiles с telegram_enabled true.
  3. Для каждого профиля:
     - проверить match через user_interest_matching
     - если mismatch, не создавать outbox
     - если match, применить current evaluate_lot_notification_eligibility
     - dedupe_key должен включать user_id + interest_profile_id + lot_record_id + report_hash
     - cooldown_key должен включать user_id + interest_profile_id + lot_record_id
     - заполнить user_id, interest_profile_id, telegram_chat_id если доступен
  4. Пока нет Telegram binding, оставь telegram_chat_id nullable и sender пусть продолжает использовать global chat_id.
  5. Tests:
     - same lot enqueues for matching user only
     - same lot can enqueue for two users with different dedupe keys
     - non-matching profile does not enqueue
     - duplicate enqueue is idempotent

  Минимизируй изменения в существующей логике.

  Slice 6: Telegram Binding

  Добавь минимальную привязку Telegram к пользователю.

  Контекст:
  - Сейчас config имеет telegram_chat_id глобально.
  - Target docs: user_id -> telegram_chat_id.
  - User-scoped outbox уже имеет telegram_chat_id nullable.

  Задача:
  1. Добавить таблицу или поля для Telegram binding:
     recommended table user_telegram_bindings:
     - user_id primary/FK users.id cascade
     - telegram_chat_id string not null
     - username nullable
     - connected_at
     - updated_at
  2. Добавить CRUD/service минимум:
     - get current user binding
     - upsert current user binding manually via API
     - delete binding
  3. API:
     - GET /api/v1/telegram/binding
     - PUT /api/v1/telegram/binding
     - DELETE /api/v1/telegram/binding
  4. При enqueue заполнять telegram_chat_id из binding.
  5. Tests ownership/current user.

  Не реализуй Telegram bot deep-link webhook в этом слайсе.

  Slice 7: Sender Uses Per-Entry Chat

  Обнови Telegram sender, чтобы он отправлял в per-entry telegram_chat_id, если он задан.

  Контекст:
  - send_pending_telegram_notifications currently receives global chat_id.
  - TelegramNotificationOutbox now can have telegram_chat_id.
  - Some old entries may not have telegram_chat_id.

  Задача:
  1. В sender выбрать target_chat_id:
     - entry.telegram_chat_id если задан
     - иначе global chat_id из settings
  2. Если dry_run false и нет ни per-entry chat, ни global chat, помечать entry failed или retry-safe error согласно текущему стилю.
  3. Tests:
     - per-entry chat overrides global chat
     - fallback to global chat works
     - missing chat does not crash whole batch
  4. Не меняй формат сообщения.

  Сохрани backward compatibility.

  Slice 8: Frontend API And UI

  Добавь frontend управление user interest profiles.

  Контекст:
  - Frontend Vue 3 + TypeScript.
  - Есть filter presets UI/API patterns in App.vue and src/api.
  - Backend endpoints /api/v1/user-interest-profiles готовы.

  Задача:
  1. Добавить TS types and API client for user interest profiles.
  2. В UI добавить минимальный блок "Профили интересов":
     - list
     - create
     - edit active/name/min_rating/telegram_enabled
     - delete
  3. Добавить действие "Создать профиль из текущих фильтров":
     - minPrice -> budget_min
     - maxPrice -> budget_max
     - minRating -> min_rating
     - quick/search query -> desired_keywords if reasonable
     - category/status where available -> target_categories if currently represented in filters
  4. Использовать существующий визуальный стиль.
  5. Validation:
     - pnpm type-check/build or smallest existing frontend check.

  Не трогай datagrid internals сверх необходимого.

  Slice 9: End-To-End Tests And Docs

  Закрой feature тестами и документацией.

  Задача:
  1. Добавить/обновить backend tests:
     - profile CRUD
     - profile matching
     - personal enqueue
     - sender per-entry chat
  2. Обновить docs/telegram-architecture.md если реализация отличается от плана.
  3. Добавить краткую пользовательскую заметку в docs/how-it-works.md:
     - что такое профиль интересов
     - чем он отличается от фильтра таблицы
     - как Telegram решает, что отправлять
  4. Запустить минимальный relevant test set.
  5. Report remaining risks.

  Не добавляй новые крупные фичи.

  Я бы начинал с Slice 1 + Slice 2, потом Slice 3, и только после этого трогал outbox. Это снизит риск сломать текущие Telegram-уведомления.