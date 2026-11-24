# Анализ влияния: отмена заказа после оплаты, до отправки

Задача: «Покупатель должен иметь возможность отменить заказ и после оплаты, пока заказ не отправлен. Деньги при такой отмене возвращаются покупателю через платёжный процессор.»

Репозиторий: `/private/tmp/claude-501/-Users-ekotov-AI-skills-hub/27bc2ddf-d4cd-48cd-ac1f-1124a29170a5/scratchpad/withcode/r2`. Пути ниже относительны к корню репо, строки на момент анализа. AGENTS.md в корне репо нет. Код не менялся, ничего не запускалось и не собиралось.

Факты, на которые опирается анализ:
- Статусы: Submitted, AwaitingValidation, StockConfirmed, Paid, Shipped, Cancelled (`src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderStatus.cs:8-13`). Хранятся строкой, max 30 (`src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs:18-21`).
- Оплата происходит в PaymentProcessor. Ordering публикует `OrderStatusChangedToStockConfirmed`, PaymentProcessor по флагу `PaymentOptions.PaymentSucceeded` шлёт `OrderPaymentSucceeded` или `OrderPaymentFailed` (`src/PaymentProcessor/IntegrationEvents/EventHandling/OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs:21-32`). Идентификатора транзакции нет.
- Статус Paid ставится позже: `SetPaidOrderStatusCommandHandler` ждёт `Task.Delay(10000)` (`src/Ordering.API/Application/Commands/SetPaidOrderStatusCommandHandler.cs:22`), затем `SetPaidStatus`.
- Отмена сейчас запрещена только из Paid и Shipped (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:142-153`).

## 1. Затронутое поведение

Меняется:
- Отмена из Paid становится разрешённой (`Order.cs:144-148`, guard сейчас включает Paid).
- Отмена оплаченного заказа запускает возврат через платёжный процессор.
- Отмена, когда деньги уже списаны, но Ordering ещё не в Paid (окно между StockConfirmed и Paid), тоже должна вести к возврату. Это решение нужно подтвердить (см. п. 9).
- Событие `OrderPaymentSucceeded`, пришедшее после отмены, сейчас молча игнорируется. Его надо превратить в возврат.

Сохраняется:
- Shipped блокирует отмену (`Order.cs:144-148`, `Order.cs:132-135` для ship).
- Отмена из Submitted, AwaitingValidation, StockConfirmed работает как раньше.
- Авто-отмена по `OrderPaymentFailed` (`src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentFailedIntegrationEventHandler.cs:12`) не меняется. Оплаты не было, возврат не нужен.
- Отмена при отказе стока (`Order.cs:155-168`) не меняется.
- Клиентская кнопка отмены видна только для Submitted (`src/ClientApp/ViewModels/OrderDetailViewModel.cs:38`). Это меняется (см. п. 4).

## 2. Контракты API

- `PUT /api/orders/cancel` (`src/Ordering.API/Apis/OrdersApi.cs:11`, обработчик `:22-49`).
  - Запрос: тело `CancelOrderCommand { OrderNumber: int }`, заголовок `x-requestid` (Guid, пустой даёт 400).
  - Ответы сейчас: 200 Ok, 400 BadRequest, 500 `ProblemHttpResult` «Cancel order failed to process.» при `false`.
  - Меняется: отмена оплаченного заказа возвращает 200 (сейчас 500). Для Shipped предлагается 409 вместо 500 (сейчас тоже 500, через `IdentifiedCommandHandler`).
  - Совместимость: `src/ClientApp/Services/Order/OrderService.cs:104` ловит только 400. Смена 500 на 409 не ломает ClientApp, но меняет контракт для любых других клиентов. Других клиентов в репо не найдено.
- `GET /api/orders/{orderId}` и `GET /api/orders` (`OrdersApi.cs:13-14`): поле статуса строкой. Если добавляется новый статус (например Refunded), клиенты с парсингом строк не сломаются. Ответ сериализует enum через `JsonStringEnumConverter` (`OrderStatus.cs:5`).
- Новых эндпоинтов для покупателя не нужно. Возврат внутренний, через события.
- Webhooks `POST /api/webhooks` (`src/Webhooks.API/Model/WebhookSubscriptionRequest.cs:22-26`): если добавить `WebhookType.OrderCancelled`, вход принимает новое имя без изменения API.

## 3. События

Меняются:
- `OrderCancelledDomainEvent` (`src/Ordering.Domain/Events/OrderCancelledDomainEvent.cs`, публикуется в `Order.cs:152`). Подписчик `OrderCancelledDomainEventHandler` (`src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:23-31`) сейчас публикует интеграционное событие. Нужно знать статус до отмены и наличие оплаты. Сейчас handler читает уже Cancelled (`:30`).
- `OrderStatusChangedToCancelledIntegrationEvent` (`src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs:3-17`). Поля: OrderId, OrderStatus (enum), BuyerName, BuyerIdentityGuid. Подписчик WebApp (`src/WebApp/Extensions/Extensions.cs:49`, `src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToCancelledIntegrationEventHandler.cs:10-13`) обновляет список заказов. Контракт продублирован в WebApp (`src/WebApp/Services/OrderStatus/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs:5-19`), там OrderStatus строкой. При изменении полей менять оба. Возможно, нужен флаг `RefundRequired`.
- `OrderPaymentSucceededIntegrationEvent`. Публикует PaymentProcessor (`src/PaymentProcessor/IntegrationEvents/Events/OrderPaymentSucceededIntegrationEvent.cs:3`). Подписчик Ordering `OrderPaymentSucceededIntegrationEventHandler.cs:8-21` шлёт `SetPaidOrderStatusCommand`. Меняется смысл: если заказ уже Cancelled, нужен запрос возврата.

Новые (предложение):
- `OrderRefundRequestedIntegrationEvent { OrderId, RefundId, Amount }`. Публикует Ordering через outbox (`src/Ordering.API/Application/IntegrationEvents/OrderingIntegrationEventService.cs:36-41`). Подписчик PaymentProcessor (`src/PaymentProcessor/Program.cs:5-6`).
- `OrderRefundSucceededIntegrationEvent` и `OrderRefundFailedIntegrationEvent { OrderId, RefundId }`. Публикует PaymentProcessor. Подписчик Ordering (`src/Ordering.API/Extensions/Extensions.cs:57-61`) переводит состояние возврата.
- Для Catalog нужно восстановить сток. Либо новое событие `OrderCancelledAfterPaymentIntegrationEvent` с items, либо расширить `OrderStatusChangedToCancelled` полем items. Подписчик Catalog (`src/Catalog.API/Extensions/Extensions.cs:32-33`) вызывает `AddStock`.
- Опционально: `WebhookType.OrderCancelled` (`src/Webhooks.API/Model/WebhookType.cs:3-8`) и подписка в `src/Webhooks.API/Extensions/Extensions.cs:21-23`.

Не меняются: `OrderStatusChangedToPaid` (`src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToPaidIntegrationEvent.cs`). Его подписчики: Catalog (`src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:8-21`, RemoveStock), Webhooks (`src/Webhooks.API/IntegrationEvents/OrderStatusChangedToPaidIntegrationEventHandler.cs:8-17`), WebApp.

## 4. Потребители и сервисы

Меняются:
- Ordering.API: команда отмены, обработчики событий, новые события возврата, ответы API, проверка владельца заказа.
- PaymentProcessor: новый обработчик запроса возврата и публикация результата. Это единственный «платёжный процессор» в репо, и он симулятор (см. п. 9).
- Catalog.API: обработчик возврата стока. Сток списывается при Paid (`OrderStatusChangedToPaidIntegrationEventHandler.cs:17`), значит при отмене после Paid его надо вернуть.
- ClientApp (MAUI): кнопка отмены для Paid, логика статуса после отмены (`src/ClientApp/ViewModels/OrderDetailViewModel.cs:38, 43-59`, `src/ClientApp/Views/OrderDetailView.xaml:78-80`), мок (`src/ClientApp/Services/Order/OrderMockService.cs:183-186`).

Проверить (возможно менять):
- WebApp: список заказов (`src/WebApp/Components/Pages/User/Orders.razor:36-56`). Кнопки отмены в WebApp нет и в `src/WebApp/Services/OrderingService.cs` метода отмены нет. Если кнопка нужна и в вебе, добавить метод и кнопку. Класс статуса строится из строки (`Orders.razor:51`), новый статус получит стиль по умолчанию. Уведомления через `OrderStatusNotificationService.cs` работают только в памяти одного инстанса (`:6-7`).
- Webhooks.API: покупатель получит `OrderPaid`, потом `Cancelled` без вебхука. Нужно решить, нужен ли `OrderCancelled`.
- OrderProcessor: `src/OrderProcessor/Services/GracePeriodOrdersRepository.cs:27` выбирает только Submitted. Не меняется.
- Identity и gateway: `src/Ordering.API/Program.cs:21-22` требует авторизацию для всего `/api/orders`. Конфиг шлюза не читал.

## 5. Данные

- `orders.OrderStatus` (строка, max 30): новый статус не требует изменения колонки, если нет CHECK-ограничения (миграции не читал, см. п. 9).
- `orders.PaymentMethodId` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:35`, `:93-97`): ссылка на карту, а не на транзакцию. Для возврата нужен идентификатор платежа/транзакции. Нужна новая колонка в `orders` или новая таблица `payments`/`refunds`. Конфиг: `src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs:23-32`. Миграция: новая в `src/Ordering.Infrastructure/Migrations/`, снапшот `OrderingContextModelSnapshot.cs`.
- Таблица возвратов с идентификатором `RefundId` и уникальным ключом (`OrderId`, `RefundId`) для идемпотентности. Новая.
- Сумма возврата: `Order.GetTotal()` (`Order.cs:185`) считает `Units * UnitPrice`, без учёта `Discount`. Если скидка хранится отдельно, сумма возврата может не совпасть с списанием. `OrderItem.cs` не читал.
- Outbox: `IntegrationEventLogEF` уже есть (`src/IntegrationEventLogEF/Services/IntegrationEventLogService.cs`). Новые события пойдут через него.
- Catalog: `CatalogItem.AvailableStock` (`src/Catalog.API/Model/CatalogItem.cs`), восстановление через `AddStock` (`:86-101`).
- Webhooks: `WebhookSubscription.Type` (способ хранения не читал).
- Засев (`src/Ordering.API/Infrastructure/OrderingContextSeed.cs`) и кэш: не менять. Кэша статусов в Ordering не найдено.

## 6. Код

Ordering.Domain:
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderStatus.cs:8-13`: новый статус (например `Refunded`), если выбран вариант с отдельным статусом.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:142-153` `SetCancelledStatus`: разрешить Paid, запретить Shipped, добавить признак возврата в событие.
- `Order.cs:119-128` `SetPaidStatus`: учесть, что заказ может быть уже Cancelled (оплата пришла после отмены).
- `Order.cs:35`, `:93-97`: поле для идентификатора транзакции.
- `Order.cs:185` `GetTotal`: проверить расчёт с учётом скидки.
- `src/Ordering.Domain/Events/OrderCancelledDomainEvent.cs`: признак «была оплата» или предыдущий статус.
- Новые доменные события возврата в `src/Ordering.Domain/Events/`.

Ordering.API:
- `src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs:19-29`: без изменений логики, если возврат идёт из domain event.
- `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:23-31`: публиковать запрос возврата, если была оплата.
- `src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderPaymentSucceededIntegrationEventHandler.cs:8-21`: если заказ Cancelled, запустить возврат.
- `src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs:3-17`: поля при необходимости.
- Новые файлы: `src/Ordering.API/Application/IntegrationEvents/Events/OrderRefund*IntegrationEvent.cs` и обработчики в `.../EventHandling/`.
- `src/Ordering.API/Extensions/Extensions.cs:57-61`: подписки на результаты возврата.
- `src/Ordering.API/Apis/OrdersApi.cs:22-49`: ответ 409 для Shipped, проверка владельца заказа (сейчас нет, см. риск R3). `IdentityService` доступен через `src/Ordering.API/Apis/OrderServices.cs:10`.
- `src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs:99-102`: `catch` возвращает `default` и прячет доменные исключения. Для 409 нужен другой путь.
- `src/Ordering.API/Application/Validations/CancelOrderCommandValidator.cs:7`: без изменений.
- `src/Ordering.API/Application/Behaviors/TransactionBehavior.cs:20-50`: запись события возврата в outbox попадает в ту же транзакцию. Проверить.

Ordering.Infrastructure:
- `src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs:23-32`: новые поля или связь.
- `src/Ordering.Infrastructure/Migrations/`: новая миграция.
- `src/Ordering.Infrastructure/Repositories/OrderRepository.cs:21-32` `GetAsync`: без изменений, нужно для items и суммы.

PaymentProcessor:
- `src/PaymentProcessor/Program.cs:5-6`: подписка на `OrderRefundRequested`.
- Новые файлы в `src/PaymentProcessor/IntegrationEvents/EventHandling/` и `.../Events/`.
- `src/PaymentProcessor/PaymentOptions.cs:5` и `src/PaymentProcessor/appsettings.json:14-16`: флаг только для оплаты. Для возврата нужна своя настройка или всегда успех.

Catalog.API:
- `src/Catalog.API/Extensions/Extensions.cs:32-33`: подписка на событие возврата стока.
- Новый обработчик в `src/Catalog.API/IntegrationEvents/EventHandling/` (образец: `OrderStatusChangedToPaidIntegrationEventHandler.cs:8-21`).
- `src/Catalog.API/Model/CatalogItem.cs:86-101` `AddStock`: без изменений, но см. риск R5.

Webhooks.API (опционально):
- `src/Webhooks.API/Model/WebhookType.cs:3-8`: `OrderCancelled = 4`.
- `src/Webhooks.API/Extensions/Extensions.cs:21-23`: подписка.
- Новый файл в `src/Webhooks.API/IntegrationEvents/`.

WebApp (проверить):
- `src/WebApp/Components/Pages/User/Orders.razor:51`: стиль нового статуса.
- `src/WebApp/Services/OrderingService.cs`: метод отмены, если нужна кнопка.
- `src/WebApp/Services/OrderStatus/IntegrationEvents/Events/OrderStatusChangedToCancelledIntegrationEvent.cs`: синхронизировать поля.

ClientApp:
- `src/ClientApp/ViewModels/OrderDetailViewModel.cs:38`: условие `IsSubmittedOrder` включает Paid.
- `src/ClientApp/ViewModels/OrderDetailViewModel.cs:43-59` `ToggleCancelOrderAsync`: статус «Cancelled» показывается сразу. Для возврата нужен промежуточный текст.
- `src/ClientApp/Views/OrderDetailView.xaml:78-80`: видимость кнопки.
- `src/ClientApp/Services/Order/OrderService.cs:83-110`: ловит только 400 (`:104`). Для 500 или 409 поведение нужно проверить.
- `src/ClientApp/Services/Order/OrderMockService.cs:183-186`: мок, всегда true.

OrderProcessor: `src/OrderProcessor/Services/GracePeriodOrdersRepository.cs:24-28`: не менять.

## 7. Тесты и проверка

Обновить или добавить:
- `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs`: тестов на отмену нет. Добавить: Paid to Cancelled допустимо, Shipped to Cancelled бросает исключение, повторная отмена, событие с признаком возврата.
- `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs:25-50`, `:158-170`: сценарии отмены. Добавить 409 для Shipped.
- `tests/Ordering.UnitTests/Application/IdentifiedCommandHandlerTest.cs`: если меняется `catch` в `IdentifiedCommandHandler.cs`.
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs:39-66`: сценарии отмены с пустым GUID и несуществующим заказом. Нужны Postgres и RabbitMQ (через Aspire AppHost). Проверить, что окружение поднимается.
- `tests/Application.UnitTests/PaymentProcessorTests.cs:13-40`: добавить тесты обработчика возврата.
- `tests/Catalog.FunctionalTests/CatalogApiTests.cs`: тест восстановления стока.
- `tests/Webhooks.FunctionalTests/WebhooksApiTests.cs`: если добавляется `OrderCancelled`.
- `tests/ClientApp.UnitTests/ViewModels/OrderViewModelTests.cs`, `tests/ClientApp.UnitTests/Services/OrdersServiceTests.cs`: кнопка для Paid и ответы сервиса.
- `e2e/`: тестов отмены нет. Добавлять только если меняется UI веба.
- Новые тесты: идемпотентность обработки повторного события возврата, порядок «оплата пришла после отмены», сумма возврата с учётом скидки.

## 8. Риски

- R1 (высокий): окно между оплатой и Paid. Оплата в PaymentProcessor идёт сразу после StockConfirmed (`OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs:21-32`), а Paid ставится через 10 секунд (`SetPaidOrderStatusCommandHandler.cs:22`). Отмена в StockConfirmed сейчас проходит (`Order.cs:144-148`), и деньги могут быть уже списаны без возврата. Также `OrderPaymentSucceeded` после Cancelled сейчас молча игнорируется. Нужна явная модель состояния платежа и правило «возврат при любой успешной оплате».
- R2 (высокий): доставка событий и повторы. RabbitMQ подтверждает сообщение даже при ошибке (`src/EventBusRabbitMQ/RabbitMQEventBus.cs:180`, комментарий «Even on exception we take the message off the queue»). Потерянный `RefundRequested` означает отменённый заказ без возврата. Обработчики Catalog (`OrderStatusChangedToPaidIntegrationEventHandler.cs:13-20`) и PaymentProcessor не идемпотентны. Повтор события даст двойной сток или двойной возврат. Нужны outbox (есть), идемпотентность по `RefundId` и повторная обработка или DLX.
- R3 (высокий): авторизация. `PUT /api/orders/cancel` (`OrdersApi.cs:22-49`) и `PUT /api/orders/ship` (`:51-78`) не проверяют владельца заказа и роль. `GetAsync(OrderNumber)` не фильтрует по пользователю. Любой вошедший пользователь может отменить чужой оплаченный заказ, и возврат уйдёт не тому покупателю. Любой может поставить Shipped, и тогда отмена станет невозможна. Нужна проверка `BuyerIdentityGuid` и роли до внесения изменения.
- R4: сумма возврата. `GetTotal` (`Order.cs:185`) не учитывает `Discount`. Возврат может не совпасть с фактическим списанием.
- R5: восстановление стока. `AddStock` обрезает по `MaxStockThreshold` (`CatalogItem.cs:91-95`). Часть единиц пропадает.
- R6: конкурентность. В `OrderEntityTypeConfiguration.cs` нет токена конкурентности. Гонка «отмена и отправка» или «отмена и оплата» может затереть статус (lost update). Проверено по конфигурации, миграции не смотрел.
- R7: совместимость. Ответ 500 меняется на 409. Клиент ловит только 400 (`OrderService.cs:104`). Новый статус без стиля в WebApp (`Orders.razor:51`).
- R8: `IdentifiedCommandHandler.cs:99-102` прячет доменные исключения за `false`, и клиент видит общее 500. Причина отказа не возвращается.

## 9. Чего не хватило

Предположения и пробелы:
- Есть ли реальный платёжный шлюз с API возврата и id транзакции. Предположил, что PaymentProcessor (симулятор с флагом `PaymentOptions.PaymentSucceeded`) — единственный процессор и id транзакции отсутствует. Влияние высокое: меняет контракт, таблицы и тесты.
- Что значит «отправлен». Предположил: статус Shipped, который ставит `PUT /api/orders/ship`. Отдельного трекинга доставки не нашёл. Влияние высокое.
- Должна ли отмена в окне StockConfirmed (до Paid) тоже возвращать деньги. Предположил да (R1). Влияние высокое.
- Частичная отмена позиций. Предположил, что нет, отменяется весь заказ. Влияние среднее.
- Срок, валюта, комиссия возврата. Валюты в модели нет. Предположил полный возврат `GetTotal()`. Влияние среднее.
- Новый статус заказа (например Refunded) или Cancelled плюс отдельный статус возврата. Предположил второе: меньше изменений в контракте. Влияние среднее.
- Роли администратора и claims для ship. Не читал Identity.API и `AddDefaultAuthentication`. Предположил, что ship и cancel ограничены только авторизацией, без ролей (`OrdersApi.cs` и `Program.cs:21-22`). Влияние высокое (R3).
- Поведение ClientApp при 500. Не читал `RequestProvider.PutAsync`. Предположил, что исключение не обрабатывается в `ToggleCancelOrderAsync` (`OrderDetailViewModel.cs:44-59`). Влияние среднее.
- Способ хранения `WebhookSubscription.Type` (int или string). Модель не читал. Предположил, что `Enum.Parse` (`WebhookSubscriptionRequest.cs:22`) достаточно для нового типа. Влияние низкое.
- CHECK-ограничения на `OrderStatus` в миграциях. Миграции не читал. Предположил, что нет. Влияние низкое.
- `OrderItem.cs` (как `Discount` связан с `UnitPrice`). Не читал. Влияние среднее (R4).
- Не читал: `OrderingContextSeed`, `OrderQueries` детально, `WebhooksSender`, тесты ClientApp, `IntegrationEventLogEF`. Предположил, что связанной логики там нет.
- Не найдено ограничений по времени для отмены.

Итог: затронуто 3 сервиса меняются (Ordering, PaymentProcessor, Catalog) и 4 проверяются (Webhooks, WebApp, ClientApp, OrderProcessor), всего 7. Событий: 3 меняются (`OrderCancelledDomainEvent`, `OrderStatusChangedToCancelled` в двух копиях, `OrderPaymentSucceeded`), 3 новых (запрос возврата, результат успех и ошибка), плюс опционально `OrderCancelled` для вебхуков и событие для стока. Файлов около 45, из них около 15 новых. Топ-3 риска: R1 (окно оплаты и Paid), R2 (потеря и повтор событий, нет идемпотентности), R3 (отмена и отправка без проверки владельца и роли).
