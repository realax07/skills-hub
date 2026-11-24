# Анализ влияния: вес товара в граммах

Задача: «У товара каталога появляется вес в граммах. Его задают при создании и правке товара, он показывается на витрине в карточке товара и в корзине и сохраняется в позиции заказа.»

Репозиторий: `/private/tmp/claude-501/-Users-ekotov-AI-skills-hub/27bc2ddf-d4cd-48cd-ac1f-1124a29170a5/scratchpad/withcode/r1` (eShop). Код не менялся, ничего не запускалось и не собиралось. Опирался на `AGENTS.md`, `system-context/` (GUIDE, contracts, data, domain), `openspec/specs/` и код по путям ниже.

Примечание о формате: файл `scratchpad/dorab/impact-format.md` вне репозитория, а в задании сказано не открывать ничего вне репозитория. Поэтому структура разделов ниже выбрана по содержанию, а не по шаблону. Сверить с форматом нужно отдельно.

---

## 1. Затронутые возможности (openspec)

| Возможность | Что меняется | Файл требований |
|---|---|---|
| `catalog-management` | Создание и правка товара принимают вес; вес сохраняется | `openspec/specs/catalog-management/spec.md` (требование «значения полей товара», ~стр. 78) |
| `storefront` | Вес на странице товара и в корзине; вес в строке корзины | `openspec/specs/storefront/spec.md` (стр. 40 — страница товара; стр. 79–83 — корзина) |
| `order-placement` | Вес в позиции заказа (снимок при создании); черновик отдаёт позиции | `openspec/specs/order-placement/spec.md` (стр. ~95 — черновик) |
| `basket` | Не меняется. Спека: корзина отдаёт только `ProductId` и `Quantity`, без названия и цены (`openspec/specs/basket/spec.md`, стр. 22). Вес туда не добавлять | — |
| `catalog-browsing` | Не меняется по умолчанию (фильтры, сортировка по весу не входят в задачу) | — |
| `catalog-semantic-search` | Не меняется по умолчанию: текст для эмбеддинга `CatalogItemToString` = Name + Description | `src/Catalog.API/Services/CatalogAI.cs:75` |

Возможности, которые получат вес в контракте: 4 (`catalog-management`, `storefront`, `order-placement`, и косвенно `order-management` через `GET /api/orders/{id}`).

## 2. Затронутые сервисы

**Обязательные (меняются):**

1. **Catalog.API** — хранение веса, создание, правка, засев, миграция.
2. **Ordering.API** (+ библиотеки `Ordering.Domain`, `Ordering.Infrastructure`) — вес в `OrderItem`, снимок при создании, миграция таблицы `orderItems`, чтение в `GET /api/orders/{id}`.
3. **WebApp** — снимок веса из каталога в корзине, показ в корзине и на странице товара.
4. **WebAppComponents** (общая библиотека, не сервис) — модель `CatalogItem` (positional record), которую используют WebApp и HybridApp.

**Опциональные (решение нужно):**

5. **HybridApp** — тот же `ItemPage` с ценой (`src/HybridApp/Components/Pages/Item/ItemPage.razor:22`). Использует общий `CatalogItem`, поэтому поле появится в модели автоматически, но вывод веса там — отдельная правка.
6. **ClientApp** (MAUI) — собственные модели `CatalogItem`, `BasketItem`, `OrderItem` (`src/ClientApp/Models/...`). Общей модели с WebApp нет. Вывод веса в мобильном клиенте сейчас не ожидается — уточнить (см. раздел 9).

**Не затрагиваются (проверено):**

- **Basket.API** — gRPC-контракт `src/Basket.API/Proto/basket.proto` (`BasketItem` содержит только `product_id`, `quantity`); маппинг в `src/Basket.API/Grpc/BasketService.cs:76-86` тоже только эти поля. Модель `src/Basket.API/Model/BasketItem.cs:3-13` имеет `UnitPrice`, но в ответах он не заполняется.
- **Webhooks.API** — не использует `UnitPrice`/позиции заказа (проверено grep по `src/Webhooks.API`). Копия `ProductPriceChangedIntegrationEvent` не меняется.
- **OrderProcessor, PaymentProcessor, Identity.API** — в поиске `UnitPrice` не найдены, по позициям заказа не работают. Глубоко не разбирал.

## 3. Эндпоинты

### Catalog.API (`src/Catalog.API/Apis/CatalogApi.cs`)

| Эндпоинт | Обработчик | Что меняется |
|---|---|---|
| `POST /api/catalog/items` | `CreateItem`, стр. 415; ручное копирование полей стр. 419–430 | Добавить `Weight` в список копируемых полей (стр. ~426). Поля здесь перечисляются вручную, поэтому без правки вес молча не сохранится |
| `PUT /api/catalog/items` (v1) | `UpdateItemV1`, стр. 359 | Вес приходит в теле `CatalogItem` — ничего дописывать не надо |
| `PUT /api/catalog/items/{id}` (v2) | `UpdateItem`, стр. 373; `SetValues` стр. 390 | `SetValues` копирует всё тело. Поля, не пришедшие в теле, обнулятся. См. риск R1 |
| `GET /api/catalog/items/{id}` | `GetItemById`, стр. ~222 | Сущность сериализуется целиком — вес появится в JSON сам, правки не нужны |
| `GET /api/catalog/items/by?ids=` | `GetItemsByIds`, стр. ~208 | То же. Корзина WebApp берёт товары отсюда |
| `GET /api/catalog/items` (v1, v2), `/by/{name}`, `/withsemanticrelevance*` | `CatalogApi.cs` | Вес попадёт в ответ автоматически, фильтров по весу не добавляем |

### Ordering.API (`src/Ordering.API/Apis/OrdersApi.cs`)

| Эндпоинт | Что меняется |
|---|---|
| `POST /api/orders` (`CreateOrderAsync`, стр. 118) | Тело `CreateOrderRequest` (стр. 171) содержит `Items: List<BasketItem>` — в `BasketItem` добавить `Weight`. Далее `CreateOrderCommand` (стр. 66–70 `CreateOrderCommand.cs`) мапит в `OrderItemDTO` |
| `POST /api/orders/draft` | Тот же `BasketItem` → `CreateOrderDraftCommandHandler` → `OrderDraftDTO.OrderItems`. Вес должен вернуться в ответе черновика (спека `order-placement` стр. ~95 описывает позиции черновика) |
| `GET /api/orders/{orderId}` | `OrderQueries.cs:25-35` мапит `Orderitem` вручную (`ProductName`, `Units`, `UnitPrice`, `PictureUrl`) — добавить `Weight`. `OrderViewModel.cs:3-9` — добавить поле |
| `GET /api/orders` | `OrderSummary` (`OrderQueries.cs:40-48`) — веса нет и не нужно |
| `PUT /api/orders/cancel`, `PUT /api/orders/ship` | Не меняются |

### WebApp (`src/WebApp`)

WebApp сам ходит в Catalog и Ordering через `WebAppComponents/Services`. Внешних HTTP-входов WebApp, которые меняются, нет. Страницы — в разделе 4.

### gRPC Basket

Не менять. Вес хранить в Basket нельзя: контракт и спека `basket` запрещают название и цену, вес — того же класса данных. Вес берём из Catalog в момент показа, как цену.

## 4. Страницы интерфейса

| Страница | Файл:строка | Что меняется |
|---|---|---|
| Карточка товара (WebApp) | `src/WebApp/Components/Pages/Item/ItemPage.razor:41` (`$@item.Price`) — блок `item-buy`, стр. ~36–41 | Добавить строку веса рядом с ценой или в `dl.item-meta` (стр. ~36–38, там уже бренд). Формат решить |
| Корзина (WebApp) | `src/WebApp/Components/Pages/Cart/CartPage.razor:46` (цена за единицу), `:79` (сумма строки), `:123` (итог) | Вывести вес в строке `p.name`/`p.price` блока `catalog-item-content` (стр. 44–47). Сумма и итог веса не считают (если не решено иное) |
| Список каталога (WebApp) | `src/WebAppComponents/Catalog/CatalogListItem.razor:18` | В задаче — «карточка товара». Если имелась в виду карточка в списке, вывод сюда. Уточнить (раздел 9) |
| Чат-бот (WebApp) | `src/WebApp/Components/Chatbot/ChatState.cs:125, 141` — использует `CatalogItem` через `with`/`GetCatalogItem` | Не меняется; вес в ответе бота не нужен |
| Страница товара (HybridApp) | `src/HybridApp/Components/Pages/Item/ItemPage.razor:22` | Опционально (раздел 2) |

## 5. События

**Изменяемых событий: 0. Новых: 0.** Вес в интеграционных событиях не нужен: ни один из подписчиков не читает позиции заказа с ценой или весом. Проверено по `system-context/contracts.md` и коду.

| Событие | Файлы | Вывод |
|---|---|---|
| `ProductPriceChangedIntegrationEvent` (`ProductId`, `NewPrice`, `OldPrice`) | `src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs:6`; копия `src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEvent.cs:3`; публикация `src/Catalog.API/Apis/CatalogApi.cs:399-405` | Не менять. Событие рождается только при смене `Price`. Смена веса событие не порождает (и не должна). Вес в `CatalogItem` вне `Price`, поэтому условие `priceEntry.IsModified` не затрагивается |
| `OrderStatusChangedToAwaitingValidationIntegrationEvent` / `...ToPaidIntegrationEvent` (`OrderStockItems`: `ProductId`, `Units`) | `src/Ordering.API/Application/IntegrationEvents/Events/...` | Не менять. Catalog списывает остаток по `ProductId`/`Units`, вес не нужен |
| `OrderStartedIntegrationEvent` (`UserId`) | `src/Ordering.API/Application/IntegrationEvents/Events/OrderStartedIntegrationEvent.cs:6`, `src/Basket.API/IntegrationEvents/Events/OrderStartedIntegrationEvent.cs:6` | Не менять |
| Доменные `OrderStatusChangedToAwaitingValidationDomainEvent(Id, OrderItems)`, `OrderStatusChangedToPaidDomainEvent(Id, OrderItems)` (`src/Ordering.Domain/Events/...`) | Передают сущности `OrderItem` целиком | Вес поедет внутри сущности автоматически; подписчики его не читают |

## 6. Сущности и данные

### Catalog: `CatalogItem` (`src/Catalog.API/Model/CatalogItem.cs`)

- Добавить поле веса. Рекомендация: `int Weight` (граммы, целое) — см. раздел 9 про nullable.
- Место: рядом с `Price` (стр. 16) или после `MaxStockThreshold` (стр. 36).
- Конфигурация EF: `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs:8-23` — отдельной настройки не нужно (обычный `int`). Если нужен `CHECK >= 0` или default — здесь.
- Миграция: новая в `src/Catalog.API/Infrastructure/Migrations/` (последняя `20231026091140_Outbox.cs`). Обновить `src/Catalog.API/Infrastructure/Migrations/CatalogContextModelSnapshot.cs` (`Price` объявлен на стр. ~82). Миграции применяются при старте через `MigrateAsync` (`src/Shared/MigrateDbContextExtensions.cs:65`).
- Копии полей, которым надо добавить вес:
  - `src/WebAppComponents/Catalog/CatalogItem.cs:3-10` — positional record `CatalogItem(int Id, string Name, string Description, decimal Price, string PictureUrl, int CatalogBrandId, CatalogBrand CatalogBrand, int CatalogTypeId, CatalogItemType CatalogType)`. Добавить `int Weight` в конец списка. Это ломает все места, где конструктор вызывается позиционно (grep: в `src` позиционных `new CatalogItem(...)` для этого типа не найдено; для `Catalog.API` — другой класс с конструктором `CatalogItem(string name)`).
  - `src/ClientApp/Models/Catalog/CatalogItem.cs:9` (только если ClientApp в scope).
  - `src/HybridApp/Services/CatalogJsonContext.cs:6-14` — source-generated JSON: тип уже в списке, правка не нужна, но при появлении поля перекомпилировать.
  - `src/Catalog.API/Infrastructure/CatalogContextSeed.cs:52` (`Price = source.Price`) и `:84` (`CatalogSourceEntry.Price`) — засев веса из `catalog.json`.
- Засев: `src/Catalog.API/Setup/catalog.json` (записи ~101, поля `Id`, `Type`, `Brand`, `Name`, `Description`, `Price`). Веса там нет. Засев идёт только в пустую таблицу (`CatalogContextSeed.cs:~30`, `if (!context.CatalogItems.Any())`), поэтому у существующих товаров вес не появится — нужна миграция данных (раздел 6, риск R2).
- Embedding: `src/Catalog.API/Services/CatalogAI.cs:75` — текст `Name + Description`. Вес в эмбеддинг не входит. Если нужно, то это отдельное решение; при добавлении пересчёт всех эмбеддингов.
- Ограничение на вход: `src/Catalog.API/Model/CatalogItem.cs:11` `[Required]` на `Name` не проверяется сервером (спека `catalog-management` и Q-021). Для веса тоже нет проверки диапазона, пока не решено.

### Ordering: `OrderItem` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs:5`)

- Поля `ProductName`, `PictureUrl`, `UnitPrice`, `Discount`, `Units`, `ProductId` — добавить `Weight`.
- Конструктор `OrderItem(int productId, string productName, decimal unitPrice, decimal discount, string pictureUrl, int units = 1)` — добавить параметр `weight` (с default `0`, чтобы не ломать тесты) или сделать обязательным.
- `Order.AddOrderItem(...)` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:71`) и `new OrderItem(...)` (стр. 88) — пробросить вес. Внимание: при повторном добавлении того же `ProductId` вес берётся от первой строки (стр. 74–85), `AddUnits` вес не трогает — решить, что делать, если цена/вес у товара поменялись между добавлениями.
- EF: `src/Ordering.Infrastructure/EntityConfigurations/OrderItemEntityTypeConfiguration.cs:8-13` — колонка создаётся по свойству, отдельной конфигурации не нужно.
- Миграция: новая в `src/Ordering.Infrastructure/Migrations/` (последняя `20240106121712_UseEnumForOrderStatus.cs`). Обновить `src/Ordering.Infrastructure/Migrations/OrderingContextModelSnapshot.cs` (колонка `UnitPrice` объявлена стр. 219–221 — рядом добавить `Weight`).
- Копии полей, которым нужен вес:
  - `src/Ordering.API/Application/Models/BasketItem.cs:3-11` — входная модель (`init`-свойства). Добавить `public int Weight { get; init; }`.
  - `src/Ordering.API/Extensions/BasketItemExtensions.cs:13-24` — `ToOrderItemDTO` (строки `ProductId`, `ProductName`, `PictureUrl`, `UnitPrice`, `Units`). Добавить `Weight = item.Weight`.
  - `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:46-57` — `OrderItemDTO` (`ProductId`, `ProductName`, `UnitPrice`, `Discount`, `Units`, `PictureUrl`). Добавить `Weight`.
  - `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:16` (вызов `AddOrderItem`), `:36-38` (`FromOrder` → DTO черновика) — пробросить вес.
  - `src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:44` — `AddOrderItem(...)` с `item.Weight`.
  - `src/Ordering.API/Application/Commands/CreateOrderCommand.cs:66-70` — мапинг через `ToOrderItemsDTO` (менять не надо, если правки в `BasketItemExtensions` сделаны).
  - `src/Ordering.API/Application/Queries/OrderQueries.cs:25-35` — `Orderitem` мапится вручную: добавить `Weight = oi.Weight`.
  - `src/Ordering.API/Application/Queries/OrderViewModel.cs:3-9` — `Orderitem` record: добавить `int Weight`.
  - `src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs:7-17` — правила для позиций не проверяют цену; вес тоже не проверять, пока не решено (R3).
- WebApp-модель, которая уходит в Ordering: `src/WebApp/Services/BasketItem.cs:3-10` — добавить `public int Weight { get; set; }`. Иначе JSON без веса, и в заказ `Weight` = 0 без ошибки.
- WebApp: `src/WebApp/Services/BasketState.cs:133-147` (`FetchCoreAsync`) — заполнять `Weight = catalogItem.Weight` рядом с `UnitPrice = catalogItem.Price` (стр. 144). `CheckoutAsync` (стр. ~92–107) собирает `CreateOrderRequest(..., Items: [.. orderItems])` — поле уйдёт автоматически, если есть в `BasketItem`.
- Модель в `WebApp/Services/BasketItem.cs` используется и в `CartPage` (через `BasketState.GetBasketItemsAsync`) — вес будет доступен для показа.

### Заказы, созданные до релиза

- В таблице `orderItems` старые строки получат значение по умолчанию миграции. Для `int` это `0`, что для веса не то же самое, что «не задан». Выбор между `int` со значением 0 и `int?` (NULL = неизвестно) — решение (раздел 9).
- Сумма заказа `GetTotal` (`Order.cs`, `OrderQueries.cs:46`) по весу не считается — не меняется.

## 7. Тесты и спеки, которые затронет правка

**Ломаются при изменении сигнатуры** (если сделать вес обязательным без default):
- `tests/Ordering.UnitTests/Builders.cs:38` — `order.AddOrderItem(productId, productName, unitPrice, discount, pictureUrl, units)`.
- `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs:24, 42, 57, 72, 90` — `new OrderItem(...)`.

**Нужны новые тесты:**
- `tests/Catalog.FunctionalTests/CatalogApiTests.cs:397-408` (`AddCatalogItem`, `new CatalogItem("TestCatalog1") {...}`) и `:52`, `:87-117` (`UpdateCatalogItemWorksWith(out)PriceUpdate`) — добавить проверку веса в создании и правке, в том числе правку без веса в теле (R1).
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs` (стр. ~144, 171, 203) — `BasketItem` со снимком веса, проверка `GET /api/orders/{id}`.
- `tests/Basket.FunctionalTests/RedisBasketRepositoryTests.cs` — не меняется (Basket вес не хранит).

**Спеки для дельты (`openspec/changes/<изменение>/`), не правятся напрямую:**
- `openspec/specs/catalog-management/spec.md` — требование «значения полей товара» (~стр. 78): добавить вес.
- `openspec/specs/storefront/spec.md` — стр. 40 (страница товара), стр. 79–83 (корзина): добавить вес.
- `openspec/specs/order-placement/spec.md` — позиции заказа и черновик (~стр. 95).
- `openspec/specs/basket/spec.md` — не меняется (стр. 22 остаётся).

**Документация системы:** `system-context/data.md` (разделы `CatalogItem`, `OrderItem`, миграции), `system-context/contracts.md` (`http:GET/PUT/POST /api/catalog/items`, `http:POST /api/orders`, `http:POST /api/orders/draft`, `http:GET /api/orders/{orderId}`), `system-context/trace.md` (строки `catalog-management`, `storefront`, `order-placement`) — по GUIDE обновить после изменения кода.

## 8. Список файлов (путь:строка)

**Catalog.API:**
- `src/Catalog.API/Model/CatalogItem.cs:16` (добавить `Weight`)
- `src/Catalog.API/Apis/CatalogApi.cs:390` (`SetValues`, риск R1), `:419-430` (ручной `CreateItem`), `:431` (эмбеддинг)
- `src/Catalog.API/Infrastructure/CatalogContextSeed.cs:52`, `:84`
- `src/Catalog.API/Setup/catalog.json` (поле `Weight` в ~101 записях, либо решение не засевать)
- `src/Catalog.API/Infrastructure/Migrations/` — новая миграция + `CatalogContextModelSnapshot.cs`
- `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs:8-23` (только если нужны ограничения)
- `src/Catalog.API/Services/CatalogAI.cs:75` — без изменений (вес не в эмбеддинге), упомянуто для решения

**Ordering (API, Domain, Infrastructure):**
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs:5` (+ поля и конструктор)
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:71`, `:88`
- `src/Ordering.Infrastructure/Migrations/` — новая миграция + `OrderingContextModelSnapshot.cs:219-221`
- `src/Ordering.API/Application/Models/BasketItem.cs:3-11`
- `src/Ordering.API/Extensions/BasketItemExtensions.cs:13-24`
- `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:16, 36-38, 46-57`
- `src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs:44`
- `src/Ordering.API/Application/Commands/CreateOrderCommand.cs:66-70` — без изменений при правке расширения
- `src/Ordering.API/Application/Queries/OrderQueries.cs:25-35`
- `src/Ordering.API/Application/Queries/OrderViewModel.cs:3-9`
- `src/Ordering.API/Apis/OrdersApi.cs:118, 171` — без изменений (`Items` уже `BasketItem`)
- `src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs:7-17` — решение по R3

**WebApp и WebAppComponents:**
- `src/WebAppComponents/Catalog/CatalogItem.cs:3-10` (добавить `int Weight`)
- `src/WebApp/Services/BasketItem.cs:3-10` (добавить `Weight`)
- `src/WebApp/Services/BasketState.cs:133-147` (заполнение `Weight` при загрузке корзины из каталога)
- `src/WebApp/Components/Pages/Cart/CartPage.razor:44-47` (вывод веса)
- `src/WebApp/Components/Pages/Item/ItemPage.razor:36-41` (вывод веса на карточке товара)
- `src/WebAppComponents/Catalog/CatalogListItem.razor:18` — только если нужна карточка в списке (раздел 9)

**Опционально:**
- `src/HybridApp/Components/Pages/Item/ItemPage.razor:22`
- `src/ClientApp/Models/Catalog/CatalogItem.cs:9`, `src/ClientApp/Models/Basket/BasketItem.cs:13`, `src/ClientApp/Models/Orders/OrderItem.cs:12`, `src/ClientApp/ViewModels/BasketViewModel.cs:46`, `src/ClientApp/ViewModels/CheckoutViewModel.cs:151`, `src/ClientApp/Views/Templates/BasketItemTemplate.xaml:89`, `src/ClientApp/Views/Templates/OrderItemTemplate.xaml:83`

**Тесты и спеки:**
- `tests/Ordering.UnitTests/Builders.cs:38`, `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs:24, 42, 57, 72, 90`
- `tests/Catalog.FunctionalTests/CatalogApiTests.cs:52, 87-117, 397-408`
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs:144, 171, 203`
- `openspec/specs/catalog-management/spec.md:~78`, `openspec/specs/storefront/spec.md:40, 79-83`, `openspec/specs/order-placement/spec.md:~95` (через `openspec/changes/`)
- `system-context/data.md`, `system-context/contracts.md`, `system-context/trace.md` (после изменения кода)

**Не менять:** `src/Basket.API/Proto/basket.proto`, `src/Basket.API/Grpc/BasketService.cs`, `src/Basket.API/Model/BasketItem.cs`, `src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs`, `src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEvent.cs`.

## 9. Что осталось неизвестным и что я предположил

**Неизвестно (нужно решить или уточнить):**

1. **Тип и обязательность веса.** Предположил `int` в граммах, обязательное поле с default `0`. Вариант `int?` (NULL = «не задан») честнее для старых товаров и заказов; тогда в WebApp надо скрывать строку веса при `null`. Нужно решение.
2. **Старые товары и старые заказы.** Предположил, что старые товары получают вес через миграцию данных или ручную правку, а старые заказы показываются без веса (или с 0). Не знаю, допустим ли 0 как «вес неизвестен».
3. **Что считается «карточкой товара».** Предположил `ItemPage` (страница товара WebApp, `storefront` стр. 40). Если нужна карточка в списке каталога — это `CatalogListItem.razor:18`, и объём работ меняется.
4. **Нужен ли вес в корзине по сумме.** Предположил, что нет: только показ веса за единицу, без суммарного веса и без стоимости доставки.
5. **Нужен ли вес в ClientApp и HybridApp.** Предположил, что ClientApp (MAUI) вне scope, HybridApp — опционально.
6. **Нужны ли фильтры, сортировка или поиск по весу.** Предположил, что нет.
7. **Нужно ли событие смены веса.** Предположил, что нет: подписчиков, которым вес нужен, в системе не найдено (Webhooks, Basket, Catalog-stock не читают вес).
8. **Проверка значения.** Предположил, что диапазон веса не проверяем (как и цену, Q-021). Отрицательный вес сейчас не ловится нигде. Нужно решение: добавлять проверку или нет.
9. **Доверие к клиенту при снимке.** Из кода: WebApp передаёт `UnitPrice` в `POST /api/orders`, и Ordering его принимает без сверки с каталогом (`CreateOrderCommandValidator` цену не проверяет, `OrderItemDTO.UnitPrice` приходит из запроса). Предположил, что вес пойдёт по тому же пути (из WebApp, без сверки). Если вес должен быть из каталога на сервере — это отдельный вызов Catalog из Ordering, которого сейчас нет.
10. **Что делать, если вес поменяли, а заказ уже содержит старое значение.** Предположил: снимок не обновляется, как и цена.
11. **Точное поведение `order-management`** (`GET /api/orders/{id}`) при отсутствии веса в старых заказах — не проверял, как UI-клиенты разбирают `null`.
12. **Не проверял вживую:** не запускал ни сервисы, ни миграции, ни тесты; EF-модель и результат миграции выведены из кода и `Snapshot.cs`.
13. **Поле `Weight` в `CatalogItem` как имя.** Предположил `Weight` (граммы в имени не отражены). Альтернатива `WeightGrams`; выбрать до миграции, потому что имя уйдёт в JSON API.

**Предположения, на которых держится анализ:**

- Веса в `system-context` и `openspec` нет (grep по `weight`/`вес`/`грамм` ничего не нашёл), значит задача новая.
- Поля, которые сервер не получает в `PUT`, в `SetValues` обнуляются (это реальное поведение `EF SetValues`, как описано в `contracts.md` и видно в `CatalogApi.cs:390`).
- Эмбеддинг считается только по Name и Description (`CatalogAI.cs:75`).

## 10. Топ-3 риска

- **R1. Затирание веса при `PUT /api/catalog/items/{id}` и `PUT /api/catalog/items`.** `CatalogApi.cs:390` (`catalogEntry.CurrentValues.SetValues(productToUpdate)`) копирует всё тело. Клиент, который шлёт `PUT` без `Weight`, получит `0`. Тот же риск уже есть для `AvailableStock` и других полей. Митигация: в тестах `CatalogApiTests` (`UpdateCatalogItemWorksWithoutPriceUpdate`) проверить, что вес не сбрасывается, либо задокументировать, что `PUT` — полная замена. Решение нужно до реализации.

- **R2. Старые данные и засев.** `CatalogContextSeed.cs` (стр. ~30) засевает только пустую таблицу, а `catalog.json` веса не содержит. У всех существующих товаров вес останется `0`/NULL, без миграции данных и без правки `catalog.json` на витрине будут пустые карточки. Для заказов: в `orderItems` старые строки получат значение по умолчанию миграции, и если `0` не отличить от «не задан», показ будет вводить в заблуждение. Митигация: миграция данных или обновление `catalog.json` и ручной backfill; `int?` в `OrderItem` и в `CatalogItem`.

- **R3. Ручные списки полей, которые легко пропустить, и клиент как источник снимка.** Поля в `CatalogApi.cs:419-430` (`CreateItem`), `OrderQueries.cs:25-35`, `OrderViewModel.cs:3-9`, `CreateOrderDraftCommandHandler.cs:46-57`, `BasketItemExtensions.cs:13-24`, `BasketState.cs:144`, `WebApp/Services/BasketItem.cs` — каждое место, где не добавили `Weight`, молча даст 0 или пустую строку. Плюс `UnitPrice` и `Weight` в заказе принимаются от клиента без сверки с каталогом (`CreateOrderCommandValidator.cs:7-17`), то есть вес в заказе подменяем через API. Митигация: чек-лист по списку из раздела 8 и тест на `GET /api/orders/{id}`, проверка на сервере или явное решение «как цена».
