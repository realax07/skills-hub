# Анализ влияния: отмена оплаченного заказа с возвратом через платёжный процессор

Задача: покупатель может отменить заказ и после оплаты, пока заказ не отправлен (статус Paid). Деньги возвращаются через платёжный процессор.
Репозиторий: r1 (eShop). Код не менялся, ничего не запускалось. Пути — относительно корня r1. Номера строк сверены по файлам.

Исходная точка (по коду и спекам): сейчас отмена покупателем разрешена из Submitted, AwaitingValidation, StockConfirmed. Из Paid и Shipped она запрещена исключением (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:144-148`, ответ 500 «Cancel order failed to process.»). Спека `openspec/specs/order-management/spec.md` (требование «Отмена заказа», сценарий «Отмена оплаченного заказа») фиксирует это как текущее поведение. Значит изменение — это MODIFIED-требование, а не новое.

## 1. Затронутое поведение

Меняется:
- Отмена заказа в статусе Paid из запрещённой становится разрешённой (`PUT /api/orders/cancel`). Запрет из Shipped сохраняется.
- Из Paid заказ больше не переходит в Cancelled сразу: деньги сначала возвращаются, и только после ответа процессора заказ получает итоговый статус. Это предложение (см. раздел 9), а не факт кода.
- Отмена, которую запускает отказ оплаты (`OrderPaymentFailedIntegrationEventHandler` → `CancelOrderCommand`), идёт через тот же `SetCancelledStatus()`. Если разрешить Paid в нём, отказ оплаты для уже оплаченного заказа станет возможен без возврата. Поэтому нужен отдельный метод для отмены после оплаты (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:142-153`).
- Заказ, отменённый до ответа оплаты: сейчас оплату «Оплата прошла» тихо игнорируют (`Order.cs:121`, Q-061). После изменения такая оплата означает списанные деньги без заказа, и возврат должен запускаться и в этом случае.

Сохраняется, но на это опирается изменение:
- Статус Shipped необратим: из Shipped переходов нет (`Order.cs:132-135`, `Order.cs:144-148`).
- Отгрузка доступна только из Paid (`Order.cs:130-140`, `ShipOrderCommandHandler.cs:27`).
- Задержка 10 с перед переходом в Paid (`SetPaidOrderStatusCommandHandler.cs:22`).
- Событие отмены публикуется через outbox после фиксации транзакции (`TransactionBehavior.cs:43-52`, `OrderingIntegrationEventService.cs:13-34`). Внешний вызов процессора внутри транзакции команды делать нельзя.
- Идемпотентность по `x-requestid` (`IdentifiedCommandHandler.cs:41-48`, Q-058).

## 2. Контракты API

- `PUT /api/orders/cancel` (`src/Ordering.API/Apis/OrdersApi.cs:22-49`). Меняется поведение, тело и заголовки те же.
  - Тело: `CancelOrderCommand { OrderNumber: int }` (`src/Ordering.API/Application/Commands/CancelOrderCommand.cs:3`). Без изменений.
  - Заголовок `x-requestid` (Guid, пустой → 400). Без изменений.
  - Коды: 200 при успехе, 400 при пустом GUID, 500 «Cancel order failed to process.» при отказе (`OrdersApi.cs:27-30, 43-46`).
  - Новое: для Paid код 200 будет означать «принято» или «отменено»? Если возврат асинхронный, 200 не гарантирует возврат денег. Нужно решить и описать в контракте (см. раздел 9).
  - Совместимость: клиенты, которые ждут 500 для Paid, перестанут его получать. Ломающее изменение — нет по форме, но меняется смысл 200.
- `GET /api/orders/{orderId}` и `GET /api/orders` (`OrdersApi.cs:80-98`). Форма ответа не меняется. Статус отдаётся строкой `OrderStatus.ToString()` (`src/Ordering.API/Application/Queries/OrderQueries.cs:25, 45`). Если появится новый статус (например `RefundPending`), клиенты получат новое строковое значение.
- `PUT /api/orders/ship` (`OrdersApi.cs:51-78`). Контракт не меняется. Нужно проверить гонку с отменой (раздел 8).
- Внешний вебхук-API `POST /api/webhooks` (`src/Webhooks.API/Apis/WebHooksApi.cs:50`): тип события парсится через `Enum.Parse<WebhookType>`. Если добавлять тип `OrderCancelled`, это новое значение, старые клиенты его не знают. Нужно решить, нужен ли он (раздел 4).
- Внутренний API процессора: не существует. Нужен новый контракт «возврат» между Ordering и PaymentProcessor (см. раздел 3).

## 3. События

Изменяется смысл существующего события:
- `OrderStatusChangedToCancelledIntegrationEvent` (`src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs:3-17`): поля `OrderId`, `OrderStatus`, `BuyerName`, `BuyerIdentityGuid`. Сейчас публикуется для отмены из Submitted/AwaitingValidation/StockConfirmed (`src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:23-32`). После изменения публикуется и для Paid. Подписчики: только WebApp (`src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs:10-14`, перерисовка списка). Catalog и Webhooks на него не подписаны.
  - Для возврата остатка и суммы в событии нужны данные позиций и сумма. Сейчас их нет. Варианты: добавить `OrderStockItems` (как в `OrderStatusChangedToPaidIntegrationEvent.cs:9`) и сумму, либо публиковать отдельное событие.

Новые события (предложение, названия условные):
- `OrderRefundRequested` (Ordering → PaymentProcessor): номер заказа, сумма, id попытки возврата (ключ идемпотентности). Публикуется через outbox после фиксации перехода в состояние «возврат ожидается».
- `OrderRefundSucceeded` / `OrderRefundFailed` (PaymentProcessor → Ordering): номер заказа, id попытки, результат. Подписка в `src/Ordering.API/Extensions/Extensions.cs:55-61` (рядом с `OrderPaymentSucceededIntegrationEvent`). Обработчик переводит заказ в Cancelled или оставляет в состоянии ожидания и пишет причину.
- Событие о возврате для Catalog (или переиспользование `OrderStatusChangedToCancelledIntegrationEvent` с позициями). Подписка в `src/Catalog.API/Extensions/Extensions.cs:32-33` (сейчас там только AwaitingValidation и Paid). Нужен новый обработчик, который вернёт остаток.

Изменяется набор входящих событий:
- `OrderPaymentSucceededIntegrationEvent` (`src/PaymentProcessor/IntegrationEvents/Events/OrderPaymentSucceededIntegrationEvent.cs:3`, `src/Ordering.API/Application/IntegrationEvents/Events/OrderPaymentSucceededIntegrationEvent.cs`): сейчас только `OrderId`. Для возврата процессору нужен идентификатор платежа (charge id). Его либо добавить в событие, либо хранить в PaymentProcessor. Сейчас его нет нигде (раздел 5).

Не меняются, но проверить:
- `OrderStatusChangedToPaidIntegrationEvent` (Catalog списывает остаток, `src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:12-20`; Webhooks рассылает `OrderPaid`; WebApp перерисовывает список). Для возврата остатка нужен симметричный путь.
- `OrderStatusChangedToShippedIntegrationEvent` (Webhooks `OrderShipped`, WebApp). Не меняется, но отмена после отгрузки должна быть невозможна, иначе будет и Shipped, и возврат.
- `OrderPaymentFailedIntegrationEvent` (`src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs:12`): вызывает `CancelOrderCommand`. Нужно не дать ему отменять Paid (см. раздел 1).

## 4. Потребители и сервисы

Обязательно менять:
- Ordering.API (`src/Ordering.API`): команда отмены, доменная модель, обработчики событий, новые подписки, статусы. Основная работа.
- Ordering.Domain (`src/Ordering.Domain`): метод отмены после оплаты, событие с позициями или суммой, новый статус (если нужен).
- PaymentProcessor (`src/PaymentProcessor`): обработчик возврата, вызов процессора, публикация результата. Сейчас процессор не хранит состояние и не знает про заказы кроме номера (`src/PaymentProcessor/Program.cs:5-9`, `PaymentOptions.cs:5`).
- Catalog.API (`src/Catalog.API`): возврат остатка. Сейчас единственная обработка Paid — списание (`CatalogItem.cs:62-84`). `AddStock` есть (`src/Catalog.API/Model/CatalogItem.cs:86-98`), но обрезает до `MaxStockThreshold` (строки 91-96): часть возвращаемых единиц пропадёт без ошибки.

Проверить и, вероятно, менять:
- Webhooks.API (`src/Webhooks.API/IntegrationEvents/OrderStatusChangedToPaidIntegrationEventHandler.cs:10-16`, `src/Webhooks.API/Model/WebhookType.cs:3-7`): внешние получатели подписались на `OrderPaid` и не узнают об отмене. Если нужен сигнал, добавить тип `OrderCancelled = 4` и подписку. Тип продублирован в `src/WebhookClient/Services/WebhookType.cs:3-7`, его тоже надо синхронизировать.
- WebApp (`src/WebApp`):
  - подписка на отмену уже есть (`src/WebApp/Extensions/Extensions.cs:49`), перерисовка списка будет работать;
  - статус «возврат ожидается» нужен отдельный CSS-класс (`src/WebApp/Components/Pages/User/Orders.razor.css:113-131`, сейчас есть cancelled и paid);
  - кнопки отмены в витрине нет вовсе (`src/WebApp/Components/Pages/User/Orders.razor` и ниже по дереву — поиска по «cancel» нет). Если задача требует отмену и в витрине, это новая UI-работа, а не правка.
- ClientApp (MAUI, `src/ClientApp`): кнопка «CANCEL ORDER» видна только при Submitted (`src/ClientApp/ViewModels/OrderDetailViewModel.cs:38`, `src/ClientApp/Views/OrderDetailView.xaml:76`). После изменения нужно показывать и для Paid, а `OrderDetailViewModel.cs:50-58` (ставит «Cancelled» сразу после ответа 200) — учесть асинхронный возврат.
- eShop.AppHost (`src/eShop.AppHost/AppHost.cs:52-53`): процессор сейчас без БД и без параметров. Если нужен учёт платежей или ключи процессора, понадобятся ресурсы и переменные окружения.
- OrderProcessor (`src/OrderProcessor`): не затрагивается. Фоновый процесс работает только с Submitted.
- Basket.API, Identity.API: не затрагиваются.

## 5. Данные

- Таблица `orders`: `OrderStatus` хранится строкой, `HasMaxLength(30)` (`src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs:18-21`). Новое значение статуса уместится. Ограничения CHECK в миграциях не проверял (допущение).
- Нужны новые данные (сейчас их нет):
  - идентификатор платежа/списания у процессора. Ordering хранит только `PaymentMethodId` (ссылка на сохранённую карту, `OrderEntityTypeConfiguration.cs:23-25`), а не результат списания;
  - валюта. В домене её нет нигде (проверено поиском по `src/`, кроме Identity).
  - сумма возврата. Есть `Order.GetTotal()` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:185`) и `UnitPrice`/`Units` в `OrderItem`, но без валюты.
  - учёт попыток возврата: номер попытки, ключ идемпотентности, статус, причина отказа. Нужна таблица (в Ordering или в PaymentProcessor) и, соответственно, миграция. Для PaymentProcessor это новая БД (`src/PaymentProcessor/PaymentProcessor.csproj`: нет EF/БД; AppHost тоже без БД).
- Миграции: EF-миграции Ordering (`src/Ordering.Infrastructure`). Для PaymentProcessor — нового механизма миграций нет.
- Засев: `OrderingContextSeed.cs` не меняется.
- Копии полей (правило из `system-context/data.md`): `Order` есть в `src/ClientApp/Models/Orders/Order.cs` (строка статуса), `OrderSummary` в WebApp `src/WebApp/Services/OrderingService.cs` — их проверить при добавлении полей.
- Остаток: `CatalogItem.AvailableStock` (нижняя граница 0, `CatalogItem.cs:74-76`); возврат должен увеличивать его с учётом `MaxStockThreshold`.
- Конкурентность: защиты от параллельных изменений нет (нет версии строки и блокировок, по `system-context/data.md`). Для Paid+Ship+Cancel это важно (раздел 8).

## 6. Код

Ordering.Domain:
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:142-153` — `SetCancelledStatus()`: сейчас запрещает Paid и Shipped. Нужен отдельный путь для Paid (не менять общий метод, потому что на него опирается отказ оплаты).
- `Order.cs:119-128` — `SetPaidStatus()`: при отмене до оплаты оплата молча игнорируется (`if (OrderStatus == StockConfirmed)`). Нужно добавить ветку «заказ отменён — запустить возврат».
- `Order.cs:130-140` — `SetShippedStatus()`: проверка `!= Paid`, ок. Без изменений.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderStatus.cs:8-13` — enum статусов, если добавляется новый статус.
- `src/Ordering.Domain/Events/OrderCancelledDomainEvent.cs:5-11` — несёт весь `Order`, сумму можно посчитать; позиции есть.
- `src/Ordering.Domain/Events/OrderStatusChangedToPaidDomainEvent.cs` — образец события с позициями.

Ordering.API:
- `src/Ordering.API/Apis/OrdersApi.cs:22-49` — `CancelOrderAsync`: 500 при `false`. Сейчас для Paid `false` приходит из-за исключения в домене (`IdentifiedCommandHandler.cs:99-102` проглатывает исключение и возвращает default).
- `src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs:19-29` — вызывает `SetCancelledStatus()`. Нужна отдельная команда или ветка для Paid (например `RequestOrderCancellationAfterPaymentCommand`).
- `src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs:41-48, 63-66, 87, 99-102` — идемпотентность: запись `x-requestid` до выполнения, любая ошибка → default. См. раздел 8.
- `src/Ordering.API/Application/Commands/CancelOrderIdentifiedCommandHandler.cs` (строки 44-47): дубликат возвращает true. Важно для повторов возврата.
- `src/Ordering.API/Application/Validations/CancelOrderCommandValidator.cs:7` — проверка только `OrderNumber` не пустой. Владелец и статус не проверяются (Q-055).
- `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:23-32` — собирает `OrderStatusChangedToCancelledIntegrationEvent` без позиций и суммы. Нужно дополнить.
- `src/Ordering.API/Application/DomainEventHandlers/OrderStatusChangedToPaidDomainEventHandler.cs:22-40` — образец публикации позиций.
- `src/Ordering.API/Application/Commands/SetPaidOrderStatusCommandHandler.cs:22, 30` — задержка 10 с и `SetPaidStatus()`. Если заказ отменён в окне 10 с, возврат должен запускаться отсюда (или из обработчика события).
- `src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs:12-21` — здесь же место для сохранения идентификатора платежа (если он приходит в событии).
- `src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs:12` — `CancelOrderCommand`. Не должен отменять Paid.
- `src/Ordering.API/Extensions/Extensions.cs:55-61` — подписки. Здесь добавить подписки на результаты возврата.
- Новые обработчики результата возврата (по образцу `OrderPaymentSucceededIntegrationEventHandler.cs`).
- `src/Ordering.API/Application/Behaviors/TransactionBehavior.cs:25-53` и `src/Ordering.API/Application/IntegrationEvents/OrderingIntegrationEventService.cs:13-34` — публикация после коммита; при ошибке событие помечается PublishedFailed и не повторяется (`src/IntegrationEventLogEF/Services/IntegrationEventLogService.cs:58`). Для возврата это главный риск (раздел 8).
- `src/Ordering.API/Application/Queries/OrderQueries.cs:25, 45` — статус отдаётся строкой; новых полей в ответе нет, если не добавлять.
- `src/Ordering.API/Application/Queries/OrderViewModel.cs` — проверить, нужно ли показывать сумму возврата.

Ordering.Infrastructure:
- `src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs:18-21` — статус (string, 30).
- `src/Ordering.Infrastructure/Idempotency/RequestManager.cs:21-29` — `CreateRequestForCommandAsync` бросает исключение, если запрос уже есть.
- Новая таблица попыток возврата и её конфигурация, миграция.

PaymentProcessor:
- `src/PaymentProcessor/Program.cs:5-6` — регистрация подписки. Добавить подписку на запрос возврата.
- `src/PaymentProcessor/PaymentOptions.cs:5` — настройка исхода оплаты. Для возврата нужны адрес и ключи процессора (настройки).
- `src/PaymentProcessor/IntegrationEvents/EventHandling/OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs:21-28, 32` — здесь имитация оплаты. Нужно сохранять идентификатор списания, если он есть.
- Новые файлы: события возврата (запрос, результат), обработчик запроса возврата, клиент процессора (HTTP), конфигурация.
- `src/PaymentProcessor/IntegrationEvents/Events/OrderPaymentSucceededIntegrationEvent.cs:3` — если добавляем charge id, здесь и в `src/Ordering.API/Application/IntegrationEvents/Events/OrderPaymentSucceededIntegrationEvent.cs`.

Catalog.API:
- `src/Catalog.API/Extensions/Extensions.cs:32-33` — новая подписка на отмену/возврат.
- Новый обработчик, по образцу `src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:12-20`, который вызывает `AddStock`.
- `src/Catalog.API/Model/CatalogItem.cs:86-98` — `AddStock`: лимит `MaxStockThreshold` молча обрезает возврат (строки 91-96). Решить: допускать превышение или фиксировать потерю.

Webhooks.API / WebhookClient (если нужен сигнал):
- `src/Webhooks.API/Extensions/Extensions.cs:22-23`, `src/Webhooks.API/IntegrationEvents/...` — новый обработчик и тип.
- `src/Webhooks.API/Model/WebhookType.cs:3-7`, `src/WebhookClient/Services/WebhookType.cs:3-7`.

WebApp:
- `src/WebApp/Extensions/Extensions.cs:45-50` — подписки на статусы.
- `src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs:10-14` — без изменений, если событие то же.
- `src/WebApp/Components/Pages/User/Orders.razor:51-52` и `Orders.razor.css:113-131` — стили статусов.
- `src/WebApp/Components/Pages/User/Orders.razor` — кнопки отмены нет; если нужна, новая работа.

ClientApp (MAUI):
- `src/ClientApp/ViewModels/OrderDetailViewModel.cs:38, 44-59` — видимость и поведение после отмены.
- `src/ClientApp/Views/OrderDetailView.xaml:76` — `IsVisible="{Binding IsSubmittedOrder}"`.
- `src/ClientApp/Services/Order/OrderService.cs:83-110` — вызов отмены, код 400 → false, остальные ошибки пробрасываются.

eShop.AppHost:
- `src/eShop.AppHost/AppHost.cs:52-53` — процессор: если нужны ключи или БД, здесь.

Не менять: `src/OrderProcessor/*`, `src/Basket.API/*`, `src/Identity.API/*`.

## 7. Тесты и проверка

Существующие тесты, которые сломаются или поменяют смысл:
- `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs:25-48, 158-170` — тесты отмены через mock медиатора. Тест «Cancel_order_returns_problem_when_command_fails» остаётся, но ожидания по Paid добавить.
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs:39-66` — отмена с пустым GUID и несуществующим заказом. Поведение не меняется, но функциональные тесты нужны для нового сценария.
- `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs` — тестов отмены и оплаты в нём нет (проверено поиском). Нужны новые: Paid→Cancelled (через новый метод), Shipped→Cancelled (запрет), StockConfirmed + оплата после отмены (возврат), повторная отмена.
- `tests/Ordering.UnitTests/Application/IdentifiedCommandHandlerTest.cs` — повтор `x-requestid` после ошибки (Q-058).
- Тестов для `OrderStatusChangedToPaidDomainEventHandler`, `OrderPaymentSucceededIntegrationEventHandler`, Catalog Paid-handler в `tests/` не найдено. Их и обработчики возврата надо покрыть.
- `tests/Application.UnitTests/OrderProcessorTests.cs` — не затрагивается.
- `tests/Webhooks.FunctionalTests/WebhooksApiTests.cs` и `tests/Application.UnitTests/WebhookTests.cs` — если добавляется тип вебхука.
- `tests/ClientApp.UnitTests` — видимость кнопки и текст статуса в `OrderDetailViewModel`.
- `tests/Catalog.FunctionalTests` — возврат остатка и обрезка по `MaxStockThreshold`.
- PaymentProcessor тестового проекта нет. Нужно добавить (по образцу `tests/Application.UnitTests`).
- `e2e/` (Playwright) — сценария отмены в e2e нет (поиском не найдено). Если меняется витрина, добавить.
- Для функциональных тестов нужны поднятые зависимости (БД, RabbitMQ) через AppHost или Docker — из кода не проверено, как именно запускается `tests/*FunctionalTests`. Не запускал.

Спеки и документы, которые надо обновить через `openspec/changes/<изменение>/` (AGENTS.md: основные спеки руками не правим):
- `openspec/specs/order-management/spec.md`: MODIFIED «Отмена заказа», «Доступ к операциям заказа» (Q-055 блокирует).
- `openspec/specs/order-payment/spec.md`: «Отказ оплаты отменяет заказ» (сценарий «Заказ уже оплачен»), «Исход оплаты» (если меняется событие), «Оплата переводит заказ в Paid» (сценарий «Заказ в другом статусе», Q-061).
- `openspec/specs/order-lifecycle/spec.md`: новые статусы и переходы.
- `openspec/specs/catalog-stock/spec.md`: возврат остатка.
- `openspec/specs/webhook-delivery/spec.md` / `webhook-subscriptions/spec.md`: если добавляется тип.
- `system-context/contracts.md`, `data.md`, `domain.md`, `trace.md`, `integrations.md` — обновить разделы по контрактам и данным (AGENTS.md: после изменения кода — trace.md и integrations.md).

## 8. Риски

Топ-3:
1. Авторизация. Владелец и роль не проверяются (Q-055, `openspec/specs/order-management/spec.md`, «Доступ к операциям заказа»). Номера заказов последовательные (HiLo, `OrderEntityTypeConfiguration.cs:11-12`). После изменения любой вошедший пользователь сможет отменить чужой оплаченный заказ и инициировать возврат. Это денежный риск. Нужна проверка владельца (по `sub` = `BuyerIdentityGuid`) до включения отмены Paid.
2. Согласованность денег и состояния при асинхронном возврате:
   - Обмен событиями без повторов: сбой публикации помечает событие PublishedFailed и не повторяет (`IntegrationEventLogService.cs:58`, Q-054); входящие события подтверждаются даже при исключении (Q-049). Потерянный запрос возврата = заказ отменён в состоянии ожидания или, наоборот, деньги не вернулись.
   - Гонка Paid: отмена и отгрузка одновременно на одном заказе. Оба читают Paid, оба пишут без версии строки (`data.md`, «Конкурентность»). Итог: заказ отгружен и деньги возвращены, или отменён, но отправлен.
   - Окно 10 с: отмена в StockConfirmed, потом «оплата прошла» → `SetPaidStatus` молча пропускает (`Order.cs:121`). Деньги списаны без заказа. Возврат здесь обязателен.
   - Внешний вызов нельзя делать внутри `TransactionBehavior` (`TransactionBehavior.cs:43-52`). Иначе откат транзакции не откатит возврат.
3. Идемпотентность и повтор. `x-requestid` записывается до выполнения команды (`IdentifiedCommandHandler.cs:48`), любая ошибка → default (99-102). Значит после неудачного возврата повтор с тем же id вернёт 200 без действия (Q-058). Для возврата нужен отдельный ключ идемпотентности по попытке возврата (в процессоре и в БД), а клиентский `x-requestid` не должен означать «возврат выполнен». Иначе клиент получит 200 при невозвращённых деньгах.

Прочие риски:
- Ответ 200 для Paid при асинхронном возврате: клиент MAUI (`OrderDetailViewModel.cs:48-50`) сразу ставит «Cancelled». Витрина показывает статус из БД. Пользователь может увидеть «Отменён» до возврата.
- Отмена Paid из `OrderPaymentFailed`: если ошибочно разрешить Paid в общем `SetCancelledStatus`, отказ оплаты будет отменять оплаченный заказ без возврата (`OrderPaymentFailedIntegrationEventHandler.cs:12`).
- Остаток: `AddStock` обрезает по `MaxStockThreshold` (`CatalogItem.cs:91-96`), часть возврата пропадёт тихо. Catalog сейчас не подписан на отмену — остаток при отмене не вернётся вообще.
- Вебхуки: внешние получатели видят `OrderPaid` и не получают ничего при отмене. Повторов доставки нет (Q-099), сбой = потеря.
- Валюта и сумма: не хранятся. Возврат по сумме без валюты может быть неверным при смене валюты процессора.
- Процессор сейчас заглушка (`PaymentOptions.PaymentSucceeded`, Q-064). Реального идентификатора списания нет, поэтому возврат нельзя проверить на реальном процессоре.
- Частичная отмена: спека и задача про весь заказ. Если понадобится частичный возврат, модель изменится сильнее.

## 9. Чего не хватило

Не было в файлах, и что я предположил:
- Какой платёжный процессор и его API возврата: нет ни клиента, ни настроек, ни ключей. Предположил: HTTP-вызов возврата из PaymentProcessor, полный возврат суммы заказа, результат приходит асинхронно (событием). Влияние: высокое. Меняет разделы 2, 3, 4, 5.
- Идентификатор списания: в событии `OrderPaymentSucceeded` его нет, в домене и БД нет. Предположил, что процессор его вернёт и его надо сохранить. Влияние: высокое (без него возврат невозможен).
- Что делает отмена Paid в API: 200 сразу (до возврата) или после подтверждения возврата. Не решено в задаче. Предположил асинхронно, с промежуточным статусом (например `RefundPending`) и итогом Cancelled после подтверждения. Влияние: высокое (контракт, UI, статусы).
- Валюта и единица суммы: не нашёл. Предположил одну валюту, сумма = `GetTotal()`. Влияние: среднее.
- Нужна ли кнопка отмены в витрине (WebApp): в витрине её нет, в MAUI есть только для Submitted. Предположил, что задача касается обоих клиентов, но это может быть только API. Влияние: среднее (объём UI).
- Нужен ли сигнал внешним получателям вебхуков при отмене. Предположил, что да, но не обязательно. Влияние: низкое–среднее.
- Включена ли в ходе задачи реальная оплата или остаётся заглушка (Q-064). Предположил, что заглушка остаётся, а возврат добавляется как интерфейс с той же заглушкой. Влияние: высокое (тесты и что проверяется).
- Есть ли в EF-миграциях CHECK на статус. Не открывал миграции. Предположил, что нет. Влияние: низкое.
- Как запускаются функциональные тесты (нужны ли Docker, БД, RabbitMQ). Не проверял. Влияние: среднее (план проверки).
- Ответы на открытые вопросы: Q-055 (кто может отменять), Q-060 (отмена до/после оплаты), Q-061 (оплата после отмены), Q-058 (повтор с тем же requestId), Q-049/Q-054 (потеря событий). В `system-context/QUESTIONS.md` они открыты; по ним нельзя опираться без ответа. Влияние: высокое — пять вопросов блокируют реализацию денежного пути.
- Не смотрел `src/EventBusRabbitMQ/RabbitMQEventBus.cs` (общий файл, см. `system-context/GUIDE.md`) и реализацию повторов шины; опирался на спеку order-payment и order-lifecycle. Влияние: среднее.
- Не проверял конкурентность в EF (нет ли `RowVersion` в конфигурациях), опирался на `system-context/data.md`. Влияние: среднее.
