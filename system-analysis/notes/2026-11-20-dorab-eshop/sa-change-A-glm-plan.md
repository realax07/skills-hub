# Отмена оплаченного заказа с возвратом денег

## Why
Покупатель может отменить заказ только до оплаты: отмена оплаченного (Paid) заказа запрещена доменом и возвращает 500
(`Order.SetCancelledStatus`), а механизма возврата денег нет вовсе — PaymentProcessor только списывает. Оплаченный и не
отправленный заказ нельзя отменить, деньги вернуть нечем. Просьба пользователя (2026-11-26): покупатель отменяет
оплаченный заказ до отгрузки, деньги возвращаются через платёжный процессор.

## What Changes
- Отмена оплаченного заказа: `PUT /api/orders/cancel` из статуса «Оплачен» (Paid) теперь переводит заказ в «Отменён»
  (сейчас — 500). Из «Отправлен» (Shipped) по-прежнему запрещена.
- В событиях отмены появляется признак «был оплачен» (`OrderWasPaid`): доменное `OrderCancelledDomainEvent` и
  интеграционное `OrderStatusChangedToCancelledIntegrationEvent` получают новое поле.
- PaymentProcessor подписывается на событие отмены и имитирует возврат денег для оплаченных заказов (заглушка,
  как и списание: Q-064); для неоплаченных отмен возврата нет — повторная отмена отменённого не возвращает деньги второй раз.
- Защита от гонки отмены и отгрузки: rowversion на сущности `Order`; при конфликте одна из операций получает 500
  (сейчас защиты нет, «последняя запись побеждает» — возможен возврат по уже отгруженному заказу).
- Не меняется: HTTP-контракт `PUT /api/orders/cancel` (маршрут, заголовок x-requestid, коды 200/400/500), набор статусов
  заказа (нового статуса «Возвращён» нет), права на отмену (Q-055 — как в коде: любой вошедший), окно отмены до оплаты,
  витрина WebApp и ClientApp (кнопки отмены оплаченного заказа в UI нет — отдельное изменение, не в этом пакете), вебхуки
  (отмена через них не рассылается).

## Влияние
- `OrderCancelledDomainEvent` (S-01) — новое поле `OrderWasPaid`: задача 1.1, заполняет издатель `Order.SetCancelledStatus` (задача 1.2).
- `OrderStatusChangedToCancelledIntegrationEvent` (S-06) — новое поле `OrderWasPaid` в издателе Ordering.API (задачи 1.3, 1.4);
  новая минимальная копия в PaymentProcessor (задача 1.5); обработчик-подписчик в PaymentProcessor (задача 2.1).
  Копия WebApp не меняется: поле ей не нужно, неизвестные поля JSON пропускаются при десериализации.
- События `OrderShippedDomainEvent`, `OrderStatusChangedToPaidDomainEvent`, `OrderPaymentFailedIntegrationEvent`,
  `OrderPaymentSucceededIntegrationEvent` (S-02…S-05) — не затрагиваются: их поля и обработка не меняются.
- Сущность `Order` (E-01…E-05) — новое поле `Timestamp` (rowversion) заполняется БД автоматически; места создания заказа
  и клиентская копия модели не меняются. Миграция схемы — задача 1.7 (E-06).
- `src/ClientApp → /api/orders` (C-01) — не затрагивается: HTTP-контракт тот же; кнопка «CANCEL ORDER» по-прежнему только
  для Submitted, расширение UI — отдельное изменение.
- `src/WebApp → /api/orders` (C-02) — не затрагивается: читает только GET-модели, PUT-контракт не меняется.
- `src/eShop.AppHost → /api/orders` (C-03) — не затрагивается: маршрут и версия API не меняются.
- Q-049 [блокирует] — изменение опирается: потеря события отмены = невыполненный возврат. Принято до ответа: поведение шины
  не меняется (см. «Открытые вопросы»).
- Q-055 [блокирует] — изменение опирается: права на отмену. Принято до ответа: любой вошедший, как сейчас (риск повышается
  с деньгами — см. «Открытые вопросы»).
- Q-058 [блокирует] — не затрагивается: идемпотентность повторов с тем же x-requestid не меняется.

## Открытые вопросы
- **Q-055 (блокирует, владелец продукта).** Кто может отменять заказы: сейчас любой вошедший может отменить любой заказ по номеру.
  С возвратом денег любой вошедший сможет триггерить возвраты чужих заказов — риск выше прежнего.
  **Принято до ответа:** оставить как в коде (любой вошедший). Если ответ «только владелец» — добавить проверку владельца
  в `CancelOrderCommandHandler` отдельной задачей (дизайн не меняется).
- **Q-064 (блокирует, владелец продукта / архитектор).** Оплата — заглушка: какой будет реальный платёжный шлюз?
  **Принято до ответа:** возврат тоже заглушка — запись в журнале PaymentProcessor; сумма в событие не передаётся.
  Если появится реальный шлюз — отдельное изменение: в событие понадобятся сумма и идемпотентный ключ возврата.
- **Q-049 (блокирует, архитектор).** Шина подтверждает событие даже при ошибке обработки — без повтора и очереди ошибок.
  **Принято до ответа:** не менять. Риск: потерянное событие отмены = заказ «Отменён» без возврата; то же ограничение
  уже действует для событий оплаты. Если нужен надёжный возврат — сначала очередь ошибок/повторы в шине (отдельное изменение).
- **CQ-01 (блокирует, владелец продукта).** Требуется ли защита от одновременной отмены и отгрузки (кто первый сохранил —
  тот и прав, второй получает 500)? **Принято до ответа:** да, rowversion на `Order` (деньги). Если ответ «не нужна» —
  убрать задачи 1.6, 1.7, 4.4 и допущение из сценария «Отмена оплаченного заказа».
- **CQ-02 (уточняет, владелец продукта).** Показывать ли покупателю отдельный признак возврата (текст/статус)?
  **Принято до ответа:** нет — описание прежнее «The order was cancelled.», факт возврата только в журнале процессора.
  Связан с Q-064: при реальном шлюзе вопрос вернётся вместе со статусом «Возвращён».
- **Q-056 (уточняет, владелец продукта).** Код ответа при отказе отмены: 500 или 4xx? **Принято до ответа:** 500,
  как в коде — сценарий «Отмена отправленного заказа» опирается на это допущение.
- **Q-059 (уточняет, владелец продукта).** Повторная отмена отменённого публикует событие снова (возможная ошибка).
  **Принято до ответа:** поведение не менять; двойного возврата нет, потому что признак «был оплачен» при повторе равен false.
  Если ошибку починят (повтор игнорируется) — сценарий «Повторная отмена отменённого заказа» упростится, возврат по-прежнему не повторится.
- **Q-060 (уточняет, владелец продукта).** Окно отмены до оплаты: любой момент или только период ожидания?
  **Принято до ответа:** как в коде — любой статус до «Оплачен». Это изменение окно до оплаты не трогает.

## Impact
- Возможности: `order-management` (MODIFIED «Отмена заказа»), `order-payment` (ADDED «Возврат денег при отмене оплаченного заказа»)
- Код: Ordering.Domain (`Order.cs`, `Events/OrderCancelledDomainEvent.cs`), Ordering.API
  (`Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs`, `Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs`),
  PaymentProcessor (`Program.cs`, `IntegrationEvents/Events/`, `IntegrationEvents/EventHandling/`),
  Ordering.Infrastructure (`EntityConfigurations/OrderEntityTypeConfiguration.cs`, `Migrations/`)
- Проверка: tests/Ordering.FunctionalTests/OrderingApiTests.cs, tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs,
  tests/Application.UnitTests/PaymentProcessorTests.cs; ручной прогон стенда (см. design.md «Проверка»)
# Дизайн: Отмена оплаченного заказа с возвратом денег

## Контекст
Как есть, с багами: `Order.SetCancelledStatus()` бросает `OrderingDomainException` для Paid и Shipped
(`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:142-153`), исключение глотается в `IdentifiedCommandHandler`
→ покупатель видит 500. Событие отмены (`OrderCancelledDomainEvent` → `OrderCancelledDomainEventHandler`) публикует
интеграционное событие только с OrderId/OrderStatus/BuyerName/BuyerIdentityGuid — признака «был оплачен» нет, и в момент
обработки статус уже Cancelled, прежний статус неоткуда взять. PaymentProcessor — заглушка: на «склад подтвердил»
публикует успех/отказ из настройки `PaymentOptions.PaymentSucceeded`, никакого возврата нет (Q-064). Защиты от
конкурентных изменений нет во всей системе («последняя запись побеждает», data.md): одновременные отмена и отгрузка
читают один и тот же статус Paid, и обе проходят.

## Решения
- **Признак «был оплачен» через доменное событие.** `OrderCancelledDomainEvent` получает поле `OrderWasPaid bool`;
  `Order.SetCancelledStatus()` захватывает статус до перехода и передаёт его в событие. Отвергнуто: читать прежний
  статус в `OrderCancelledDomainEventHandler` — там заказ уже Cancelled (репозиторий возвращает изменённую сущность);
  публиковать отдельное событие «возврат нужен» — лишний контракт при живом событии отмены.
- **Возврат — имитация в PaymentProcessor (Q-064).** Новый обработчик `OrderStatusChangedToCancelledIntegrationEventHandler`:
  при `OrderWasPaid = true` пишет в журнал «возврат выполнен», иначе — «заказ не был оплачен». Сумма и реквизиты
  в событие не передаются. Отвергнуто: новое событие «возврат выполнен» обратно в Ordering — покупатель и так видит
  статус «Отменён», а при появлении реального шлюза контракт возврата (сумма, идемпотентный ключ) всё равно переделывать.
- **Без нового статуса «Возвращён».** Заказ остаётся в едином статусе Cancelled. Отвергнуто: новый статус сломал бы
  CSS-классы витрины (`Status.ToLower()`, Orders.razor), уведомления и все спеки переходов — несоразмерно задаче.
- **Гонка отмены и отгрузки закрывается rowversion.** Поле `Timestamp byte[]` с `IsRowVersion()` на `Order` + миграция.
  Кто сохранил первым — тот и прав; второй получает `DbUpdateConcurrencyException`, которое `IdentifiedCommandHandler`
  уже превращает в `false` → 500 «…failed to process» (отдельный catch не нужен). Запись интеграционного события
  в журнал и публикация после коммита — в одной транзакции с заказом (TransactionBehavior), поэтому при конфликте
  фантомных событий отмены/отгрузки в шину не уйдёт. Отвергнуто: ничего не делать — реальный возврат денег по
  отгруженному заказу; SELECT FOR UPDATE — блокировки выходят за принятый стиль кодовой базы.
- **Повторная отмена отменённого не возвращает деньги.** При повторе прежний статус — Cancelled, `OrderWasPaid = false`,
  процессор возврат не выполняет. Двойной возврат невозможен даже при повторной публикации события (Q-059, Q-066).
- **Описание заказа прежнее.** «The order was cancelled.» без упоминания возврата (CQ-02).

## Данные и контракты
- **Сущность `Order`**: было — без поля версионности; стало — `Timestamp byte[]`, конфигурация
  `OrderEntityTypeConfiguration.Property(o => o.Timestamp).IsRowVersion()`, миграция `AddOrderRowVersion` в
  `src/Ordering.Infrastructure/Migrations`. Существующие строки: столбец добавится с NULL, EF заполнит при первом
  обновлении; данные не переносятся. Места создания (E-01…E-04) поле не заполняют — его генерирует БД; в клиентскую
  копию `Order` (E-05, src/ClientApp/Models/Orders/Order.cs) и вью-модели (`OrderViewModel`) поле не попадает.
- **Доменное событие `OrderCancelledDomainEvent`** (S-01): было — `Order Order`; стало — `Order Order`, `OrderWasPaid bool`.
  Подписчик один: `OrderCancelledDomainEventHandler`.
- **Интеграционное событие `OrderStatusChangedToCancelledIntegrationEvent`** (S-06): было — `OrderId int, OrderStatus,
  BuyerName string, BuyerIdentityGuid string`; стало — + `OrderWasPaid bool`.
  Копии: Ordering.API (издатель — задача 1.3, передаёт обработчик — задача 1.4), PaymentProcessor (новая минимальная
  копия `OrderId int, OrderWasPaid bool` — задача 1.5, остальные поля процессору не нужны, как и у его копии события
  «склад подтвердил»), WebApp — не меняется: неизвестные поля JSON пропускаются десериализатором, поле WebApp не нужно.
- **Вход `PUT /api/orders/cancel`** — не меняется: тот же маршрут, заголовок x-requestid, те же коды (200/400/500).
  Меняется только допустимый исходный статус (Paid больше не отказ).
- **Совместимость**: старые события отмены без `OrderWasPaid` десериализуются в PaymentProcessor как `false`
  (возврата нет) — выкатка безопасна в любом порядке сервисов. Старые клиенты контракта HTTP не замечают изменений.

## Риски
- **Гонка отмена/отгрузка**: закрывается rowversion, но поле версионности действует на всех писателей `Order`:
  внутренние обработчики переходов (SetPaid, SetStockConfirmed…) при редком конфликте упадут с исключением, и событие
  не повторяется (Q-049) — переход потеряется вместо прежнего тихого затирания. Принято: интервалы между переходами
  одного заказа — минуты, конфликт возможен только в окне миллисекунд, а прежнее поведение молча портило данные.
- **Потеря события отмены (Q-049)**: возврат не выполнится, заказ останется «Отменён» без денег — то же системное
  ограничение, что для событий оплаты. Владельцу — вопрос в proposal.
- **Права (Q-055)**: любой вошедший может отменить любой заказ → с этим изменением — триггерить возвраты чужих заказов.
  Владельцу — вопрос в proposal; дизайн прав не меняет.
- **Повторы**: повтор с тем же x-requestid возвращает 200 без выполнения команды (Q-058) — двойного возврата нет;
  с новым x-requestid — см. решение про `OrderWasPaid = false`.
- **Выкатка**: PaymentProcessor можно выкатить раньше Ordering (события без поля → false, возврата нет) и позже
  (поле появится вместе с новым поведением Ordering). Откат: миграция обратима (удалить столбец), поведение
  откатывается вместе с кодом Ordering.API/Domain; обработчик PaymentProcessor после отката просто перестанет
  получать события с `OrderWasPaid = true`.

## Проверка
- Тесты по сценариям дельты «Отмена заказа»: функционально — отмена оплаченного даёт 200 и статус Cancelled,
  отмена отправленного даёт 500, отмена до оплаты и повторная отмена не изменились (OrderingApiTests,
  OrdersWebApiTest); юнит — `SetCancelledStatus` из Paid не бросает, из Shipped бросает.
- Тесты по сценариям ADDED «Возврат денег при отмене оплаченного заказа»: лог возврата при `OrderWasPaid = true`,
  отсутствие возврата при `false` (PaymentProcessorTests).
- Тест rowversion: два экземпляра контекста изменяют один заказ, второе сохранение бросает `DbUpdateConcurrencyException`.
- Ручной прогон стенда (aspire): оформить заказ, дождаться статуса Paid (заглушка оплаты ~10 с), вызвать
  `PUT /api/orders/cancel` — 200; в журнале PaymentProcessor запись о возврате; заказ «Отменён» на витрине
  (список обновится по событию). Отмена уже отправленного заказа — 500.
- test-cases/ нет (qa-scan не запускался), design-context/ нет — проверка интерфейса не требуется.
## 1. Данные и контракты
- [ ] 1.1 Добавить поле `OrderWasPaid bool` в `OrderCancelledDomainEvent` (конструктор и свойство) —
  `src/Ordering.Domain/Events/OrderCancelledDomainEvent.cs`. Готово, когда: проект Ordering.Domain собирается,
  единственный подписчик `OrderCancelledDomainEventHandler` обновлён компилятором в задаче 1.4 (без значения по умолчанию).
- [ ] 1.2 Реализовать в домене требование «Отмена заказа»: в `Order.SetCancelledStatus` разрешить переход из «Оплачен»
  (запрет оставить только для «Отправлен») и передать в `OrderCancelledDomainEvent` признак
  `OrderWasPaid = (статус до перехода == Paid)` —
  `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs`, `Класс.Метод Order.SetCancelledStatus`. Готово, когда:
  сценарии «Отмена оплаченного заказа» и «Отмена отправленного заказа» выполняются на уровне домена;
  юнит-тест: из Paid не бросает и ставит `OrderWasPaid = true`, из Shipped бросает `OrderingDomainException`,
  из StockConfirmed ставит `OrderWasPaid = false`.
- [ ] 1.3 Добавить поле `OrderWasPaid bool` в издателя `OrderStatusChangedToCancelledIntegrationEvent` —
  `src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs`. Готово, когда:
  конструктор принимает и сохраняет поле; проект Ordering.API собирается.
- [ ] 1.4 Передать `domainEvent.OrderWasPaid` в интеграционное событие —
  `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs`, `Класс.Метод OrderCancelledDomainEventHandler.Handle`.
  Готово, когда: требование «Отмена заказа», сценарий «Отмена оплаченного заказа» (AND: событие с признаком «был оплачен»).
- [ ] 1.5 Создать минимальную копию события `OrderStatusChangedToCancelledIntegrationEvent` (поля `OrderId int`,
  `OrderWasPaid bool`) — `src/PaymentProcessor/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs`
  (по образцу соседней копии `OrderStatusChangedToStockConfirmedIntegrationEvent`). Готово, когда: проект PaymentProcessor собирается.
- [ ] 1.6 Добавить в `Order` поле `Timestamp byte[]` и включить версионность
  (`OrderEntityTypeConfiguration.Property(o => o.Timestamp).IsRowVersion()`) —
  `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs`,
  `src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs`. Готово, когда: модель собирается,
  конфигурация применена (решение по гонке отмены/отгрузки, CQ-01).
- [ ] 1.7 Сгенерировать миграцию `AddOrderRowVersion` — `src/Ordering.Infrastructure/Migrations`
  (`dotnet ef migrations add AddOrderRowVersion -p src/Ordering.Infrastructure -s src/Ordering.API`). Готово, когда:
  миграция и снимок схемы созданы, `dotnet build` проходит (impact E-06).

## 2. Поведение
- [ ] 2.1 Реализовать требование «Возврат денег при отмене оплаченного заказа»: обработчик `OrderStatusChangedToCancelledIntegrationEventHandler` в `src/PaymentProcessor/IntegrationEvents/EventHandling/` — при `OrderWasPaid` запись в журнал о выполненном возврате
  по `OrderId`, иначе запись, что заказ не был оплачен; ничего не публиковать. Регистрация подписки
  `AddSubscription<OrderStatusChangedToCancelledIntegrationEvent, …>` — `src/PaymentProcessor/Program.cs`.
  Готово, когда: сценарии «Возврат оплаченного заказа» и «Отмена неоплаченного заказа» выполняются (после задач 1.5).

## 3. Вызывающие и подписчики
Задач нет: все вызывающие входа не затрагиваются (impact C-01 ClientApp, C-02 WebApp, C-03 шлюз — HTTP-контракт и версия API
не меняются); копия события в WebApp остаётся без нового поля (неизвестные поля JSON пропускаются, см. proposal «Влияние»).

## 4. Проверка
- [ ] 4.1 Функциональные тесты отмены — `tests/Ordering.FunctionalTests/OrderingApiTests.cs`: добавить тесты
  «отмена оплаченного заказа» (заказ в Paid → `PUT /api/orders/cancel` → 200 и статус Cancelled) и «отмена отправленного
  заказа» (→ 500 «Cancel order failed to process.»); проверить, что существующие `CancelWithEmptyGuidFails`,
  `CancelNonExistentOrderFails` остались зелёными. Готово, когда: требование «Отмена заказа», сценарии «Отмена
  оплаченного заказа» и «Отмена отправленного заказа» (после задач 1.2–1.4, 1.6–1.7).
- [ ] 4.2 Юнит-тесты API — `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs`: обновить ожидания, если есть
  тесты на отказ отмены оплаченного заказа. Готово, когда: все тесты класса зелёные.
- [ ] 4.3 Тесты процессора — `tests/Application.UnitTests/PaymentProcessorTests.cs`: добавить тесты обработчика из 2.1 —
  `OrderWasPaid = true` → запись лога о возврате и ни одной публикации в шину; `OrderWasPaid = false` → запись «не был
  оплачен». Готово, когда: требование «Возврат денег при отмене оплаченного заказа», сценарии «Возврат оплаченного
  заказа», «Отмена неоплаченного заказа» (после задачи 2.1).
- [ ] 4.4 Тест версионности — `tests/Ordering.FunctionalTests/OrderingApiTests.cs` (или класс
  `OrderingConcurrencyTests` там же): загрузить один заказ двумя экземплярами контекста, сохранить оба изменения —
  второе бросает `DbUpdateConcurrencyException`. Готово, когда: тест воспроизводит конфликт отмены и отгрузки;
  поведение при конфликте — 500 одной из операций (после задач 1.6–1.7).

## 5. Слой контекста
- [ ] 5.1 Обновить system-context/trace.md: строки изменённых и новых требований → код и тесты
  (order-management «Отмена заказа», order-payment «Возврат денег при отмене оплаченного заказа»)
- [ ] 5.2 Пересобрать слой, если установлен sa-scan: contracts.py scan . и plan.py guide . (иначе — пункт в отчёте); check.py . без ошибок
# Влияние изменения `cancel-paid-order`

Собрано `change.py analyze` из слоя sa-scan. Затронуто: возможности `order-management`, `order-payment`; входы http:PUT /api/orders/cancel; события OrderStatusChangedToCancelledIntegrationEvent; сущности Order.
У каждого пункта — **Решение**: `задача N.N` (номер из tasks.md, можно несколько) или `не затрагивается: <почему>`.
Для вопросов [блокирует]: изменение на него не опирается — `не затрагивается: <почему>`; опирается — `ответ: …` (человек ответил)
или `в proposal: <что принято до ответа>` (тогда вопрос — в «Открытые вопросы» proposal и в чат).
Повторный `analyze` обновит пункты и сохранит решения. Пункты, которых нет в слое, добавь сам в конце с буквой X (X-01…).


## Кто вызывает затронутые входы

- [ ] C-01 `src/ClientApp → /api/orders` — клиентское приложение <!-- key: caller:src/ClientApp → /api/orders -->
  - опирается на: только версия 1.0 (`api-version=1.0`, src/ClientApp/Services/Order/OrderService.cs:14). Страница заказа читает `Order` с JSON-именами `status`, `ordernumber`, `date`, `total`, `items`, `city`, `street`, `state`, `country`, `zipCode` (src/ClientApp/Models/Orders/Order.cs:13-50); сервер отдаёт `Status`, `OrderNumber`, `Zipcode`, `OrderItems` (src/Ordering.API/Application/Queries/OrderViewModel.cs:12-23): `status`, `ordernumber`, `zipCode` совпадают только без учёта регистра, а `items` клиента и `OrderItems` сервера различаются по имени — список позиций на клиенте может не заполняться. Кнопка «CANCEL ORDER» видна только когда `status` равен `Submitted` без учёта регистра (src/ClientApp/ViewMode
  - где: src/ClientApp/Services/Order/OrderService.cs:13
  - **Решение:** не затрагивается: HTTP-контракт `PUT /api/orders/cancel` не меняется (маршрут, x-requestid, коды 200/400/500); кнопка «CANCEL ORDER» остаётся только для Submitted — расширение UI вне скоупа (proposal «What Changes»)
- [ ] C-02 `src/WebApp → /api/orders` <!-- key: caller:src/WebApp → /api/orders -->
  - опирается на: `GET api/Orders/` в `OrderRecord(OrderNumber, Date, Status, Total)` (src/WebApp/Services/OrderingService.cs:9, 21-25) — форма `OrderSummary` сервера; список заказов выводит их и строит CSS-класс из `Status.ToLower()` (src/WebApp/Components/Pages/User/Orders.razor:48-52), то есть новый статус без CSS-класса отрисуется без стиля. `POST` создания заказа шлёт `x-requestid` и тело `CreateOrderRequest` (OrderingService.cs:12-18); ответ не проверяется, `EnsureSuccess` нет — а сервер на невалидный заказ всё равно отвечает 200 (см. заметку под `POST /api/orders`). Версия 1.0 через `AddApiVersion(1.0)` (src/WebApp/Extensions/Extensions.cs:38-40). Сломается при: переименовании `OrderNumber`/`Status`/`T
  - где: src/WebApp/Services/OrderingService.cs:5
  - **Решение:** не затрагивается: WebApp читает только GET-модели (`OrderSummary`, `Order`), PUT-контракт и ответы GET не меняются; нового статуса нет (Cancelled уже есть с CSS-классом); копия события в WebApp остаётся без нового поля — неизвестные поля JSON пропускаются при десериализации
- [ ] C-03 `src/eShop.AppHost → /api/orders` <!-- key: caller:src/eShop.AppHost → /api/orders -->
  - опирается на: конфигурация шлюза: `/api/orders/{*any}` → ordering-api, пропускает только `api-version` 1.0/1 (src/eShop.AppHost/Extensions.cs:155-156); авторизация — на стороне сервиса (`RequireAuthorization`). Сломается при: выпуске v2 заказов — шлюз его не пропустит, пока не поменять значения здесь.
  - где: src/eShop.AppHost/Extensions.cs:155
  - **Решение:** не затрагивается: маршрут `/api/orders/{*any}` и версия API не меняются

## События: публикуемые и названные

- [ ] S-01 `OrderCancelledDomainEvent` (внутреннее) <!-- key: event:OrderCancelledDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:3 (MediatR → OrderCancelledDomainEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** задачи 1.1 (поле `OrderWasPaid bool` в событии), 1.2 (издатель `Order.SetCancelledStatus` захватывает статус до перехода); суммы не добавляем — возврат заглушка (Q-064, proposal)
- [ ] S-02 `OrderShippedDomainEvent` (внутреннее) <!-- key: event:OrderShippedDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderShippedDomainEventHandler.cs:3 (MediatR → OrderShippedDomainEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: событие отгрузки и его подписчик не меняются
- [ ] S-03 `OrderStatusChangedToPaidDomainEvent` (внутреннее) <!-- key: event:OrderStatusChangedToPaidDomainEvent -->
  - поля: OrderId int, OrderItems IEnumerable<OrderItem>
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderStatusChangedToPaidDomainEventHandler.cs:3 (MediatR → OrderStatusChangedToPaidDomainEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: переход в «Оплачен» не меняется
- [ ] S-04 `OrderPaymentFailedIntegrationEvent` <!-- key: event:OrderPaymentFailedIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderPaymentFailedIntegrationEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: поля и обработка события отказа оплаты не меняются
- [ ] S-05 `OrderPaymentSucceededIntegrationEvent` <!-- key: event:OrderPaymentSucceededIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderPaymentSucceededIntegrationEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: поля и обработка события успеха оплаты не меняются
- [ ] S-06 `OrderStatusChangedToCancelledIntegrationEvent` <!-- key: event:OrderStatusChangedToCancelledIntegrationEvent -->
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs:5 (обработчик интеграционного события → OrderStatusChangedToCancelledIntegrationEventHandler)
  - проверь: хватит ли этих полей новому поведению? (возврату нужны ссылка на платёж и сумма, уведомлению — получатель…) Не хватает — это задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** задачи 1.3 (издатель Ordering.API + `OrderWasPaid bool`), 1.4 (передача признака в `OrderCancelledDomainEventHandler`), 1.5 (новая минимальная копия в PaymentProcessor), 2.1 (новый подписчик PaymentProcessor); копия WebApp — не затрагивается: поле ей не нужно, неизвестные поля JSON пропускаются при десериализации

## Сущности: где поле потеряется молча

- [ ] E-01 `Order` создаётся: `CheckoutViewModel.InitializeAsync` src/ClientApp/ViewModels/CheckoutViewModel.cs:70 <!-- key: create:Order:`CheckoutViewModel.InitializeAsync` src/ClientApp/ViewModels/CheckoutViewModel.cs:70 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: новое поле `Timestamp` (rowversion) генерирует БД — при создании не заполняется
- [ ] E-02 `Order` создаётся: `CreateOrderCommandHandler.Handle` src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:40 <!-- key: create:Order:`CreateOrderCommandHandler.Handle` src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:40 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: `Timestamp` генерирует БД — при создании не заполняется
- [ ] E-03 `Order` создаётся: `OrderQueries.GetOrderAsync` src/Ordering.API/Application/Queries/OrderQueries.cs:15 <!-- key: create:Order:`OrderQueries.GetOrderAsync` src/Ordering.API/Application/Queries/OrderQueries.cs:15 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: `Timestamp` генерирует БД — при создании не заполняется
- [ ] E-04 `Order` создаётся: `Order.NewDraft` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:39 <!-- key: create:Order:`Order.NewDraft` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:39 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: черновик не сохраняется и без БД; `Timestamp` генерирует БД
- [ ] E-05 `Order` → копия `Order` (src/ClientApp/Models/Orders/Order.cs:5) <!-- key: copy:Order:Order:src/ClientApp/Models/Orders/Order.cs -->
  - общих полей 2 из 18, нет: address, buyer, buyerid, description, isdraft, paymentid
  - **Решение:** не затрагивается: `Timestamp` не попадает ни в JSON-модель ClientApp, ни во вью-модели (`OrderViewModel` не меняется)
- [ ] E-06 `Order` миграция схемы: src/Ordering.Infrastructure/Migrations: миграций 4, последние: 20231026091055_Outbox.cs, 20240106121712_UseEnumForOrderStatus.cs; схема или снимок: src/Ordering <!-- key: migr:Order -->
  - новая миграция, снимок схемы сверить с моделью
  - **Решение:** задачи 1.6 (rowversion-поле и конфигурация `IsRowVersion()`), 1.7 (миграция `AddOrderRowVersion`)

## Блокирующие вопросы затронутых возможностей — опирается ли изменение?

- [ ] Q-049 [блокирует] Шина подтверждает сообщение даже при ошибке обработки — без повтора и очереди ошибок: так задумано? <!-- key: q:Q-049 -->
  - допущение: событие теряется, заказ остаётся в AwaitingValidation, как в коде
  - статус: открыт
  - **Решение:** в proposal: принято до ответа — шину не меняем; риск «заказ Отменён без возврата» назван в proposal и design (риски); сценарий «Ошибка обработки события возврата» в дельте order-payment опирается на это допущение
- [ ] Q-055 [блокирует] Кто может отменять, отгружать и читать чужие заказы? <!-- key: q:Q-055 -->
  - допущение: спека описывает код: любой вошедший пользователь может отменить, отгрузить и прочитать любой заказ по номеру
  - статус: открыт
  - **Решение:** в proposal: принято до ответа — права не меняем (любой вошедший, как в коде); с деньгами риск «чужие возвраты» назван в proposal; если ответ «только владелец» — отдельная задача проверки владельца в `CancelOrderCommandHandler`
- [ ] Q-058 [блокирует] Повтор с тем же x-requestid после неудачи должен повторить действие? <!-- key: q:Q-058 -->
  - допущение: спека описывает код: повтор после неудачи даёт 200 и не выполняет команду
  - статус: открыт
  - **Решение:** не затрагивается: идемпотентность повторов (`RequestManager`, `CreateResultForDuplicateRequest`) не меняется; двойного возврата при повторе с тем же x-requestid нет
- [ ] Q-064 [блокирует] Оплата — заглушка (исход из настроек, фиксированная тестовая карта): какой будет реальная оплата? <!-- key: q:Q-064 -->
  - допущение: оплата имитируется, внешний платёжный шлюз не используется и не описан
  - статус: открыт
  - **Решение:** в proposal: принято до ответа — возврат тоже заглушка (запись в журнале PaymentProcessor), сумма в событие не передаётся; при реальном шлюзе — отдельное изменение с суммой и идемпотентным ключом возврата

## Уточняющие вопросы по затронутым возможностям

- Q-056 Для отказа в отмене и отгрузке нужен код 500 или 4xx (например 409)? — опирается: сценарий «Отмена отправленного заказа» — 500 (допущение) — в proposal
- Q-057 Если обработчик события отмены упал, статус «Отменён» должен откатиться? — не затрагивается: поведение обработчика не меняется, сценарий сохранён как есть
- Q-059 Повторная отмена уже отменённого заказа: допустима ли повторная публикация события? — опирается: сценарий сохранён (событие публикуется снова), возврат при повторе исключён через `OrderWasPaid = false` — в proposal
- Q-060 Отмена пользователем разрешена в любой момент до оплаты или только в период ожидания? — опирается: текст требования до оплаты сохранён с допущением — в proposal
- Q-061 Заказ отменён до ответа оплаты: оплату молча принимать или считать ошибкой? — не затрагивается: переход в «Оплачен» не меняется
- Q-063 Пауза 10 секунд перед переходом в «Оплачен» — имитация или ошибка? — не затрагивается: переход в «Оплачен» не меняется
- Q-066 Повторные события оплаты: допустимо ли повторное событие отмены и повторная публикация статуса? — не затрагивается: события оплаты не меняются; повторная отмена исключает двойной возврат через `OrderWasPaid = false`

## Тесты затронутых возможностей (запустить и обновить)

- order-management: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs — задачи 4.1, 4.2, 4.4
- order-payment: tests/Application.UnitTests/PaymentProcessorTests.cs — задача 4.3

## Код затронутых возможностей

Файлы из трассировки и обработчиков — по ним волны и пересечения с другими изменениями.

- src/EventBusRabbitMQ/EventBusOptions.cs — не затрагивается: шина не меняется
- src/EventBusRabbitMQ/RabbitMQEventBus.cs — не затрагивается: шина не меняется
- src/Ordering.API/Apis/OrdersApi.cs — не затрагивается: контракт входа не меняется
- src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs — не затрагивается: домен проверяет статусы сам
- src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs — не затрагивается: catch уже превращает конфликт rowversion в 500
- src/Ordering.API/Application/Commands/SetPaidOrderStatusCommandHandler.cs — не затрагивается: переход в Paid не меняется (риск конфликта — design «Риски»)
- src/Ordering.API/Application/Commands/ShipOrderCommandHandler.cs — не затрагивается: отгрузка не меняется (риск конфликта — design «Риски»)
- src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs — не затрагивается
- src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs — не затрагивается
- src/Ordering.API/Application/Queries/OrderQueries.cs — не затрагивается: вью-модели не меняются
- src/Ordering.API/Application/Validations/CancelOrderCommandValidator.cs — не затрагивается: валидация номера не меняется
- src/Ordering.API/Application/Validations/ShipOrderCommandValidator.cs — не затрагивается
- src/Ordering.API/Infrastructure/Services/IdentityService.cs — не затрагивается
- src/Ordering.API/Program.cs — не затрагивается: новых подписок в Ordering.API нет
- src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs — задачи 1.2 (SetCancelledStatus), 1.6 (Timestamp)
- src/Ordering.Infrastructure/Idempotency/RequestManager.cs — не затрагивается
- src/PaymentProcessor/IntegrationEvents/EventHandling/OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs — не затрагивается: обработчик списания не меняется
- src/PaymentProcessor/PaymentOptions.cs — не затрагивается: настройка списания не меняется
- src/PaymentProcessor/appsettings.json — не затрагивается

## Дополнительно (нет в слое)

- [ ] X-01 Гонка отмены и отгрузки: `PUT /api/orders/cancel` и `PUT /api/orders/ship` одновременно читают статус Paid
  без блокировок — «последняя запись побеждает»: возможен возврат денег по уже отгруженному заказу (или отгрузка
  отменённого). В слое числится как общее ограничение конкурентности, пункта влияния не было. <!-- key: x:race-cancel-ship -->
  - **Решение:** задачи 1.6, 1.7 (rowversion на Order) и 4.4 (тест конфликта); конфликт → `DbUpdateConcurrencyException` → 500 одной из операций (IdentifiedCommandHandler); поведение зафиксировано в сценарии «Отмена оплаченного заказа» AND и в proposal (CQ-01)
