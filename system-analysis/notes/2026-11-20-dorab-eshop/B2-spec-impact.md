# Impact: вес товара в граммах (item-weight)

Источник: только спеки и system-context (кода не было). Имена новых полей — `WeightGrams` (C#) / `weightGrams` (JSON camelCase): это моё предложение, в материалах имени нет.

## 1. Затронутое поведение
Меняется (дельты в `changes/item-weight/specs/`):
- catalog-management: «Создание товара», «Изменение товара», «Значения товара не проверяются»; новое «Вес товара».
- catalog-browsing: новое «Вес товара в ответах каталога» (поле появляется в каждом ответе с `CatalogItem`).
- storefront: «Страница товара…», «Содержимое корзины», «Оформление заказа из корзины»; новое «Показ веса товара».
- order-placement: «Состав заказа», «Черновик заказа».
- order-management: «Просмотр заказа по номеру».

Сохраняется, но на нём стоит изменение (не менять, только учесть):
- basket: корзина хранит только `ProductId` + `Quantity` (basket.proto: `repeated BasketItem`), название/цена/вес добавляются витриной из каталога. Вес в корзину НЕ добавляем.
- catalog-management «Изменение товара»: PUT заменяет все поля телом (`SetValues`, Q-018) — поэтому PUT без веса обнуляет вес.
- catalog-management «Создание товара»: POST создаёт только часть полей тела (CatalogApi.cs:419-430) — вес надо добавить явно.
- order-placement «Состав заказа»: снимок данных на момент покупки (как `UnitPrice`, `ProductName`); слияние позиций по `productId`.
- catalog-semantic-search: эмбеддинг строится из Name+Description — вес не влияет, пересчёт не нужен.
- order-placement «Ответ на создание заказа» (Q-068): ошибки в позиции клиент не увидит, всегда 200.

## 2. Контракты API
Все изменения аддитивные (новое необязательное поле), новых маршрутов/RPC нет; шлюз YARP (`src/eShop.AppHost/Extensions.cs:106-156`) менять не надо.

HTTP Catalog.API (оба `api-version` 1.0 и 2.0 — тип `CatalogItem` общий):
- `POST /api/catalog/items` — в теле новое `weightGrams` (int?). Ответ 201 как раньше; при `weightGrams <= 0` новый 400 (сигнатура сейчас `Task<Created>` — менять на `Results<Created, BadRequest<ProblemDetails>>`).
- `PUT /api/catalog/items` (v1) и `PUT /api/catalog/items/{id}` (v2) — то же поле в теле; 400 при `<= 0` (в сигнатуре `BadRequest<ProblemDetails>` уже есть). **Ломающее по смыслу:** старый клиент без поля обнулит вес.
- `GET /api/catalog/items` (v1, v2), `/items/by/{name}`, `/items/type/{typeId}/brand/{brandId?}`, `/items/type/all/brand/{brandId}`, `/items/{id}`, `/items/by?ids=`, `/items/withsemanticrelevance` и `/items/withsemanticrelevance/{text}` — в `CatalogItem` в ответе новое `weightGrams` (null если не задан). Без изменения кода обработчиков, если они отдают сущность целиком.
- `GET /api/catalog/items/{id}/pic`, `/facets`, `/catalogtypes`, `/catalogbrands` — без изменений.

HTTP Ordering.API (только версия 1.0, шлюз пускает 1/1.0):
- `POST /api/orders` — в `CreateOrderRequest.Items` (`List<BasketItem>`, Ordering-DTO) новое `weightGrams` (int?) в позиции. Ответ 200/400 без изменений; невалидный вес не обрабатываем (Q-068).
- `POST /api/orders/draft` — `CreateOrderDraftCommand.Items` (`IEnumerable<BasketItem>`) принимает вес; `OrderDraftDTO.OrderItems` (`OrderItemDTO`) отдаёт `weightGrams`.
- `GET /api/orders/{orderId}` — в `Order.OrderItems` (`Orderitem`: сейчас 4 поля — productname, units, unitprice, pictureurl; по data.md «нет: discount, productid») новое `weightgrams` (регистр — как у соседних полей, подтвердить).
- `GET /api/orders` (`OrderSummary`), `PUT /api/orders/cancel`, `PUT /api/orders/ship`, `GET /api/orders/cardtypes` — без изменений.

gRPC Basket (`GetBasket`/`UpdateBasket`/`DeleteBasket`) — **без изменений**, `basket.proto` (Basket.API и копия в src/ClientApp) не трогать.

## 3. События
Меняется: **0**. Проверено, что вес не нужен:
- `OrderStartedIntegrationEvent` (поле только `UserId`; 2 копии) — нет.
- `OrderStatusChangedToAwaitingValidationIntegrationEvent`, `OrderStatusChangedToPaidIntegrationEvent` — несут `OrderStockItems` (`OrderStockItem`: идентификатор товара и количество); подписчики Catalog (проверка и списание остатка), Webhooks, WebApp — вес не используют. Не менять (3 копии у Paid, 2 у AwaitingValidation).
- `OrderStatusChangedToSubmitted/StockConfirmed/Cancelled/Shipped…`, `GracePeriodConfirmed`, `OrderStockConfirmed/Rejected`, `OrderPaymentSucceeded/Failed` — вес не несут.
- `ProductPriceChangedIntegrationEvent` (Catalog -> Webhooks; ProductId, NewPrice, OldPrice; обработчик пустой) — вес не добавлять; отдельного события «вес изменён» не создаём (допущение).
- Внутренние доменные события `OrderStatusChangedToAwaitingValidationDomainEvent` и `…ToPaidDomainEvent` несут `OrderItems` (`IEnumerable<OrderItem>`) — новое поле в `OrderItem` пойдёт внутри процесса автоматически, но обработчики его не читают.
Публикация/повторы/порядок не меняются.

## 4. Потребители и сервисы
Менять:
- Catalog.API — модель, API, миграция, засев.
- WebApp (+ общая библиотека WebAppComponents): страница товара, корзина, сборка заказа.
- Ordering.API / Ordering.Domain / Ordering.Infrastructure: запрос, команда, агрегат, схема, чтение.

Проверить, но не менять:
- Basket.API — gRPC не меняется; убедиться, что WebApp не пытается писать вес в корзину.
- HybridApp (Blazor, использует тип `CatalogItem` из WebAppComponents, JSON source-generated контекст `CatalogJsonContext.cs`, camelCase) — новое поле: проверить, что десериализация не падает; показ веса вне задачи (допущение 9).
- Мобильный ClientApp (`src/ClientApp`, свой `CatalogItem`, `api-version=2.0`; свой `Order`/`OrderItem`, v1) — лишнее поле игнорируется; список позиций заказа там и так, возможно, не заполняется (имя `items` vs `OrderItems`).
- WebhookClient/Webhooks.API — нагрузка `OrderPaid` содержит только `OrderId`/`OrderStockItems`, не затрагивается.
- OrderProcessor, PaymentProcessor, Identity.API — не затрагиваются.
- Внешние вызывающие `/api/catalog` и `/api/orders`, которых нет в репозитории (скрипты администратора, партнёры): неизвестны. Любой, кто делает `PUT` товара, должен начать присылать вес, иначе он обнулится.
- Шлюз мобильного BFF (YARP в `src/eShop.AppHost/Extensions.cs`) — маршруты не меняются.

## 5. Данные
Catalog (PostgreSQL + pgvector, EF Core):
- Таблица `Catalog` — новая колонка `WeightGrams int NULL`. Миграция в `src/Catalog.API/Infrastructure/Migrations` (последние: `20231018163051_RemoveHiLoAndIndexCatalogName`, `20231026091140_Outbox`); обновить `CatalogContextModelSnapshot.cs` (сверить снимок с моделью заранее).
- Конфигурация: `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs` (таблица `Catalog`, `Name` max 50); индекс не нужен. Check-constraint `> 0` — по решению.
- Засев: `src/Catalog.API/Infrastructure/CatalogContextSeed.cs` (создание :48, `CatalogSourceEntry` :77) + `src/Catalog.API/Setup/catalog.json` (~101 запись). Засев работает на пустой базе (предположение), существующие базы останутся без весов.
- Embedding — не меняется.
Ordering (SQL Server/Postgres — тип СУБД в материалах не указан):
- Таблица `orderItems` — колонка `WeightGrams int NULL`. Миграция в `src/Ordering.Infrastructure/Migrations` (последние `20231026091055_Outbox`, `20240106121712_UseEnumForOrderStatus`); `OrderingContextModelSnapshot.cs`.
- Существующие позиции заказов получают `NULL`; бэкфилл не планируется.
Копии поля (data.md, «Копии полей»):
- `CatalogItem`: `src/WebAppComponents/Catalog/CatalogItem.cs:3` (8 из 9 общих), `src/ClientApp/Models/Catalog/CatalogItem.cs:3` (не менять).
- `OrderItem`: `OrderItemDTO` (`CreateOrderDraftCommandHandler.cs:46`), `Orderitem` (`OrderViewModel.cs:3`), `src/ClientApp/Models/Orders/OrderItem.cs:5` (не менять).
- Корзинные: `src/WebApp/Services/BasketItem.cs:5-10` (ProductName, UnitPrice… собирается из каталога).
Кэш: корзина в Redis (`/basket/{userId}`) вес не хранит — прогрев/инвалидация не нужны. Кэша каталога в материалах нет.
Данные в полёте: корзины в Redis остаются валидными; заказы в статусах до Paid не пересчитываются.

## 6. Код
Пути взяты из материалов; если указаны строки — из sa-scan; «?» — путь неизвестен.
Catalog.API:
- `src/Catalog.API/Model/CatalogItem.cs` — добавить `WeightGrams`.
- `src/Catalog.API/Apis/CatalogApi.cs` — `CreateItem` (:415-437: добавить поле в инициализатор), `UpdateItem` (:373-412) и `UpdateItemV1` (:359), проверка веса, сигнатура POST; чтения — проверить.
- `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs`.
- `src/Catalog.API/Infrastructure/Migrations/<новая>_AddWeightGrams.cs` + `CatalogContextModelSnapshot.cs`.
- `src/Catalog.API/Infrastructure/CatalogContextSeed.cs`, `src/Catalog.API/Setup/catalog.json`.
WebApp:
- `src/WebAppComponents/Catalog/CatalogItem.cs` (:3-17) — поле.
- `src/WebApp/Services/BasketItem.cs` (:5-10) — поле.
- `src/WebApp/Services/BasketState.cs` — сборка строк корзины из каталога (~:135, `items/by?ids=`) и сборка заказа (:78-109).
- `src/WebApp/Services/OrderingService.cs` (:12-18) — тело `POST` (тип запроса WebApp-стороны — файл «?», вероятно рядом, `CreateOrderRequest`-клиентская копия).
- `src/WebApp/Components/Pages/Item/ItemPage.razor` (разметка карточки; вывод веса).
- `src/WebApp/Components/Pages/Cart/CartPage.razor` (:11-29 — строки корзины).
- `src/WebAppComponents/Catalog/CatalogListItem.razor` — только если решат показывать в списке (допущение 8).
Ordering:
- `src/Ordering.API/Apis/OrdersApi.cs` (:118 CreateOrderAsync, `CreateOrderRequest` :171) и тип `BasketItem` Ordering («?» — файл не указан).
- `src/Ordering.API/Application/Commands/CreateOrderCommand.cs`, `CreateOrderCommandHandler.cs` (:39-51), `CreateOrderDraftCommand.cs`, `CreateOrderDraftCommandHandler.cs` (`OrderItemDTO` :46).
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` (`AddOrderItem` :52-91, :88), `OrderItem.cs` (:9-19, :23-42).
- `src/Ordering.Infrastructure/EntityConfigurations/OrderItemEntityTypeConfiguration.cs`, `src/Ordering.Infrastructure/Migrations/<новая>` + `OrderingContextModelSnapshot.cs`.
- `src/Ordering.API/Application/Queries/OrderViewModel.cs` (:3 `Orderitem`), `OrderQueries.cs` (:6-35).
Не менять: `src/Basket.API/**`, `src/Catalog.API/Services/CatalogAI.cs`, `ProductPriceChangedIntegrationEvent*`, `src/EventBusRabbitMQ/**`, `src/Webhooks.API/**`, `src/ClientApp/**`, `src/HybridApp/**`.
Параллельная работа: `CatalogApi.cs` общий для catalog-browsing/management/semantic-search; `Order.cs`, `OrdersApi.cs`, `OrderQueries.cs` общие для order-placement/lifecycle/management — один исполнитель на Ordering.

## 7. Тесты и проверка
Обновить/добавить:
- `tests/Catalog.FunctionalTests/CatalogApiTests.cs` — `AddCatalogItem` (сейчас проверяет только Id — добавить вес), `UpdateCatalogItemWorksWithoutPriceUpdate`/`WithPriceUpdate` (вес меняется, события цены не лишние), новый: PUT без веса, вес 0/-1 -> 400 (v1 и v2 — тесты параметризованы по версии, `PutAsJsonAsync` на 1.0/2.0).
- `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs` — вес в `OrderItem`, слияние одинаковых позиций.
- `tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs`, `IdentifiedCommandHandlerTest.cs` — если конструируют `OrderItem`/команду (билдеры тестов в материалах не названы).
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs` — `AddNewOrder` (:128; проверяет только 200 — добавить чтение `GET api/orders/{id}`, но тест `GetStoredOrdersWithOrderId` зависит от содержимого БД), `CreateOrderDraftSucceeds`.
- `e2e/BrowseItemTest.spec.ts` (вес на `/item/{id}`), `e2e/CartTest.spec.ts` (вес в корзине), `e2e/CheckoutTest.spec.ts` (заказ создаётся; вес в БД проверить нельзя из e2e).
- `tests/ClientApp.UnitTests`, `tests/Basket.*` — прогнать как регрессию, менять не должны.
Нужно поднять: Aspire AppHost (Postgres с pgvector, Redis, RabbitMQ — `Catalog.FunctionalTests`/`Ordering.FunctionalTests` на .NET Aspire), для e2e — Playwright (`playwright.config.ts`), логин-сетап `e2e/login.setup.ts`. Тестовый заказ создаётся с тестовой картой. Ручная проверка: POST товара с весом -> /item/{id} -> корзина -> Place order -> GET /api/orders/{id}.

## 8. Риски
- **PUT обнуляет вес.** `SetValues` копирует тело поверх сущности: старый клиент / скрипт, не знающий о поле, затрёт вес (аналогично остаткам, Q-018). Параллельный PUT и списание остатка уже сейчас затирают друг друга — вес попадает в ту же гонку «последняя запись побеждает».
- **POST теряет поле молча**, если не добавить в явный инициализатор (CatalogApi.cs:419-430): тесты `AddCatalogItem` этого не поймают, пока проверяют только Id.
- **Вес приходит от клиента в Ordering** (как цена): подделка/рассинхрон с каталогом; Ordering не сверяется с каталогом.
- **Ошибка в позиции заказа невидима**: Ordering на ошибки отвечает 200 и тело пустое, WebApp ответ не проверяет и очищает корзину (Q-068) — если добавить валидацию веса в Ordering, заказ пропадёт молча. Поэтому валидацию в Ordering не вводим.
- **Порядок выката.** Новая витрина + старый Ordering: лишнее поле игнорируется (если десериализация не строгая). Старая витрина + новый Ordering: вес `null`. Миграции Catalog и Ordering независимы; код читает `NULL` корректно. Миграцию Catalog выкатывать раньше WebApp.
- **Миграции**: расхождение снимка и модели в `CatalogContextModelSnapshot.cs`/`OrderingContextModelSnapshot.cs` попадёт в новую миграцию — сверить перед генерацией.
- **Старые данные**: существующие товары и позиции заказов без веса (`null`) — UI и API должны это переносить; засев не обновит существующие базы.
- **Корзина-гонка**: две вкладки затирают друг друга (BasketState), вес на неё не влияет.
- Событийный порядок и повторы не затронуты (события не меняются); `IdentifiedCommand` по `x-requestid` не затронут.
- Проверка веса в Catalog (400) — первая проверка значения в сервисе, где проверок нет вовсе (Q-021): возможная несовместимость с клиентами, шлющими 0 как «нет веса». Тогда лучше трактовать 0/отсутствие как `null`.
- Доступ: `POST/PUT/DELETE` каталога без входа (Q-014) — вес может менять кто угодно.

## 9. Чего не хватило
Влияние: В — высокое (меняет план), С — среднее, Н — низкое.
1. **Как WebApp собирает позиции заказа и какие поля у Ordering-типа `BasketItem`/`OrderItemDTO`.** В контрактах для `CreateOrderRequest` указано `Items List<BasketItem>`, но поля `BasketItem` Ordering-стороны не перечислены; `CreateOrderCommand` в перечне полей позиций не показывает вовсе. Пришлось угадывать, что вес идёт по цепочке WebApp `BasketItem` -> тело POST -> Ordering `BasketItem` -> команда -> `Order.AddOrderItem` -> `OrderItem`, и что Ordering не ходит в каталог за ценой/названием. Влияние: В (определяет, где хранится и откуда берётся снимок).
2. **Нет ни одного места в материалах, где создаётся/правится товар «человеком».** Админ-UI не описан; единственные вызовы POST/PUT в репозитории — тесты. Неизвестно, кто «задаёт вес» (ручной curl? внешняя админка?). Влияние: В — непонятно, что именно менять в UI «создание и правка», возможно, ничего кроме API.
3. **Что хотят от PUT без поля веса** (обнулять, как остальные поля, или сохранять прежний вес). Спека фиксирует «как есть» (Q-018), но для нового поля решение продукта нужно. Влияние: В (риск потери данных).
4. **Обязательность и границы веса:** nullable ли, допустим ли 0, верхний предел, единица (целые граммы или дробные). В задаче только «в граммах». Принято: `int?`, > 0, без верхней границы. Влияние: С.
5. **Что значит «в карточке товара»**: страница `/item/{id}` или карточка в списке на `/` (`CatalogListItem.razor`), или обе; что показывать в корзине — вес единицы, вес строки, общий вес. Формат («450 g», кг?) и язык подписи. Принято: страница товара + строка корзины, единица, «450 g». Влияние: С.
6. **Тип БД и точное имя/регистр JSON у Ordering и вывод `Orderitem`.** Для Ordering не указана СУБД (в миграции `orderItems` и `UseHiLo` — вероятно SQL Server/Postgres), не указан регистр сериализации ответа `GET /api/orders/{id}` (в контракте мобильного клиента упомянуто, что имена сопоставляются без учёта регистра). Влияние: Н.
7. **Исходный код отсутствует: имена файлов `ItemPage.razor` внутри разметки, `BasketItem` Ordering, `OrderingService` WebApp-типа запроса, тестовые билдеры.** Для ряда файлов указаны только строки из sa-scan без подтверждения содержания; пути Razor-стилей, `BasketItem.cs` Ordering, тестовых помощников — не названы. Влияние: С (плану нужна проверка по коду).
8. **Как работает засев и запускается ли он на непустых базах** (`CatalogContextSeed.cs` + `catalog.json`): влияет на то, получат ли существующие окружения веса. В материалах сказано лишь «засев ~101 запись». Влияние: С.
9. **Кто ещё вызывает `PUT`/`POST /api/catalog/items` вне репозитория** (внешние админки/импорт) и поддерживает ли `System.Text.Json` у клиентов лишние поля (HybridApp имеет source-generated контекст; ClientApp — свой `CatalogItem`). Влияние: С.
10. **Нужны ли вес и в событиях/вебхуках** (например, `OrderPaid` с позициями для логистики). Материалы показывают, что нагрузка — только `OrderId`/`OrderStockItems`; я решил не менять. Влияние: Н-С, зависит от цели («для чего вес»: доставка? расчёт стоимости?). Цель доработки не указана — не ясно, нужен ли суммарный вес заказа/корзины.
11. **Поведение слияния позиций при разном весе** одного `productId` в запросе (теоретически, т.к. клиент присылает вес сам). Принято: вес первой позиции. Влияние: Н.
12. **Тесты, которые строят `CatalogItem`/`OrderItem` напрямую** (в data.md: «в тестах: 4» для CatalogItem, 5 для OrderItem, 7 для Order) — список конкретных мест не дан; сборка может сломаться при смене конструктора `OrderItem`. Влияние: Н-С.
13. **Правки мобильного клиента**: в задаче названа только витрина, но `src/ClientApp` и `HybridApp` читают тот же каталог — не ясно, входят ли они в «витрину». Принято: нет. Влияние: С.
