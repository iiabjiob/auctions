Я бы не тянул все детали со всех площадок.
  Но первичный список лотов и минимальные поля для оценки тянуть стоит.

  ## Мой практический ответ

  ### Да, делаем первую фильтрацию

  Но фильтрация должна быть локальной, после загрузки минимального списка лотов.

  То есть:

  1. С площадки забираем список лотов
     Минимум: название, цена, статус, дедлайн, регион, категория, ссылка, id.
  2. В локальной БД делаем первичную фильтрацию
      - явные неподходящие лоты отбрасываем сразу
      - подозрительные / нерелевантные помечаем ниже
      - подходящие отправляем в enrichment / scoring
  3. Детали тянем только для перспективных лотов
      - если не хватает evidence для рейтинга
      - если лот дорогой / интересный
      - если TTL истек
      - если пользователь явно открыл карточку и запросил refresh

  ———

  ## Почему не стоит тянуть “все данные”

  Потому что это:

  - сильно увеличивает число запросов,
  - повышает риск бана,
  - замедляет sync,
  - создает много мусорных данных, которые потом все равно не нужны.

  Если тянуть все детали для всех лотов, ты фактически превращаешь систему в постоянный скрапер. Это плохая модель для стабильной работы.

  ———

  ## Почему не стоит фильтровать только на стороне площадки

  Потому что:

  - площадка обычно не знает твои реальные критерии,
  - часть полезных лотов можно отсеять слишком рано,
  - у разных пользователей разные интересы.

  Если фильтровать только на стороне source, ты потеряешь гибкость.
  Если фильтровать только локально, ты сохраняешь гибкость, но не сливаешь лишние запросы наружу.

  ———

  ## Правильная схема для твоего случая

  Я бы делал двухступенчатую модель:

  ### Уровень 1. Глобальная фильтрация

  Это фильтр для всей системы, не завязанный на конкретного пользователя.

  Например:

  - не тот источник
  - явно не тот тип актива
  - отменен / архив
  - нет цены
  - мусорный статус
  - слишком мало данных, чтобы вообще иметь смысл дальше смотреть

  Это можно считать системным “неинтересно вообще”.

  ### Уровень 2. Профиль пользователя

  Это уже персональный уровень:

  - нужные регионы
  - категории
  - бюджет
  - риск
  - ключевые слова
  - дистанция
  - стратегия

  Это не надо использовать как жесткий early-drop для всех, если у тебя будет несколько пользователей.
  Лучше использовать это в scoring / ranking, а не на этапе ingest.

  ———

  ## Что я рекомендую именно тебе

  ### Для системы в целом

  - Забирать список лотов целиком по нужным источникам.
  - Не тянуть детали у всех.
  - Делать локальную первичную фильтрацию.
  - Enrichment запускать только для тех, кто прошел первый проход.

  ### Для разных пользователей

  Если у тебя:

  - один профиль,
  - или один основной пользователь,

  то можно быть агрессивнее и раньше отсекать лишнее.

  Если пользователей будет много, то:

  - не режь слишком рано по пользовательским условиям
  - лучше храни лот локально
  - а дальше уже считай score/fit под каждого профиля.

  ———

  ## Простая формула

  Я бы сделал так:

  > **Список лотов — берем широко.
  > Детали — берем узко.
  > Рейтинг — считаем локально и персонально.

  Это лучший баланс между:

  - скоростью,
  - баноустойчивостью,
  - и полезностью для пользователя.

  ## Что бы я не делал

  - не скачивал бы детали всех лотов подряд,
  - не делал бы слишком частые refresh,
  - не завязывал бы раннюю отбраковку только на один пользовательский профиль, если планируется мультипользовательская система.

  ———

  ## Итог

  Если коротко:
  да, первую фильтрацию делать надо, но не на уровне “не забирать данные вообще”, а на уровне “забрать минимум, а детали — только для перспективных”.

  Если хочешь, я могу дальше предложить конкретную схему фильтрации в 3 слоя:

  1. глобальный системный фильтр,
  2. enrichment-фильтр,
  3. profile scoring,
     с примерами полей, которые где должны работать.


› для пользователя в системе будет быстрый репорт - ключевая зада раньше рынка видеть интересные лоты, быстро принимать решение по осмотру,
  расчету, подаче заявки и максимальной цене покупки. так же в ближайшем будущем я подключю телеграм канал и туда долнжы будут скидываться интересные лоты


• Это как раз хорошо ложится на текущую архитектуру.

  Если цель пользователя такая:

  - быстро увидеть интересные лоты раньше рынка
  - быстро понять, стоит ли ехать на осмотр
  - быстро решить, считать ли экономику
  - быстро принять решение по подаче заявки и максимальной цене
  - потом еще отправлять интересные лоты в Telegram

  то система должна работать не как “каталог всех лотов”, а как машина принятия решения.

  ## Как я бы это формулировал

  Для пользователя каждый лот должен превращаться в короткую карточку решения:

  - интересно или нет
  - почему интересно
  - что проверить руками
  - можно ли ехать на осмотр
  - какая максимальная цена покупки
  - какой риск
  - до какого дедлайна нужно успеть

  То есть не просто “показать лот”, а сразу дать следующий шаг.

  ———

  ## Что это значит для системы

  ### 1. Быстрый репорт

  Это должен быть основной пользовательский экран/выдача.

  Он строится из локальных данных:

  - базовые данные лота
  - LotEvidence
  - профиль пользователя
  - экономика
  - риск
  - дедлайн
  - profile_fit

  Итог:
  система не просто сортирует лоты, а показывает, какие из них достойны внимания прямо сейчас.

  ———

  ### 2. Telegram-канал

  Telegram лучше сделать не отдельной логикой, а вторым выходом из той же аналитики.

  То есть:

  - воркер считает рейтинг локально
  - система понимает, что лот “достоин уведомления”
  - если да, то отправляет короткое сообщение в Telegram

  ———

  ## Что нельзя делать в Telegram

  Не надо слать туда все подряд. Иначе будет шум и пользователь перестанет смотреть канал.

  В Telegram должны попадать только:

  - высокоприоритетные лоты
  - лоты с близким дедлайном
  - лоты, которые хорошо подходят под профиль
  - новые лоты с сильной экономикой
  - лоты, где изменилось что-то важное: цена, статус, дедлайн, документы

  ———

  ## Какой формат сообщения я бы рекомендовал

  Короткий и практичный:

  - название лота
  - источник
  - регион
  - цена
  - дедлайн
  - score
  - estimated ROI
  - max buy price
  - 1-3 причины, почему лот интересен
  - 1-2 риска
  - ссылка на карточку в системе

  Пример логики:

  > Экскаватор, Московская область
  > Score: 91
  > ROI: 48%
  > Max buy: 1.8 млн
  > Причины: подходит по региону, высокий дисконт, дедлайн через 2 дня
  > Риски: нужны документы, юридический риск средний

  ———

  ## Какая архитектура для этого правильная

  Я бы разделил на 3 слоя:

  ### Слой 1. Отбор

  Лот вообще достоин внимания или нет.

  ### Слой 2. Подготовка решения

  Для интересных лотов система считает:

  - экономику
  - риски
  - max price
  - fit под профиль

  ### Слой 3. Доставка

  - в UI показываем полный репорт
  - в Telegram отправляем короткий alert

  ———

  ## Важный принцип

  UI и Telegram должны использовать одну и ту же аналитику.

  Не должно быть так, что:

  - в UI один score,
  - а в Telegram другой,
  - а в воркере третий.

  Должна быть одна нормализованная оценка, а потом уже два канала доставки:

  - интерфейс
  - уведомление

  ———

  ## Что я бы сделал дальше

  Для твоего сценария логично добавить 3 сущности результата по каждому лоту:

  1. Decision summary
      - короткая выжимка для пользователя
  2. Action recommendation
      - смотреть / считать / подавать / игнорировать
  3. Notification eligibility
      - отправлять ли в Telegram

  ———

  ## Практическое правило для Telegram

  Я бы сделал Telegram не на все лоты, а только когда выполняется хотя бы одно условие:

  - score выше порога
  - profile_fit высокий
  - дедлайн близко
  - ROI выше порога
  - новый лот и он сразу интересный
  - изменился статус на более важный

  И обязательно:

  - дедупликация
  - лимит на число сообщений
  - не слать один и тот же лот многократно без существенного изменения

  ———

  ## Итог

  Для твоего будущего продукта правильная форма такая:

  > система не просто хранит лоты, а помогает быстро принимать решение;
  > UI дает полный репорт, Telegram дает короткий сигнал по самым интересным лотам.

  Это очень хорошая цель для текущей архитектуры, и она уже почти туда ведет.

  Если хочешь, я могу следующим сообщением предложить конкретную схему “быстрого репорта” по лоту: какие поля там должны быть, в каком порядке, и как из этого
  делать Telegram-сообщение.

### Целевой дизайн

Главная сущность следующего уровня:

Lot Decision Report

Это не новая карточка UI, а backend-контракт:

LotEvidence
+ ScoreBreakdown
+ ScoringProfileFit
+ Economics/MaxBuyPrice
+ RiskSummary
+ Deadlines/Urgency
→ DecisionReport

Он должен отвечать на вопросы:

1. Интересно или нет?
2. Почему?
3. Что сделать дальше?
4. Какая максимальная цена покупки?
5. Стоит ли отправлять в Telegram?
Новые контракты
1. Decision Summary
decision_level:
  ignore | watch | inspect | calculate | bid_candidate

recommendation:
  ignore | monitor | request_docs | inspect | calculate_max_bid | prepare_bid

reasons:
  1–5 коротких причин

risks:
  1–5 коротких рисков

next_actions:
  practical checklist
2. Economics Summary
current_price
estimated_market_value
expected_costs
target_roi
max_buy_price
confidence
missing_inputs
3. Notification Eligibility
should_notify
channel: telegram
reason
dedupe_key
priority
cooldown_until
Реализация по слайсам
Slice 1 — Decision Report contract only
Goal:
Introduce a local-only LotDecisionReport contract without changing runtime behavior.

Important constraints:
- Do NOT change scoring values.
- Do NOT change frontend behavior.
- Do NOT send Telegram messages.
- Do NOT persist decision reports yet.
- Keep this additive and reviewable.
- Existing tests must continue to pass.

Tasks:
1. Add backend schemas for:
   - LotDecisionReport
   - DecisionLevel
   - ActionRecommendation
   - LotDecisionReason
   - LotDecisionRisk
   - LotDecisionNextAction
2. The report should include:
   - lot identity
   - title/source/region/current_price/deadline
   - rating_score/rating_level
   - profile_fit summary if available
   - decision_level
   - recommendation
   - reasons
   - risks
   - next_actions
   - generated_at
3. Add deterministic serialization helper if project style uses it.
4. Do not wire it into API or workers yet.
5. Add focused tests proving:
   - model validates minimal report
   - enums are stable
   - serialization is deterministic
6. Add docs explaining this is the shared output contract for UI and Telegram.

Validation:
- Run relevant backend tests.
- Run compile/import validation.
- Run git diff --check.

Final response format:
- Summary of what changed
- Files changed
- Validation commands run and results
- Risks/follow-up
Slice 2 — Build Decision Report from local data
Goal:
Add a local-only builder that creates LotDecisionReport from existing local analytics.

Important constraints:
- Do NOT change scoring values.
- Do NOT fetch external data.
- Do NOT send notifications.
- Do NOT change frontend behavior.
- Keep this service-only and reviewable.

Tasks:
1. Add build_lot_decision_report(record, detail_cache=None, work_item=None, profile=None).
2. Use only local data:
   - AuctionLotRecord
   - LotEvidence
   - score_breakdown
   - profile_fit helper if profile is provided
   - manual/work-item fields if available
3. Derive conservative decision_level:
   - low score / blockers → ignore/watch
   - good score + near deadline → inspect/calculate
   - high score + good fit → bid_candidate
4. Derive practical next_actions:
   - request documents
   - inspect lot
   - calculate max bid
   - monitor deadline
5. Add tests for:
   - low score → ignore/watch
   - high score → inspect/calculate
   - missing documents → request_docs action
   - profile blocker → downgraded decision
6. Update docs.

Validation:
- Run relevant backend tests.
- Run compile/import validation.
- Run git diff --check.
Slice 3 — Economics / max buy price contract
Goal:
Add a conservative max-buy economics helper for decision reports.

Important constraints:
- Do NOT change existing rating score.
- Do NOT invent market value when missing.
- Do NOT fetch external data.
- Keep output explainable.

Tasks:
1. Add LotEconomicsDecision schema:
   - current_price
   - market_value
   - expected_costs
   - target_roi
   - max_buy_price
   - estimated_profit
   - confidence
   - missing_inputs
2. Add calculate_lot_economics_decision(...).
3. Use manual/work-item economics first if present.
4. If market value is missing, return missing_inputs and low confidence.
5. Add tests:
   - complete inputs produce max_buy_price
   - missing market value does not invent result
   - expected costs reduce max buy price
   - target ROI changes max buy price
6. Wire the economics object into LotDecisionReport builder.
Slice 4 — Notification eligibility contract
Goal:
Add Telegram-ready notification eligibility without sending messages.

Important constraints:
- Do NOT integrate Telegram yet.
- Do NOT send external requests.
- Do NOT change UI.
- Keep this local-only.

Tasks:
1. Add LotNotificationEligibility schema:
   - should_notify
   - priority
   - reasons
   - blockers
   - dedupe_key
   - cooldown_key
2. Add evaluate_lot_notification_eligibility(report, profile=None).
3. Notify only for:
   - high decision level
   - high score/profile fit
   - near deadline
   - meaningful new/changed opportunity
4. Add tests:
   - high-quality report should notify
   - low score should not notify
   - blocker suppresses notification
   - dedupe key is deterministic
5. Add docs explaining Telegram will consume this later.
Slice 5 — Persist decision report snapshot
Goal:
Persist latest LotDecisionReport snapshot for fast UI/Telegram consumption.

Important constraints:
- Do NOT change scoring formulas.
- Do NOT send notifications.
- Keep latest snapshot only unless history already exists.

Tasks:
1. Add table/model:
   - auction_lot_decision_reports
   - lot_record_id
   - profile_hash nullable
   - report_payload JSONB
   - decision_level
   - recommendation
   - notification_should_send
   - report_hash
   - generated_at
2. Add migration.
3. Add upsert helper.
4. Wire report generation after scoring recalculation.
5. Add tests:
   - report snapshot is created
   - unchanged report hash is stable
   - changed score/evidence changes report
Slice 6 — Fast report API
Goal:
Expose read-only decision reports for UI.

Tasks:
1. Add GET /api/v1/auctions/lots/{id}/decision-report
2. Add list endpoint/filter if useful:
   - top decision reports
   - bid candidates
   - inspect candidates
3. Must read local DB only.
4. Add route tests proving no external fetch.
Slice 7 — Telegram message rendering, no sending
Goal:
Render Telegram messages from LotDecisionReport without sending.

Tasks:
1. Add TelegramLotMessage schema/service.
2. Format short message:
   - title
   - region
   - price
   - score
   - decision
   - max buy if available
   - deadline
   - reasons
   - risks
   - link
3. Add tests for formatting and length.
4. Do not call Telegram API yet.
Slice 8 — Telegram outbox
Goal:
Add reliable Telegram outbox, still no direct send from scoring worker.

Tasks:
1. Add telegram_notification_outbox table.
2. Insert notification only when eligibility says should_notify.
3. Add dedupe key and status:
   - pending
   - sent
   - failed
   - skipped
4. Add tests for dedupe/cooldown.
Slice 9 — Telegram sender worker
Goal:
Send pending Telegram outbox messages safely.

Tasks:
1. Add Telegram sender service.
2. Add worker with limit/retry/backoff.
3. Read bot token/chat id from config.
4. Mark sent/failed.
5. Add dry-run mode.
Я бы начал вот с этого

Первый Codex prompt давай такой:

Goal:
Introduce a local-only LotDecisionReport contract that will become the shared output for UI decision reports and future Telegram notifications.

Important constraints:
- Do NOT change scoring formulas or score values.
- Do NOT change frontend behavior.
- Do NOT send Telegram messages.
- Do NOT persist decision reports yet.
- Do NOT fetch external data.
- Keep this additive and reviewable.
- Existing tests must continue to pass.

Tasks:
1. Add backend schemas for:
   - LotDecisionReport
   - DecisionLevel
   - ActionRecommendation
   - LotDecisionReason
   - LotDecisionRisk
   - LotDecisionNextAction
2. The report should include:
   - lot identity: source, auction_id, lot_id, record_id
   - display fields: title, source_title, region, current_price, deadline
   - rating fields: rating_score, rating_level
   - optional profile fields: profile_hash, profile_fit_summary
   - decision_level
   - recommendation
   - reasons
   - risks
   - next_actions
   - generated_at
3. Use Pydantic models consistent with the backend schema style.
4. Add deterministic JSON/hash helper if similar helpers already exist in the project.
5. Do not wire this into workers, API routes, DB models, or frontend yet.
6. Add focused tests proving:
   - minimal valid report can be created
   - enum values are stable
   - serialization/hash is deterministic
   - optional profile fields can be omitted
7. Add backend docs explaining:
   - DecisionReport is the shared decision output for UI and Telegram
   - it is local-only
   - it does not perform scoring, scraping, or notification sending
   - future builders will derive it from LotEvidence, score_breakdown, economics, and profile fit

Validation:
- Run relevant backend tests.
- Run compile/import validation.
- Run git diff --check.

Final response format:
- Summary of what changed
- Files changed
- Validation commands run and results
- Risks/follow-up

Это правильный первый шаг: сначала контракт, потом builder, потом persistence/API/Telegram.