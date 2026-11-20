# Влияние доработки: вес товара (граммы) в каталоге, на витрине, в корзине и в позиции заказа

Все пути ниже относительно корня репозитория eShop. Источник: только код, тесты, проекты и конфиги. Вес в коде сейчас нигде не встречается (grep по Weight/weight/grams даёт ноль попаданий в src, tests, e2e).

Допущение: вес хранится как целое число граммов (`int`). Выбор «nullable или 0 по умолчанию» и правило валидации (>= 0 или > 0) в задаче не заданы; на плане это сказывается в разделах 5 и 8.

## 1. Затронутое поведение

Меняется:
- Создание товара: `POST /api/catalog/items` копирует поля из тела в новый `CatalogItem` вручную, поэтому новое поле без правки будет молча потеряно (`src/Catalog.API/Apis/CatalogApi.cs:419-430`).
- Правка товара: `PUT /api/catalog/items` (v1) и `PUT /api/catalog/items/{id}` (v2) перезаписывают все поля сущности через `SetValues(productToUpdate)` (`src/Catalog.API/Apis/CatalogApi.cs:389-390`). Клиент, который не знает про вес и шлёт старое тело, обнулит вес (поле при десериализации получит default). Это поведение нужно либо принять, либо защитить (nullable и «не менять, если не передано»).
- Карточка товара на витрине: плитка в списке (`src/WebAppComponents/Catalog/CatalogListItem.razor:16-19`) и страница товара (`src/WebApp/Components/Pages/Item/ItemPage.razor:33-41`, `:34-37` блок `item-meta`).
- Корзина: строка корзины показывает название и цену (`src/WebApp/Components/Pages/Cart/CartPage.razor:42-48`).
- Оформление заказа: строки заказа собираются из корзины витрины и отправляются в Ordering (`src/WebApp/Services/BasketState.cs:88-107`), там превращаются в `OrderItem` (`src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:42-45`).

Сохраняется и на это опирается изменение:
- Корзина в Basket.API хранит только `ProductId` и `Quantity`: proto-сообщение `BasketItem` содержит два поля (`src/Basket.API/Proto/basket.proto:20-23`), маппинг в обе стороны копирует только их (`src/Basket.API/Grpc/BasketService.cs:83-86`, `:102-105`). Название и цену витрина каждый раз подтягивает из каталога (`src/WebApp/Services/BasketState.cs:132-148`). Поэтому вес в корзине берётся из каталога «вживую», в Redis и в gRPC его класть не нужно, а значение в заказе фиксируется на момент оформления.
- Позиция заказа уже хранит снимок данных товара: название, картинку, цену (`src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs:8-19`). Вес ложится в тот же шаблон.
- Дубликат товара в одном заказе склеивается: при повторном `AddOrderItem` для того же `productId` обновляются только скидка и количество, остальные поля существующей позиции не трогаются (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:73-84`). Вес в склеенной позиции останется от первой.
- Событие изменения цены публикуется только когда изменилась цена (`src/Catalog.API/Apis/CatalogApi.cs:394-406`); правка одного веса идёт по ветке «просто сохранить» (`:407-410`). Если вес меняют вместе с ценой, событие уйдёт, но вес в нём не передаётся.
- Эмбеддинг для семантического поиска строится из `"{Name} {Description}"` (`src/Catalog.API/Services/CatalogAI.cs:75`), вес в него не входит и входить не должен.
- Событие оплаты и валидации заказа несут только `ProductId` и `Units` (`src/Ordering.API/Application/DomainEventHandlers/OrderStatusChangedToPaidDomainEventHandler.cs:29-30`, `src/Catalog.API/IntegrationEvents/Events/OrderStockItem.cs:3`), вес им не нужен.

## 2. Контракты API

Catalog.API, HTTP, версии 1.0 и 2.0 (`src/Catalog.API/Apis/CatalogApi.cs:17-19`). DTO отдельной нет: наружу отдаётся и принимается сама сущность `CatalogItem` (`src/Catalog.API/Model/CatalogItem.cs:7-45`). Значит, новое поле `weight` (JSON camelCase, целое, граммы) автоматически появляется во всех ответах и во всех телах запросов обеих версий.

Ответы (добавляется поле, обратно совместимо для читателей, которые игнорируют лишние поля):
- `GET /api/catalog/items` v1 `ListItems` (`CatalogApi.cs:22-26`, обработчик `:123-128`) и v2 `ListItems-V2` (`:27-31`, `:131-167`).
- `GET /api/catalog/items/by?ids=` `BatchGetItems` (`:32-36`, `:208-214`).
- `GET /api/catalog/items/{id}` `GetItem` (`:37-41`, `:217-237`).
- `GET /api/catalog/items/by/{name}` v1 (`:42-46`, `:240-246`).
- `GET /api/catalog/items/withsemanticrelevance/{text}` v1 и `.../withsemanticrelevance?text=` v2 (`:60-71`, `:276-338`).
- `GET /api/catalog/items/type/{typeId}/brand/{brandId?}` и `.../type/all/brand/{brandId?}` v1 (`:74-83`, `:341-357`).
- `GET /api/catalog/items/facets` вес не затрагивает (возвращает только счётчики, `:169-205`).

Запросы (меняется тело, добавляется поле):
- `POST /api/catalog/items` `CreateItem` (`:110-113`, `:415-437`): вес надо добавить в ручной маппинг; коды ответа прежние (201 Created).
- `PUT /api/catalog/items` v1 `UpdateItem` (`:100-104`, `:359-371`) и `PUT /api/catalog/items/{id}` v2 `UpdateItem-V2` (`:105-109`, `:373-412`): вес приходит в теле и копируется `SetValues`. Коды прежние: 201 Created, 400, 404.

Совместимость:
- Чтение: не ломает, если клиенты терпимы к неизвестным полям. Клиенты на `System.Text.Json` и MAUI-модели такие (см. раздел 4).
- Запись: старые клиенты, не присылающие `weight`, при PUT обнулят вес, при POST создадут товар с весом по умолчанию. Это единственное место с риском для совместимости.
- Валидации в Catalog.API нет: в `Program.cs` не подключена валидация минимальных API (`src/Catalog.API/Program.cs:1-29`, grep `AddValidation` по репозиторию пуст), а `[Required]` на `Name` (`CatalogItem.cs:11`) лишь попадает в OpenAPI. Правило «вес не отрицательный» атрибутом не заработает, его нужно проверять явно в `CreateItem`, `UpdateItem` и вернуть 400 ProblemDetails (формат уже есть: `CatalogApi.cs:224-226`, `:366-368`).
- OpenAPI: в репозитории лежат сгенерированные файлы, которые перегенерируются при сборке (`src/Catalog.API/Catalog.API.csproj:14-16` `OpenApiDocumentsDirectory`, пакет `Microsoft.Extensions.ApiDescription.Server` `:26-29`). Схема `CatalogItem` в `src/Catalog.API/Catalog.API.json:1069-1170` (поле `onReorder` на `:1166`) и в `src/Catalog.API/Catalog.API_v2.json:846-946` (`onReorder` на `:943`); обе обновятся при сборке, коммитить нужно оба.
- Файл ручных запросов `src/Catalog.API/Catalog.API.http:42-53` содержит пример PUT с полным телом без новых полей, стоит добавить `weight`.

Ordering.API, HTTP v1.0 (`src/Ordering.API/Apis/OrdersApi.cs:9`):
- `POST /api/orders` `CreateOrderAsync` (`:17`, `:118-168`): тело `CreateOrderRequest` содержит `List<BasketItem> Items` (`:171-185`); `BasketItem` здесь это модель `src/Ordering.API/Application/Models/BasketItem.cs:3-11`. Нужно добавить `Weight` (`init`) в эту модель. Ответ прежний: 200 Ok или 400 при пустом `x-requestid`.
- `POST /api/orders/draft` `CreateOrderDraftAsync` (`:16`, `:106-115`): тело `CreateOrderDraftCommand(BuyerId, IEnumerable<BasketItem> Items)` (`src/Ordering.API/Application/Commands/CreateOrderDraftCommand.cs:4`), ответ `OrderDraftDTO` с `OrderItems` (`src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:23-44`). Если в черновике нужен вес, его добавляют в `OrderItemDTO` (`:46-59`) и в `FromOrder` (`:32-40`).
- `GET /api/orders/{orderId}` (`:13`): ответ собирает `OrderQueries.GetOrderAsync` с вложенным `Orderitem` (`src/Ordering.API/Application/Queries/OrderQueries.cs:27-33`, `src/Ordering.API/Application/Queries/OrderViewModel.cs:3-9`). В задаче «сохраняется в позиции заказа» сказано только про хранение; показывать вес в ответе или нет, нужно решить. Если нет, оставить как есть; если да, поле добавляется в `Orderitem` и в проекцию. Ломает ли это клиентов: нет, поле добавочное.
- `GET /api/orders` (`:14`) возвращает `OrderSummary` без позиций (`OrderQueries.cs:37-49`), вес не затрагивает.
- Версионирование в Ordering одно, 1.0; витрина вызывает с `AddApiVersion(1.0)` (`src/WebApp/Extensions/Extensions.cs:11-13`).

Basket.API, gRPC (`src/Basket.API/Proto/basket.proto`): менять не нужно, если вес берётся из каталога (см. раздел 1). Копия proto в мобильном клиенте `src/ClientApp/Services/Basket/Protos/basket.proto:20-23` тоже без изменений. Менять proto пришлось бы только если вес решат хранить в корзине; это ломает совместимость между версиями клиента и сервера лишь частично (proto3 добавочные поля совместимы), но требует перегенерации `src/ClientApp/Services/Basket/Protos/Basket.cs` и `BasketGrpc.cs`.

Mobile BFF (YARP, `src/eShop.AppHost/Extensions.cs:98-160`): прокси без схемы, пропускает `GET` и запись каталога как есть (`:150-152` catch-all `/api/catalog/{*any}`, версии `1.0`, `1`, `2.0`). Правок не нужно, но через него мобильные клиенты получают новое поле автоматически.

## 3. События

Меняется ноль событий, добавляется ноль. Проверено по всем подписчикам:

- `ProductPriceChangedIntegrationEvent(ProductId, NewPrice, OldPrice)` (`src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs:6`). Публикует Catalog.API при изменении цены (`src/Catalog.API/Apis/CatalogApi.cs:396-406`) через outbox: сохранение и запись события в одной транзакции (`src/Catalog.API/IntegrationEvents/CatalogIntegrationEventService.cs:28-40`). Подписан Webhooks.API (`src/Webhooks.API/Extensions/Extensions.cs:21`), его обработчик пустой (`src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs:5-8`). Начинает использоваться иначе: нет. Вес в событие не входит. Нюанс: при правке веса без цены событие не публикуется, значит вебхуки о смене веса не будут уведомлены; если это нужно, потребуется новое событие (в задаче такого требования нет).
- `OrderStatusChangedToAwaitingValidationIntegrationEvent` и `OrderStatusChangedToPaidIntegrationEvent`: публикует Ordering.API (`src/Ordering.API/Application/DomainEventHandlers/OrderStatusChangedToAwaitingValidationDomainEventHandler.cs:30-31`, `OrderStatusChangedToPaidDomainEventHandler.cs:29-30`), подписаны Catalog.API (`src/Catalog.API/Extensions/Extensions.cs:32-33`) и витрина. Несут `OrderStockItem(ProductId, Units)` (`src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToAwaitingValidationIntegrationEvent.cs:23-28`), подписчик в Catalog списывает остаток (`src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs:13-18`). Вес не нужен, контракт не меняется.
- `OrderStartedIntegrationEvent(UserId)` публикуется в `CreateOrderCommandHandler` (`src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:32-33`), Basket.API по нему чистит корзину (`src/Basket.API/IntegrationEvents/EventHandling/OrderStartedIntegrationEventHandler.cs:10-15`). Не затрагивается.
- Доменные события `OrderStatusChangedToPaidDomainEvent` и `...ToAwaitingValidationDomainEvent` передают `IEnumerable<OrderItem>` (`src/Ordering.Domain/Events/OrderStatusChangedToPaidDomainEvent.cs:10`, `OrderStatusChangedToAwaitingValidationDomainEvent.cs:10`): после добавления свойства в `OrderItem` они будут нести и вес в памяти, но наружу он не уходит.

Дубль контрактов событий в Webhooks.API (`src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEvent.cs:3`, `OrderStockItem.cs`) тоже не меняется.

## 4. Потребители и сервисы

Нужно менять:
- Catalog.API: сущность, EF-конфигурация, миграция, засев, создание и правка, OpenAPI, `.http` (раздел 6).
- Ordering.API, Ordering.Domain, Ordering.Infrastructure: приём веса в запросе создания заказа и черновика, доменная позиция, миграция БД Ordering, маппинги.
- WebApp (витрина): модель позиции корзины и её заполнение, страница товара, корзина, запрос на создание заказа, чат-ассистент.
- WebAppComponents (общая библиотека): модель товара для витрины и плитка каталога. Этот проект подключён и к WebApp, и к HybridApp, поэтому правка плитки меняет оба клиента (`src/WebApp/Components/Pages/Catalog/Catalog.razor:88`, `src/HybridApp/Components/Pages/Catalog/Catalog.razor:22`).
- HybridApp (MAUI Blazor Hybrid): страница товара и JSON-контекст.

Нужно проверить, менять по решению:
- ClientApp (нативный MAUI, `src/ClientApp`): ходит в каталог версии 2.0 (`src/ClientApp/Services/Catalog/CatalogService.cs:12`), его модель `CatalogItem` (`src/ClientApp/Models/Catalog/CatalogItem.cs:3-15`) лишнее поле игнорирует, то есть вес не покажет, но и не сломается. Оформление заказа идёт `POST /api/orders` через `OrderService` (`src/ClientApp/Services/Order/OrderService.cs:28-40`) с телом из `Models/Orders/OrderItem.cs:5-30` без веса, значит заказ из мобильного приложения сохранит вес по умолчанию (0 или null). В требовании упомянуты только витрина и корзина, поэтому по умолчанию ClientApp оставляют как есть, но это надо подтвердить: заказы с мобильного получат пустой вес. Если вес нужен и там: `Models/Catalog/CatalogItem.cs`, `Models/Basket/BasketItem.cs:3-37`, `Models/Orders/OrderItem.cs`, `ViewModels/BasketViewModel.cs:43-46`, `ViewModels/CatalogItemViewModel.cs:44-47`, `ViewModels/CheckoutViewModel.cs:144-151`, XAML `Views/CatalogItemView.xaml:86`, `Views/Templates/ProductTemplate.xaml:63-64`, `Views/Templates/BasketItemTemplate.xaml:88-89`, мок-сервисы `Services/Catalog/CatalogMockService.cs:16-64`, `Services/Basket/BasketMockService.cs`, `Services/Order/OrderMockService.cs:41-60`.
- Mobile BFF YARP: без правок (раздел 2).
- Basket.API: без правок; проверить, что не ломается серилизация корзины в Redis (`src/Basket.API/Repositories/RedisBasketRepository.cs:31-36`, контекст `:51-53`), она не затрагивается.
- Webhooks.API и WebhookClient: без правок, событие цены не меняется (раздел 3). `CatalogItemPriceChange` в `src/Webhooks.API/Model/WebhookType.cs:5` остаётся.
- OrderProcessor и PaymentProcessor: позиции заказа не читают, не затрагиваются.
- Семантический поиск: `ICatalogAI` и `CatalogAI` не меняются (раздел 1). Тесты `tests/Application.UnitTests/CatalogAITests.cs:16` создают `CatalogItem("Test")` с описанием; конструктор не меняется.

## 5. Данные

Catalog.API, БД PostgreSQL `catalogdb`, таблица `Catalog`:
- Новое свойство `Weight` в `src/Catalog.API/Model/CatalogItem.cs` (рядом с `Price`, `:16`).
- Конфигурация сущности `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs:10-22`: явных правок может не быть, достаточно соглашений EF; если нужен default или ограничение, здесь.
- Новая миграция в `src/Catalog.API/Infrastructure/Migrations/` (формат имён `20231026091140_Outbox.cs`, последняя миграция), команда указана в комментарии `src/Catalog.API/Infrastructure/CatalogContext.cs:3-7`. Плюс обновление `CatalogContextModelSnapshot.cs` (блок сущности на `:55-96`, колонки добавляются между `Price` `:82` и `RestockThreshold`).
- Миграции применяются автоматически при старте (`src/Catalog.API/Extensions/Extensions.cs:24`, `AddMigration<CatalogContext, CatalogContextSeed>`), так что существующие строки получат значение по умолчанию колонки. Для `int` без nullable это 0, который неотличим от «вес не задан»; если нужно различать, делать `int?`.
- Засев: `src/Catalog.API/Infrastructure/CatalogContextSeed.cs`. Источник `src/Catalog.API/Setup/catalog.json` (101 запись, поля `Id, Type, Brand, Name, Description, Price`, например `:1-9`) не содержит веса; нужно добавить `Weight` в каждую запись JSON (или принять 0), в приватный класс `CatalogSourceEntry` (`:77-85`) и в маппинг (`:46-59`). Засев запускается только при пустой таблице (`:23`), поэтому на уже заполненной БД новые значения из json не подтянутся, и миграции придётся дополнять данными (UPDATE) либо ручной доводкой.
- Эмбеддинг: колонка `vector(384)` строится из имени и описания (`CatalogAI.cs:75`), пересчёт при добавлении веса не нужен.

Ordering, БД `orderingdb`, схема `ordering`, таблица `orderItems`:
- Новое свойство `Weight` в `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs` (`:8-19`), параметр в конструкторе (`:23`) и присваивание (`:35-41`).
- `Order.AddOrderItem(...)` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:71-91`): новый параметр.
- EF-конфигурация `src/Ordering.Infrastructure/EntityConfigurations/OrderItemEntityTypeConfiguration.cs:6-16` (отображение по соглашению, правок может не потребоваться).
- Новая миграция в `src/Ordering.Infrastructure/Migrations/` (последняя `20240106121712_UseEnumForOrderStatus.cs`) и снимок `OrderingContextModelSnapshot.cs`. Заметка: снимок описывает колонки `orderItems` через поля `_discount`, `_pictureUrl`, `_productName`, `_unitPrice`, `_units` с именами колонок `Discount`, `PictureUrl` и т.д. (`:192-231`), а в текущей сущности это свойства с private set. При генерации новой миграции проверить, что EF не пытается переименовывать или пересоздавать существующие колонки.
- Миграции применяются при старте (`src/Ordering.API/Extensions/Extensions.cs:23`). Существующие позиции заказов получат default. Старые заказы веса не имели, и этого не восстановить (в каталоге вес мог поменяться).

Basket (Redis): схема не меняется, `CustomerBasket.Items` хранит `ProductId` и `Quantity` (`src/Basket.API/Model/BasketItem.cs:3-11`, `src/Basket.API/Grpc/BasketService.cs:102-105`). Кэширование: в WebApp корзина кэшируется на время запроса в `BasketState._cachedBasket` (`src/WebApp/Services/BasketState.cs:15`, `:122`, обнуляется на `:53`, `:72`); отдельного кэша товаров нет.

## 6. Код

Catalog.API
- `src/Catalog.API/Model/CatalogItem.cs:16`: добавить свойство `Weight`.
- `src/Catalog.API/Apis/CatalogApi.cs:419-430`: добавить `Weight = product.Weight` в `CreateItem`; `:373-412` `UpdateItem` получит поле через `SetValues`, проверить явную валидацию (см. раздел 2); `:359-371` `UpdateItemV1` без правок логики.
- `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs:6-23`: при необходимости ограничения.
- `src/Catalog.API/Infrastructure/Migrations/<новая>.cs`, `<новая>.Designer.cs`, `CatalogContextModelSnapshot.cs:55-96`.
- `src/Catalog.API/Infrastructure/CatalogContextSeed.cs:46-59`, `:77-85`; `src/Catalog.API/Setup/catalog.json` (все 101 запись).
- `src/Catalog.API/Catalog.API.json:1069-1170`, `src/Catalog.API/Catalog.API_v2.json:846-946`: перегенерируются при сборке.
- `src/Catalog.API/Catalog.API.http:42-53`: пример тела.
- Без правок: `src/Catalog.API/Services/CatalogAI.cs:75`, `src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs`.

Ordering
- `src/Ordering.API/Application/Models/BasketItem.cs:3-11`: `Weight`.
- `src/Ordering.API/Extensions/BasketItemExtensions.cs:13-23`: маппинг `BasketItem` в `OrderItemDTO`.
- `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:16` (вызов `AddOrderItem`), `:32-40` (`FromOrder`), `:46-59` (`OrderItemDTO`).
- `src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:44`: вызов `AddOrderItem`.
- `src/Ordering.API/Application/Commands/CreateOrderCommand.cs:20`, `:59`: хранит `OrderItemDTO`, правок логики нет (поле приходит через DTO).
- `src/Ordering.API/Apis/OrdersApi.cs:171-185`: `CreateOrderRequest` использует `BasketItem`, отдельной правки не нужно.
- `src/Ordering.API/Application/Queries/OrderViewModel.cs:3-9`, `OrderQueries.cs:27-33`: только если вес показывается в ответе заказа.
- `src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs:16`: сюда добавить правило на вес позиций, если он обязателен (сейчас проверяется только непустой список, `:29-32`).
- `src/Ordering.API/Application/Models/CustomerBasket.cs:3-13`: модель используется в тестах, правок нет.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs:8-41`, `Order.cs:71-91`.
- `src/Ordering.Infrastructure/Migrations/<новая>.cs`, `.Designer.cs`, `OrderingContextModelSnapshot.cs:192-231`.

Витрина и общие компоненты
- `src/WebAppComponents/Catalog/CatalogItem.cs:3-12`: позиционная запись `CatalogItem`, добавить параметр `Weight`. Конструктор вызывается только десериализацией и выражением `with` (`src/WebApp/Components/Chatbot/ChatState.cs:31`), прямых `new CatalogItem(` в WebApp и WebAppComponents нет. Если поля нет в JSON (старый Catalog.API), значение будет default.
- `src/WebAppComponents/Catalog/CatalogListItem.razor:16-19`: показать вес в карточке списка (общий компонент, меняется и в HybridApp).
- `src/WebAppComponents/Catalog/CatalogListItem.razor.css:99` и `src/WebApp/Components/Pages/Item/ItemPage.razor.css:104-119`: стили (`.catalog-product-content .price`, `.item-meta dt/dd`).
- `src/WebApp/Components/Pages/Item/ItemPage.razor:34-37`: добавить строку веса в `dl.item-meta`.
- `src/WebApp/Services/BasketItem.cs:3-11`: добавить `Weight`.
- `src/WebApp/Services/BasketState.cs:139-146`: заполнить `Weight = catalogItem.Weight`; `:92-106` `CreateOrderRequest` содержит `List<BasketItem> Items`, сериализуется в тело `POST /api/orders` автоматически (`src/WebApp/Services/OrderingService.cs:13-19`).
- `src/WebApp/Components/Pages/Cart/CartPage.razor:44-47`: показать вес строки; итог по весу (если нужен) считается по образцу `TotalPrice` и `TotalQuantity` (`:123-124`).
- `src/WebApp/Components/Layout/CartMenu.razor:29`: считает только количество, правок нет.
- `src/WebApp/Components/Chatbot/ChatState.cs:128`, `:161`: `SearchCatalog` и `GetCartContents` сериализуют `CatalogResult` и `BasketItem` целиком в ответ ИИ-ассистенту, поэтому вес автоматически попадёт в контекст LLM; проверить, что это допустимо.
- `src/WebApp/Services/IBasketState.cs:9`: интерфейс принимает `CatalogItem`, правок нет.
- `src/WebApp/Components/Pages/Checkout/Checkout.razor:114`, `:122`: вес не показывает, правок нет.

HybridApp
- `src/HybridApp/Services/CatalogJsonContext.cs:6-14`: JSON-контекст генерируется компилятором для `CatalogItem`, перегенерация автоматическая, но проверить сборку (source generator).
- `src/HybridApp/Components/Pages/Item/ItemPage.razor:16-23`: показать вес в карточке товара (корзина в HybridApp отключена комментариями: `:4`, `:25-28`, `:67-80`).
- `src/HybridApp/Services/CatalogService.cs:13-38`: запросы с `api-version=2.0` через BFF, правок нет.

ClientApp (опционально, раздел 4).

## 7. Тесты и проверка

Тесты, которые надо обновить:
- `tests/Catalog.FunctionalTests/CatalogApiTests.cs`: `AddCatalogItem` (`:397-436`) создаёт `CatalogItem("TestCatalog1") {...}` и проверяет только `Id`; добавить `Weight` и проверку, что после `GET /items/{id}` вес сохранился (для обеих версий `1.0` и `2.0`). `UpdateCatalogItemWorksWithoutPriceUpdate` (`:52-81`) и `...WithPriceUpdate` (`:87-118`): добавить проверку веса после PUT (обе версии: v1 `PUT /api/catalog/items`, v2 `PUT /api/catalog/items/{id}`, `:67-68`, `:103-104`) и сценарий «PUT без веса не должен затирать вес» (если принято). `GetCatalogItemWithId` (`:143-157`) и `GetCatalogItemsbyIds` (`:124-137`): проверка веса из засева. Тест `GetCatalogItemPicDoesNotServeFilesOutsidePics` создаёт товар через `POST` (`:245-253`), правок не нужно. Счётчики `catalog.json` в тестах (4, 11, 8, 13 на `:210`, `:319`, `:348`, `:370`, `:390`) от добавления поля не зависят, но завязаны на состав записей.
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs`: `BasketItem` создаётся в `:139-147`, `:166-174`, `:211-221`; добавить `Weight` и проверку, что вес дошёл до позиции (для `POST /api/orders/draft` в ответе `OrderDraftDTO.OrderItems`, `AssertThatOrderItemsAreTheSameAsRequestPayloadItems` `:226-231`).
- `tests/Ordering.UnitTests/Builders.cs:30-40` (`AddOne` вызывает `AddOrderItem`, нужен новый параметр), `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs:17-24`, `:35-42`, `:50-57`, `:65-72`, `:83-93` (вызовы `new OrderItem(...)`: поменяется сигнатура конструктора, все вызовы надо поправить), плюс тесты `AddOrderItem` и склейки позиций, если они есть в этом файле. Новые тесты на вес: отрицательное значение и склейка двух одинаковых товаров.
- `tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs:69`, `IdentifiedCommandHandlerTest.cs:63`: передают пустой `List<BasketItem>`, сигнатура `CreateOrderCommand` не меняется; править не нужно, но проверить компиляцию.
- `tests/Basket.UnitTests/BasketServiceTests.cs:37`, `:55`, `:77` и `tests/Basket.FunctionalTests/RedisBasketRepositoryTests.cs:17-22`: Basket.API не меняется, тесты остаются; полезен тест, что gRPC-ответ по-прежнему не несёт веса.
- `tests/ClientApp.UnitTests/ViewModels/CatalogItemViewModelTests.cs:47` и `tests/ClientApp.UnitTests/Services/CatalogServiceTests.cs`: менять только если правится ClientApp.
- `tests/Application.UnitTests/CatalogAITests.cs:16`: без правок.
- E2E Playwright (`e2e/CartTest.spec.ts`, `e2e/BrowseItemTest.spec.ts`, `e2e/CheckoutTest.spec.ts`, `e2e/cart-helpers.ts:3-9`): ищут ссылки по имени товара (`getByRole('link', { name })`) и сумму `$399.98` в `.cart-summary-total` (`CartTest.spec.ts:22`). Если вес добавить внутрь `<a class="catalog-product">` или в `.cart-summary-total`, проверить, что имя ссылки и текст итога не сломаются. Добавить e2e на показ веса на странице товара и в корзине.

Что поднять для прогона:
- `Catalog.FunctionalTests` и `Ordering.FunctionalTests` поднимают контейнеры PostgreSQL (образ `ankane/pgvector`, `tests/Catalog.FunctionalTests/CatalogApiFixture.cs:21-23`) и применяют миграции при старте, то есть нужен Docker и обе новые миграции должны проходить на чистой БД.
- E2E: Aspire AppHost целиком (`src/eShop.AppHost/AppHost.cs:16-78`: Postgres, Redis, RabbitMQ, Catalog, Basket, Ordering, Identity, WebApp), `playwright.config.ts`.
- Юнит-тесты Ordering и Application запускаются без инфраструктуры.
- Проверка контрактов вручную: `GET /openapi/v1.json` и `/openapi/v2.json` у Catalog.API (`src/Catalog.API/Catalog.API.http:4-8`) и сверка с обновлёнными `Catalog.API.json`, `Catalog.API_v2.json`.

## 8. Риски

- Обнуление веса при PUT. `UpdateItem` заменяет все значения сущности значениями из тела (`CatalogApi.cs:389-390`). Любой клиент, не знающий про `weight` (скрипты, старые версии админки, ClientApp), обнулит его при любой правке товара. Смягчение: `int?` с логикой «не менять, если null», либо документирование.
- Потеря веса при создании. Ручной маппинг в `CreateItem` (`CatalogApi.cs:419-430`) и в засеве (`CatalogContextSeed.cs:48-59`) легко забыть: компилятор не подскажет, тесты это проверят только если проверяют вес.
- Порядок выкатки. Витрина и Ordering разворачиваются независимо. Если WebApp начнёт слать `weight` раньше, чем обновится Ordering.API, поле игнорируется (JSON с лишними полями). Если Ordering обновится раньше, в старых запросах вес будет default. Если WebApp обновится раньше Catalog.API, `Weight` в `CatalogItem` будет 0. Нужен порядок: миграции Catalog и Ordering, затем Catalog.API и Ordering.API, затем WebApp и HybridApp.
- Данные в полёте. Корзина не хранит вес, поэтому вес в заказе берётся из каталога на момент оформления (`BasketState.cs:89`, `:132-148`), а не на момент добавления в корзину; если вес поменялся между просмотром корзины и оформлением, в заказ попадёт новый. Это то же поведение, что у цены (`UnitPrice`), и оно согласуется с моделью, но пользователь видит на странице корзины одно значение, а сохранится другое.
- Неотличимость «нет веса» и 0 для старых товаров и старых заказов, если колонки `int NOT NULL DEFAULT 0` (раздел 5). Для витрины нужно правило отображения: скрывать вес, если он 0.
- Заказы с мобильного клиента (`ClientApp`) и любые внешние вызовы `POST /api/orders` без веса сохранят вес по умолчанию; снимок веса в заказе тогда неполон. В `CreateOrderCommandValidator` (`:16`) валидации позиций нет, так что отсутствие веса не отклонит заказ.
- Склейка позиций в заказе (`Order.cs:73-84`): вес остаётся от первой позиции; если два запроса придут с разным весом для одного товара, второй значение теряется. На практике из корзины каждая позиция приходит один раз, но API формально это допускает.
- Идемпотентность создания заказа не затрагивается: используется `x-requestid` (`OrdersApi.cs:118-123`), повтор запроса не создаёт вторую позицию, вес повторно не записывается.
- События: порядок, повтор и транзакционность событий не меняются (outbox в Catalog, `CatalogIntegrationEventService.cs:28-40`). Единственный новый нюанс: изменение только веса не порождает события, и подписчики (вебхуки) о нём не узнают.
- Миграции Ordering: снимок модели расходится с текущей сущностью (поля `_productName` и т.д. в `OrderingContextModelSnapshot.cs:192-231`), новая миграция может содержать лишние операции; проверить сгенерированный Up/Down до применения.
- Миграции применяются при старте сервисов (`Extensions.cs:24` в Catalog, `:23` в Ordering) без отдельного шага выкатки. Добавление колонки с default безопасно, но блокирующие операции на больших таблицах надо учитывать.
- Генерируемые OpenAPI-файлы (`Catalog.API.json`, `Catalog.API_v2.json`) меняются при каждой сборке; забытый коммит даст расхождение в диффе, функционально безвреден.
- Чат-ассистент: вес автоматически попадёт в ответы инструментов LLM (`ChatState.cs:128`, `:161`), это меняет контекст и может изменить ответы бота.
