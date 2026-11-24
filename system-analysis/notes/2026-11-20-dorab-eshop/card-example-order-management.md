# order-management — Заказы: просмотр, отмена, отгрузка

Карточка изменения: всё, что нужно, чтобы поменять эту возможность и ничего не сломать. Собрана скриптом (`plan.py guide`)
из спеки, трассировки, contracts.md, data.md и QUESTIONS.md — не правь её руками, правь источники.
Места `путь:строка` — подсказка, строки могли сдвинуться: ищи по символу (`Класс.Метод`) через grep.

**Назначение:** Просмотр своих заказов и заказа по номеру, отмена заказа до оплаты и отгрузка оплаченного заказа через HTTP API сервиса заказов.
**Спека:** `openspec/specs/order-management/spec.md` — требований 6

## Требования
- Отмена заказа
  - код: src/Ordering.API/Apis/OrdersApi.cs:11, src/Ordering.API/Apis/OrdersApi.cs:22-49; тесты: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs
- Отгрузка заказа
  - код: src/Ordering.API/Apis/OrdersApi.cs:12, src/Ordering.API/Apis/OrdersApi.cs:51-78; тесты: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs
- Повтор запроса с тем же x-requestid
  - код: src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs:39-104, src/Ordering.Infrastructure/Idempotency/RequestManager.cs:21-37; тесты: —
- Просмотр заказа по номеру
  - код: src/Ordering.API/Apis/OrdersApi.cs:13, src/Ordering.API/Apis/OrdersApi.cs:80-91; тесты: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs
- Список заказов текущего покупателя
  - код: src/Ordering.API/Apis/OrdersApi.cs:14, src/Ordering.API/Apis/OrdersApi.cs:93-98; тесты: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs
- Доступ к операциям заказа
  - код: src/Ordering.API/Program.cs:21-22, src/Ordering.API/Apis/OrdersApi.cs:22-25; тесты: —

## Входы и контракты
- `http:PUT /api/orders/cancel` → `OrdersApi.CancelOrderAsync` (src/Ordering.API/Apis/OrdersApi.cs:22)
  - заголовки: x-requestid
  - ответы: 400 BadRequest «Empty GUID is not valid for request ID»; 500 Problem «Cancel order failed to process.»; 200 Ok
  - `CancelOrderCommand`: OrderNumber int
  - `IdentifiedCommand`: Command T, Id Guid
  - заметки: ответ `400` отдаётся только при пустом `x-requestid` (src/Ordering.API/Apis/OrdersApi.cs:27-30). Отмена заказа в статусе Paid или Shipped бросает `OrderingDomainException` (src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:144-147, 182), но общий `IdentifiedCommandHandler` глотает любое исключение и возвращает `false` …
- `http:PUT /api/orders/ship` → `OrdersApi.ShipOrderAsync` (src/Ordering.API/Apis/OrdersApi.cs:51)
  - заголовки: x-requestid
  - ответы: 400 BadRequest «Empty GUID is not valid for request ID»; 500 Problem «Ship order failed to process.»; 200 Ok
  - `ShipOrderCommand`: OrderNumber int
  - `IdentifiedCommand`: Command T, Id Guid
  - заметки: отправка допустима только из Paid (Order.cs:132-135); иначе исключение глотается в `IdentifiedCommandHandler` и клиент видит `500` «Ship order failed to process.» (OrdersApi.cs:72-75), а не 4xx.
- `http:GET /api/orders/{orderId}` → `OrdersApi.GetOrderAsync` (src/Ordering.API/Apis/OrdersApi.cs:80)
  - ответы: 200 Ok; 404 NotFound
  - `Order`: OrderNumber int, Date DateTime, Status string, Description string, Street string, City string, State string, Zipcode string, Country string, OrderItems List<Orderitem> … ещё 1
  - заметки: любое исключение (включая отсутствие заказа и ошибку БД) превращается в `404` (OrdersApi.cs:82-90); в запросе нет фильтра по владельцу заказа — проверяй доступ отдельно, если меняешь.
- `http:GET /api/orders` → `OrdersApi.GetOrdersByUserAsync` (src/Ordering.API/Apis/OrdersApi.cs:93)
  - ответы: 200 Ok
  - `OrderSummary`: OrderNumber int, Date DateTime, Status string, Total double
  - заметки: список строится по `GetUserIdentity()` из токена (OrdersApi.cs:95-96) — чужие заказы не вернутся; `Total` здесь `double`, в детали заказа `decimal`.

## События
- `OrderCancelledDomainEvent` (внутреннее; подписана эта возможность)
  - поля: Order Order
  - подписаны: Ordering.API (возможности: order-management)
- `OrderShippedDomainEvent` (внутреннее; подписана эта возможность)
  - поля: Order Order
  - подписаны: Ordering.API (возможности: order-management)
- `OrderStatusChangedToCancelledIntegrationEvent` (между сервисами; публикуется по цепочке из этой возможности)
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string; копий: 2
  - подписаны: WebApp (возможности: order-status-notifications)
- `OrderStatusChangedToShippedIntegrationEvent` (между сервисами; публикуется по цепочке из этой возможности)
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string ⚠ копии в сервисах различаются
  - подписаны: WebApp, Webhooks.API (возможности: order-status-notifications, webhook-delivery)
  - заметки: в копии Webhooks нет `BuyerIdentityGuid`. Обработчик берёт ВСЕ подписки типа `OrderShipped` без фильтра по пользователю (src/Webhooks.API/Services/WebhooksRetriever.cs:5-8) и рассылает им событие целиком — каждый подписчик получит данные заказов всех покупателей (имя покупателя в `BuyerName`).

## Кто ещё вызывает эти входы
- src/ClientApp → /api/orders (клиентское приложение)
  - опирается на: только версия 1.0 (`api-version=1.0`, src/ClientApp/Services/Order/OrderService.cs:14). Страница заказа читает `Order` с JSON-именами `status`, `ordernumber`, `date`, `total`, `items`, `city`, `street`, `state`, `country`, `zipCode` (src/ClientApp/Models/Orders/Order.cs:13-50); сервер отдаёт `Status`, `OrderNumber`, `Zipcode`, `OrderItems` (src/Ordering.API/Application/Queries/OrderViewModel.cs:12-23): `status`, `ordernumber`, `zipCode` совпадают только без учёта регистра, а `items` клиента и `OrderItems` сервера различаются по имени — список позиций на клиенте может не …
- src/WebApp → /api/orders
  - опирается на: `GET api/Orders/` в `OrderRecord(OrderNumber, Date, Status, Total)` (src/WebApp/Services/OrderingService.cs:9, 21-25) — форма `OrderSummary` сервера; список заказов выводит их и строит CSS-класс из `Status.ToLower()` (src/WebApp/Components/Pages/User/Orders.razor:48-52), то есть новый статус без CSS-класса отрисуется без стиля. `POST` создания заказа шлёт `x-requestid` и тело `CreateOrderRequest` (OrderingService.cs:12-18); ответ не проверяется, `EnsureSuccess` нет — а сервер на невалидный заказ всё равно отвечает 200 (см. заметку под `POST /api/orders`). Версия 1.0 через …
- src/eShop.AppHost → /api/orders
  - опирается на: конфигурация шлюза: `/api/orders/{*any}` → ordering-api, пропускает только `api-version` 1.0/1 (src/eShop.AppHost/Extensions.cs:155-156); авторизация — на стороне сервиса (`RequireAuthorization`). Сломается при: выпуске v2 заказов — шлюз его не пропустит, пока не поменять значения здесь.

## Данные
- `Order` (src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs)
  - создаётся: `CheckoutViewModel.InitializeAsync` src/ClientApp/ViewModels/CheckoutViewModel.cs:70, `CreateOrderCommandHandler.Handle` src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:40, `OrderQueries.GetOrderAsync` src/Ordering.API/Application/Queries/OrderQueries.cs:15, `Order.NewDraft` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:39
  - копии полей: `Order` (src/ClientApp/Models/Orders/Order.cs)

## Ограничения (общие)
- Транзакции: **Конкурентность.** Защиты от параллельных изменений нет нигде: нет версии строки, `xmin`, блокировок БД; чтение-изменение-запись выполняется без проверки, «последняя запись побеждает». Конкретно: обновление товара копирует тело запроса поверх сущности (src/Catalog.API/Apis/CatalogApi.cs:389-390) — два параллельных `PUT` или `PUT` и списание остатка затрут друг друга; остаток списывается `RemoveStock` при оплате (src/Catalog.API/Model/CatalogItem.cs:62-77), а наличие проверяется раньше, на шаге …
- Валидация: Проверка входных данных подключена только в двух сервисах. **Ordering:** валидаторы FluentValidation для `CreateOrderCommand`, `CancelOrderCommand`, `ShipOrderCommand` (src/Ordering.API/Application/Validations/) запускает `ValidatorBehavior` в конвейере MediatR (src/Ordering.API/Application/Behaviors/ValidatorBehavior.cs:20-34, регистрация Extensions.cs:42, 47); при нарушении он кидает `OrderingDomainException`, а `IdentifiedCommandHandler` превращает это в `false` — API не отдаёт пользователю …

## Открытые вопросы
- Q-055 [блокирует] Кто может отменять, отгружать и читать чужие заказы?
  - допущение: спека описывает код: любой вошедший пользователь может отменить, отгрузить и прочитать любой заказ по номеру
- Q-058 [блокирует] Повтор с тем же x-requestid после неудачи должен повторить действие?
  - допущение: спека описывает код: повтор после неудачи даёт 200 и не выполняет команду
- Q-056 [уточняет] Для отказа в отмене и отгрузке нужен код 500 или 4xx (например 409)?
  - допущение: спека описывает код: 500 с текстом как в коде
- Q-057 [уточняет] Если обработчик события отмены упал, статус «Отменён» должен откатиться?
  - допущение: спека описывает код: статус сохраняется, ответ 500 (вероятно по коду, не проверено запуском)
- Q-059 [уточняет] Повторная отмена уже отменённого заказа: допустима ли повторная публикация события?
  - допущение: спека описывает код: повторная отмена публикует событие снова
- Q-060 [уточняет] Отмена пользователем разрешена в любой момент до оплаты или только в период ожидания?
  - допущение: спека описывает код: отмена разрешена из любого статуса, кроме «Оплачен» и «Отправлен»
- … ещё 1 — `system-context/QUESTIONS.md`

## Перед правкой
1. Найди требование выше и прочитай его в спеке целиком.
2. Меняешь вход — проверь «Кто ещё вызывает»: что сломается у каждого.
3. Меняешь событие или поле — проверь подписчиков и «копии полей»: добавь поле в каждую.
4. Вопрос с пометкой [блокирует] — не опирайся на допущение молча, спроси.
5. Поведение меняй через `openspec/changes/<изменение>/`; после правки кода — строки в `trace.md`.
