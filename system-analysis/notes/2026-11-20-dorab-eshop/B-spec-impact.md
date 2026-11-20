# impact: вес товара (item-weight)

## 1. Затронутое поведение
Меняются (дельты в changes/item-weight/specs/):
- catalog-management: «Создание товара», «Изменение товара» (PUT заменяет все поля, значит вес без передачи обнуляется), «Значения товара не проверяются» (исключение для веса); новые «Вес товара», «Проверка веса».
- catalog-browsing: новое «Вес товара в ответах каталога» (список v1/v2, товар по id, `items/by`, пути type/brand, семантический поиск).
- storefront: «Страница товара и ссылка «Back to catalog»», «Содержимое корзины», «Оформление заказа из корзины».
- order-placement: «Состав заказа» (снимок веса; объединение позиций с одним productId).

Сохраняются, но на них опираемся:
- basket: корзина хранит только `ProductId` и `Quantity` (цена и название витриной добавляются из каталога при показе) — вес в корзину не кладём, витрина берёт его из каталога тем же путём, что цену (`GET /api/catalog/items/by?ids=`, Q-013).
- «Цена и событие смены цены»: вес не меняет цену, событие `ProductPriceChanged` не создаётся от смены веса.
- «Векторное описание товара»: вектор по названию и описанию, вес не входит.
- «Состав заказа»: позиция = снимок данных на момент покупки (`ProductName`, `PictureUrl`, `UnitPrice`, `Discount`, `Units`); вес по тому же принципу.
- «Доступ к изменению каталога» (Q-014): вес наследует отсутствие авторизации.

## 2. Контракты API
HTTP Catalog.API (версии 1.0 и 2.0, OpenAPI `src/Catalog.API/Catalog.API.json`, `Catalog.API_v2.json`):
- `POST /api/catalog/items` — тело: новое необязательное поле веса (имя угадано: `WeightGrams`, int, null = не задан). Отрицательное -> 400 (новое поведение, угадано). Не ломает совместимость (поле необязательное).
- `PUT /api/catalog/items` (v1, Id в теле) и `PUT /api/catalog/items/{id}` (v2) — то же поле. Совместимость: клиент без поля обнулит вес (PUT заменяет все поля) — поведенческая несовместимость для старых клиентов.
- Ответы с товаром получают поле веса: `GET /api/catalog/items` (v1, v2), `GET /api/catalog/items/{id}`, `GET /api/catalog/items/by?ids=`, `GET /api/catalog/items/by/{name}`, `GET /api/catalog/items/type/{typeId}/brand/{brandId?}`, `GET /api/catalog/items/type/all/brand/{brandId}`, `GET /api/catalog/items/withsemanticrelevance` и `.../{text}`. Добавление поля обратно совместимо для JSON-клиентов.
- `GET /api/catalog/items/facets`, `/pic`, `catalogtypes`, `catalogbrands`, `DELETE` — не меняются.

HTTP Ordering.API (версия 1.0):
- `POST /api/orders` (заголовок `x-requestid`) — в позиции запроса новое необязательное поле веса. Имя DTO и поля неизвестны. Не ломает.
- `POST /api/orders/draft` — принимает позиции корзины; вес не нужен (Q-074: никем не вызывается); при общем DTO поле просто появится.
- `GET /api/orders/{orderId}`, `GET /api/orders` — вес в ответе только если решим выдавать (не решено; по умолчанию не меняются).
- `PUT /api/orders/cancel`, `/ship`, `GET /api/orders/cardtypes` — не меняются.

gRPC Basket (`src/Basket.API/Proto/basket.proto`, копия `src/ClientApp/Services/Basket/Protos/basket.proto`): `GetBasket`, `UpdateBasket`, `DeleteBasket` — не меняются (вес не в корзине).

Webhooks.API: `GET/POST/DELETE /api/webhooks...` — не меняются.

## 3. События
Новых и изменённых интеграционных событий нет.
- `ProductPriceChanged` (Catalog.API -> Webhooks.API; `CatalogApi.cs:399-405`): состав не меняется, вес не включаем (нужно подтверждение, т.к. вебхук `CatalogItemPriceChange` отдаёт данные внешним получателям).
- `OrderStatusChangedTo*` (Ordering.API -> WebApp, catalog-api, PaymentProcessor, Webhooks.API): несут позиции заказа (id товара, количество) — вес в них не нужен; не меняются.
- `OrderStarted` (Ordering -> basket-api, очистка корзины): не меняется.
- Вебхуки `OrderPaid`/`OrderShipped` (тело — Payload JSON, контракт в Q-101): если Payload включает позиции заказа, вес туда не попадёт, потому что состав события не меняется. Проверить, что новая колонка не сломает сериализацию, если события строятся из сущности.

## 4. Потребители и сервисы
Менять:
- Catalog.API — модель, API, миграция, OpenAPI.
- Ordering.API / Ordering.Domain / Ordering.Infrastructure — DTO команды, `OrderItem`, миграция.
- WebApp (витрина, Blazor Server): страница товара, корзина, оформление (передача веса в `POST /api/orders`).
- WebAppComponents (общая библиотека: `CatalogService`, модель товара) — поле веса в клиентской модели.
Проверить:
- HybridApp (`src/HybridApp/Components/Pages/Catalog`, `Item/ItemPage.razor`) — вероятно, использует общие компоненты и клиент каталога; нужен ли показ веса — не определено.
- ClientApp (MAUI, gRPC-корзина, свои модели каталога) — десериализация нового поля безопасна, но нужен ли вес в UI — не определено.
- WebhookClient, Webhooks.API, PaymentProcessor, OrderProcessor (читает таблицу заказов напрямую из БД — проверить, что явные выборки колонок не ломаются), catalog-api -> сервис эмбеддингов — не затрагиваются.
- Внешние клиенты Catalog API (Swagger UI и любые партнёрские) — PUT без веса обнулит значение.

## 5. Данные
- Catalog DB (`catalogdb`, PostgreSQL, EF Core): таблица товаров — новая колонка веса, int NULL, без default; миграция в `src/Catalog.API/Infrastructure/Migrations/` (имя новой — неизвестно; последняя из известных `20231018163051_RemoveHiLoAndIndexCatalogName`). Существующие строки -> NULL.
- Ordering DB (`orderingdb`): таблица позиций заказа (`OrderItem`) — новая колонка веса, int NULL; миграция в Ordering.Infrastructure (путь и имя таблицы неизвестны). Старые заказы -> NULL (веса задним числом не восстановить: каталог мог измениться).
- Redis (корзина): без изменений; кэша каталога в материалах нет.
- Засев: `src/Catalog.API/Infrastructure/CatalogContextSeed.cs:29-43` и исходные данные (источник товаров — файл, формат неизвестен) — веса у тестовых товаров не заданы. Тесты e2e опираются на них (Q: нужны ли веса в сидах).
- Сервис эмбеддингов/вектор — без изменений (вектор 384 по названию и описанию).

## 6. Код
Известные пути (из trace.md, inventory.md, domain.md; номера строк — оттуда):
- `src/Catalog.API/Model/CatalogItem.cs` (:7-45) — добавить свойство веса; следить за JSON-атрибутами.
- `src/Catalog.API/Apis/CatalogApi.cs` — создание (`CreateItem`, :415-437), изменение (:373-412, `SetValues`/копирование полей, :389-390), валидация веса -> 400; ответы списков (:131, :160, :208-213, :229).
- `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs` — конфигурация колонки.
- `src/Catalog.API/Infrastructure/Migrations/` — новая миграция.
- `src/Catalog.API/Infrastructure/CatalogContextSeed.cs` — (опционально) веса сидам.
- `src/Catalog.API/Catalog.API.json`, `Catalog.API_v2.json` — OpenAPI.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs` (:9-19, проверки :25-33) — поле веса.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` (:52-91, AddOrderItem) — приём веса, объединение одинаковых позиций (общий файл четырёх возможностей — менять осторожно).
- `src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs` (:39-51) и сама команда/DTO позиции (`CreateOrderCommand`, имя вложенного класса позиции — неизвестно, путь предположительно `src/Ordering.API/Application/Commands/CreateOrderCommand.cs`) — поле веса.
- `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs` и `src/Ordering.API/Application/Queries/OrderQueries.cs` (:6-35) — если выдаём вес в заказе/черновике.
- `src/Ordering.Infrastructure/` — EntityTypeConfiguration для OrderItem (файл неизвестен) и миграция (путь неизвестен).
- `src/WebApp/Components/Pages/Item/ItemPage.razor` (:19-31 разметка страницы, :124-143) — показ веса.
- `src/WebApp/Components/Pages/Cart/CartPage.razor` (:11-29, 32-37, 78-80, 86-103, 123-124) — вес в строке.
- `src/WebApp/Services/BasketState.cs` (:33-56, :78-109, :135) — сборка позиций корзины с данными каталога и позиций заказа (вес в запрос).
- `src/WebApp/Services/OrderingService.cs` (:3-18) и DTO запроса заказа на витрине (файл неизвестен) — поле веса.
- `src/WebAppComponents/Services/CatalogService.cs` (:11-67) и модель `CatalogItem` в WebAppComponents (файл неизвестен) — поле веса.
- `src/WebAppComponents/Catalog/CatalogListItem.razor` (:5-8) — карточка в списке (по задаче вес в списке не нужен; уточнить).
- `src/HybridApp/Components/Pages/Item/ItemPage.razor`, `.../Catalog/Catalog.razor` — проверить.
- Тесты: `tests/Catalog.FunctionalTests/CatalogApiTests.cs`, `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs`, `tests/Ordering.FunctionalTests/OrderingApiTests.cs`, `e2e/BrowseItemTest.spec.ts`, `e2e/CartTest.spec.ts`, `e2e/CheckoutTest.spec.ts`.
- Контекст: `system-context/domain.md`, `glossary.md`, `trace.md`, `integrations.md`.
Неизвестные пути: DTO позиции POST /api/orders, EF-конфигурация OrderItem, миграции Ordering, модель товара в WebAppComponents, Razor-компонент строки корзины.

## 7. Тесты и проверка
Обновить/добавить:
- `CatalogApiTests`: POST/PUT с весом, без веса, вес 0, вес -1 (400), PUT без веса обнуляет, GET отдаёт вес (в т.ч. `items/by`). Существующий `AddCatalogItem` проверяет только Id — вес надо проверять явно.
- `OrderAggregateTest`: вес в позиции, объединение одинаковых позиций; `OrderingApiTests`: заказ с весом и без (старый клиент), `CreateOrderDraftSucceeds` не должен упасть.
- e2e Playwright: вес на `/item/{id}` и `/cart`; `CheckoutTest` — заказ создаётся с весом.
Поднять: PostgreSQL (catalogdb, orderingdb, миграции), Redis, RabbitMQ, Identity; всё через Aspire AppHost (`src/eShop.AppHost/AppHost.cs`). Для e2e — витрина целиком и сид каталога. Эмбеддинги: без ИИ-сервиса товар сохраняется без вектора — для тестов достаточно.
Миграционный прогон на копии БД: старые строки -> NULL.

## 8. Риски
- PUT заменяет все поля: старые клиенты (без веса в теле) молча обнулят вес. Смягчение: решить (оставлять прежнее значение, если поле не передано?) — тогда нужно различать «не передано» и null.
- Две БД, две миграции: порядок выкатки (колонки nullable — сначала БД, потом сервисы, потом витрина). Ordering.API старой версии + витрина новая: лишнее поле игнорируется; обратно — вес null.
- Снимок веса в заказе: если Ordering не получает вес с витрины, а берёт из каталога, нужен вызов Catalog (синхронной связи Ordering -> Catalog нет; только события). Выбрано: вес передаёт витрина (как цену и название) — доверие клиенту (Q-067-подобный риск: клиент может прислать любой вес).
- Данные в полёте: заказы, созданные до миграции, и в процессе обработки (OrderProcessor читает таблицу напрямую) — вес NULL.
- Гонки: вес меняется между показом корзины и «Place order» — в заказ уйдёт вес, который витрина считала при загрузке страницы оформления; допустимо.
- Корзина содержит товар, удалённый из каталога (Q-003, Q-020) — веса нет, показ веса должен терпеть null.
- Общие файлы: `Order.cs` (4 возможности), `CatalogApi.cs` (3) — конфликты при параллельной работе.
- Вебхуки/внешние получатели: если Payload включает сущности целиком, новое поле попадёт наружу (Q-101).
- OpenAPI-контракты v1 и v2 — рассинхронизация, если изменить только одну.

## 9. Чего не хватило
Всё ниже пришлось угадывать; влияние на план — оценка.
1. Кода нет, а спека скрывает форму контрактов: нет JSON-схем тела `POST/PUT /api/catalog/items`, ответа списка, тела `POST /api/orders` (DTO позиции), ответа `GET /api/orders/{id}`. Имя поля (`WeightGrams`/`Weight`), регистр, nullable — угадал. Влияние: ВЫСОКОЕ — на контракт, миграции и тесты; в плане оставлена оговорка. Хватило бы ссылки на DTO/OpenAPI-схему в domain.md или контракты в отдельном файле.
2. Как витрина собирает позицию заказа и откуда берёт название/цену: известно лишь `BasketState.cs:78-109` и `:135` (items/by), но не какие поля берутся из каталога, а какие из корзины, и как называется DTO. Решение «вес передаёт витрина» — моё допущение. Влияние: ВЫСОКОЕ (определяет, нужна ли связь Ordering -> Catalog и меняется ли событие).
3. Модель данных Ordering: нет схемы таблицы `OrderItem`, имён EF-конфигураций и миграций, не указано, как OrderProcessor читает таблицу (явные колонки или сущности). Влияние: СРЕДНЕЕ.
4. Нет описания полей/объектов, возвращаемых клиенту: список полей товара в ответе (в domain.md — только поля сущности), атрибуты JSON, сериализуются ли они из сущности целиком или через DTO. Влияние: СРЕДНЕЕ (в плане «поле попадёт во все ответы» — допущение).
5. Состав событий: integrations.md перечисляет «что несёт» словами («позиции заказа (id товара, количество)»), без схем; для `OrderStatusChangedTo*` и тел вебхуков (Q-101) неизвестно, строятся ли они из сущностей. Вывод «события не меняются» держится на этом. Влияние: СРЕДНЕЕ.
6. Продуктовые решения, которых нет ни в задаче, ни в QUESTIONS.md: нужен ли вес в списке карточек на главной (`CatalogListItem`), вес позиции или единицы в корзине, формат показа («450 g»), округление/кг, нужно ли отдавать вес в `GET /api/orders`, обязательность веса, допустимый диапазон и верхний предел, поведение PUT без веса, вес при слиянии позиций. Влияние: СРЕДНЕЕ, закрыто допущениями в дельтах (помечены «нужно подтверждение»).
7. Клиенты: HybridApp и ClientApp (MAUI) указаны только в inventory (страницы и gRPC), нет описания, что они используют из каталога и заказов, и входят ли они в объём. Нет возможности/спеки для HybridApp. Влияние: СРЕДНЕЕ — может остаться недоработанным.
8. Сиды и тестовые данные: формат исходных данных каталога (`CatalogContextSeed`, источник JSON/файл) и зависимость e2e от них не описаны. Влияние: НИЗКОЕ-СРЕДНЕЕ.
9. Правила проверки: QUESTIONS.md говорит, что проверок значений нет (Q-021); не ясно, включена ли в приложении проверка моделей (атрибуты) — вводить ли проверку веса и каким кодом ответа (400) — выбрано мной; ProblemDetails/формат ошибки неизвестен. Влияние: НИЗКОЕ.
10. Версии API: нет таблицы «эндпоинт × версия» (какие маршруты существуют в v1, какие в v2 и общая ли логика), поэтому «менять оба» — осторожное допущение. Влияние: НИЗКОЕ-СРЕДНЕЕ.
11. Порядок выкатки и миграций (Aspire, автомиграция при старте или отдельный шаг, какие сервисы применяют миграции) в материалах не описан. Влияние: СРЕДНЕЕ для раздела рисков.
12. trace.md даёт строки кода, но не указывает, где объединяются позиции заказа с одним productId для DTO (Order.cs:52-91 — предположение) и где хранится «снимок»; детали копирования полей в `OrderItem` угаданы. Влияние: НИЗКОЕ.
