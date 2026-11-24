# Анализ влияния: вес товара в граммах (репозиторий r2)

Корень репозитория: `/private/tmp/claude-501/-Users-ekotov-AI-skills-hub/27bc2ddf-d4cd-48cd-ac1f-1124a29170a5/scratchpad/withcode/r2`
Сокращение `R2/` ниже = этот корень. AGENTS.md в корне репозитория нет (проверено).

Сейчас в коде нигде нет понятия веса товара (поиск по `weight` в src, tests, e2e — пусто).

Предполагаемая модель: `Weight` — целое число граммов, неотрицательное, одно значение на товар (атрибут товара, а не корзины).

## 1. Затронутое поведение

- Товар каталога получает поле веса. Задаётся при создании (`POST /api/catalog/items`) и правке (`PUT`, v1 и v2).
- Витрина: вес показывается в карточке товара (`ItemPage`) и, по решению, в списке товаров (`CatalogListItem`).
- Корзина: вес берётся из каталога при каждом показе (как сейчас цена), в `CartPage` выводится по позиции.
- Заказ: вес копируется из товара в позицию заказа в момент оформления (как сейчас `UnitPrice`). Вес в корзине и в Redis не хранится.
- Сохраняется без изменений: цена и название в корзине подтягиваются из каталога; стоки/события заказа работают по `ProductId`+`Units`; `CatalogAI` строит embedding по `Name + Description`, вес туда не входит.
- Опирается на существующее: `CatalogApi.UpdateItem` сохраняет через `SetValues` (строка 390) и уже ведёт себя по PUT-семантике (отсутствующее поле становится 0; так же сейчас ведёт себя `AvailableStock`).

## 2. Контракты API

### Catalog.API (`R2/src/Catalog.API/Apis/CatalogApi.cs`)
- `GET /api/catalog/items` (v1 `GetAllItemsV1`, строка 22; v2 `GetAllItems`, строка 27) — ответ `PaginatedItems<CatalogItem>`, поле `weight` добавится. Аддитивно.
- `GET /api/catalog/items/{id}` (строка 37) — ответ `CatalogItem`, поле `weight` добавится. Аддитивно.
- `GET /api/catalog/items/by?ids=` (строка 32, метод `GetItemsByIds` строка 208) — используется корзиной WebApp; поле добавится. Аддитивно.
- `POST /api/catalog/items` (строка 110, `CreateItem` строка 415) — запрос `CatalogItem`. Поле `Weight` в теле принимается, но метод `CreateItem` копирует поля вручную (строки 419–429), поэтому без правки `weight` молча теряется. **Ломает контракт по смыслу**, если не добавить маппинг.
- `PUT /api/catalog/items` v1 (строка 100, `UpdateItemV1` строка 359) и `PUT /api/catalog/items/{id}` v2 (строка 105, `UpdateItem` строка 373) — тело `CatalogItem`, `SetValues(productToUpdate)` (строка 390). Если клиент не передаст `weight`, значение станет 0. Это PUT-семантика, как сейчас у остальных полей. Решение нужно принять явно (см. раздел 9).
- Ответы: `Created` (201) и `BadRequest`/`NotFound` — без изменений.
- Валидация веса (неотрицательный, верхняя граница): в `CatalogItem` сейчас только `[Required]` на `Name` (`R2/src/Catalog.API/Model/CatalogItem.cs`). Нужна `[Range(0, ...)]` или проверка в `CreateItem`/`UpdateItem`. Новых кодов ответа не требуется, но без проверки отрицательные значения пройдут.
- OpenAPI-снимки `R2/src/Catalog.API/Catalog.API.json` (схема `CatalogItem`, строка ~1069) и `R2/src/Catalog.API/Catalog.API_v2.json` содержат схему товара. Ссылок на них из сборки/CI не найдено (`.spectral.yml` только задаёт правила линта). Обновлять вручную или генерировать — не выяснено (см. раздел 9).

### Ordering.API (`R2/src/Ordering.API/Apis/OrdersApi.cs`)
- `POST /api/orders` (`CreateOrderAsync`, маршрут строка 17, метод строка 120) — тело `CreateOrderRequest` (строка 171), поле `Items: List<BasketItem>` (строка 185). Нужно добавить `Weight` в модель позиции (см. §5/§6). Для старых клиентов поле должно быть необязательным (по умолчанию 0 или null). Иначе текущие клиенты (WebApp до обновления, MAUI ClientApp) получат 400/0 без явного сообщения. Коды ответа — без изменений.
- `POST /api/orders/draft` (`CreateOrderDraftAsync`, маршрут `R2/src/Ordering.API/Apis/OrdersApi.cs` строка 16) — тело `CreateOrderDraftCommand(BuyerId, Items)`. Вызовов внутри репозитория нет, кроме `tests/Ordering.FunctionalTests/OrderingApiTests.cs`. Вес в ответе `OrderDraftDTO.OrderItems` — если добавлять, то здесь тоже.
- `GET /api/orders/{orderId}` — `Order`/`Orderitem` (`R2/src/Ordering.API/Application/Queries/OrderViewModel.cs`) и маппинг в `R2/src/Ordering.API/Application/Queries/OrderQueries.cs` строки 27–33. Вес в ответе не выводится. Добавлять или нет — решение (см. раздел 9). Ответ станет шире, это аддитивно.
- `GET /api/orders` (summary) — без изменений.

### WebApp (внутренний контракт с Ordering)
- `R2/src/WebApp/Services/OrderingService.cs` POST `/api/Orders/` с `CreateOrderRequest` (`R2/src/WebApp/Services/BasketState.cs`, строки 161–176) и `Items: List<BasketItem>`. Поле веса в `BasketItem` (WebApp) добавить и передать.

### Basket.API (gRPC `R2/src/Basket.API/Proto/basket.proto`)
- Без изменений (решение: вес в корзину не сохраняется). Если всё же нужно сохранять вес в корзине — понадобится новое поле в `BasketItem` (proto, номер 3+) и синхронизация копии `R2/src/ClientApp/Services/Basket/Protos/basket.proto`.

## 3. События

Меняющихся или новых событий не требуется (по решению «вес пишется в заказ при создании, не передаётся событиями»). Проверены и остаются без изменений:

- `ProductPriceChangedIntegrationEvent(ProductId, NewPrice, OldPrice)` — `R2/src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs`. Публикует `CatalogApi.UpdateItem` (строка ~399–403), когда меняется цена. Подписчик — только Webhooks (`R2/src/Webhooks.API/Extensions/Extensions.cs` строка 21, обработчик `R2/src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs` — пустой `Task.CompletedTask`). Изменение веса событие не вызывает. Если решено, что вес меняет событие — это отдельный новый тип события и новая подписка. Не предлагаю.
- `OrderStatusChangedToAwaitingValidationIntegrationEvent` и `OrderStatusChangedToPaidIntegrationEvent` — `OrderStockItem(ProductId, Units)` (`R2/src/Ordering.API/Application/IntegrationEvents/Events/OrderStatusChangedToAwaitingValidationIntegrationEvent.cs` строки 23–28). Вес в них не нужен: Catalog снимает остатки по `ProductId`/`Units`. Подписчики: Catalog (`R2/src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs`, `...ToAwaitingValidation...`), Webhooks (копии классов в `R2/src/Webhooks.API/IntegrationEvents/`), WebApp, PaymentProcessor.
- `OrderStartedIntegrationEvent(UserId)` — `R2/src/Ordering.API/...` публикует `CreateOrderCommandHandler` (строка 32 в `R2/src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs`), Basket чистит корзину (`R2/src/Basket.API/IntegrationEvents/EventHandling/OrderStartedIntegrationEventHandler.cs`). Не затрагивается.
- `OrderStockRejectedIntegrationEvent` — без изменений.

## 4. Потребители и сервисы

- **Catalog.API** — меняется: модель, миграция, сид, `CreateItem`, валидация, OpenAPI-снимки.
- **Ordering.API / Ordering.Domain / Ordering.Infrastructure** — меняется: доменная позиция, DTO, команда, миграция, модель запроса, тесты.
- **WebApp** (`R2/src/WebApp`) — меняется: сервис корзины, страница товара, корзина, отправка заказа.
- **WebAppComponents** (`R2/src/WebAppComponents`, общая библиотека для WebApp и HybridApp) — меняется: модель `CatalogItem` (positional record) и, при решении, карточка списка `CatalogListItem.razor`.
- **HybridApp** (`R2/src/HybridApp`) — проверить: использует `WebAppComponents.Catalog.CatalogItem` через `CatalogJsonContext` (source-generated JSON, `R2/src/HybridApp/Services/CatalogJsonContext.cs`). Новое поле попадёт в десериализацию автоматически, но source-gen нужно пересобрать. Вывода веса в UI HybridApp нет.
- **ClientApp** (MAUI, `R2/src/ClientApp`) — проверить, не менять (если веса нет в scope): собственные модели `R2/src/ClientApp/Models/Catalog/CatalogItem.cs` и `R2/src/ClientApp/Models/Orders/OrderItem.cs`; заказ отправляется в `api/orders` через `R2/src/ClientApp/Services/Order/OrderService.cs` строка 36 (версия API 1.0) с собственной моделью. Поле веса там отсутствует: без `Weight` в DTO заказ создастся с весом 0 (если поле необязательное). Это надо явно принять.
- **Basket.API** (`R2/src/Basket.API`) — без изменений (см. §2).
- **Webhooks.API / WebhookClient** — без изменений (вес в вебхуки не отдаётся; `WebhookType` в `R2/src/Webhooks.API/Model/WebhookType.cs` не меняется).
- **OrderProcessor, PaymentProcessor** — без изменений (работают по событиям с `OrderStockItem`/ID).
- **Внешние системы/фоновые процессы**: `R2/src/Catalog.API/Services/CatalogAI.cs` (embedding) — без изменений; `R2/src/WebApp/Components/Chatbot/MessageProcessor.cs` — цены и описания не выводит, без изменений.
- **Админ-интерфейса для товаров в репозитории не найдено** (проверено: нет вызовов `CreateItem`/`PutAsync` на каталог в WebApp/HybridApp). Создание и правка — только через API (см. §9).
- **E2E** (`R2/e2e/BrowseItemTest.spec.ts`, `CartTest.spec.ts`, `CheckoutTest.spec.ts`) — текстов цены не проверяют, вес не ломает их; новых проверок — по решению.

## 5. Данные

### Catalog (таблица `Catalog`, EF-сущность `CatalogItem`)
- Новое свойство `int Weight` (или `int?`) в `R2/src/Catalog.API/Model/CatalogItem.cs` рядом с `Price` (строка 16).
- Конфигурация: `R2/src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs` — явного свойства нет, достаточно конвенции; при необходимости `HasDefaultValue`/check constraint.
- Миграция: новая в `R2/src/Catalog.API/Infrastructure/Migrations/` (после `20231026091140_Outbox`) + обновление `R2/src/Catalog.API/Infrastructure/Migrations/CatalogContextModelSnapshot.cs` (колонка рядом с `Price`, строка ~82).
- Существующие строки: без значения по умолчанию колонка получит 0 (если `int`) или NULL (если `int?`). Выбор влияет на смысл «вес не задан».
- **Сид**: `R2/src/Catalog.API/Infrastructure/CatalogContextSeed.cs` (строки ~38–56 создают `CatalogItem`, класс `CatalogSourceEntry` строки ~75–85). Сид запускается только если таблица пуста (`if (!context.CatalogItems.Any())`). На уже развёрнутой БД новые значения веса не появятся: нужен отдельный data-миграционный шаг/UPDATE. Исходные данные `R2/src/Catalog.API/Setup/catalog.json` (101 запись) веса не содержат: добавлять поле в JSON или задавать 0 по умолчанию — решение (см. §9).
- Кэш: `CatalogItem` в Catalog отдельного кэша не имеет (не найдено). Кэш в браузере/клиентах — не проверялся.

### Ordering (таблица `ordering.orderItems`)
- Новое свойство в доменной сущности `R2/src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs`: `Weight` с `private set`, по аналогии с `UnitPrice`/`Discount`.
- Конфигурация: `R2/src/Ordering.Infrastructure/EntityConfigurations/OrderItemEntityTypeConfiguration.cs` — явного свойства нет. В снимке (`R2/src/Ordering.Infrastructure/Migrations/OrderingContextModelSnapshot.cs`, строки ~198–226) свойства идут с backing-полями (`_discount`, `_unitPrice` с `HasColumnName`). Нужно проверить, какую колонку EF создаст для нового поля, на сгенерированной миграции.
- Миграция: новая в `R2/src/Ordering.Infrastructure/Migrations/` + обновление снимка. Существующие строки `orderItems` получат значение по умолчанию (0 или NULL). Историческим заказам вес не проставляется, их нельзя восстановить из каталога на текущий момент (см. §8).
- Сохранение: вес берётся из DTO (`OrderItemDTO`) и передаётся через `Order.AddOrderItem` (`R2/src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` строка 71) в конструктор `OrderItem` (строка 23).
- Слияние дублей: `Order.AddOrderItem` (строки 71–95) объединяет позиции с одним `ProductId`, увеличивая `Units`. Вес одного товара в одном запросе одинаков, отдельной логики не нужно, но тест на это желателен.

### Корзина (Redis, `R2/src/Basket.API/Repositories/RedisBasketRepository.cs`)
- Не меняется. Модель `R2/src/Basket.API/Model/BasketItem.cs` хранит только `ProductId`, `Quantity` в gRPC-ответе; `ProductName`/`UnitPrice` и т.п. в gRPC не отдаются (`R2/src/Basket.API/Grpc/BasketService.cs` строки 80–90, 102–111). Вес в Redis не пишется, значит миграции Redis не нужны.

## 6. Код

Catalog.API:
- `R2/src/Catalog.API/Model/CatalogItem.cs` — свойство `Weight` (после строки 16 `Price`) и `[Range]`/проверка неотрицательности.
- `R2/src/Catalog.API/Apis/CatalogApi.cs` — `CreateItem` (строки 419–429): добавить `Weight = product.Weight` в инициализатор. `UpdateItem` (строки 373–411): решение о PUT-семантике веса (см. §9). Ничего в маршрутах менять не нужно.
- `R2/src/Catalog.API/Infrastructure/Migrations/` — новая миграция и `CatalogContextModelSnapshot.cs`.
- `R2/src/Catalog.API/Infrastructure/CatalogContextSeed.cs` — `CatalogSourceEntry` (строки ~75–85) и создание `CatalogItem` (строки ~38–56): добавить `Weight` из JSON (если решено).
- `R2/src/Catalog.API/Setup/catalog.json` — поле `Weight` в 101 записи, если решено заполнять сидом.
- `R2/src/Catalog.API/Catalog.API.json` и `R2/src/Catalog.API/Catalog.API_v2.json` — схема `CatalogItem` (строка ~1069), добавить `weight`.

Ordering.Domain:
- `R2/src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs` — свойство `Weight`, параметр конструктора (строка 23), в `protected OrderItem()` ничего не менять.
- `R2/src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` — сигнатура `AddOrderItem` (строка 71) и вызов `new OrderItem(...)` (строка 88).

Ordering.Infrastructure:
- `R2/src/Ordering.Infrastructure/Migrations/` — новая миграция и `OrderingContextModelSnapshot.cs`.
- `R2/src/Ordering.Infrastructure/EntityConfigurations/OrderItemEntityTypeConfiguration.cs` — при необходимости явная колонка/значение по умолчанию.

Ordering.API:
- `R2/src/Ordering.API/Application/Models/BasketItem.cs` — `int Weight` (init), по умолчанию 0.
- `R2/src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs` строка 44 — передать `item.Weight` в `AddOrderItem`.
- `R2/src/Ordering.API/Application/Commands/CreateOrderCommand.cs` — `OrderItemDTO` приходит через `ToOrderItemsDTO`, поле `Weight` в DTO (см. ниже).
- `R2/src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs` — `record OrderItemDTO` (строки 46–56) получает `Weight`; строка 16 и маппинг в `OrderDraftDTO.FromOrder` (строки 27–38) тоже.
- `R2/src/Ordering.API/Extensions/BasketItemExtensions.cs` строки 13–21 — `ProductId`/`ProductName`/`UnitPrice`/`Units` сейчас переносятся вручную: добавить `Weight = item.Weight`. Если пропустить, вес в заказ не попадёт, компилятор не предупредит.
- `R2/src/Ordering.API/Application/Queries/OrderViewModel.cs` и `R2/src/Ordering.API/Application/Queries/OrderQueries.cs` строки 27–33 — если вес показывается в деталях заказа (решение, см. §9).
- `R2/src/Ordering.API/Apis/OrdersApi.cs` — `CreateOrderRequest` (строка 171) и `BasketItem` из модели запроса; маршруты не меняются.
- `R2/src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs` — если вес обязательный или проверяется на неотрицательность, добавить правило на `OrderItems`. По умолчанию правил на позиции нет.

WebAppComponents:
- `R2/src/WebAppComponents/Catalog/CatalogItem.cs` — positional record `CatalogItem` (строки 3–12): добавить `int Weight` (порядок параметров важен для позиционного создания; прямых `new CatalogItem(` в WebApp/HybridApp не найдено).
- `R2/src/WebAppComponents/Catalog/CatalogListItem.razor` — вывод веса в карточке списка (по решению, строки ~20–24 `<span class='price'>`).

WebApp:
- `R2/src/WebApp/Services/BasketItem.cs` — `int Weight` (строки 3–10).
- `R2/src/WebApp/Services/BasketState.cs` — `FetchCoreAsync` (строки ~139–146): `Weight = catalogItem.Weight`. Передача в `CreateOrderRequest` (строка 106 `Items: [.. orderItems]`) уже использует `BasketItem`, поэтому поле уйдёт в JSON автоматически.
- `R2/src/WebApp/Components/Pages/Item/ItemPage.razor` — блок `<dl class="item-meta">` (строки 34–37): добавить `<dt>Weight</dt><dd>…г</dd>`. Это «карточка товара».
- `R2/src/WebApp/Components/Pages/Cart/CartPage.razor` — вывод веса в `cart-item` (строки ~44–47 `<p class="price">`) и, по решению, суммарного веса (строки ~123–125 `TotalPrice`).
- `R2/src/WebApp/Components/Pages/Item/ItemPage.razor.css` и `Cart/CartPage.razor.css` — стили, если нужны.

Не менять (проверено): `R2/src/Basket.API/Proto/basket.proto`, `R2/src/Basket.API/Model/BasketItem.cs`, `R2/src/Catalog.API/Services/CatalogAI.cs`, события в `R2/src/Webhooks.API/`, `R2/src/ClientApp/` и `R2/src/HybridApp/` (только проверить, см. §4).

## 7. Тесты и проверка

Обновить (сломаются при изменении сигнатур или проверяют структуру):
- `R2/tests/Ordering.UnitTests/Builders.cs` строка 38 — `order.AddOrderItem(...)` с новой сигнатурой.
- `R2/tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs` строки 24, 42, 57, 72, 90 — `new OrderItem(...)` с новым параметром.
- `R2/tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs` строка 68 и `IdentifiedCommandHandlerTest.cs` строка 62 — `new CreateOrderCommand(...)` (списки `BasketItem`).
- `R2/tests/Ordering.FunctionalTests/OrderingApiTests.cs` строки 139–150, 166–175, 213–220 — `BasketItem` и `CreateOrderRequest`, добавить `Weight` и проверку, что он сохранён.

Добавить:
- `Ordering.UnitTests`: сохранение `Weight` в `OrderItem`/`AddOrderItem`, объединение дублей не теряет вес, вес по умолчанию (0) при старом клиенте.
- `Ordering.UnitTests` для `BasketItemExtensions.ToOrderItemDTO` (чтобы поймать пропущенный маппинг).
- `Catalog.FunctionalTests/CatalogApiTests.cs`: создание (строки ~405–432) — проверить, что `weight` вернулся; PUT v1 и v2 с весом; отрицательный вес — 400, если добавлена валидация.
- `R2/tests/Application.UnitTests/CatalogAITests.cs` (строка 16): не меняется; добавить проверку, что embedding не зависит от веса (по желанию).
- `WebApp`: в проекте тестов WebApp нет; проверка страниц — через e2e (`R2/e2e/BrowseItemTest.spec.ts`, `CartTest.spec.ts`, `CheckoutTest.spec.ts`): добавить ожидание текста веса на карточке и в корзине.

Что поднять:
- Миграции и БД: Catalog и Ordering используют PostgreSQL (`R2/src/Catalog.API/Infrastructure/...`, `R2/src/Ordering.Infrastructure/...`); функциональные тесты поднимают через AppHost/контейнеры (`R2/tests/Catalog.FunctionalTests/CatalogApiFixture.cs`, `R2/tests/Ordering.FunctionalTests/OrderingApiFixture.cs`). Нужны Docker и .NET SDK (версия по `R2/global.json`).
- E2E: Playwright (`R2/playwright.config.ts`), поднятый AppHost (Aspire).
- Basket.FunctionalTests (Redis) — без изменений.

Проверка по контракту: `R2/.spectral.yml` — линт OpenAPI, если снимки обновляются.

## 8. Риски

1. **Тихая потеря веса при создании** — `CatalogApi.CreateItem` (строки 419–429) переносит поля вручную. Без `Weight` в инициализаторе товар создастся с весом 0 без ошибки. Тест на создание обязателен.
2. **PUT затирает вес нулём** — `SetValues(productToUpdate)` (строка 390) заменит вес, если клиент не передал его. Отличие от цены: `priceEntry.IsModified` не срабатывает, поэтому и событие `ProductPriceChangedIntegrationEvent` не уходит. Нужно решить: требовать поле или сохранять старое значение при отсутствии.
3. **Существующие товары без веса** — сид не перезапускается на заполненной БД (`CatalogContextSeed.cs`, `if (!context.CatalogItems.Any())`). Миграция даст 0/NULL, и на витрине будет «0 г» или пусто. Нужен явный шаг заполнения (UPDATE/скрипт/админ-правка).
4. **Исторические заказы** — существующие `orderItems` получат 0/NULL. Если вес будет использоваться для доставки или счётов, это неверные данные. Нужна отметка «неизвестно» (NULL) вместо 0.
5. **Старые клиенты** — MAUI `ClientApp` (`R2/src/ClientApp/Services/Order/OrderService.cs`) и `OrderCheckout`/`OrderItem` без `Weight`; версия WebApp, развёрнутая до обновления, тоже пошлёт заказ без веса. Поле в `Ordering.API.Application.Models.BasketItem` должно быть необязательным. Иначе — 400/сбой заказа в процессе выкатки.
6. **Позиционный record в WebAppComponents** — `CatalogItem` (`R2/src/WebAppComponents/Catalog/CatalogItem.cs`) разделяется WebApp и HybridApp через `CatalogJsonContext` (source-gen). Порядок параметров и пересборка HybridApp обязательны. Если старый Catalog не вернёт поле, WebApp получит 0.
7. **Ручной маппинг в заказе** — `BasketItemExtensions.ToOrderItemDTO` (`R2/src/Ordering.API/Extensions/BasketItemExtensions.cs` строки 13–21) переносит поля вручную. Вес, который не добавили, попадёт в заказ как 0, не давая ошибки компиляции.
8. **EF и приватные свойства** — в снимке `OrderingContextModelSnapshot.cs` колонки названы через backing-поля (`_discount`, `_unitPrice`). Новое `Weight` с `private set` может получить неожиданное имя колонки. Проверить сгенерированную миграцию до применения.
9. **Цена/вес «в полёте»** — корзина не хранит вес: он всегда берётся из каталога на момент показа и оформления. Товар, у которого вес поменяли между добавлением в корзину и оформлением, уйдёт в заказ с новым весом (то же самое сейчас с ценой). Это поведение нужно подтвердить.
10. **Копии proto** — если вес понадобится в корзине (gRPC), придётся синхронизировать `R2/src/Basket.API/Proto/basket.proto` и `R2/src/ClientApp/Services/Basket/Protos/basket.proto`. Не делается в текущем плане.
11. **Порядок и повтор событий** — новых событий нет, поэтому риск дублирования/порядка не добавляется. Идемпотентность создания заказа (`x-requestid`, `IdentifiedCommandHandler`) не меняется.
12. **Транзакции** — `CreateOrderCommandHandler` сохраняет заказ и `OrderStarted` в одной транзакции (`IntegrationEventLog`); вес в тот же `SaveEntitiesAsync`, отдельной транзакции не требуется. Для Catalog `SaveEventAndCatalogContextChangesAsync` (строка 402) тоже не меняется.

## 9. Чего не хватило

Ниже — что не было в спеке и что я предположил.

1. **Тип и единицы** — предположил `int` граммов, неотрицательный. Если нужны дробные граммы или килограммы, меняются миграции и валидация. Влияние: высокое.
2. **Обязательность и значение по умолчанию** — предположил, что поле необязательное (`int?` или 0). При создании без веса — 0 или NULL? Влияет на миграции (§5), PUT-поведение (§8 п.2) и вывод на витрине. Влияние: высокое.
3. **PUT-семантика** — предположил, что вес, не переданный в PUT, сбрасывается в 0 как остальные поля. Возможно, нужно сохранять старое значение. Влияние: среднее.
4. **Сид для существующих товаров** — предположил, что сид не трогаем, веса в `catalog.json` нет. Нужны ли значения для 101 товара и как заполнить уже существующую БД. Влияние: высокое (без этого вес пустой).
5. **«Карточка товара»** — предположил, что это `ItemPage` (`/item/{id}`). Если имелась в виду карточка в списке каталога (`CatalogListItem.razor`), план тот же, но место другое. Влияние: низкое.
6. **Список товаров** — предположил, что вес в списке каталога не показываем (только в карточке). Влияние: низкое.
7. **Корзина** — предположил, что вес показывается по позиции и не сохраняется в Redis. Нужен ли суммарный вес в итогах. Влияние: среднее.
8. **Заказ** — предположил, что вес сохраняется в `orderItems`, но в деталях заказа (`GET /api/orders/{id}`) не показывается. Нужно ли выводить его в `Orderitem` (WebApp-страница заказов сейчас не показывает позиции). Влияние: среднее.
9. **Админ-интерфейс** — в репозитории не нашёл UI для создания и правки товара, поэтому предположил, что задают через API `POST/PUT /api/catalog/items`. Если есть внешний админ-сервис, его контракт не виден. Влияние: высокое для границы работ.
10. **ClientApp и HybridApp** — предположил, что мобильные клиенты не получают вес (остаются без изменений). Если MAUI-клиенты тоже должны показывать вес, объём растёт. Влияние: среднее.
11. **OpenAPI-снимки** (`Catalog.API.json`, `Catalog.API_v2.json`) — не выяснил, генерируются ли они автоматически или правятся руками. Влияние: низкое.
12. **Валидация веса** — предположил неотрицательность без верхней границы. Нужны ли лимиты. Влияние: низкое.
13. **Embedding (`CatalogAI`)** — предположил, что вес в embedding не входит. Влияние: низкое.
14. **Версионирование API** — предположил, что вес добавляется в обе версии v1/v2 без новой версии (аддитивно). Влияние: среднее.
15. **Тестовая среда** — не запускал и не собирал (по условию). Версия .NET по `R2/global.json` и наличие Docker для функциональных тестов не проверены. Влияние: низкое.
16. **Ограничения выкатки** — не знаю, выкатываются ли сервисы по одному (Catalog раньше Ordering/WebApp). Это влияет на риски §8 п.5–6. Влияние: среднее.

## Сводка

- Затронутые сервисы: 3 основных (Catalog.API, Ordering.API с Domain и Infrastructure, WebApp с общей библиотекой WebAppComponents); 2 проверить (HybridApp, ClientApp); 3 без изменений (Basket.API, Webhooks.API, PaymentProcessor/OrderProcessor).
- События: 0 меняются, 0 новых; 6 проверено (ProductPriceChanged, OrderStatusChangedToAwaitingValidation, OrderStatusChangedToPaid, OrderStarted, OrderStockRejected, OrderStatusChangedToShipped).
- Файлы: около 30 с правкой в коде/миграциях/снимках (включая 2 OpenAPI-снимка и 2 новые миграции), 7 тестовых файлов, 3 Razor-страницы/компонента.
- Топ-3 риска:
  1. Тихая потеря веса: `CatalogApi.CreateItem` и `BasketItemExtensions.ToOrderItemDTO` переносят поля вручную (`R2/src/Catalog.API/Apis/CatalogApi.cs`:419–429, `R2/src/Ordering.API/Extensions/BasketItemExtensions.cs`:13–21).
  2. Пустой вес у существующих товаров и заказов: сид не перезапускается (`R2/src/Catalog.API/Infrastructure/CatalogContextSeed.cs`), миграция даёт 0/NULL, PUT без веса сбрасывает его (`CatalogApi.cs`:390).
  3. Выкатка и старые клиенты: WebApp и MAUI `ClientApp` шлют заказ без веса; поле в `Ordering.API.Application.Models.BasketItem` должно быть необязательным, а позиционный record `WebAppComponents.Catalog.CatalogItem` требует синхронной пересборки HybridApp.
