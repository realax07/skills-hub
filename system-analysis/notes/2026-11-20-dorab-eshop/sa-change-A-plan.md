# Отмена оплаченного заказа покупателем с возвратом денег

## Why
Покупатель может отменить заказ только до оплаты (статусы «Оформлен»…«Подтверждён складом»). После оплаты отмена отвечает 500
«Cancel order failed to process.» (order-management, сценарий «Отмена оплаченного заказа»). Запрос: покупатель отменяет заказ и после оплаты,
пока заказ не отправлен; деньги возвращаются через платёжный процессор. Источник — просьба владельца продукта (чат, без уточнений: см. «Открытые вопросы»).

## What Changes
- Отмена заказа из статуса «Оплачен» разрешена (PUT /api/orders/cancel). Из статуса «Отправлен» — по-прежнему нет (500).
- Отмена оплаченного заказа доступна только его владельцу (допущение Q-055; существующая отмена до оплаты поведения не меняет).
- При такой отмене: остаток товаров возвращается в каталог; запускается возврат полной суммы через платёжный процессор
  (новая возможность order-refund: событие запроса возврата, ответ «возврат прошёл / не прошёл», признак возврата у заказа).
- Клиентское приложение (ClientApp) показывает кнопку отмены и для статуса «Оплачен».
- Новое поле у заказа: признак возврата (null, «Запрошен», «Возвращён», «Возврат не прошёл»).
- Нет **BREAKING**: существующие вызовы отмены до оплаты и ответы кодов не меняются; ответ 500 для отгруженного заказа сохраняется.

## Влияние
По пунктам impact.md (все решения — в impact.md и design.md):
- `src/ClientApp → /api/orders` (C-01) — кнопка «CANCEL ORDER» сейчас только для `Submitted`; показать и для `Paid` (задача 3.1).
- `src/WebApp → /api/orders` (C-02) — не затрагивается: интерфейса отмены в WebApp нет, статус «Отменён» уже выводится; новые поля ответа не добавляются.
- `src/eShop.AppHost → /api/orders` (C-03) — не затрагивается: путь, версия API и шлюз не меняются.
- `OrderCancelledDomainEvent` (S-01) — обработчик дополняет интеграционное событие позициями для возврата остатка и запускает возврат (задачи 1.2, 1.3, 2.3).
- `OrderStatusChangedToCancelledIntegrationEvent` (S-09) — новое поле `OrderStockItems` (задачи 1.3, 1.6); у Catalog — новая копия события; WebApp копию не меняет: читает только статус и покупателя, лишнее поле игнорируется.
- `OrderStatusChangedToPaidIntegrationEvent` (S-03), `OrderStatusChangedToPaidDomainEvent` (S-04), события оплаты и склада (S-05…S-08), `OrderShippedDomainEvent` (S-02) — не затрагиваются: их обработка не меняется.
- `Order` (E-01…E-04) — новое поле признака возврата nullable: при создании не заполняется, значение по умолчанию null — не затрагивается (задача 1.1 — миграция).
- Копия `Order` в ClientApp (E-05) — не затрагивается: клиент новое поле не читает (CQ-05).
- Миграция схемы `Order` (E-06) — задача 1.1.
- Блокирующие вопросы: Q-055 и Q-064 — приняты допущения (ниже); Q-058, Q-030, Q-049, Q-095 — не меняются этим изменением, риски записаны.

## Открытые вопросы
Блокирующие (ответ нужен до разработки, допущения приняты и записаны в дельтах пометкой):
- **Q-055** Кто может отменять чужие заказы? Принято: оплаченный заказ отменяет только владелец; для отмены до оплаты поведение как в коде (любой вошедший) — это отдельная дыра безопасности, которую стоит закрыть отдельным изменением.
- **Q-064** Какой платёжный процессор и как он возвращает деньги? В репозитории оплата — заглушка (PaymentProcessor, исход из настройки). **CQ-03**: возврат тоже заглушка, исход из новой настройки `PaymentOptions.RefundSucceeded`. Кто ответит: владелец продукта / тех. лид.

Новые вопросы этого изменения (CQ-…; без ответа — принятое до ответа в колонке справа):
- **CQ-01** (важно, владелец продукта) Отмена оплаченного заказа — до статуса «Отправлен» и на полную сумму, без частичного возврата и без штрафа? Принято до ответа: да, до «Отправлен», полная сумма, без штрафа.
- **CQ-02** (важно, владелец продукта) Нужно ли сообщать вебхук-подписчикам об отмене? Сейчас типов событий отмены в Webhooks.API нет. Принято до ответа: нет, в этом изменении не меняется.
- **CQ-03** (блокирует, см. Q-064) Исход возврата — настройка-заглушка. Принято до ответа: `RefundSucceeded` по умолчанию `true`, как исход оплаты.
- **CQ-04** (важно, тех. лид) Что делать, если возврат не прошёл: повтор, ручной разбор или новый запрос? Принято до ответа: автоповтора нет; заказ остаётся «Отменён» с признаком «Возврат не прошёл»; повторного запроса возврата через API нет (повторная отмена отвечает 200 и возврат не запускает), разбор — вручную через поддержку.
- **CQ-05** (уточняет, владелец продукта) Показывать ли покупателю признак возврата в интерфейсе? Принято до ответа: нет, в этом изменении.
- **CQ-06** (блокирует, риск денег, см. Q-061) Отмена во время оплаты: если пришло «оплата прошла» для уже отменённого заказа, `SetPaidStatus` ничего не делает — деньги списаны, заказ отменён, возврата нет. Принято до ответа: поведение не меняется (как в коде), вариант «возвращать такую оплату» — отдельным изменением. Нужен ответ до выката.

Уже открытые вопросы, на которые опирается изменение, но которые оно не решает: Q-049 (шина без повтора: событие возврата может потеряться, тогда признак останется «Запрошен»), Q-058 (повтор с тем же x-requestid отвечает 200 без действия, возврат не запускает), Q-030 (остаток не резервируется: при параллельных заказах возможен перерасход), Q-095 (подписки вебхуков получают события всех покупателей; изменение рассылку не трогает).

## Impact
- Возможности: `order-management` (MODIFIED «Отмена заказа»), `order-refund` (ADDED «Возврат оплаты при отмене оплаченного заказа», новая возможность), `catalog-stock` (ADDED «Возврат остатка при отмене оплаченного заказа»).
- Код: src/Ordering.API/Apis/OrdersApi.cs, src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs, src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs, src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs, src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs и миграция в src/Ordering.Infrastructure/Migrations, src/PaymentProcessor (новые события, обработчик, PaymentOptions.cs), src/Catalog.API (копия события, обработчик, src/Catalog.API/Extensions/Extensions.cs), src/ClientApp/ViewModels/OrderDetailViewModel.cs и src/ClientApp/Views/OrderDetailView.xaml.
- Проверка: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs, tests/Application.UnitTests/PaymentProcessorTests.cs, tests/Catalog.FunctionalTests (новый тест на возврат остатка), trace.md и пересборка слоя. Тест-кейсы qa-scan и design-context отсутствуют.
# Дизайн: Отмена оплаченного заказа покупателем с возвратом денег

## Контекст
- Отмена (`order-management`, «Отмена заказа»): `Order.SetCancelledStatus` (src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs) кидает исключение для статусов «Оплачен» и «Отправлен»; `IdentifiedCommandHandler` глотает исключение, API отвечает 500 «Cancel order failed to process.» (как в коде, с багом: 500 вместо 4xx — Q-056).
- Остаток (`catalog-stock`): Catalog списывает остаток при событии «Оплачен» (`OrderStatusChangedToPaidIntegrationEventHandler` → `CatalogItem.RemoveStock`). Обратного пополнения при отмене нет; метод `CatalogItem.AddStock` существует, но нигде не вызывается.
- Оплата (`order-payment`): заглушка в PaymentProcessor (исход из `PaymentOptions.PaymentSucceeded`). Возврата денег в репозитории нет (grep по `refund`/`возврат` пуст).
- Подписчики отмены: WebApp (`OrderStatusChangedToCancelledIntegrationEvent`) — статус в списке заказов. Webhooks.API типа события отмены не знает (только `OrderPaid`, `OrderShipped`).
- Шина RabbitMQ без повтора и очереди ошибок (Q-049): событие, потерянное при сбое, не доставляется повторно.

## Решения
1. **Разрешённые статусы для отмены.** Из «Оплачен» отмена разрешена; из «Отправлен» — нет (как сейчас). Остальные статусы — как сейчас (CQ-01).
2. **Владелец для оплаченного заказа.** Проверка `BuyerIdentityGuid` заказа с `sub` токена в `CancelOrderCommandHandler`-пути (передать пользователя из `OrdersApi.CancelOrderAsync` через `IdentityService`). Только для оплаченных заказов; для остальных поведение не меняется (Q-055 — отдельная дыра).
3. **Признак «был оплачен».** `Order.SetCancelledStatus` запоминает, был ли статус «Оплачен», и передаёт его в `OrderCancelledDomainEvent` (поле `WasPaid bool`). Это единственный способ понять, нужен ли возврат и возврат остатка, — `OrderStatus` уже «Отменён» в обработчике.
4. **Возврат остатка.** Интеграционное событие `OrderStatusChangedToCancelledIntegrationEvent` получает поле `OrderStockItems` (ProductId, Units). Заполняется только при `WasPaid`, иначе пусто. Catalog подписывается и вызывает `CatalogItem.AddStock` (уже есть в модели). Без `WasPaid` остаток не трогается — иначе отмена до оплаты увеличила бы остаток, которого не списывали.
5. **Возврат денег.** Новые интеграционные события: `OrderRefundRequestedIntegrationEvent` (OrderId int, Amount decimal; Ordering → PaymentProcessor), `OrderRefundSucceededIntegrationEvent` и `OrderRefundFailedIntegrationEvent` (OrderId int; PaymentProcessor → Ordering). Публикация через журнал событий как у остальных (`OrderingIntegrationEventService`), чтобы не потерять их при коммите.
6. **Признак возврата у заказа.** Новое поле `RefundStatus` (nullable enum: `Requested`, `Refunded`, `RefundFailed`; null = возврата не было). Миграция добавляет колонку без значения по умолчанию (существующие заказы — null).
7. **Исход возврата.** `PaymentOptions.RefundSucceeded` (bool, по умолчанию true) — заглушка, как `PaymentSucceeded` (CQ-03). Без реального процессора возврат не проверяется.
8. **Повтора нет.** Неудачный возврат не повторяется (CQ-04).

## Данные и контракты
- `Order` (E-06): `RefundStatus` nullable; миграция в src/Ordering.Infrastructure/Migrations; снимок `OrderingContextModelSnapshot.cs` обновить. Создание заказа (E-01…E-04) — не заполняет поле (null).
- Событие `OrderStatusChangedToCancelledIntegrationEvent` (S-09): было — `OrderId, OrderStatus, BuyerName, BuyerIdentityGuid`; стало — + `OrderStockItems` (список `{ProductId, Units}`, пустой, если заказ не был оплачен). Совместимость: WebApp читает существующие поля, лишнее поле игнорируется; Catalog — новый подписчик, старых сообщений без поля нет (события в полёте при выкатке: Catalog до выката не подписан — проверить порядок выката: сначала Catalog, потом Ordering).
- Новые события (см. решения 5): только новые подписчики, существующие не меняются.
- Вход `PUT /api/orders/cancel`: поля и коды не меняются; меняется поведение (оплаченный — 200 вместо 500 для владельца).
- `OrderCancelledDomainEvent` (S-01): + `WasPaid`. Внутреннее, один подписчик.

## Риски
- **Гонка отмены и оплаты (CQ-06, Q-061).** `SetPaidStatus` работает только из «Подтверждён складом». Если отмена прошла раньше события оплаты, заказ отменён, а деньги списаны, возврата нет. Изменение этого не исправляет — решение за владельцем продукта; до ответа выкатывать только с понятной поддержкой.
- **Потеря событий (Q-049, Q-076).** Событие запроса возврата может не дойти: признак остаётся «Запрошен», деньги не возвращены. Нужен отчёт/сверка по `RefundStatus = Requested` — вне этого изменения.
- **Повтор с тем же x-requestid (Q-058).** Повтор отмены даёт 200 и не запускает возврат; возврат после неудачи вручную.
- **Конкурентность.** Нет версии строки (data.md): одновременная отмена и отгрузка могут перепутаться — отгрузка проверяет «Оплачен», отмена — тоже; риск окна одного запроса. Остаток: `RemoveStock` и `AddStock` без блокировок (Catalog — «последняя запись побеждает»); при параллельной покупке возможен перерасход — существующий риск (Q-030).
- **Выкатка.** Сначала Catalog (подписчик), потом Ordering (публикатор нового поля), потом клиент (кнопка для «Оплачен»). Откат: отключить кнопку; новые события без подписчиков не ломают.
- **Потеря признака при сбое транзакции.** Публикация через журнал в той же транзакции — признак и событие согласованы.

## Проверка
- Unit: `Order.SetCancelledStatus` — из «Оплачен» → «Отменён» с `WasPaid`; из «Отправлен» — исключение (tests/Ordering.UnitTests).
- Unit: обработчик отмены — `OrderStockItems` пусто без оплаты, заполнено с оплатой; запрос возврата только при `WasPaid` (tests/Ordering.UnitTests).
- Functional: `PUT /api/orders/cancel` для оплаченного заказа владельцем → 200; чужим → 500; отгруженного → 500 (tests/Ordering.FunctionalTests/OrderingApiTests.cs).
- PaymentProcessor: возврат с `RefundSucceeded` true/false (tests/Application.UnitTests/PaymentProcessorTests.cs).
- Catalog: `AddStock` по событию (новый тест в tests/Catalog.FunctionalTests); до оплаты остаток не меняется.
- Ручная проверка на стенде: заказ → оплата (10 с) → отмена → остаток вернулся, признак «Возвращён».
- Тест-кейсы qa-scan и design-context отсутствуют: проверка интерфейса не нужна.
## 1. Данные и контракты

- [ ] 1.1 Добавить в `Order` nullable-поле `RefundStatus` (enum `RefundStatus`: `Requested`, `Refunded`, `RefundFailed`), настроить колонку в `OrderEntityTypeConfiguration` и создать миграцию в `src/Ordering.Infrastructure/Migrations` (обновить `OrderingContextModelSnapshot.cs`) — файл `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` — готово, когда: миграция применяется, существующие заказы получают null, заказ, созданный без возврата, имеет `RefundStatus == null` (тест в `tests/Ordering.UnitTests`).
- [ ] 1.2 `Order.SetCancelledStatus` запоминает, был ли статус «Оплачен», и передаёт флаг в `OrderCancelledDomainEvent` (поле `WasPaid bool`) — `Order.SetCancelledStatus` в `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` — готово, когда: требование «Отмена заказа», сценарии «Отмена до оплаты» и «Отмена оплаченного заказа» проходят в unit-тестах.
- [ ] 1.3 Дополнить `OrderStatusChangedToCancelledIntegrationEvent` полем `OrderStockItems` (ProductId, Units) и заполнять его в `OrderCancelledDomainEventHandler` только при `WasPaid`, иначе пустым списком — файлы `src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs`, `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs` — готово, когда: требование «Возврат остатка при отмене оплаченного заказа», сценарий «Заказ отменён до оплаты» (пустой список) и «Оплаченный заказ отменён» (позиции заказа) проходят в тесте.
- [ ] 1.4 Создать интеграционные события `OrderRefundRequestedIntegrationEvent` (OrderId, Amount) в `src/PaymentProcessor` (и в копии Ordering.API) и ответы `OrderRefundSucceededIntegrationEvent`, `OrderRefundFailedIntegrationEvent` (OrderId) — файлы `src/PaymentProcessor/IntegrationEvents/Events/`, `src/Ordering.API/Application/IntegrationEvents/Events/` — готово, когда: имена и поля событий совпадают в обеих копиях (сверка глазами), сборка проходит.
- [ ] 1.5 Добавить `PaymentOptions.RefundSucceeded` (bool, по умолчанию true) — файл `src/PaymentProcessor/PaymentOptions.cs` — готово, когда: требование «Возврат оплаты при отмене оплаченного заказа», сценарии «Возврат прошёл» и «Возврат не прошёл» читают настройку.
- [ ] 1.6 Добавить копию `OrderStatusChangedToCancelledIntegrationEvent` с полем `OrderStockItems` в Catalog и подписку на неё — файлы `src/Catalog.API/IntegrationEvents/Events/` (новый файл), `src/Catalog.API/Extensions/Extensions.cs` (`AddSubscription`) — готово, когда: Catalog принимает событие с `OrderStockItems` (тест в `tests/Catalog.FunctionalTests`).

## 2. Поведение

- [ ] 2.1 В `OrdersApi.CancelOrderAsync` передавать владельца из токена (`IdentityService`), в `CancelOrderCommandHandler` или `Order` отказывать в отмене оплаченного заказа не-владельцу (возврат 500 «Cancel order failed to process.») — файлы `src/Ordering.API/Apis/OrdersApi.cs`, `src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs`, `src/Ordering.API/Application/Commands/CancelOrderCommand.cs` (если нужен идентификатор владельца) — готово, когда: требование «Отмена заказа», сценарий «Отмена оплаченного чужого заказа» (допущение Q-055) проходит.
- [ ] 2.2 Снять запрет на отмену из статуса «Оплачен» в `Order.SetCancelledStatus` (оставить запрет для «Отправлен») — файл `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` — готово, когда: требование «Отмена заказа», сценарий «Отмена отгруженного заказа» (500) и «Отмена оплаченного заказа» (200) проходят.
- [ ] 2.3 В `OrderCancelledDomainEventHandler` при `WasPaid` выставлять `RefundStatus = Requested` и публиковать `OrderRefundRequestedIntegrationEvent` через журнал событий — файл `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs` — готово, когда: требование «Возврат оплаты при отмене оплаченного заказа», сценарий «Отмена до оплаты без возврата» (запрос не публикуется), и признак «Запрошен» выставлен (требование «Признак возврата заказа»).
- [ ] 2.4 В `PaymentProcessor` обработчик `OrderRefundRequestedIntegrationEvent`: по `PaymentOptions.RefundSucceeded` публиковать `OrderRefundSucceededIntegrationEvent` или `OrderRefundFailedIntegrationEvent` — файл `src/PaymentProcessor/IntegrationEvents/EventHandling/OrderRefundRequestedIntegrationEventHandler.cs` (новый) — готово, когда: требование «Возврат оплаты при отмене оплаченного заказа», сценарии «Возврат прошёл» и «Возврат не прошёл» проходят.
- [ ] 2.5 В `Ordering.API` подписчики `OrderRefundSucceededIntegrationEvent` и `OrderRefundFailedIntegrationEvent`: выставлять `RefundStatus` = `Refunded` или `RefundFailed`, статус заказа не менять; подписки регистрировать там же, где остальные — файлы `src/Ordering.API/Application/IntegrationEvents/EventHandling/` (два новых обработчика), `src/Ordering.API/Extensions/Extensions.cs` (подписка) — готово, когда: требование «Признак возврата заказа», сценарии «Признак после успешного возврата» и «Признак после неудачного возврата» проходят.
- [ ] 2.6 В `Catalog.API` обработчик нового события вызывает `CatalogItem.AddStock` для каждой позиции, при пустом списке ничего не делает, сохраняет через `SaveChangesAsync` — файл `src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs` (новый) — готово, когда: требование «Возврат остатка при отмене оплаченного заказа», сценарии «Оплаченный заказ отменён» и «Заказ отменён до оплаты» проходят.

## 3. Вызывающие и подписчики

- [ ] 3.1 Клиентское приложение: кнопка «CANCEL ORDER» показывается и для статуса `Paid` (сейчас только `Submitted`) — файлы `src/ClientApp/ViewModels/OrderDetailViewModel.cs` (строка с `IsSubmittedOrder`), `src/ClientApp/Views/OrderDetailView.xaml` (`IsVisible`) — готово, когда: для заказа в статусе Paid кнопка видна, для Shipped и Cancelled — нет; требование «Отмена заказа» (покупатель может отменить оплаченный).

## 4. Проверка

- [ ] 4.1 Unit-тесты домена: `Order` из «Оплачен» → «Отменён» с `WasPaid`; из «Отправлен» — исключение — файл `tests/Ordering.UnitTests/Domain/` — готово, когда: сценарии требования «Отмена заказа» покрыты тестами.
- [ ] 4.2 Functional-тесты `PUT /api/orders/cancel` для оплаченного заказа: владелец — 200, чужой — 500, отгруженный — 500, повтор — 200 без повторного возврата — файл `tests/Ordering.FunctionalTests/OrderingApiTests.cs` — готово, когда: все сценарии требования «Отмена заказа» проходят.
- [ ] 4.3 Тесты PaymentProcessor на возврат с `RefundSucceeded` true и false — файл `tests/Application.UnitTests/PaymentProcessorTests.cs` — готово, когда: требование «Возврат оплаты при отмене оплаченного заказа» покрыто сценариями «Возврат прошёл» и «Возврат не прошёл».
- [ ] 4.4 Functional-тест Catalog: `AddStock` по событию отмены с позициями и с пустым списком — файл `tests/Catalog.FunctionalTests` — готово, когда: требование «Возврат остатка при отмене оплаченного заказа» покрыто сценариями.
- [ ] 4.5 Существующие тесты затронутых возможностей прогнать: `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs`, `tests/Ordering.FunctionalTests/OrderingApiTests.cs`, `tests/Application.UnitTests/WebhookTests.cs` (рассылка не меняется) — готово, когда: все зелёные, кроме тестов, которые ожидали 500 для оплаченного заказа (их обновить под новое поведение).
- [ ] 4.6 Сквозной сценарий (`e2e/`, Playwright или ручной прогон стенда): заказ → оплата → отмена → признаки в API: заказ → оплата → отмена → остаток в Catalog вернулся, признак возврата «Возвращён» — готово, когда: сценарий «Отмена оплаченного заказа» наблюдается в сквозном прогоне.

## 5. Слой контекста

- [ ] 5.1 Обновить `system-context/trace.md`: строки новых и изменённых требований → код и тесты
- [ ] 5.2 Пересобрать слой, если установлен sa-scan: `contracts.py scan .` и `plan.py guide .`; `check.py .` без ошибок (иначе — пункт в отчёте)
# Влияние изменения `cancel-paid-order`

Собрано `change.py analyze` из слоя sa-scan. Затронуто: возможности `order-management`, `catalog-stock`, `order-payment`, `webhook-delivery`, `order-status-notifications`; входы http:PUT /api/orders/cancel; события OrderStatusChangedToCancelledIntegrationEvent, OrderStatusChangedToPaidIntegrationEvent; сущности Order.
У каждого пункта — **Решение**: `задача N.N` (номер из tasks.md, можно несколько) или `не затрагивается: <почему>`.
Для вопросов [блокирует]: `ответ: …` (если человек ответил) или `в proposal: <что принято до ответа>`.
Повторный `analyze` обновит пункты и сохранит решения. Пункты, которых нет в слое, добавь сам в конце с буквой X (X-01…).


## Кто вызывает затронутые входы

- [ ] C-01 `src/ClientApp → /api/orders` — клиентское приложение <!-- key: caller:src/ClientApp → /api/orders -->
  - опирается на: только версия 1.0 (`api-version=1.0`, src/ClientApp/Services/Order/OrderService.cs:14). Страница заказа читает `Order` с JSON-именами `status`, `ordernumber`, `date`, `total`, `items`, `city`, `street`, `state`, `country`, `zipCode` (src/ClientApp/Models/Orders/Order.cs:13-50); сервер отдаёт `Status`, `OrderNumber`, `Zipcode`, `OrderItems` (src/Ordering.API/Application/Queries/OrderViewModel.cs:12-23): `status`, `ordernumber`, `zipCode` совпадают только без учёта регистра, а `items` клиента и `OrderItems` сервера различаются по имени — список позиций на клиенте может не заполняться. Кнопка «CANCEL ORDER» видна только когда `status` равен `Submitted` без учёта регистра (src/ClientApp/ViewMode
  - где: src/ClientApp/Services/Order/OrderService.cs:13
  - **Решение:** задача 3.1
- [ ] C-02 `src/WebApp → /api/orders` <!-- key: caller:src/WebApp → /api/orders -->
  - опирается на: `GET api/Orders/` в `OrderRecord(OrderNumber, Date, Status, Total)` (src/WebApp/Services/OrderingService.cs:9, 21-25) — форма `OrderSummary` сервера; список заказов выводит их и строит CSS-класс из `Status.ToLower()` (src/WebApp/Components/Pages/User/Orders.razor:48-52), то есть новый статус без CSS-класса отрисуется без стиля. `POST` создания заказа шлёт `x-requestid` и тело `CreateOrderRequest` (OrderingService.cs:12-18); ответ не проверяется, `EnsureSuccess` нет — а сервер на невалидный заказ всё равно отвечает 200 (см. заметку под `POST /api/orders`). Версия 1.0 через `AddApiVersion(1.0)` (src/WebApp/Extensions/Extensions.cs:38-40). Сломается при: переименовании `OrderNumber`/`Status`/`T
  - где: src/WebApp/Services/OrderingService.cs:5
  - **Решение:** не затрагивается: WebApp не вызывает отмену (кнопки отмены в интерфейсе нет), новые поля ответа не добавляются
- [ ] C-03 `src/eShop.AppHost → /api/orders` <!-- key: caller:src/eShop.AppHost → /api/orders -->
  - опирается на: конфигурация шлюза: `/api/orders/{*any}` → ordering-api, пропускает только `api-version` 1.0/1 (src/eShop.AppHost/Extensions.cs:155-156); авторизация — на стороне сервиса (`RequireAuthorization`). Сломается при: выпуске v2 заказов — шлюз его не пропустит, пока не поменять значения здесь.
  - где: src/eShop.AppHost/Extensions.cs:155
  - **Решение:** не затрагивается: путь, версия API и правила шлюза не меняются

## События: публикуемые и названные

- [ ] S-03 `OrderStatusChangedToPaidIntegrationEvent` <!-- key: event:OrderStatusChangedToPaidIntegrationEvent -->
  - поля: OrderId int, OrderStockItems IEnumerable<OrderStockItem>
  - ⚠ копии события в сервисах различаются по полям
  - подписаны: src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderStatusChangedToPaidIntegrationEventHandler); src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:5 (обработчик интеграционного события → OrderStatusChangedToPaidIntegrationEventHandler); src/Webhooks.API/IntegrationEvents/OrderStatusChangedToPaidIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderStatusChangedToPaidIntegrationEventHandler)
  - заметки: Заметки: Catalog списывает остаток по `OrderStockItems` (`RemoveStock` — исключение, если товара нет в наличии; блокировок нет, проверка наличия на шаге валидации и списание разнесены — возможен перерасход); WebApp использует `BuyerIdentityGuid` для уведомления пользователя (src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:13); у ко
  - **Решение:** не затрагивается: событие оплаты и списание остатка при оплате не меняются
- [ ] S-01 `OrderCancelledDomainEvent` (внутреннее) <!-- key: event:OrderCancelledDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:3 (MediatR → OrderCancelledDomainEventHandler)
  - **Решение:** задачи 1.2, 1.3, 2.3
- [ ] S-02 `OrderShippedDomainEvent` (внутреннее) <!-- key: event:OrderShippedDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderShippedDomainEventHandler.cs:3 (MediatR → OrderShippedDomainEventHandler)
  - **Решение:** не затрагивается: отгрузка и её событие не меняются; отгруженный заказ отмену не проходит (сценарий «Отмена отгруженного заказа»)
- [ ] S-04 `OrderStatusChangedToPaidDomainEvent` (внутреннее) <!-- key: event:OrderStatusChangedToPaidDomainEvent -->
  - поля: OrderId int, OrderItems IEnumerable<OrderItem>
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderStatusChangedToPaidDomainEventHandler.cs:3 (MediatR → OrderStatusChangedToPaidDomainEventHandler)
  - **Решение:** не затрагивается: обработка оплаты не меняется, признак «был оплачен» берётся из статуса при отмене (задача 1.2)
- [ ] S-05 `OrderPaymentFailedIntegrationEvent` <!-- key: event:OrderPaymentFailedIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderPaymentFailedIntegrationEventHandler)
  - **Решение:** не затрагивается: отказ оплаты отменяет заказ из «Подтверждён складом», возврата не нужно; путь через CancelOrderCommand не меняется
- [ ] S-06 `OrderPaymentSucceededIntegrationEvent` <!-- key: event:OrderPaymentSucceededIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderPaymentSucceededIntegrationEventHandler)
  - **Решение:** не затрагивается: обработка оплаты не меняется; гонка отмены и оплаты вынесена в proposal (CQ-06)
- [ ] S-07 `OrderStockConfirmedIntegrationEvent` <!-- key: event:OrderStockConfirmedIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderStockConfirmedIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderStockConfirmedIntegrationEventHandler)
  - **Решение:** не затрагивается: подтверждение склада не меняется
- [ ] S-08 `OrderStockRejectedIntegrationEvent` <!-- key: event:OrderStockRejectedIntegrationEvent -->
  - поля: OrderId int, OrderStockItems List<ConfirmedOrderStockItem>
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderStockRejectedIntegrationEventHandler.cs:2 (обработчик интеграционного события → OrderStockRejectedIntegrationEventHandler)
  - **Решение:** не затрагивается: отказ склада отменяет заказ из «Ожидает проверки», путь не меняется
- [ ] S-09 `OrderStatusChangedToCancelledIntegrationEvent` <!-- key: event:OrderStatusChangedToCancelledIntegrationEvent -->
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs:5 (обработчик интеграционного события → OrderStatusChangedToCancelledIntegrationEventHandler)
  - **Решение:** задачи 1.3, 1.6; копия WebApp не меняется: читает только статус и покупателя, лишнее поле в JSON игнорируется

## Сущности: где поле потеряется молча

- [ ] E-01 `Order` создаётся: `CheckoutViewModel.InitializeAsync` src/ClientApp/ViewModels/CheckoutViewModel.cs:70 <!-- key: create:Order:`CheckoutViewModel.InitializeAsync` src/ClientApp/ViewModels/CheckoutViewModel.cs:70 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: новое поле nullable, при создании не заполняется (null = возврата не было)
- [ ] E-02 `Order` создаётся: `CreateOrderCommandHandler.Handle` src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:40 <!-- key: create:Order:`CreateOrderCommandHandler.Handle` src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:40 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: новое поле nullable, при создании не заполняется (null)
- [ ] E-03 `Order` создаётся: `OrderQueries.GetOrderAsync` src/Ordering.API/Application/Queries/OrderQueries.cs:15 <!-- key: create:Order:`OrderQueries.GetOrderAsync` src/Ordering.API/Application/Queries/OrderQueries.cs:15 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: чтение заказа не создаёт и не копирует новое поле (только запрос из базы)
- [ ] E-04 `Order` создаётся: `Order.NewDraft` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:39 <!-- key: create:Order:`Order.NewDraft` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:39 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: новое поле nullable, в черновике не заполняется (null)
- [ ] E-05 `Order` → копия `Order` (src/ClientApp/Models/Orders/Order.cs:5) <!-- key: copy:Order:Order:src/ClientApp/Models/Orders/Order.cs -->
  - общих полей 2 из 18, нет: address, buyer, buyerid, description, isdraft, paymentid
  - **Решение:** не затрагивается: клиент не читает признак возврата; отображение возврата в клиенте — CQ-05 (proposal)
- [ ] E-06 `Order` миграция схемы: src/Ordering.Infrastructure/Migrations: миграций 4, последние: 20231026091055_Outbox.cs, 20240106121712_UseEnumForOrderStatus.cs; схема или снимок: src/Ordering <!-- key: migr:Order -->
  - новая миграция, снимок схемы сверить с моделью
  - **Решение:** задача 1.1

## Блокирующие вопросы

- [ ] Q-030 [блокирует] Нужно ли резервировать остаток между проверкой и оплатой? <!-- key: q:Q-030 -->
  - допущение: как в коде и комментарии: остаток не резервируется; два заказа могут пройти проверку на один и тот же остаток, а при оплате второй получит частичное списание или ошибку
  - статус: открыт
  - **Решение:** не затрагивается: резервирование остатка не вводится; перерасход — существующий риск (design, риски)
- [ ] Q-049 [блокирует] Шина подтверждает сообщение даже при ошибке обработки — без повтора и очереди ошибок: так задумано? <!-- key: q:Q-049 -->
  - допущение: событие теряется, заказ остаётся в AwaitingValidation, как в коде
  - статус: открыт
  - **Решение:** в proposal: событие возврата может не дойти (Q-049) — признак останется «Запрошен»; сверка вне этого изменения
- [ ] Q-055 [блокирует] Кто может отменять, отгружать и читать чужие заказы? <!-- key: q:Q-055 -->
  - допущение: спека описывает код: любой вошедший пользователь может отменить, отгрузить и прочитать любой заказ по номеру
  - статус: открыт
  - **Решение:** в proposal: оплаченный заказ отменяет только владелец (допущение); отмена до оплаты поведения не меняет, дыра вынесена в proposal
- [ ] Q-058 [блокирует] Повтор с тем же x-requestid после неудачи должен повторить действие? <!-- key: q:Q-058 -->
  - допущение: спека описывает код: повтор после неудачи даёт 200 и не выполняет команду
  - статус: открыт
  - **Решение:** в proposal: повтор с тем же x-requestid не меняется, повтор не запускает возврат (риск в design)
- [ ] Q-064 [блокирует] Оплата — заглушка (исход из настроек, фиксированная тестовая карта): какой будет реальная оплата? <!-- key: q:Q-064 -->
  - допущение: оплата имитируется, внешний платёжный шлюз не используется и не описан
  - статус: открыт
  - **Решение:** в proposal: CQ-03 — возврат тоже заглушка с настройкой RefundSucceeded (задача 1.5)
- [ ] Q-095 [блокирует] Все подписки типа получают события всех покупателей: владелец подписки ничем не ограничен? <!-- key: q:Q-095 -->
  - допущение: подписка любого пользователя получает события всех заказов
  - статус: открыт
  - **Решение:** не затрагивается: рассылка вебхуков не меняется; вопрос остаётся открытым, назван в proposal

## Уточняющие вопросы по затронутым возможностям

- Q-018 Остатки товара задаются вручную через PUT или их ведёт склад?
- Q-029 Что делать, если заказ оплачен, а товара на складе не хватает?
- Q-031 Что делать, если товара заказа уже нет в каталоге?
- Q-034 Нужны ли порог перезаказа, признак перезаказа и добавление остатка?
- Q-056 Для отказа в отмене и отгрузке нужен код 500 или 4xx (например 409)?
- Q-057 Если обработчик события отмены упал, статус «Отменён» должен откатиться?
- Q-059 Повторная отмена уже отменённого заказа: допустима ли повторная публикация события?
- Q-060 Отмена пользователем разрешена в любой момент до оплаты или только в период ожидания?
- Q-061 Заказ отменён до ответа оплаты: оплату молча принимать или считать ошибкой?
- Q-063 Пауза 10 секунд перед переходом в «Оплачен» — имитация или ошибка?
- Q-066 Повторные события оплаты: допустимо ли повторное событие отмены и повторная публикация статуса?
- Q-075 Сколько экземпляров WebApp работает одновременно и должна ли открытая страница заказов обновляться на каждом из них?
- Q-076 Допустимо ли терять событие смены статуса, если обработка упала или экземпляр был остановлен?
- Q-077 Нужно ли всплывающее уведомление о смене статуса, или достаточно перезагрузки списка?
- Q-078 Нужен ли в боевом коде перехват сообщений с текстом «throw-fake-exception»?
- Q-096 Имя покупателя из события отгрузки можно отдавать внешним получателям?
- Q-097 Рассылка смены цены должна работать, или подписки типа CatalogItemPriceChange не нужны?
- Q-098 Должна ли рассылка повторяться, если получатель ответил 4xx или 5xx?
- Q-100 Нужны ли порядок событий и доставка ровно один раз?
- Q-101 Формат тела рассылки (Payload — строка с JSON внутри JSON, PascalCase) — это контракт для получателей?
- Q-102 Перехватчик «throw-fake-exception» в шине — тестовый код или поведение, которое должно уйти из продакшена?

## Тесты затронутых возможностей (запустить и обновить)

- order-management: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs
- order-payment: tests/Application.UnitTests/PaymentProcessorTests.cs
- webhook-delivery: tests/Application.UnitTests/WebhookTests.cs

## Сущности в коде затронутых возможностей (если меняешь их поля — добавь --entity)

- CatalogItem

## Код затронутых возможностей

Файлы из трассировки и обработчиков — по ним волны и пересечения с другими изменениями.

- src/Catalog.API/Extensions/Extensions.cs
- src/Catalog.API/IntegrationEvents/CatalogIntegrationEventService.cs
- src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToAwaitingValidationIntegrationEventHandler.cs
- src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs
- src/Catalog.API/IntegrationEvents/Events/ConfirmedOrderStockItem.cs
- src/Catalog.API/IntegrationEvents/Events/OrderStockConfirmedIntegrationEvent.cs
- src/Catalog.API/IntegrationEvents/Events/OrderStockRejectedIntegrationEvent.cs
- src/Catalog.API/Model/CatalogItem.cs
- src/EventBusRabbitMQ/EventBusOptions.cs
- src/EventBusRabbitMQ/RabbitMQEventBus.cs
- src/Ordering.API/Apis/OrdersApi.cs
- src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs
- src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs
- src/Ordering.API/Application/Commands/SetPaidOrderStatusCommandHandler.cs
- src/Ordering.API/Application/Commands/ShipOrderCommandHandler.cs
- src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs
- src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs
- src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs
- src/Ordering.API/Application/Queries/OrderQueries.cs
- src/Ordering.API/Application/Validations/CancelOrderCommandValidator.cs
- src/Ordering.API/Application/Validations/ShipOrderCommandValidator.cs
- src/Ordering.API/Infrastructure/Services/IdentityService.cs
- src/Ordering.API/Program.cs
- src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs
- src/Ordering.Infrastructure/Idempotency/RequestManager.cs
- src/PaymentProcessor/IntegrationEvents/EventHandling/OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs
- src/PaymentProcessor/PaymentOptions.cs
- src/PaymentProcessor/appsettings.json
- src/WebApp/Components/Pages/User/OrdersRefreshOnStatusChange.razor
- src/WebApp/Extensions/Extensions.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToAwaitingValidationIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToShippedIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToSubmittedIntegrationEventHandler.cs
- src/WebApp/Services/OrderStatus/IntegrationEvents/Events/OrderStatusChangedToPaidIntegrationEvent.cs
- src/WebApp/Services/OrderStatus/OrderStatusNotificationService.cs
- src/WebApp/appsettings.json
- src/Webhooks.API/IntegrationEvents/OrderStatusChangedToPaidIntegrationEventHandler.cs
- src/Webhooks.API/IntegrationEvents/OrderStatusChangedToShippedIntegrationEvent.cs
- src/Webhooks.API/IntegrationEvents/OrderStatusChangedToShippedIntegrationEventHandler.cs
- src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs
- src/Webhooks.API/Model/WebhookData.cs
- src/Webhooks.API/Services/WebhooksRetriever.cs
- src/Webhooks.API/Services/WebhooksSender.cs
