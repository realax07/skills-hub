# Вес товара в граммах

## Why
Покупателю нужно видеть вес товара на витрине и в корзине, а заказу — сохранять вес позиций на момент оформления.
Сейчас в каталоге у товара веса нет. Задача от владельца продукта: вес задаётся при создании и правке товара (через Catalog.API),
показывается в карточке товара и в корзине и фиксируется в позиции заказа. Владельца нет на связи: решения, которые он мог бы
принять сам, приняты как допущения и перечислены в «Открытых вопросах».

## What Changes
- Товар каталога получает необязательное поле `WeightGrams` (целые граммы, пусто, если не задано). Задаётся при POST и PUT /api/catalog/items (и PUT /api/catalog/items/{id}).
- Вес ≤ 0 отклоняется ответом 400 (CQ-02). Остальные поля товара проверяются как раньше.
- Вес есть в ответах каталога: список, карточка по id, пакетный запрос по списку id.
- Страница товара и карточка товара в каталоге на главной показывают «Weight: N g», если вес задан.
- Корзина показывает вес за единицу, если он задан. Корзина вес не хранит: он берётся из каталога, как цена (CQ-07).
- Оформление заказа передаёт вес позиций; позиция заказа сохраняет `WeightGrams` (пусто для старых заказов). Вес виден в ответе
  GET /api/orders/{номер}.
- **BREAKING (мягкое):** PUT-замена товара без поля `WeightGrams` сбрасывает вес в пусто (CQ-03). Старые клиенты, которые не знают
  поля, стирают вес при каждом PUT. Новые поля в ответах старым клиентам не мешают.

## Влияние
По пунктам `impact.md` (решения там же). Здесь — строкой то, что меняется у затронутого:

- **C-01, C-02 (клиенты ClientApp, HybridApp → каталог)** — код не меняется, новое поле в ответе игнорируется; проверка в задаче 3.1.
- **C-04 (WebAppComponents → каталог)** — тип `CatalogItem` получает `WeightGrams`, карточка показывает вес (задачи 1.6, 2.2).
- **C-05 (шлюз AppHost)** — новых путей и версий нет, без изменений.
- **C-06 (ClientApp → заказы)** — новое поле игнорируется, мобильный клиент вес не показывает (CQ-10).
- **C-07 (WebApp → заказы)** — позиции оформления несут вес из корзины (задача 2.4).
- **C-08 (шлюз → заказы)** — без изменений.
- **C-09 (ClientApp → gRPC Basket)** — `basket.proto` не меняется, корзина вес не хранит.
- **C-10 (WebApp → gRPC Basket)** — вес берётся из каталога в `BasketState` (задача 2.4); proto не меняется.
- **S-01…S-04 (события)** — позиций в событиях нет, кроме внутренних `S-05`, `S-06` (несут весь заказ, вес попадает сам; задача 4.3 проверяет обработчики).
- **E-01 (создание товара `CreateItem`)** — вес копируется вручную (задача 1.3); без этого поле тихо теряется.
- **E-02, E-10, E-11, E-12 (засев каталога)** — засев вес не задаёт; существующие товары и строки остаются без веса (CQ-06); миграция
  колонки nullable, данные не переносятся.
- **E-03…E-08, E-16…E-18, E-21 (клиентское приложение: моки, модели, оформление)** — не меняются (CQ-10).
- **E-09 (копия `CatalogItem` в WebAppComponents)** — получает поле (задача 1.6).
- **E-13, E-14 (ИИ, эмбеддинг)** — вес в текст эмбеддинга не входит (имя и описание), проверка в задаче 4.2.
- **E-15 (миграция Catalog)** — колонка `WeightGrams` NULL (задача 1.2).
- **E-19 (`OrderItem`, `Order.AddOrderItem`)** — принимают и хранят вес (задачи 1.7, 1.8).
- **E-20 (`OrderItemDTO`)** — переносит вес (задача 1.11).
- **E-22 (`OrderViewModel.Orderitem`)** — отдаёт вес (задача 1.13).
- **E-23 (миграция `orderItems`)** — колонка `WeightGrams` NULL (задача 1.9).
- **Возможности-дельты:** catalog-management (ADDED «Вес товара», MODIFIED «Значения товара не проверяются»); catalog-browsing (ADDED «Вес товара в ответах каталога»);
  storefront (ADDED «Вес в карточке товара каталога», MODIFIED «Страница товара…», «Содержимое корзины», «Оформление заказа из корзины»);
  order-placement (MODIFIED «Состав заказа»); order-management (MODIFIED «Просмотр заказа по номеру»). basket — без дельты: корзина вес не хранит.
- **Тесты (пункты T):** тесты каталога, заказов, e2e витрины — задачи 4.1, 4.3, 4.4, 4.6; тест-кейсов qa-scan в репозитории нет.
- **Интерфейс (D):** `design-context/` нет — проверка wd-fit не применяется.
- **X-01:** в репозитории нет админки товаров: вес задаётся только через API Catalog.API (CQ-11).

## Открытые вопросы
Блокирующие вопросы слоя (из `impact.md`) — ответ нужен до разработки, но ниже указано, что принято до ответа:

- **Q-001** Принимает ли API любой токен Identity? Принято: доступ к записи каталога как сейчас; вес правил доступа не меняет. Ответит: владелец безопасности.
- **Q-014** Должны ли изменения каталога требовать вход и роль? Принято: как сейчас (без проверки). Вес пишется теми же вызовами. Ответит: владелец продукта.
- **Q-035** Данные карты в токенах и журналах — допустимо? Принято: изменение платёжных данных не трогает. Ответит: владелец продукта.
- **Q-055** Кто может читать заказы чужих покупателей? Принято: как сейчас. Важно: вес в заказе станет видимым тем же, кто читает заказ; риск не растёт, но виден. Ответит: владелец продукта.
- **Q-058** Повтор с тем же `x-requestid` после неудачи — повторять ли действие? Принято: как сейчас.
- **Q-064** Оплата — заглушка. Принято: как сейчас.
- **Q-067** Брать UserId покупателя из токена или из тела? Принято: как сейчас (из тела).
- **Q-068** Ответ 200 при ошибке создания заказа — так задумано? Принято: как сейчас; новых ошибок в ответе нет.

Новые вопросы этого изменения (принятые допущения помечены в дельтах):

- **CQ-01** Единица и подпись: целые граммы; подпись «Weight: N g» на английском, как остальной интерфейс витрины. Ответит: владелец продукта. Принято до ответа: так.
- **CQ-02** Обязательность: вес необязателен; допустим только целый > 0, иначе 400. Ответит: владелец продукта. Принято до ответа: так.
- **CQ-03** PUT без `WeightGrams` сбрасывает вес в пусто (как остальные поля замены), а не сохраняет. Ответит: владелец продукта. Принято до ответа: сброс. Если ответ «сохранять» — PUT не трогает вес при отсутствии поля, это меняет задачу 1.3 и дельту «Вес товара».
- **CQ-04** Где показывать вес: страница товара, карточка в каталоге на главной, корзина (за единицу). Список заказов в WebApp и мобильный клиент — нет. Ответит: владелец продукта. Принято до ответа: так.
- **CQ-05** Объединение одинаковых позиций в заказе: вес сохраняется у первой позиции. Ответит: владелец продукта (на практике веса совпадают). Принято до ответа: первая.
- **CQ-06** Существующие товары и заказы остаются без веса; засев веса не задаёт. Ответит: владелец каталога — нужно ли заполнить вес уже существующих товаров. Принято до ответа: пусто.
- **CQ-07** Вес в корзине не хранится, берётся из каталога при показе и оформлении. Изменение веса в каталоге видно в корзине сразу; в заказе фиксируется на момент оформления. Ответит: владелец продукта. Принято до ответа: так.
- **CQ-08** Событие смены цены и вебхуки вес не получают (подписчик пустой). Ответит: владелец Webhooks, если нужен вес во внешних интеграциях. Принято до ответа: не расширяем.
- **CQ-09** Итоговый вес корзины и заказа (для доставки) не считаем. Ответит: владелец продукта. Принято до ответа: не считаем.
- **CQ-10** Мобильное клиентское приложение и HybridApp вес не показывают и не передают. Ответит: владелец продукта. Принято до ответа: не меняем.
- **CQ-11** В репозитории нет админки товаров; вес задаётся через API. Ответит: владелец продукта, если нужна форма ввода. Принято до ответа: только API.

## Impact
- Возможности: catalog-management, catalog-browsing, storefront, order-placement, order-management (дельты в `specs/`); basket — без дельты.
- Код: см. «Код затронутых возможностей» в `impact.md`; главное — `src/Catalog.API/Model/CatalogItem.cs`, `src/Catalog.API/Apis/CatalogApi.cs`,
  `src/WebAppComponents/Catalog/CatalogItem.cs`, `src/WebAppComponents/Catalog/CatalogListItem.razor`, `src/WebApp/Services/BasketState.cs`,
  `src/WebApp/Services/BasketItem.cs`, `src/WebApp/Components/Pages/Item/ItemPage.razor`, `src/WebApp/Components/Pages/Cart/CartPage.razor`,
  `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs`, `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs`,
  `src/Ordering.API/Application/Models/BasketItem.cs`, `src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs`,
  `src/Ordering.API/Application/Queries/OrderViewModel.cs`, `src/Ordering.API/Application/Queries/OrderQueries.cs`, миграции Catalog.API и Ordering.Infrastructure.
- Проверка: тесты из задач раздела 4; тест-кейсов qa-scan нет; wd-fit не применяется (нет `design-context/`).
# Дизайн: Вес товара в граммах

## Контекст
- Товар каталога (`CatalogItem`, Catalog.API) хранит цену, остатки и описание; создаётся в `CatalogApi.CreateItem` (ручное копирование полей),
  меняется в `CatalogApi.UpdateItem` / `UpdateItemV1` через `SetValues` (замена всех полей). Проверки значений нет (Q-021), кроме ограничений БД.
- Витрина (WebApp) собирает корзину из `basket-api` (только `ProductId` и количество) и добирает название и цену из каталога (`BasketState`).
- Оформление (`BasketState.CreateOrder`) шлёт позиции в Ordering.API (`CreateOrderRequest.Items`); позиция заказа (`OrderItem`) хранит название,
  цену, скидку, фото и количество — снимок на момент заказа.
- Спеки «как есть» (с багами, см. QUESTIONS.md): вход PUT без версии и PUT с Id в теле — Q-015, Q-016; ответ заказа всегда 200 — Q-068.

## Решения
1. **Поле `WeightGrams`, `int?` (граммы).** Пусто = вес не задан. Целое, чтобы не тянуть десятичные единицы (CQ-01).
2. **Вес необязателен, допустим только > 0.** 0 и отрицательные — 400 при POST и PUT. Это единственное новое правило проверки;
   остальные поля остаются без проверки (требование «Значения товара не проверяются» сохраняет остальное, см. дельту) (CQ-02).
3. **PUT — замена, как у остальных полей.** Нет поля — вес пуст (CQ-03). Альтернатива «сохранять при отсутствии» отброшена: при `SetValues`
   её пришлось бы писать отдельно для одного поля, и она расходится с остальными полями замены. Если владелец выберет «сохранять», меняется задача 1.5.
4. **Корзина вес не хранит.** Вес берётся из каталога при показе и при оформлении, как цена (CQ-07). Плюс: `basket.proto` и Redis не меняются,
   старые корзины работают. Минус: изменение веса видно в корзине сразу, в заказе — на момент оформления. Это ожидаемо для снимка заказа.
5. **Вес в заказе — снимок.** `OrderItem.WeightGrams` фиксируется при создании позиции и не меняется при последующих правках каталога.
   Объединение одинаковых позиций сохраняет вес первой (CQ-05).
6. **Вес не входит в векторное описание.** Эмбеддинг строится из имени и описания (`CatalogAI.CatalogItemToString`); вес туда не добавляем,
   чтобы не менять поиск без отдельного решения.
7. **Вес не уходит в события.** Событие смены цены и события заказа вес не несут (CQ-08); внутренние события несут весь заказ, и вес в них попадает сам.
8. **Клиентское приложение и HybridApp не меняются** (CQ-10): их модели игнорируют новое поле.

## Данные и контракты

| Что | Было | Стало |
|---|---|---|
| `Catalog.Catalog` (таблица) | нет веса | колонка `WeightGrams` integer NULL (миграция 1.2) |
| `CatalogItem` (ответы GET каталога) | без веса | поле `WeightGrams` int? (null, если не задан) |
| POST /api/catalog/items | `Created` | `Created` или 400 при весе ≤ 0; `WeightGrams` сохраняется |
| PUT /api/catalog/items[/{id}] | `Created` / 404 | то же + 400 при весе ≤ 0; без поля вес сбрасывается (CQ-03) |
| `orderItems` (Ordering) | нет веса | колонка `WeightGrams` integer NULL (миграция 1.9) |
| `CreateOrderRequest.Items[]` (POST /api/orders, Ordering.API) | без веса | поле `WeightGrams` int?, необязательное |
| GET /api/orders/{номер} → `OrderItems[]` | без веса | поле `WeightGrams` int? |
| Событие `ProductPriceChangedIntegrationEvent` | без веса | без изменений (CQ-08) |
| Корзина (`basket.proto`, Redis) | ProductId, Quantity | без изменений |

**Совместимость.**
- Старые клиенты (ClientApp, HybridApp, старые копии WebApp) новое поле в ответах игнорируют; в запросах поле необязательно.
- Старые клиенты PUT без поля **сбрасывают вес** (CQ-03) — это главный риск выкатки, см. «Риски».
- Существующие товары и заказы: вес пуст (NULL). Засев не задаёт вес (CQ-06). Данные не переносятся.
- Ответ заказа при ошибке (Q-068) не меняется.

## Риски
- **Сброс веса при PUT.** Клиент, который знает только старые поля, при PUT стирает вес. Смягчение: до выкатки проверить, какие клиенты вызывают PUT
  (в репозитории — только API и тесты; админки нет, CQ-11). Если клиентов с PUT нет — риск низкий.
- **Вес виден тем, кто читает заказ.** Ответ `GET /api/orders/{номер}` отдаёт вес; права чтения не меняются (Q-055 — любой вошедший читает любой заказ).
  Вес — не персональные данные, но это новое поле в существующем открытом ответе.
- **Расхождение корзины и заказа.** Если вес изменили между добавлением в корзину и оформлением, заказ получит новый вес. Это снимок на момент
  оформления (решение 5); отдельного уведомления нет.
- **Выкатка миграций.** Обе миграции добавляют nullable-колонку: блокировок таблиц и переписывания данных нет; откат — удаление колонки.
- **Гонки.** Новых гонок не добавляем: вес пишется в той же транзакции, что и остальные поля каталога (`SaveChangesAsync`); событие цены не меняется.
- **Откат.** Откат кода без отката миграций безопасен: старый код колонку не читает. Откат миграций удаляет вес у всех товаров и заказов.

## Проверка
- Тесты по сценариям дельт: задачи 4.1 (каталог), 4.3 (заказ, домен и команды), 4.4 (чтение заказа), 4.6 (e2e витрины).
- Регресс: корзина и API заказа без веса (4.5); тесты затронутых возможностей из `impact.md`.
- Тест-кейсов qa-scan в репозитории нет; `design-context/` нет — wd-fit не применяется. Визуальная проверка подписи «Weight: N g» на витрине — вручную (4.7).
- Вручную на стенде: сценарий из задачи 4.7 целиком.
# Задачи: Вес товара в граммах

Каждая задача — одно место в коде. Требования и сценарии — из `specs/`. Решения по пунктам `impact.md` ссылаются на номера ниже.
Допущения CQ-01…CQ-11 — в `proposal.md`; при ответе, отличном от принятого, сначала меняется дельта, потом задача.

## 1. Данные и контракты

- [ ] 1.1 Добавить свойство `public int? WeightGrams { get; set; }` в `CatalogItem` (`src/Catalog.API/Model/CatalogItem.cs`) — готово, когда: сборка Catalog.API проходит, свойство без `[Required]`, по умолчанию пусто («Вес товара»).
- [ ] 1.2 Создать миграцию Catalog: `dotnet ef migrations add AddCatalogItemWeightGrams` в проекте Catalog.API (папка `src/Catalog.API/Infrastructure/Migrations`) — колонка `WeightGrams` integer NULL в таблице `Catalog`, без заполнения значений — готово, когда: миграция применяется к существующей базе, старые строки получают NULL («Вес товара», CQ-06).
- [ ] 1.3 В `CatalogApi.CreateItem` (`src/Catalog.API/Apis/CatalogApi.cs`, создание `new CatalogItem(...)` с ручным копированием полей) добавить `WeightGrams = product.WeightGrams` — готово, когда: сценарий «Товар создан с весом» из «Вес товара» проходит (тест 4.1).
- [ ] 1.4 Валидация веса в `CatalogApi.CreateItem`, `CatalogApi.UpdateItem` и `CatalogApi.UpdateItemV1`: если `WeightGrams` задан и не больше 0, вернуть 400 с `ProblemDetails` (`Detail` = «Weight must be positive»); тип результата метода расширить до `Results<..., BadRequest<ProblemDetails>>` там, где его нет. Товар не сохранять — готово, когда: сценарий «Вес не положительный» из «Вес товара» проходит (тест 4.1); исключение веса из требования «Значения товара не проверяются» (MODIFIED) учтено в комментарии кода.
- [ ] 1.5 Проверить, что `UpdateItem` (`CatalogEntry.CurrentValues.SetValues(productToUpdate)`) переносит `WeightGrams` и сбрасывает его в пусто, если поле не передано в теле — готово, когда: сценарий «Вес сброшен заменой без поля» из «Вес товара» проходит (тест 4.1). Если SetValues не переносит поле — дописать явно.
- [ ] 1.6 Добавить последним параметром `int? WeightGrams` в positional record `CatalogItem` (`src/WebAppComponents/Catalog/CatalogItem.cs`) — готово, когда: WebApp получает вес из ответа каталога (сценарий «Товар с весом» из «Вес товара в ответах каталога»).
- [ ] 1.7 В `OrderItem` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs`) добавить `public int? WeightGrams { get; private set; }` и параметр конструктора `int? weightGrams = null` после `units`; присвоить в конструкторе — готово, когда: сценарии «Вес сохраняется в позиции» и «Позиция без веса» из «Состав заказа» проходят (тест 4.3).
- [ ] 1.8 В `Order.AddOrderItem` (`src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs`, строка ~71) добавить параметр `int? weightGrams = null` и передать в `new OrderItem`; при слиянии с уже существующей позицией того же `productId` вес не менять (CQ-05) — готово, когда: сценарий «Одинаковые позиции» из «Состав заказа» проходит и вес сохраняется у первой позиции (тест 4.3).
- [ ] 1.9 Создать миграцию Ordering: `dotnet ef migrations add AddOrderItemWeightGrams` в проекте Ordering.Infrastructure (`src/Ordering.Infrastructure/Migrations`) — колонка `WeightGrams` integer NULL в таблице `orderItems` — готово, когда: миграция применяется, существующие позиции получают NULL (CQ-06).
- [ ] 1.10 Добавить `public int? WeightGrams { get; init; }` в `BasketItem` (`src/Ordering.API/Application/Models/BasketItem.cs`) — готово, когда: JSON-тело `CreateOrderRequest` с полем `WeightGrams` принимается, без поля — пусто.
- [ ] 1.11 В `OrderItemDTO` (`src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs`) добавить `public int? WeightGrams { get; init; }`; в `OrderDraftDTO.FromOrder` передать `WeightGrams = oi.WeightGrams`; в `ToOrderItemDTO` (`src/Ordering.API/Extensions/BasketItemExtensions.cs`) передать `WeightGrams = item.WeightGrams` — готово, когда: сценарий «Вес сохраняется в позиции» проходит на уровне DTO (тест 4.3).
- [ ] 1.12 Передать `item.WeightGrams` в `order.AddOrderItem(...)` в `CreateOrderCommandHandler.Handle` (`src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs`) и в `CreateOrderDraftCommandHandler.Handle` — готово, когда: сценарий «Вес сохраняется в позиции» из «Состав заказа» проходит через команду (тест 4.3).
- [ ] 1.13 В `Orderitem` (`src/Ordering.API/Application/Queries/OrderViewModel.cs`) добавить `public int? WeightGrams { get; init; }`; в `OrderQueries` (`src/Ordering.API/Application/Queries/OrderQueries.cs`, строки ~27–32) заполнить `WeightGrams = oi.WeightGrams` — готово, когда: сценарий «Заказ найден» из «Просмотр заказа по номеру» возвращает вес позиции (тест 4.4).

## 2. Поведение

- [ ] 2.1 Страница товара (`src/WebApp/Components/Pages/Item/ItemPage.razor`, блок `item-buy`, рядом с ценой или описанием): если `item.WeightGrams` задан, вывести `<p class="item-weight">Weight: {WeightGrams} g</p>`; если нет — ничего не выводить — готово, когда: сценарии «Вес на странице товара» и «Прямая ссылка на товар» из «Страница товара и ссылка «Back to catalog»» проходят (тест 4.6); ссылка «Back to catalog» не меняется.
- [ ] 2.2 Карточка товара в каталоге (`src/WebAppComponents/Catalog/CatalogListItem.razor`, внутри `catalog-product-content` после `span.price`): если `Item.WeightGrams` задан, вывести `<span class='weight'>Weight: {WeightGrams} g</span>` — готово, когда: сценарии «Карточка с весом» и «Карточка без веса» из «Вес в карточке товара каталога» проходят (тест 4.6).
- [ ] 2.3 Корзина (`src/WebApp/Components/Pages/Cart/CartPage.razor`, под ценой за единицу в строке позиции, строка ~46): если `item.WeightGrams` задан, вывести вес за единицу (`Weight: {n} g`) — готово, когда: сценарий «Корзина с позициями» из «Содержимое корзины» проходит (тест 4.6). Сумма и итог не меняются.
- [ ] 2.4 Вес в корзине и заказе: в `src/WebApp/Services/BasketItem.cs` добавить `public int? WeightGrams { get; set; }`; в `BasketState.FetchCoreAsync` (`src/WebApp/Services/BasketState.cs`, блок создания `new BasketItem`, строка ~135) заполнить `WeightGrams = catalogItem.WeightGrams` (из каталога, как цена; корзина на бэкенде вес не хранит, CQ-07) — готово, когда: `CreateOrderRequest.Items` содержит `WeightGrams` для каждой позиции (сценарий «Успешное оформление» из «Оформление заказа из корзины», тест 4.6).

## 3. Вызывающие и подписчики

- [ ] 3.1 Проверка клиентов без изменения кода: `src/ClientApp` (модели `Models/Catalog/CatalogItem.cs`, `Models/Orders/Order.cs`) и `src/HybridApp/Services/CatalogService.cs` (source-generated JSON-контекст) читают ответы каталога и заказов с новым полем `WeightGrams` без ошибок — готово, когда: проверка (ручная или unit) подтверждает, что неизвестное поле игнорируется и клиентский сценарий не ломается; код клиентов не меняется (CQ-10).

## 4. Проверка

- [ ] 4.1 `tests/Catalog.FunctionalTests/CatalogApiTests.cs`: сценарий «Название длиннее 50 символов» из «Значения товара не проверяются» не меняется (регресс); добавить сценарии «Товар создан с весом», «Товар создан без веса», «Вес не положительный» (0 и -5, 400), «Вес сброшен заменой без поля» из «Вес товара» — готово, когда: тесты зелёные.
- [ ] 4.2 `tests/Application.UnitTests/CatalogAITests.cs`: тест, что текст для эмбеддинга (`CatalogItemToString`) не зависит от `WeightGrams` — готово, когда: требование «Вес товара» («вес не входит в векторное описание») подтверждено тестом.
- [ ] 4.3 `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs` и `tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs`: сценарии «Вес сохраняется в позиции», «Позиция без веса», «Одинаковые позиции» (вес первой) из «Состав заказа»; проверить, что обработчики `OrderStatusChangedToAwaitingValidation` / `OrderStatusChangedToPaid` (S-05, S-06) не разбирают позиции — готово, когда: тесты зелёные.
- [ ] 4.4 `tests/Ordering.FunctionalTests/OrderingApiTests.cs`: сценарий «Заказ найден» из «Просмотр заказа по номеру» — ответ `GET /api/orders/{номер}` содержит `WeightGrams` позиции — готово, когда: тест зелёный.
- [ ] 4.5 Регресс: `tests/Basket.UnitTests/BasketServiceTests.cs` и `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs` проходят без изменений — готово, когда: зелёные (корзина и API заказа без веса работают как раньше).
- [ ] 4.6 e2e витрины (`e2e/BrowseItemTest.spec.ts`, `e2e/CartTest.spec.ts`, `e2e/CheckoutTest.spec.ts`): прогнать; в `BrowseItemTest.spec.ts` добавить проверку строки «Weight: N g» для товара с весом и её отсутствия у товара без веса (сценарии «Вес на странице товара», «Карточка без веса», «Корзина с позициями»). Тест-кейсов qa-scan в репозитории нет — пункта T нет.
- [ ] 4.7 Ручная проверка на стенде: создать товар через POST с весом, открыть витрину, положить в корзину, оформить, проверить `GET /api/orders/{номер}`.

## 5. Слой контекста

- [ ] 5.1 Обновить `system-context/trace.md`: строки изменённых и новых требований → код и тесты (включая «Вес товара», «Вес товара в ответах каталога», «Вес в карточке товара каталога»).
- [ ] 5.2 Пересобрать слой, если установлен sa-scan: `contracts.py scan .` и `plan.py guide .` (иначе — пункт в отчёте); `check.py .` без ошибок.
# Влияние изменения `product-weight-grams`

Собрано `change.py analyze` из слоя sa-scan. Затронуто: возможности `catalog-management`, `catalog-browsing`, `storefront`, `basket`, `order-placement`, `order-management`; входы http:PUT /api/catalog/items; сущности CatalogItem, OrderItem.
У каждого пункта — **Решение**: `задача N.N` (номер из tasks.md, можно несколько) или `не затрагивается: <почему>`.
Для вопросов [блокирует]: `ответ: …` (если человек ответил) или `в proposal: <что принято до ответа>`.
Повторный `analyze` обновит пункты и сохранит решения. Пункты, которых нет в слое, добавь сам в конце с буквой X (X-01…).


## Кто вызывает затронутые входы

- [ ] C-01 `src/ClientApp → /api/catalog` — клиентское приложение <!-- key: caller:src/ClientApp → /api/catalog -->
  - опирается на: читает ответ `GET items` как `CatalogRoot` — поля `Data`, `PageIndex`, `PageSize`, `Count` (src/ClientApp/Models/Catalog/CatalogRoot.cs) и `CatalogItem` с `PictureUri` (src/ClientApp/Models/Catalog/CatalogItem.cs:9); сервер такого поля не отдаёт (только `PictureFileName`), поэтому картинку клиент строит сам: `{шлюз}/api/catalog/items/{id}/pic` (src/ClientApp/Services/FixUri/FixUriService.cs:36). Версия API зашита `api-version=2.0` (src/ClientApp/Services/Catalog/CatalogService.cs:12). Фильтр шлёт одиночные `type`/`brand` и путь с двойным слэшем `//items` (CatalogService.cs:29). Статусов не сравнивает: ошибка HTTP исключением уходит в вызывающего, пустой ответ превращается в пустой список (Ca
  - где: src/ClientApp/Services/Catalog/CatalogService.cs:11, src/ClientApp/Services/FixUri/FixUriService.cs:36
  - **Решение:** задача 3.1 (клиент читает известные поля и игнорирует новое WeightGrams; код не меняется, проверка в 3.1)
- [ ] C-02 `src/HybridApp → /api/catalog` — клиентское приложение <!-- key: caller:src/HybridApp → /api/catalog -->
  - опирается на: `GetFromJsonAsync` с camelCase-контекстом (src/HybridApp/Services/CatalogService.cs:16, 22; контекст src/HybridApp/Services/CatalogJsonContext.cs:13) в типы `CatalogItem`, `CatalogResult`, `CatalogBrand[]`, `CatalogItemType[]` из WebAppComponents. Всегда `api-version=2.0` (CatalogService.cs:15, 22, 28, 35, 42, 49); пути `items/{id}`, `items/by?ids=`, `items/withsemanticrelevance?text=`, `catalogBrands`, `catalogTypes`. Статусы не обрабатывает — любой не-2xx бросает `HttpRequestException`; `result!` без проверки на null (CatalogService.cs:23). Сломается при: смене имён полей JSON (source-generated контекст не примет неизвестные формы), снятии версии 2.0, смене формы `withsemanticrelevance` (к
  - где: src/HybridApp/Services/CatalogService.cs:10
  - **Решение:** задача 3.1 (source-generated JSON игнорирует неизвестное поле; проверка в 3.1)
- [ ] C-03 `src/WebApp → /api/catalog` <!-- key: caller:src/WebApp → /api/catalog -->
  - опирается на: не вызывает API сам — только проксирует картинки: `/product-images/{id}` → `catalog-api` `/api/catalog/items/{id}/pic` (src/WebApp/Program.cs:32), без `api-version`. Каталог WebApp читает через WebAppComponents (см. ниже), клиент зарегистрирован с `AddApiVersion(2.0)` (src/WebApp/Extensions/Extensions.cs:34-36). Сломается при: смене маршрута `/pic` — все картинки витрины (`IProductImageUrlProvider`) перестанут грузиться.
  - где: src/WebApp/Program.cs:32
  - **Решение:** не затрагивается: проксирует только картинки (/pic), маршрут и ответ картинки не меняются
- [ ] C-04 `src/WebAppComponents → /api/catalog` <!-- key: caller:src/WebAppComponents → /api/catalog -->
  - опирается на: общий клиент каталога витрины, который использует WebApp. Читает `CatalogResult(PageIndex, PageSize, Count, Data)` и `CatalogItem(Id, Name, Description, Price, PictureUrl, CatalogBrandId, CatalogBrand, CatalogTypeId, CatalogType)` (src/WebAppComponents/Catalog/CatalogItem.cs:3-17). Страница каталога делит `Count` на размер страницы 9 для пагинации (src/WebApp/Components/Pages/Catalog/Catalog.razor:93, 151), карточка показывает `Name`, `Price`, `CatalogBrand.Brand` (src/WebAppComponents/Catalog/CatalogListItem.razor:6-18). Страница товара ловит именно `404` от `GET items/{id}` и отдаёт 404 пользователю (src/WebApp/Components/Pages/Item/ItemPage.razor:117-120) — другой код (400, 500) станет не
  - где: src/WebAppComponents/Services/CatalogService.cs:9
  - **Решение:** задачи 1.6, 2.2 (тип CatalogItem получает WeightGrams; карточка показывает вес)
- [ ] C-05 `src/eShop.AppHost → /api/catalog` <!-- key: caller:src/eShop.AppHost → /api/catalog -->
  - опирается на: это конфигурация шлюза мобильного BFF (YARP): список маршрутов каталога с обязательным `api-version` (запрос без параметра или с другим значением до каталога не дойдёт — 404 шлюза): `items`, `items/by`, `items/{id}`, `{id}/pic`, `catalogTypes`, `catalogBrands` — 1.0/1/2.0; `items/by/{name}`, `items/type/...` и `withsemanticrelevance/{text}` — только 1.0/1; `withsemanticrelevance` — только 2.0 (src/eShop.AppHost/Extensions.cs:106-148); общий `/api/catalog/{*any}` (151). Сломается при: переименовании путей или версий в Catalog.API — шлюз отфильтрует их раньше сервиса; новый маршрут или версия требуют строки здесь.
  - где: src/eShop.AppHost/Extensions.cs:106
  - **Решение:** не затрагивается: новых путей и версий API нет, WeightGrams — поле ответа, шлюз его не фильтрует
- [ ] C-06 `src/ClientApp → /api/orders` — клиентское приложение <!-- key: caller:src/ClientApp → /api/orders -->
  - опирается на: только версия 1.0 (`api-version=1.0`, src/ClientApp/Services/Order/OrderService.cs:14). Страница заказа читает `Order` с JSON-именами `status`, `ordernumber`, `date`, `total`, `items`, `city`, `street`, `state`, `country`, `zipCode` (src/ClientApp/Models/Orders/Order.cs:13-50); сервер отдаёт `Status`, `OrderNumber`, `Zipcode`, `OrderItems` (src/Ordering.API/Application/Queries/OrderViewModel.cs:12-23): `status`, `ordernumber`, `zipCode` совпадают только без учёта регистра, а `items` клиента и `OrderItems` сервера различаются по имени — список позиций на клиенте может не заполняться. Кнопка «CANCEL ORDER» видна только когда `status` равен `Submitted` без учёта регистра (src/ClientApp/ViewMode
  - где: src/ClientApp/Services/Order/OrderService.cs:13
  - **Решение:** не затрагивается: клиент читает только известные поля заказа, новое поле в ответе игнорируется; вес в мобильном клиенте не показывается (CQ-10)
- [ ] C-07 `src/WebApp → /api/orders` <!-- key: caller:src/WebApp → /api/orders -->
  - опирается на: `GET api/Orders/` в `OrderRecord(OrderNumber, Date, Status, Total)` (src/WebApp/Services/OrderingService.cs:9, 21-25) — форма `OrderSummary` сервера; список заказов выводит их и строит CSS-класс из `Status.ToLower()` (src/WebApp/Components/Pages/User/Orders.razor:48-52), то есть новый статус без CSS-класса отрисуется без стиля. `POST` создания заказа шлёт `x-requestid` и тело `CreateOrderRequest` (OrderingService.cs:12-18); ответ не проверяется, `EnsureSuccess` нет — а сервер на невалидный заказ всё равно отвечает 200 (см. заметку под `POST /api/orders`). Версия 1.0 через `AddApiVersion(1.0)` (src/WebApp/Extensions/Extensions.cs:38-40). Сломается при: переименовании `OrderNumber`/`Status`/`T
  - где: src/WebApp/Services/OrderingService.cs:5
  - **Решение:** задача 2.4 (WebApp передаёт вес позиции в CreateOrderRequest; ответ заказа клиент не разбирает по позициям)
- [ ] C-08 `src/eShop.AppHost → /api/orders` <!-- key: caller:src/eShop.AppHost → /api/orders -->
  - опирается на: конфигурация шлюза: `/api/orders/{*any}` → ordering-api, пропускает только `api-version` 1.0/1 (src/eShop.AppHost/Extensions.cs:155-156); авторизация — на стороне сервиса (`RequireAuthorization`). Сломается при: выпуске v2 заказов — шлюз его не пропустит, пока не поменять значения здесь.
  - где: src/eShop.AppHost/Extensions.cs:155
  - **Решение:** не затрагивается: маршруты и версии шлюза не меняются, поля тела проходят как есть
- [ ] C-09 `src/ClientApp → gRPC Basket` — клиентское приложение <!-- key: caller:src/ClientApp → gRPC Basket -->
  - опирается на: мобильное приложение ходит в Basket по gRPC напрямую с bearer-токеном в метаданных (src/ClientApp/Services/Basket/BasketService.cs:46, 84, 108). Читает `CustomerBasketResponse.Items` → `ProductId`, `Quantity` (BasketService.cs:50-53, 91-94) — больше ничего (название, цена в корзине берутся не отсюда). `GetBasket` при любом исключении печатает его и возвращает `null` корзину (BasketService.cs:56-60), `UpdateBasket` ошибки не ловит. Без токена методы тихо ничего не делают (BasketService.cs:38, 70, 103). Сломается при: смене номеров полей и имён в `basket.proto`, замене `repeated items`, добавлении обязательной авторизации в `GetBasket` (сейчас он `AllowAnonymous` и для анонима отдаёт пустую ко
  - где: src/ClientApp/Services/Basket/BasketService.cs:18, src/ClientApp/Services/Basket/Protos/BasketGrpc.cs:90
  - **Решение:** не затрагивается: basket.proto не меняется, корзина вес не хранит (вес берётся из каталога, CQ-07)
- [ ] C-10 `src/WebApp → gRPC Basket` <!-- key: caller:src/WebApp → gRPC Basket -->
  - опирается на: gRPC-клиент `Basket.BasketClient` на `http://basket-api` с проброшенным токеном пользователя (src/WebApp/Extensions/Extensions.cs:31-32). Читает `Items` → `ProductId`, `Quantity` (src/WebApp/Services/BasketService.cs:40-43); шлёт `UpdateBasketRequest.Items` с теми же двумя полями (34-35). Цена и название в корзине в gRPC не передаются: страница корзины и чат берут их из каталога по `ProductId` (`BasketState` собирает `BasketItem` с `ProductName`, `UnitPrice` из каталога — src/WebApp/Services/BasketItem.cs:5-10). Ошибки: страница `CartMenu` ловит `HttpRequestException` со статусом `401` и выходит из сессии (src/WebApp/Components/Layout/CartMenu.razor:45-48); чат различает gRPC `Unauthenticate
  - где: src/WebApp/Extensions/Extensions.cs:31, src/WebApp/Services/BasketService.cs:3
  - **Решение:** задача 2.4 (корзина вес не хранит: BasketState берёт WeightGrams из каталога по ProductId, как цену; basket.proto не меняется)

## События: публикуемые и названные

- [ ] S-01 `OrderStartedIntegrationEvent` <!-- key: event:OrderStartedIntegrationEvent -->
  - поля: UserId string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Basket.API/IntegrationEvents/EventHandling/OrderStartedIntegrationEventHandler.cs:6 (обработчик интеграционного события → OrderStartedIntegrationEventHandler)
  - заметки: Заметки: публикуется внутри доменного обработчика старта заказа; Basket по нему очищает корзину пользователя. Поле только `UserId`.
  - **Решение:** не затрагивается: событие несёт только UserId, позиций и веса нет
- [ ] S-05 `OrderCancelledDomainEvent` (внутреннее) <!-- key: event:OrderCancelledDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs:3 (MediatR → OrderCancelledDomainEventHandler)
  - **Решение:** не затрагивается: событие несёт весь заказ, вес попадает в него сам; обработчик отмены не разбирает позиции (проверка в задаче 4.3)
- [ ] S-06 `OrderShippedDomainEvent` (внутреннее) <!-- key: event:OrderShippedDomainEvent -->
  - поля: Order Order
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/OrderShippedDomainEventHandler.cs:3 (MediatR → OrderShippedDomainEventHandler)
  - **Решение:** не затрагивается: событие несёт весь заказ, вес попадает в него сам; обработчик отгрузки не разбирает позиции (проверка в задаче 4.3)
- [ ] S-02 `BuyerAndPaymentMethodVerifiedDomainEvent` (внутреннее) <!-- key: event:BuyerAndPaymentMethodVerifiedDomainEvent -->
  - поля: Buyer Buyer, Payment PaymentMethod, OrderId int
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler.cs:3 (MediatR → UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler)
  - **Решение:** не затрагивается: событие несёт покупателя и метод оплаты, позиций нет
- [ ] S-03 `OrderStatusChangedToSubmittedIntegrationEvent` <!-- key: event:OrderStatusChangedToSubmittedIntegrationEvent -->
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToSubmittedIntegrationEventHandler.cs:5 (обработчик интеграционного события → OrderStatusChangedToSubmittedIntegrationEventHandler)
  - **Решение:** не затрагивается: событие статуса несёт номер, статус и покупателя, позиций нет
- [ ] S-04 `ProductPriceChangedIntegrationEvent` <!-- key: event:ProductPriceChangedIntegrationEvent -->
  - поля: ProductId int, NewPrice decimal, OldPrice decimal
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs:3 (обработчик интеграционного события → ProductPriceChangedIntegrationEventHandler)
  - заметки: Заметки: единственный подписчик — Webhooks, и его обработчик пустой (`Task.CompletedTask`, src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs:5-8): событие никого не уведомляет. Корзина (Basket) на изменение цены не подписана.
  - **Решение:** не затрагивается: вес не нужен событию смены цены; подписчик Webhooks пустой (CQ-08)

## Сущности: где поле потеряется молча

- [ ] E-01 `CatalogItem` создаётся: `CatalogApi.CreateItem` src/Catalog.API/Apis/CatalogApi.cs:419 <!-- key: create:CatalogItem:`CatalogApi.CreateItem` src/Catalog.API/Apis/CatalogApi.cs:419 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 1.3 (CreateItem копирует поля вручную)
- [ ] E-02 `CatalogItem` создаётся: `CatalogContextSeed.SeedAsync` src/Catalog.API/Infrastructure/CatalogContextSeed.cs:48 <!-- key: create:CatalogItem:`CatalogContextSeed.SeedAsync` src/Catalog.API/Infrastructure/CatalogContextSeed.cs:48 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: засев не задаёт вес, существующие товары остаются без веса (CQ-06)
- [ ] E-03 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:16 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:16 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок клиентского приложения, вес в мобильном клиенте не нужен (CQ-10)
- [ ] E-04 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:28 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:28 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок клиентского приложения (CQ-10)
- [ ] E-05 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:40 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:40 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок клиентского приложения (CQ-10)
- [ ] E-06 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:52 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:52 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок клиентского приложения (CQ-10)
- [ ] E-07 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:64 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:64 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок клиентского приложения (CQ-10)
- [ ] E-08 `CatalogItem` → копия `CatalogItem` (src/ClientApp/Models/Catalog/CatalogItem.cs:3) <!-- key: copy:CatalogItem:CatalogItem:src/ClientApp/Models/Catalog/CatalogItem.cs -->
  - общих полей 8 из 9, нет: availablestock, embedding, maxstockthreshold, onreorder, picturefilename, restockthreshold
  - **Решение:** не затрагивается: модель мобильного клиента не показывает вес (CQ-10); лишнее поле игнорируется
- [ ] E-09 `CatalogItem` → копия `CatalogItem` (src/WebAppComponents/Catalog/CatalogItem.cs:3) <!-- key: copy:CatalogItem:CatalogItem:src/WebAppComponents/Catalog/CatalogItem.cs -->
  - общих полей 8 из 9, нет: availablestock, embedding, maxstockthreshold, onreorder, picturefilename, restockthreshold
  - **Решение:** задача 1.6 (копия в WebAppComponents получает WeightGrams)
- [ ] E-10 `CatalogItem` → копия `CatalogContextSeed` (src/Catalog.API/Infrastructure/CatalogContextSeed.cs:7) <!-- key: copy:CatalogItem:CatalogContextSeed:src/Catalog.API/Infrastructure/CatalogContextSeed.cs -->
  - общих полей 4 из 6, нет: availablestock, catalogbrand, catalogbrandid, catalogtype, catalogtypeid, embedding
  - **Решение:** не затрагивается: модель засева, вес не задаётся (CQ-06)
- [ ] E-11 `CatalogItem` → копия `CatalogSourceEntry` (src/Catalog.API/Infrastructure/CatalogContextSeed.cs:77) <!-- key: copy:CatalogItem:CatalogSourceEntry:src/Catalog.API/Infrastructure/CatalogContextSeed.cs -->
  - общих полей 4 из 6, нет: availablestock, catalogbrand, catalogbrandid, catalogtype, catalogtypeid, embedding
  - **Решение:** не затрагивается: вход засева без веса (CQ-06)
- [ ] E-12 `CatalogItem` засев: src/Catalog.API/Infrastructure/CatalogContextSeed.cs (только в пустую таблицу) <!-- key: seed:CatalogItem:src/Catalog.API/Infrastructure/CatalogContextSeed.cs (только в пустую таблицу) -->
  - засев только в пустую таблицу — существующим данным нужна миграция данных
  - **Решение:** не затрагивается: колонка nullable, существующие строки получают NULL, данные не переносятся; заполнение — CQ-06
- [ ] E-13 `CatalogItem` уходит в модель ИИ: src/Catalog.API/Services/CatalogAI.cs:40 <!-- key: ai:CatalogItem:src/Catalog.API/Services/CatalogAI.cs:40 -->
  - новое поле может попасть в промпт или эмбеддинг само
  - **Решение:** не затрагивается: текст для эмбеддинга — имя и описание (CatalogAI.CatalogItemToString), вес в него не входит; проверка в 4.2
- [ ] E-14 `CatalogItem` уходит в модель ИИ: src/Catalog.API/Services/CatalogAI.cs:75 <!-- key: ai:CatalogItem:src/Catalog.API/Services/CatalogAI.cs:75 -->
  - новое поле может попасть в промпт или эмбеддинг само
  - **Решение:** не затрагивается: то же, что E-13 (CatalogAI.cs:75); проверка в 4.2
- [ ] E-15 `CatalogItem` миграция схемы: src/Catalog.API/Infrastructure/Migrations: миграций 3, последние: 20231018163051_RemoveHiLoAndIndexCatalogName.cs, 20231026091140_Outbox.cs; схема или снимок: s <!-- key: migr:CatalogItem -->
  - новая миграция, снимок схемы сверить с моделью
  - **Решение:** задача 1.2 (миграция Catalog: колонка WeightGrams NULL)
- [ ] E-16 `OrderItem` создаётся: `OrderMockService` src/ClientApp/Services/Order/OrderMockService.cs:43 <!-- key: create:OrderItem:`OrderMockService` src/ClientApp/Services/Order/OrderMockService.cs:43 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок заказов клиентского приложения (CQ-10)
- [ ] E-17 `OrderItem` создаётся: `OrderMockService` src/ClientApp/Services/Order/OrderMockService.cs:53 <!-- key: create:OrderItem:`OrderMockService` src/ClientApp/Services/Order/OrderMockService.cs:53 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мок заказов клиентского приложения (CQ-10)
- [ ] E-18 `OrderItem` создаётся: `CheckoutViewModel.CreateOrderItems` src/ClientApp/ViewModels/CheckoutViewModel.cs:144 <!-- key: create:OrderItem:`CheckoutViewModel.CreateOrderItems` src/ClientApp/ViewModels/CheckoutViewModel.cs:144 -->
  - новое поле здесь не заполнится само
  - **Решение:** не затрагивается: мобильный клиент не передаёт вес в заказе (CQ-10)
- [ ] E-19 `OrderItem` создаётся: `Order.AddOrderItem` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:88 <!-- key: create:OrderItem:`Order.AddOrderItem` src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs:88 -->
  - новое поле здесь не заполнится само
  - **Решение:** задачи 1.7, 1.8 (OrderItem и Order.AddOrderItem принимают вес)
- [ ] E-20 `OrderItem` → копия `OrderItemDTO` (src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs:46) <!-- key: copy:OrderItem:OrderItemDTO:src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs -->
  - общих полей 6 из 6
  - **Решение:** задача 1.11 (OrderItemDTO и ToOrderItemDTO переносят вес)
- [ ] E-21 `OrderItem` → копия `OrderItem` (src/ClientApp/Models/Orders/OrderItem.cs:5) <!-- key: copy:OrderItem:OrderItem:src/ClientApp/Models/Orders/OrderItem.cs -->
  - общих полей 5 из 7, нет: units
  - **Решение:** не затрагивается: модель заказа мобильного клиента не показывает вес (CQ-10)
- [ ] E-22 `OrderItem` → копия `Orderitem` (src/Ordering.API/Application/Queries/OrderViewModel.cs:3) <!-- key: copy:OrderItem:Orderitem:src/Ordering.API/Application/Queries/OrderViewModel.cs -->
  - общих полей 4 из 4, нет: discount, productid
  - **Решение:** задача 1.13 (OrderViewModel.Orderitem отдаёт вес)
- [ ] E-23 `OrderItem` миграция схемы: src/Ordering.Infrastructure/Migrations: миграций 4, последние: 20231026091055_Outbox.cs, 20240106121712_UseEnumForOrderStatus.cs; схема или снимок: src/Ordering <!-- key: migr:OrderItem -->
  - новая миграция, снимок схемы сверить с моделью
  - **Решение:** задача 1.9 (миграция orderItems: колонка WeightGrams NULL)

## Блокирующие вопросы

- [ ] Q-001 [блокирует] Должны ли API принимать любой токен Identity — аудитория и scope не проверяются? <!-- key: q:Q-001 -->
  - допущение: принимается любой токен Identity, как в коде
  - статус: открыт
  - **Решение:** в proposal: доступ к записи каталога не меняется; вес не меняет правил доступа
- [ ] Q-014 [блокирует] Должны ли изменения каталога требовать вход и роль? <!-- key: q:Q-014 -->
  - допущение: как в коде: изменения доступны без проверки аутентификации и роли
  - статус: открыт
  - **Решение:** в proposal: доступ к записи каталога как сейчас; вес пишется теми же вызовами (Q-014 вне этого изменения)
- [ ] Q-035 [блокирует] Данные карты (номер, код безопасности) попадают в токены и журналы — допустимо? <!-- key: q:Q-035 -->
  - допущение: код безопасности и номер карты передаются клиентам, как в коде
  - статус: открыт
  - **Решение:** в proposal: изменение не трогает платёжные данные заказа
- [ ] Q-055 [блокирует] Кто может отменять, отгружать и читать чужие заказы? <!-- key: q:Q-055 -->
  - допущение: спека описывает код: любой вошедший пользователь может отменить, отгрузить и прочитать любой заказ по номеру
  - статус: открыт
  - **Решение:** в proposal: право чтения заказа не меняется; вес станет виден тому, кто читает заказ по номеру, — это усиливает риск Q-055 (см. «Открытые вопросы»)
- [ ] Q-058 [блокирует] Повтор с тем же x-requestid после неудачи должен повторить действие? <!-- key: q:Q-058 -->
  - допущение: спека описывает код: повтор после неудачи даёт 200 и не выполняет команду
  - статус: открыт
  - **Решение:** в proposal: повтор заказа с тем же x-requestid не меняется; вес уходит в тот же заказ
- [ ] Q-064 [блокирует] Оплата — заглушка (исход из настроек, фиксированная тестовая карта): какой будет реальная оплата? <!-- key: q:Q-064 -->
  - допущение: оплата имитируется, внешний платёжный шлюз не используется и не описан
  - статус: открыт
  - **Решение:** в proposal: оплата остаётся заглушкой; вес на оплату не влияет
- [ ] Q-067 [блокирует] Должен ли сервер брать UserId покупателя из токена, а не из тела запроса? <!-- key: q:Q-067 -->
  - допущение: заказ создаётся на UserId из тела, как написано в коде
  - статус: открыт
  - **Решение:** в proposal: UserId заказа берётся как сейчас; вес не меняет источник покупателя
- [ ] Q-068 [блокирует] Создание заказа не сообщает об ошибке: API отвечает 200, витрина очищает корзину без заказа — так задумано? <!-- key: q:Q-068 -->
  - допущение: клиент видит успех при любом исходе, как в коде; витрина по этому ответу удаляет корзину (src/WebApp/Services/BasketState.cs, после CreateOrder)
  - статус: открыт
  - **Решение:** в proposal: ответ 200 при ошибке создания не меняется; вес не добавляет новых ошибок в ответ заказа

## Уточняющие вопросы по затронутым возможностям

- Q-002 Нулевое количество и повтор одного товара в корзине: так задумано или ошибка?
- Q-003 Должна ли корзина отвергать товар, которого нет в каталоге?
- Q-004 Допустима ли потеря позиций при одновременных изменениях корзины?
- Q-005 Должна ли корзина истекать по времени?
- Q-006 Корзина должна очищаться при создании заказа, а не после оплаты?
- Q-007 Что должно быть, если очистка корзины по событию не выполнилась?
- Q-008 Какую версию API получает запрос без api-version и что тогда возвращается?
- Q-009 Версия 1.0 списка /api/catalog/items не применяет name, type и brand: баг или так задумано?
- Q-010 Поиск по названию: только по началу и с учётом регистра — так задумано?
- Q-011 Нужны ли ограничения размера страницы и проверка параметров пагинации?
- Q-012 Нужен ли второй ключ сортировки при одинаковых названиях товаров?
- Q-013 В пакетном ответе товаров по списку id бренд и тип не заполняются, и лимита на число id нет: так задумано?
- Q-015 PUT «создать или заменить» или 404, если товара нет?
- Q-016 Что делать, если Id в пути и в теле PUT (версия 2) различаются?
- Q-017 Должен ли клиент задавать Id нового товара?
- Q-018 Остатки товара задаются вручную через PUT или их ведёт склад?
- Q-019 Что должно происходить, если сервис эмбеддингов недоступен при записи товара?
- Q-020 Можно ли удалять товар, который есть в заказах или корзинах?
- Q-021 Нужна ли проверка значений товара (длина названия, цена не ниже нуля)?
- Q-056 Для отказа в отмене и отгрузке нужен код 500 или 4xx (например 409)?
- Q-057 Если обработчик события отмены упал, статус «Отменён» должен откатиться?
- Q-059 Повторная отмена уже отменённого заказа: допустима ли повторная публикация события?
- Q-060 Отмена пользователем разрешена в любой момент до оплаты или только в период ожидания?
- Q-061 Заказ отменён до ответа оплаты: оплату молча принимать или считать ошибкой?
- Q-071 Может ли заказ сохраниться без покупателя и метода оплаты?
- Q-073 Должен ли метод оплаты переиспользоваться по маске номера карты?
- Q-074 Нужен ли черновик заказа (POST /api/orders/draft), если в репозитории его не вызывает ни один клиент?
- Q-081 Должен ли возврат после входа допускать адреса вида «//хост»?
- Q-082 Нужно ли завершать сессию покупателя без сообщения, когда Basket API отвечает 401?
- Q-083 Должна ли ссылка «Back to catalog» на прямой ссылке вести на каталог?
- Q-084 Нужны ли верхний предел количества и проверка остатков при изменении количества в корзине?
- Q-085 Нужна ли пагинация списка заказов?
- Q-086 Должна ли сортировка каталога действовать на все страницы, а не только на текущую?

## Тесты затронутых возможностей (запустить и обновить)

- catalog-management: tests/Catalog.FunctionalTests/CatalogApiTests.cs, tests/Application.UnitTests/CatalogAITests.cs
- catalog-browsing: tests/Catalog.FunctionalTests/CatalogApiTests.cs
- storefront: e2e/cart-helpers.ts, e2e/CartTest.spec.ts, e2e/BrowseItemTest.spec.ts, e2e/CheckoutTest.spec.ts, e2e/login.setup.ts
- basket: tests/Basket.UnitTests/BasketServiceTests.cs
- order-placement: tests/Ordering.FunctionalTests/OrderingApiTests.cs, tests/Ordering.UnitTests/Application/IdentifiedCommandHandlerTest.cs, tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs, tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs, tests/Ordering.UnitTests/Domain/BuyerAggregateTest.cs, tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs
- order-management: tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs, tests/Ordering.FunctionalTests/OrderingApiTests.cs

## Сущности в коде затронутых возможностей (если меняешь их поля — добавь --entity)

- Buyer, Order, PaymentMethod

## Код затронутых возможностей

Файлы из трассировки и обработчиков — по ним волны и пересечения с другими изменениями.

- src/Basket.API/Extensions/Extensions.cs
- src/Basket.API/Extensions/ServerCallContextIdentityExtensions.cs
- src/Basket.API/Grpc/BasketService.cs
- src/Basket.API/IntegrationEvents/EventHandling/OrderStartedIntegrationEventHandler.cs
- src/Basket.API/Proto/basket.proto
- src/Basket.API/Repositories/RedisBasketRepository.cs
- src/Catalog.API/Apis/CatalogApi.cs
- src/Catalog.API/Extensions/Extensions.cs
- src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs
- src/Catalog.API/IntegrationEvents/CatalogIntegrationEventService.cs
- src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs
- src/Catalog.API/Model/PaginatedItems.cs
- src/Catalog.API/Model/PaginationRequest.cs
- src/Catalog.API/Program.cs
- src/Catalog.API/Services/CatalogAI.cs
- src/EventBusRabbitMQ/RabbitMQEventBus.cs
- src/Ordering.API/Apis/OrdersApi.cs
- src/Ordering.API/Application/Behaviors/TransactionBehavior.cs
- src/Ordering.API/Application/Behaviors/ValidatorBehavior.cs
- src/Ordering.API/Application/Commands/CancelOrderCommandHandler.cs
- src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs
- src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs
- src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs
- src/Ordering.API/Application/Commands/ShipOrderCommandHandler.cs
- src/Ordering.API/Application/DomainEventHandlers/UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler.cs
- src/Ordering.API/Application/DomainEventHandlers/ValidateOrAddBuyerAggregateWhenOrderStartedDomainEventHandler.cs
- src/Ordering.API/Application/Queries/OrderQueries.cs
- src/Ordering.API/Application/Validations/CancelOrderCommandValidator.cs
- src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs
- src/Ordering.API/Application/Validations/ShipOrderCommandValidator.cs
- src/Ordering.API/Infrastructure/OrderingContextSeed.cs
- src/Ordering.API/Infrastructure/Services/IdentityService.cs
- src/Ordering.API/Program.cs
- src/Ordering.Domain/AggregatesModel/BuyerAggregate/Buyer.cs
- src/Ordering.Domain/AggregatesModel/BuyerAggregate/PaymentMethod.cs
- src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs
- src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderItem.cs
- src/Ordering.Infrastructure/EntityConfigurations/PaymentMethodEntityTypeConfiguration.cs
- src/Ordering.Infrastructure/Idempotency/RequestManager.cs
- src/WebApp/Components/Layout/CartMenu.razor
- src/WebApp/Components/Layout/UserMenu.razor
- src/WebApp/Components/Pages/Cart/CartPage.razor
- src/WebApp/Components/Pages/Catalog/Catalog.razor
- src/WebApp/Components/Pages/Checkout/Checkout.razor
- src/WebApp/Components/Pages/Item/ItemPage.razor
- src/WebApp/Components/Pages/User/LogIn.razor
- src/WebApp/Components/Pages/User/LogOut.razor
- src/WebApp/Components/Pages/User/Orders.razor
- src/WebApp/Components/Pages/User/OrdersRefreshOnStatusChange.razor
- src/WebApp/Services/BasketCheckoutInfo.cs
- src/WebApp/Services/BasketState.cs
- src/WebApp/Services/LogOutService.cs
- src/WebApp/Services/OrderingService.cs
- src/WebApp/wwwroot/js/cart-quantity.js
- src/WebApp/wwwroot/js/catalog-sort.js
- src/WebAppComponents/Catalog/CatalogListItem.razor
- src/WebAppComponents/Services/CatalogService.cs
- src/Webhooks.API/Program.cs
- src/eShop.ServiceDefaults/AuthenticationExtensions.cs
