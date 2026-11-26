# Снятие товара с продажи

## Why

Менеджер не может убрать товар из продажи: покупаемость товара определяется только остатком, а товар без остатка нельзя отличить от «временно кончился» — витрина предлагает кнопку «Add to shopping bag», корзина принимает его без сверок (Q-003), а заказ с ним отклоняется только после создания, на проверке остатков. Нужно уметь пометить товар каталога как недоступный: такой товар нельзя добавить в корзину и заказать, а лежащий в корзинах покупатель видит его недоступным и не может оформить заказ, пока не удалит.

## What Changes

- У товара каталога появляется признак `available` (bool, по умолчанию true); менеджер снимает товар с продажи и возвращает на продажу через существующий PUT /api/catalog/items/{id} (полное замещение).
- Ответы каталога (списки, по id, по списку id) включают `available` и не фильтруют снятые товары.
- Basket.API отклоняет добавление недоступных товаров (`InvalidArgument` с id); изменение и удаление уже лежащих позиций работают. **BREAKING** для клиентов, не обрабатывающих новую ошибку gRPC: в системе такие — витрина и мобильный клиент, обработчики добавляются этим же изменением.
- Витрина: страница товара со снятым товаром показывает «Unavailable» без кнопки; корзина помечает недоступные позиции (только «Remove», вне сводки); оформление блокируется сообщением, пока недоступные позиции не удалены.
- catalog-stock при проверке заказа на AwaitingValidation считает позицию снятого товара не подтверждённой — заказ отклоняется и отменяется (серверная страховка для обхода UI).
- Мобильный ClientApp: поле в модели, блок добавления со страницы товара, алерт при отказе корзины; корзина и оформление мобильного приложения недоступность не показывают (см. открытые вопросы).
- События, Ordering.API и существующие заказы не меняются.

## Влияние

`src/ClientApp → /api/catalog` — модель товара дополняется `available` (по умолчанию true); страница товара блокирует добавление снятого (задачи 5.1, 5.2)
`src/HybridApp → /api/catalog` — читает товары витринным биндингом: новое поле биндится по имени, изменений не требует — не затрагивается
`src/WebApp → /api/catalog` — только прокси картинок — не затрагивается
`src/WebAppComponents → /api/catalog` — модель товара дополняется `available`; клиент `items/by` и страницы товара/корзины используют её (задача 4.1)
`src/eShop.AppHost → /api/catalog` — новых маршрутов и версий нет — не затрагивается
`src/ClientApp → /api/orders` — контракт оформления не меняется; заказ с недоступным товаром будет отклонён на проверке остатков (звено 6 design) — задача не нужна
`src/WebApp → /api/orders` — заказ теперь не отправляется при недоступных позициях (валидация + страховка в BasketState.CheckoutAsync, задачи 4.5, 4.6)
`src/eShop.AppHost → /api/orders` — не затрагивается (маршруты и версии прежние)
`src/ClientApp → gRPC Basket` — UpdateBasket может вернуть `InvalidArgument`: алерт на странице товара (задача 5.2); операции с уже лежащими позициями не меняются
`src/WebApp → gRPC Basket` — страница товара ловит `InvalidArgument` и показывает недоступный товар (задача 4.3); CartPage отклонений не провоцирует
`OrderStartedIntegrationEvent` — поля и подписчики не меняются — не затрагивается (корзина очищается по нему как раньше)
`BuyerAndPaymentMethodVerifiedDomainEvent` — внутреннее событие создания заказа, не задето — не затрагивается
`OrderStockConfirmedIntegrationEvent` — публикуется как раньше для подтверждённых заказов — не затрагивается
`OrderStockRejectedIntegrationEvent` — публикуется теперь и для снятых с продажи товаров; поля прежние, обработчик order-lifecycle отменяет заказ без изменений — не затрагивается
`OrderStatusChangedToSubmittedIntegrationEvent` — не меняется — не затрагивается
`ProductPriceChangedIntegrationEvent` — смена цены не связана с признаком доступности — не затрагивается
`E-01` создание товара (`CatalogApi.CreateItem`) — `available` = true через инициализатор (задача 1.1)
`E-02` создание при засеве (`CatalogContextSeed.SeedAsync`) — true через инициализатор (задача 1.1)
`E-03…E-07` мок-сервисы ClientApp — true через инициализатор в модели (задача 5.1)
`E-08` копия ClientApp CatalogItem — поле добавляется (задача 5.1)
`E-09` копия WebAppComponents CatalogItem — поле добавляется (задача 4.1)
`E-10`, `E-11` копии seed — покрываются инициализатором (задача 1.1)
`E-12` засев — только в пустую таблицу: новые строки получают true; существующим строкам значение ставит миграция (задача 1.1)
`E-13`, `E-14` модель ИИ — `CatalogItemToString` использует только Name и Description, поле в эмбеддинг не попадает — не затрагивается
`E-15` миграция схемы — новая EF-миграция, колонка `Available` NOT NULL DEFAULT TRUE (задача 1.1)
`Q-001` любой токен Identity — изменение не меняет проверку доступа — не затрагивается
`Q-014` вход и роль для изменений каталога — изменение не опирается: снятие с продажи доступно так же, как остальные правки каталога сейчас; риск «менять может кто угодно» не расширяется этим изменением — не затрагивается
`Q-030` резервирование остатка — не опирается: отказ по недоступности не зависит от резервирования — не затрагивается
`Q-035` данные карты — не задето — не затрагивается
`Q-049` потери сообщений шины — не опирается: при потере события проверки заказ остаётся в AwaitingValidation, как и сейчас; поведение не worsens (см. дизайн, звено 6) — не затрагивается
`Q-058` повтор x-requestid — не задето — не затрагивается
`Q-064` оплата-заглушка — не задето — не затрагивается
`Q-067` UserId из тела — не задето — не затрагивается
`Q-068` ответ 200 при неуспешном создании — не опирается: блокировка витриной происходит до отправки заказа — не затрагивается
`N-01` catalog-semantic-search — выдача поиска не фильтруется (как списки), поле приходит в той же сущности; поведение поиска не меняется — не затрагивается
`N-02` order-lifecycle — получает существующий `OrderStockRejected` и отменяет заказ без изменений кода — не затрагивается
`N-03` order-management — не меняется — не затрагивается
`N-04` order-payment — оплаченные заказы не задеты (недоступность блокирует до оплаты) — не затрагивается
`N-05` order-status-notifications — событие отмены то же — не затрагивается
`N-06` webhook-delivery — события вебхуков не меняются — не затрагивается
Уточняющие вопросы Q-002/Q-003/Q-004 (повторы, неизвестные товары, гонки корзины) — поведение сохранено как в спеках, дельта не опирается на их ответы — не затрагиваются; Q-031 (товар удалён из каталога) — поведение пропуска позиции сохранено (сценарий дельты catalog-stock) — не затрагиваются.

## Открытые вопросы

Все блокирующие вопросы затронутых возможностей (Q-001, Q-014, Q-030, Q-035, Q-049, Q-058, Q-064, Q-067, Q-068) на это изменение не опираются — принятые допущения описаны в карточках, ни одно решение здесь от них не зависит.

Новые вопросы (из решений design R4, R5, R8):

- **[владелец каталога]** Кому можно снимать товары с продажи: сейчас любые правки каталога доступны без входа и роли (Q-014). Это изменение не расширяет права, но операция «снять с продажи» влияет на продажи сильнее правки полей — возможно, для неё нужна роль менеджера и/или отдельный маршрут. До ответа: PUT как остальные правки, без роли.
- **[владелец заказа]** Синхронный ли отказ при создании заказа с недоступным товаром: принято «нет» — заказ может создаться (обход UI витрины) и будет отменён на проверке остатков (R5). Если нужен отказ до создания — потребуется зависимость Ordering.API → Catalog.API (новое решение). До ответа: страховка на AwaitingValidation.
- **[владелец корзины]** Поведение при недоступности Catalog.API при проверке корзины: принято fail-open (замена сохраняется, предупреждение в журнал) — иначе отказ каталога выключает редактирование корзин всем (R4). Альтернатива fail-closed строже, но жёстче по отказам.
- **[владелец мобильного приложения]** Нужна ли мобильной корзине и оформлению витрина-подобная работа с недоступными товарами (пометки, блокировка checkout): принято «нет, минимальный скоуп» — добавление блокировано, заказ отклоняется страховкой остатков и отменяется (R8). Если да — отдельное изменение.
- **[владелец каталога]** Должен ли снятый товар исчезать из витринной выдачи и семантического поиска: принято «не исчезает, показывается как недоступный» (R1). Если «исчезает из выдачи покупателя» — отдельное изменение с обработкой «товар исчез из корзины».

## Impact

- Возможности: `catalog-management`, `catalog-browsing`, `basket`, `storefront`, `catalog-stock` (дельты в `specs/`)
- Код: `src/Catalog.API` (Model/CatalogItem, Apis/CatalogApi, Infrastructure — миграция, IntegrationEvents/EventHandling/OrderStatusChangedToAwaitingValidationIntegrationEventHandler), `src/Basket.API` (Grpc/BasketService + новый клиент каталога), `src/WebApp` (Services/BasketState, Services/BasketItem, Components/Pages/Item/ItemPage, Components/Pages/Cart/CartPage, Components/Pages/Checkout/Checkout), `src/WebAppComponents` (Catalog/CatalogItem), `src/ClientApp` (Models/Catalog/CatalogItem, ViewModels/CatalogItemViewModel)
- Проверка: `tests/Catalog.FunctionalTests/CatalogApiTests.cs`, `tests/Basket.UnitTests/BasketServiceTests.cs`, обработчик catalog-stock (новый тест), e2e `CartTest/CheckoutTest/BrowseItemTest` при поднятом стенде, ручной прогон витрины и мобильного клиента
# Дизайн: Снятие товара с продажи

## Контекст

Сейчас у товара каталога нет признака «снят с продажи»: покупаемость определяется только остатком (`AvailableStock`) на этапе проверки заказа (catalog-stock) и кнопкой витрины. Корзина (Basket.API) принимает любой идентификатор товара без сверки с каталогом (Q-003), витрина при отрисовке корзины и страницы товара уже читает товары из Catalog.API (`GET /api/catalog/items/by?ids=…` в `BasketState.FetchBasketItemsAsync`, `GET /api/catalog/items/{id}` в `ItemPage`), но берёт из ответа только имя и цену. Оформление заказа — `BasketState.CheckoutAsync` шлёт `POST /api/orders` без проверок состава; серверная проверка состава происходит позже, когда заказ уже создан (AwaitingValidation → catalog-stock). Спеки описывают код «как есть, с багами» (Q-002, Q-003, Q-004 — поведение принято как есть).

## Цепочка

Новый сценарий: менеджер снимает товар 7 с продажи; покупатель с товаром 7 в корзине видит его недоступным и не может оформить заказ, пока не удалит.

1. **Менеджер → PUT /api/catalog/items/7 с `available=false`** → `CatalogApi.UpdateItem` → `SetValues` записывает всё тело, включая `available` → ответ 201.
   - **повтор**: тот же PUT дважды — идемпотентно, признак остаётся false.
   - **гонка**: параллельный PUT или списание остатка затирают друг друга целиком (известное ограничение, без версий строк) — `available` при затирании может вернуться в true; принято как существующее поведение.
   - **отказ**: запись не подтвердилась — 500, признак не изменился; событие не публикуется (его и нет) — другие части узнают при следующем чтении.
   - **данные**: поле `available` добавлено в сущность и ответ; копии полей — ClientApp и WebAppComponents модели (задачи 1.3, 4.1), seed (1.2), миграция (1.1).
2. **Покупатель (витрина) открывает страницу товара 7** → `ItemPage.OnInitializedAsync` → `CatalogService.GetCatalogItem` → товар с `available=false` → страница показывает «Unavailable» вместо кнопки.
   - **повтор**: страница перезапрашивает товар при каждом открытии — актуальное состояние.
   - **гонка**: товар снят с продажи между рендером и нажатием «Add to shopping bag» → `BasketState.AddAsync` → Basket.API отклоняет (звено 3) → `RpcException InvalidArgument` → страница ловит и показывает недоступный (задача 4.3).
   - **отказ**: Catalog.API недоступен — HttpRequestException, поведение как сейчас (страница ломается) — не расширяем.
   - **данные**: `available` в ответе хватает.
3. **Покупатель (любой клиент) добавляет товар 7 в корзину** → gRPC `Basket.UpdateBasket` → `BasketService.UpdateBasket` читает текущую корзину из Redis, определяет добавляемые id (нет в текущей корзине) → HTTP `GET catalog-api/api/catalog/items/by?ids=…` → среди добавляемых есть недоступный → `RpcException InvalidArgument` со списком id, корзина не меняется.
   - **повтор**: тот же запрос дважды — обе проверки одинаковы, второй запрос отклонён так же; идемпотентного ключа нет, как и сейчас.
   - **гонка**: две параллельные замены — «последняя запись побеждает» (Q-004, как есть); проверка выполняется до записи, добавление недоступного товара через гонку возможно при почти одновременных обновлениях — подстраховано звеном 6.
   - **отказ**: Catalog.API недоступен → замена выполняется без проверки, предупреждение в журнал (fail-open; решение «R-недоступность каталога») — заказ всё равно заблокирован звеньями 5–6.
   - **данные**: `items/by` возвращает `available` (дельта catalog-browsing); поле доходит вместе с той же сущностью.
4. **Покупатель открывает корзину** → `CartPage` → `BasketState.GetBasketItemsAsync` → `FetchBasketItemsAsync` разрешает позиции через `items/by` → недоступной позиции ставится флаг `Unavailable` → строка с пометкой «Unavailable», только «Remove»; сводка считает только доступные (задача 4.4).
   - **повтор**: состояние вычисляется при каждом чтении — кэш `_cachedBasket` сбрасывается при изменениях; снятие с продажи между чтениями подхватится на новом рендере.
   - **гонка**: параллельное изменение корзины — как есть (Q-004).
   - **отказ**: Catalog.API недоступен — `GetCatalogItems` бросает исключение, страница корзины падает (как сейчас, C-10) — не расширяем.
   - **данные**: флаг вычисляется из `available`; в Basket.API ничего не хранится.
5. **Покупатель нажимает «Place order»** → `Checkout.HandleSubmitAsync` → `PerformCustomValidationAsync` видит недоступные позиции (по `Unavailable`) → сообщение под формой, `CheckoutAsync` не вызывается.
   - **повтор**: повторная отправка — то же сообщение, пока позиция не удалена.
   - **гонка**: товар снят с продажи после валидации формы, но до `CheckoutAsync` → страховка в `BasketState.CheckoutAsync` (задача 4.6): заказ не отправляется.
   - **отказ**: — (локальная проверка).
   - **данные**: флаг `Unavailable` уже в позициях.
6. **Заказ всё же создан (мобильный клиент, обход UI) → Submitted → AwaitingValidation** → событие `OrderStatusChangedToAwaitingValidation` → `OrderStatusChangedToAwaitingValidationIntegrationEventHandler` читает CatalogItem 7: `available=false` → позиция не подтверждена → `OrderStockRejectedIntegrationEvent` → заказ отменяется (существующий обработчик order-lifecycle).
   - **повтор**: событие повторно — как есть (Q-049: повторов нет).
   - **гонка**: возврат товара на продажу параллельно с проверкой — исход зависит от момента чтения; допустимо.
   - **отказ**: Catalog.API недоступен в момент проверки — заказ застревает в AwaitingValidation (как есть, Q-049-смежное).
   - **данные**: событию полей не добавляем — CatalogItem читается по id напрямую.
7. **Мобильный клиент**: добавление товара 7 → тот же gRPC-отказ (звено 3) → `CatalogItemViewModel.AddCatalogItemAsync` ловит `RpcException InvalidArgument` и показывает алерт «товар недоступен» (задача 5.2). Корзина мобильного приложения недоступность не показывает (см. открытый вопрос).

## Решения

- **R1. Признак доступности — новое поле `Available` (bool) на `CatalogItem`, а не отдельная сущность «статусы товара».** Задача — один флаг; статусы, история и расписание публикаций не запрошены. Меняется через существующий PUT (полное замещение) — отдельный маршрут не нужен. Вариант «фильтровать снятые товары из выдачи» отброшен: витрина разрешает позиции корзины через `items/by`, и фильтрация ломала бы корзину и страницы (и потребовала бы обработку «товар исчез»); возврат с `available=false` даёт покупателю объяснение «недоступен» вместо 404.
- **R2. Значение по умолчанию `true` — инициализатором свойства** (`public bool Available { get; set; } = true;`), а не в коде обработчиков: покрывает POST-создание, засев и все конструкторы копий сразу (E-01, E-02, E-03…E-07, E-10, E-11). В EF-конфигурации — `HasDefaultValue(true)`, чтобы миграция проставила true существующим строкам.
- **R3. «Нельзя добавить» enforced на сервере в Basket.API** (дельта basket): проверки только в UI хватило бы витрине, но мобильный ClientApp ходит в Basket по gRPC напрямую — без серверной проверки просьба «нельзя добавить» не выполнялась бы. Проверяются только добавляемые позиции (id нет в текущей корзине): изменение количества и удаление уже лежащих позиций продолжают работать — покупатель может убрать снятый товар и менять остальные. Проверка — HTTP `GET /api/catalog/items/by?ids=…` (новая зависимость Basket.API → Catalog.API, клиент через `AddHttpClient`, адрес `https+http://catalog-api`, без `api-version` — так же, как прокси картинок WebApp). Прото не меняется: ошибка — `RpcException(InvalidArgument)` с текстом-списком id.
- **R4. Недоступность Catalog.API при проверке корзины — fail-open** (замена сохраняется, предупреждение в журнал), а не fail-closed: иначе отказ одного сервиса выключает редактирование корзин всем покупателям. Остаточный риск (добавление недоступного товара во время отказа каталога) закрывается звеном 6 — проверкой остатка на AwaitingValidation.
- **R5. «Нельзя заказать» — на витрине (валидация + страховка в `CheckoutAsync`) плюс серверная страховка в catalog-stock**: Ordering.API новой зависимости на Catalog.API не получает (вариант «синхронная проверка в CreateOrderCommandHandler» отброшен — новая межсервисная связь в цепочке создания заказа и новое место отказа). Если заказ с недоступным товаром всё же создан (мобильный клиент, гонка) — catalog-stock на AwaitingValidation возвращает отказ (`OrderStockRejected`), и существующий обработчик order-lifecycle отменяет заказ: товар не будет оплачен. Отмечено в открытых вопросах (владелец может предпочесть синхронный отказ при создании).
- **R6. Витрина: пометка «Unavailable» + исключение из сводки.** Недоступная позиция показывается с ценой и суммой строки (покупатель видит, что за позиция), но не учитывается в общем количестве и итоге, чтобы сводка не обещала покупку невозможного. Кнопка «Back»… управление количеством скрывается (только «Remove») — совпадает с правкой Basket.API: увеличение количества недоступного разрешено сервером, но UI его не предлагает.
- **R7. События о снятии с продажи нет.** Все потребители вычисляют недоступность чтением каталога в момент действия (лениво). Альтернатива — событие «доступность изменилась» и подписки — не запрошена и не нужна при ленивом чтении; корзина хранит только id и количество, помечать в ней нечего.
- **R8. Мобильный ClientApp — минимальный скоуп**: поле в модели (по умолчанию true), блок добавления со страницы товара и алерт при отказе обновления корзины. Корзина и оформление мобильного приложения недоступность не показывают (вне просьбы; серверные страховки — звенья 3 и 6 — не дают купить): вынесено в открытые вопросы.

## Данные и контракты

**Сущность `CatalogItem` (src/Catalog.API/Model/CatalogItem.cs)** — было → стало:
- было: полей нет о продажности; стало: `public bool Available { get; set; } = true;` (JSON `available`).
- создаётся: `CatalogApi.CreateItem` — инициализатор даёт true (E-01); `CatalogContextSeed.SeedAsync` — true (E-02, E-10, E-11); мок-сервисы клиентов — инициализатор в их моделях (E-03…E-07, задачи 1.3, 5.1).
- копии полей: `CatalogItem` (src/WebAppComponents/Catalog/CatalogItem.cs — задача 4.1), `CatalogItem` (src/ClientApp/Models/Catalog/CatalogItem.cs — задача 5.1); `CatalogContextSeed`/`CatalogSourceEntry` — инициализатор (E-10, E-11, задача 1.2).
- миграция (E-15): EF-миграция `AddCatalogItemAvailable`, колонка `Available` bit NOT NULL DEFAULT TRUE — существующие товары остаются в продаже; снимок схемы сверить.
- модель ИИ (E-13, E-14): `CatalogItemToString` строит строку из `Name` и `Description` (src/Catalog.API/Services/CatalogAI.cs:75) — поле в эмбеддинг не попадает, задача не нужна.

**Вход `PUT /api/catalog/items/{id}` (и v1-вариант)** — было: тело без `available`; стало: `available` записывается как передано. Обратно совместимо: старые тела без поля дают `available=true` (полное замещение, как для остальных полей) — задокументировано сценарием дельты catalog-management.

**Входы GET каталога** — было: ответ без `available`; стало: поле во всех ответах с товарами. Совместимо: клиенты читают часть полей; `HybridApp` и витрина используют source-generated/дефолтный JSON-биндинг — новое поле биндится по имени, старые клиенты его игнорируют.

**Вход `grpc:Basket.UpdateBasket`** — было: любая замена сохраняется; стало: замена с добавлением недоступного товара отклоняется `InvalidArgument` (перечень id в тексте). Прото не меняется. Клиенты: WebApp — ловит только на странице товара (задача 4.3), CartPage отклонений не вызывает (добавления недоступного блокирует UI до gRPC); ClientApp — `CatalogItemViewModel.AddCatalogItemAsync` ловит и показывает алерт (задача 5.2); `BasketViewModel.DeleteAsync`/`AddBasketItemAsync` — удаления проходят, добавления уже лежащих позиций проходят.

**События** — не меняются: поля `OrderStartedIntegrationEvent`, `OrderStockRejectedIntegrationEvent` и остальных хватает (копий и подписчиков не добавляем; звено 6 использует существующий отказ).

**Мобильная корзина и checkout (`ClientApp`)** — не меняются: недоступность в корзине мобильного клиента не показывается (R8, открытый вопрос).

## Риски

- **Конкурентность**: изменения товара и корзин без версий строк («последняя запись побеждает», data.md). PUT товара параллельно с другим PUT может потерять `available=false`; проверка корзины и замена корзины не атомарны — недоступный товар может попасть в корзину через гонку. Обе щели закрыты страховкой звена 6 (отказ на AwaitingValidation), полное устранение требует версионирования — вне скоупа.
- **Выкатка**: поле добавляется с дефолтом true — старые клиенты (читают часть полей) не ломаются; `InvalidArgument` на UpdateBasket — новая ветка ошибки: витрина и мобильный клиент получают обработчики в этом же изменении (задачи 4.3, 5.2); прочие gRPC-клиенты корзины в системе не обнаружены (карточка basket: ClientApp и WebApp).
- **События в полёте**: заказ, созданный до выкатки с товаром, снятым с продажи после создания, отклоняется проверкой остатков уже после выкатки — заказ отменится корректно, покупатель увидит отмену (order-status-notifications — без изменений, событие то же).
- **Откат**: миграция аддитивная (колонка с дефолтом); откат — убрать поле из кода и миграцию вниз. Несовместимости данных нет.
- **PUT без поля `available` возвращает товар на продажу** — свойство полного замещения, известное для всех полей; менеджеру нужно слать полное тело (см. сценарий дельты catalog-management). Если владелец сочтёт опасным — отдельное изменение «частичный PATCH».

## Проверка

- **Catalog.FunctionalTests** (`tests/Catalog.FunctionalTests/CatalogApiTests.cs`): создание — `available=true`; PUT с `available=false` — сохранён и возвращён; PUT без поля — true; `items/by` и списки отдают `available=false` и не фильтруют.
- **Basket.UnitTests** (`tests/Basket.UnitTests/BasketServiceTests.cs`): подставной HTTP-обработчик CatalogClient — добавление недоступного отклоняется `InvalidArgument` с id в тексте; замена без добавления недоступных проходит; корзина со снятым товаром внутри изменяется и очищается от него; отказ каталога — замена сохраняется.
- **Витрина (ручной прогон + e2e, где есть)**: страница снятого товара — «Unavailable» без кнопки; корзина — пометка, только «Remove», сводка без недоступных; checkout — сообщение и заказ не отправляется; удаление недоступной позиции возвращает оформление. e2e: `e2e/CartTest.spec.ts`, `e2e/CheckoutTest.spec.ts`, `e2e/BrowseItemTest.spec.ts` — дополнить сценариями, если стенд поднимается.
- **catalog-stock**: юнит/функциональный тест обработчика — `available=false` даёт отказ при достаточном остатке.
- **Мобильный**: страница товара со снятым — алерт/нет добавления (проверка вручную на эмуляторе, автотестов на UI в репо нет).
## 1. Данные и контракты

- [ ] 1.1 Поле признака доступности на товаре — `src/Catalog.API/Model/CatalogItem.cs`: свойство `public bool Available { get; set; } = true;` (JSON `available`); `src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs`: `HasDefaultValue(true)`; новая EF-миграция в `src/Catalog.API/Infrastructure/Migrations` (`dotnet ef migrations add AddCatalogItemAvailable`) — колонка `Available` bit NOT NULL, значение по умолчанию true, снимок схемы сверить. Готово, когда: новые товары создаются с `available=true` (требование «Снятие товара с продажи и возврат на продажу», сценарий «Новый товар создаётся доступным»), существующие строки в БД после миграции `Available=true`.
- [ ] 1.2 Функциональные тесты каталога — `tests/Catalog.FunctionalTests/CatalogApiTests.cs`: добавить сценарии — POST без `available` даёт true; PUT с `available=false` сохраняет и возвращает false; PUT без поля после снятия возвращает true; `GET /items`, `GET /items/{id}`, `GET /items/by?ids=` отдают `available=false` и не фильтруют снятый товар (требования «Снятие товара с продажи и возврат на продажу», «Признак доступности товара в ответах»). Готово, когда: тесты зелёные, включая сценарии «Менеджер снимает товар с продажи», «Менеджер возвращает товар на продажу», «Поле `available` не передано в теле PUT», «Снятый товар в списке», «Снятый товар по идентификатору», «Снятый товар в списке по идентификаторам».

## 2. Поведение

- [ ] 2.1 Клиент Catalog.API в Basket.API — новый файл `src/Basket.API/Services/CatalogClient.cs` (метод `GetItemsByIdsAsync(int[] ids)` → `GET {catalog-api}/api/catalog/items/by?ids=…`, разбор `available`), регистрация `AddHttpClient` с базовым адресом `https+http://catalog-api` и таймаутом ~5 секунд — `src/Basket.API/Extensions/Extensions.cs` (`AddApplicationServices`). Готово, когда: клиент возвращает товары с признаком доступности; адрес резолвится сервис-дискавери Aspire (без `api-version`, как прокси картинок WebApp).
- [ ] 2.2 Проверка добавляемых позиций — `src/Basket.API/Grpc/BasketService.cs` (`BasketService.UpdateBasket`): перед сохранением прочитать текущую корзину `repository.GetBasketAsync(userId)`, вычислить добавляемые id (нет в текущей корзине); для них вызвать каталог; если у какого-то `available=false` — бросить `RpcException(new Status(StatusCode.InvalidArgument, "Products unavailable: {id, …}"))`, корзину не менять. Позиции, уже лежащие в корзине, не проверяются. `HttpRequestException`/таймаут каталога — записать `LogWarning` и продолжить без проверки (требование «Полная замена корзины»). Готово, когда: сценарии «Добавление снятого с продажи товара», «Изменение корзины, где уже лежит снятый товар», «Каталог недоступен при проверке» выполняются по дельте basket.
- [ ] 2.3 Тесты проверки корзины — `tests/Basket.UnitTests/BasketServiceTests.cs`: подставной `HttpMessageHandler` для `CatalogClient`. Готово, когда: добавление недоступного товара отклоняется `InvalidArgument` с id в тексте и корзина не меняется; замена без добавления проходит; отказ каталога даёт успешную замену и запись в журнале.
- [ ] 2.4 Отказ по недоступности на проверке остатков — `src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToAwaitingValidationIntegrationEventHandler.cs` (`Handle`): при `catalogItem.Available == false` формировать `ConfirmedOrderStockItem` с `hasStock = false` независимо от остатка (требование «Проверка остатка при ожидании проверки заказа»). Готово, когда: сценарий «Товар снят с продажи» дельты catalog-stock — заказ с недоступным товаром получает `OrderStockRejected` при достаточном остатке.

## 3. Вызывающие и подписчики

- [ ] 3.1 Модель товара витрины — `src/WebAppComponents/Catalog/CatalogItem.cs`: параметр `bool Available = true` в record. Готово, когда: `available` из ответа каталога биндится в модель (в т.ч. в HybridApp через тот же тип), отсутствие поля не ломает биндинг.
- [ ] 3.2 Модель товара мобильного клиента — `src/ClientApp/Models/Catalog/CatalogItem.cs`: свойство `public bool Available { get; set; } = true;`. Готово, когда: мок-сервисы (`CatalogMockService`) без изменений дают доступный товар, JSON `available` биндится.
- [ ] 3.3 Позиция корзины витрины помечается недоступной — `src/WebApp/Services/BasketItem.cs`: свойство `bool Unavailable`; `src/WebApp/Services/BasketState.cs` (`BasketState.FetchBasketItemsAsync`): `Unavailable = !catalogItem.Available`. Готово, когда: корзина со снятым товаром даёт позицию с `Unavailable=true` (требование «Недоступный товар в корзине»).
- [ ] 3.4 Страница товара — `src/WebApp/Components/Pages/Item/ItemPage.razor`: при `!item.Available` показывать «Unavailable» вместо кнопки «Add to shopping bag» и не отправлять форму; в `AddToCartAsync` ловить `RpcException` со статусом `InvalidArgument` — повторно запросить товар и показать как недоступный (требование «Добавление товара в корзину со страницы товара», сценарий «Товар снят с продажи»). Готово, когда: снятый товар не добавляется в корзину со страницы, гонка «снятие после загрузки» завершается пометкой «Unavailable», а не необработанным исключением.
- [ ] 3.5 Корзина витрины — `src/WebApp/Components/Pages/Cart/CartPage.razor`: у позиции с `Unavailable` — пометка «Unavailable», без степпера количества (кнопки «+»/«−» и поле скрыты), кнопка «Remove» работает; в сводке `TotalQuantity`/`TotalPrice` считать только доступные позиции (требование «Недоступный товар в корзине»). Готово, когда: сценарии «Пометка недоступной позиции», «Недоступные позиции не входят в сводку», «Удаление недоступной позиции» выполняются.
- [ ] 3.6 Оформление витрины — `src/WebApp/Components/Pages/Checkout/Checkout.razor` (`PerformCustomValidationAsync`): если среди позиций есть `Unavailable` — сообщение под формой «удалите недоступные товары», форму не отправлять (требование «Оформление заказа из корзины», сценарий «В корзине недоступный товар»). Готово, когда: заказ не уходит в Ordering API и показано сообщение, пока в корзине недоступная позиция.
- [ ] 3.7 Страховка оформления — `src/WebApp/Services/BasketState.cs` (`BasketState.CheckoutAsync`): перед `orderingService.CreateOrder` при наличии `Unavailable` позиций бросить исключение — заказ не отправляется (требование «Оформление заказа из корзины»). Готово, когда: вызов `CheckoutAsync` с недоступной позицией не порождает `POST /api/orders` (гонка «снятие после валидации формы»).
- [ ] 3.8 Мобильная страница товара — `src/ClientApp/ViewModels/CatalogItemViewModel.cs` (`AddCatalogItemAsync`): при `!CatalogItem.Available` показать алерт через `IDialogService.ShowAlertAsync` (добавить в конструктор; зарегистрирован в `MauiProgram.cs:76`) и выйти; обернуть `UpdateBasketAsync` в try/catch `RpcException` со статусом `InvalidArgument` — тот же алерт. Готово, когда: снятый товар не добавляется, отказ корзины показывает алерт вместо необработанного исключения.

## 4. Проверка

- [ ] 4.1 Прогнать модульные и функциональные тесты затронутых возможностей: `tests/Basket.UnitTests`, `tests/Basket.FunctionalTests`, `tests/Catalog.FunctionalTests`, `tests/Application.UnitTests` (`CatalogAITests` — убедиться, что эмбеддинг не изменился), `tests/Ordering.UnitTests`, `tests/Ordering.FunctionalTests` (не должны сломаться: контракты заказов не менялись). Готово, когда: все зелёные.
- [ ] 4.2 e2e витрины при поднятом стенде — `e2e/CartTest.spec.ts`, `e2e/CheckoutTest.spec.ts`, `e2e/BrowseItemTest.spec.ts`: снять товар с продажи через PUT и проверить «Unavailable» на странице товара, пометку в корзине, блокировку checkout и оформление после удаления позиции. Если стенд недоступен — ручной прогон по разделу «Проверка» design.md и пометка в отчёте.
- [ ] 4.3 Проверить мобильный клиент вручную (эмулятор) — точки из задач 3.2, 3.8 (`src/ClientApp/ViewModels/CatalogItemViewModel.cs`, `BasketViewModel.cs`): страница товара со снятым — алерт, корзина без пометок, заказ с недоступной позицией отменяется после AwaitingValidation (проверка на стенде с шиной). Готово, когда: необработанных исключений нет.

## 5. Слой контекста

- [ ] 5.1 Обновить `system-context/trace.md`: строки изменённых и новых требований → код и тесты (catalog-management, catalog-browsing, basket, storefront, catalog-stock)
- [ ] 5.2 Пересобрать слой, если установлен sa-scan: `contracts.py scan .` и `plan.py guide .` (иначе — пункт в отчёте); `check.py .` без ошибок
# Влияние изменения `delist-catalog-item`

Собрано `change.py analyze` из слоя sa-scan. Затронуто: возможности `basket`, `catalog-management`, `catalog-browsing`, `storefront`, `order-placement`, `catalog-stock`; входы http:PUT /api/catalog/items/{id}, grpc:Basket.UpdateBasket, http:POST /api/orders, ui:/cart, ui:/item/{itemId}; сущности CatalogItem.
У каждого пункта — **Решение**: `задача N.N` (номер из tasks.md, можно несколько) или `не затрагивается: <почему>`.
Для вопросов [блокирует]: изменение на него не опирается — `не затрагивается: <почему>`; опирается — `ответ: …` (человек ответил)
или `в proposal: <что принято до ответа>` (тогда вопрос — в «Открытые вопросы» proposal и в чат).
Повторный `analyze` обновит пункты и сохранит решения. Пункты, которых нет в слое, добавь сам в конце с буквой X (X-01…).


## Кто вызывает затронутые входы

- [ ] C-01 `src/ClientApp → /api/catalog` — клиентское приложение <!-- key: caller:src/ClientApp → /api/catalog -->
  - опирается на: читает ответ `GET items` как `CatalogRoot` — поля `Data`, `PageIndex`, `PageSize`, `Count` (src/ClientApp/Models/Catalog/CatalogRoot.cs) и `CatalogItem` с `PictureUri` (src/ClientApp/Models/Catalog/CatalogItem.cs:9); сервер такого поля не отдаёт (только `PictureFileName`), поэтому картинку клиент строит сам: `{шлюз}/api/catalog/items/{id}/pic` (src/ClientApp/Services/FixUri/FixUriService.cs:36). Версия API зашита `api-version=2.0` (src/ClientApp/Services/Catalog/CatalogService.cs:12). Фильтр шлёт одиночные `type`/`brand` и путь с двойным слэшем `//items` (CatalogService.cs:29). Статусов не сравнивает: ошибка HTTP исключением уходит в вызывающего, пустой ответ превращается в пустой список (Ca
  - где: src/ClientApp/Services/Catalog/CatalogService.cs:11, src/ClientApp/Services/FixUri/FixUriService.cs:36
  - **Решение:** задача 3.2
- [ ] C-02 `src/HybridApp → /api/catalog` — клиентское приложение <!-- key: caller:src/HybridApp → /api/catalog -->
  - опирается на: `GetFromJsonAsync` с camelCase-контекстом (src/HybridApp/Services/CatalogService.cs:16, 22; контекст src/HybridApp/Services/CatalogJsonContext.cs:13) в типы `CatalogItem`, `CatalogResult`, `CatalogBrand[]`, `CatalogItemType[]` из WebAppComponents. Всегда `api-version=2.0` (CatalogService.cs:15, 22, 28, 35, 42, 49); пути `items/{id}`, `items/by?ids=`, `items/withsemanticrelevance?text=`, `catalogBrands`, `catalogTypes`. Статусы не обрабатывает — любой не-2xx бросает `HttpRequestException`; `result!` без проверки на null (CatalogService.cs:23). Сломается при: смене имён полей JSON (source-generated контекст не примет неизвестные формы), снятии версии 2.0, смене формы `withsemanticrelevance` (к
  - где: src/HybridApp/Services/CatalogService.cs:10
  - **Решение:** не затрагивается: новое поле биндится по имени через общий тип WebAppComponents (задача 3.1), неизвестных форм JSON нет
- [ ] C-03 `src/WebApp → /api/catalog` <!-- key: caller:src/WebApp → /api/catalog -->
  - опирается на: не вызывает API сам — только проксирует картинки: `/product-images/{id}` → `catalog-api` `/api/catalog/items/{id}/pic` (src/WebApp/Program.cs:32), без `api-version`. Каталог WebApp читает через WebAppComponents (см. ниже), клиент зарегистрирован с `AddApiVersion(2.0)` (src/WebApp/Extensions/Extensions.cs:34-36). Сломается при: смене маршрута `/pic` — все картинки витрины (`IProductImageUrlProvider`) перестанут грузиться.
  - где: src/WebApp/Program.cs:32
  - **Решение:** не затрагивается: WebApp ходит в каталог только прокси картинок, маршруты не меняются
- [ ] C-04 `src/WebAppComponents → /api/catalog` <!-- key: caller:src/WebAppComponents → /api/catalog -->
  - опирается на: общий клиент каталога витрины, который использует WebApp. Читает `CatalogResult(PageIndex, PageSize, Count, Data)` и `CatalogItem(Id, Name, Description, Price, PictureUrl, CatalogBrandId, CatalogBrand, CatalogTypeId, CatalogType)` (src/WebAppComponents/Catalog/CatalogItem.cs:3-17). Страница каталога делит `Count` на размер страницы 9 для пагинации (src/WebApp/Components/Pages/Catalog/Catalog.razor:93, 151), карточка показывает `Name`, `Price`, `CatalogBrand.Brand` (src/WebAppComponents/Catalog/CatalogListItem.razor:6-18). Страница товара ловит именно `404` от `GET items/{id}` и отдаёт 404 пользователю (src/WebApp/Components/Pages/Item/ItemPage.razor:117-120) — другой код (400, 500) станет не
  - где: src/WebAppComponents/Services/CatalogService.cs:9
  - **Решение:** задача 3.1
- [ ] C-05 `src/eShop.AppHost → /api/catalog` <!-- key: caller:src/eShop.AppHost → /api/catalog -->
  - опирается на: это конфигурация шлюза мобильного BFF (YARP): список маршрутов каталога с обязательным `api-version` (запрос без параметра или с другим значением до каталога не дойдёт — 404 шлюза): `items`, `items/by`, `items/{id}`, `{id}/pic`, `catalogTypes`, `catalogBrands` — 1.0/1/2.0; `items/by/{name}`, `items/type/...` и `withsemanticrelevance/{text}` — только 1.0/1; `withsemanticrelevance` — только 2.0 (src/eShop.AppHost/Extensions.cs:106-148); общий `/api/catalog/{*any}` (151). Сломается при: переименовании путей или версий в Catalog.API — шлюз отфильтрует их раньше сервиса; новый маршрут или версия требуют строки здесь.
  - где: src/eShop.AppHost/Extensions.cs:106
  - **Решение:** не затрагивается: новых маршрутов и версий каталога нет
- [ ] C-06 `src/ClientApp → /api/orders` — клиентское приложение <!-- key: caller:src/ClientApp → /api/orders -->
  - опирается на: только версия 1.0 (`api-version=1.0`, src/ClientApp/Services/Order/OrderService.cs:14). Страница заказа читает `Order` с JSON-именами `status`, `ordernumber`, `date`, `total`, `items`, `city`, `street`, `state`, `country`, `zipCode` (src/ClientApp/Models/Orders/Order.cs:13-50); сервер отдаёт `Status`, `OrderNumber`, `Zipcode`, `OrderItems` (src/Ordering.API/Application/Queries/OrderViewModel.cs:12-23): `status`, `ordernumber`, `zipCode` совпадают только без учёта регистра, а `items` клиента и `OrderItems` сервера различаются по имени — список позиций на клиенте может не заполняться. Кнопка «CANCEL ORDER» видна только когда `status` равен `Submitted` без учёта регистра (src/ClientApp/ViewMode
  - где: src/ClientApp/Services/Order/OrderService.cs:13
  - **Решение:** не затрагивается: контракт оформления прежний; заказ с недоступным товаром отклоняется на проверке остатков (задача 2.4), правки клиента не нужны
- [ ] C-07 `src/WebApp → /api/orders` <!-- key: caller:src/WebApp → /api/orders -->
  - опирается на: `GET api/Orders/` в `OrderRecord(OrderNumber, Date, Status, Total)` (src/WebApp/Services/OrderingService.cs:9, 21-25) — форма `OrderSummary` сервера; список заказов выводит их и строит CSS-класс из `Status.ToLower()` (src/WebApp/Components/Pages/User/Orders.razor:48-52), то есть новый статус без CSS-класса отрисуется без стиля. `POST` создания заказа шлёт `x-requestid` и тело `CreateOrderRequest` (OrderingService.cs:12-18); ответ не проверяется, `EnsureSuccess` нет — а сервер на невалидный заказ всё равно отвечает 200 (см. заметку под `POST /api/orders`). Версия 1.0 через `AddApiVersion(1.0)` (src/WebApp/Extensions/Extensions.cs:38-40). Сломается при: переименовании `OrderNumber`/`Status`/`T
  - где: src/WebApp/Services/OrderingService.cs:5
  - **Решение:** задача 3.6, 3.7
- [ ] C-08 `src/eShop.AppHost → /api/orders` <!-- key: caller:src/eShop.AppHost → /api/orders -->
  - опирается на: конфигурация шлюза: `/api/orders/{*any}` → ordering-api, пропускает только `api-version` 1.0/1 (src/eShop.AppHost/Extensions.cs:155-156); авторизация — на стороне сервиса (`RequireAuthorization`). Сломается при: выпуске v2 заказов — шлюз его не пропустит, пока не поменять значения здесь.
  - где: src/eShop.AppHost/Extensions.cs:155
  - **Решение:** не затрагивается: маршруты и версии заказов не меняются
- [ ] C-09 `src/ClientApp → gRPC Basket` — клиентское приложение <!-- key: caller:src/ClientApp → gRPC Basket -->
  - опирается на: мобильное приложение ходит в Basket по gRPC напрямую с bearer-токеном в метаданных (src/ClientApp/Services/Basket/BasketService.cs:46, 84, 108). Читает `CustomerBasketResponse.Items` → `ProductId`, `Quantity` (BasketService.cs:50-53, 91-94) — больше ничего (название, цена в корзине берутся не отсюда). `GetBasket` при любом исключении печатает его и возвращает `null` корзину (BasketService.cs:56-60), `UpdateBasket` ошибки не ловит. Без токена методы тихо ничего не делают (BasketService.cs:38, 70, 103). Сломается при: смене номеров полей и имён в `basket.proto`, замене `repeated items`, добавлении обязательной авторизации в `GetBasket` (сейчас он `AllowAnonymous` и для анонима отдаёт пустую ко
  - где: src/ClientApp/Services/Basket/BasketService.cs:18, src/ClientApp/Services/Basket/Protos/BasketGrpc.cs:90
  - **Решение:** задача 3.8
- [ ] C-10 `src/WebApp → gRPC Basket` <!-- key: caller:src/WebApp → gRPC Basket -->
  - опирается на: gRPC-клиент `Basket.BasketClient` на `http://basket-api` с проброшенным токеном пользователя (src/WebApp/Extensions/Extensions.cs:31-32). Читает `Items` → `ProductId`, `Quantity` (src/WebApp/Services/BasketService.cs:40-43); шлёт `UpdateBasketRequest.Items` с теми же двумя полями (34-35). Цена и название в корзине в gRPC не передаются: страница корзины и чат берут их из каталога по `ProductId` (`BasketState` собирает `BasketItem` с `ProductName`, `UnitPrice` из каталога — src/WebApp/Services/BasketItem.cs:5-10). Ошибки: страница `CartMenu` ловит `HttpRequestException` со статусом `401` и выходит из сессии (src/WebApp/Components/Layout/CartMenu.razor:45-48); чат различает gRPC `Unauthenticate
  - где: src/WebApp/Extensions/Extensions.cs:31, src/WebApp/Services/BasketService.cs:3
  - **Решение:** задача 3.4

## События: публикуемые и названные

- [ ] S-01 `OrderStartedIntegrationEvent` <!-- key: event:OrderStartedIntegrationEvent -->
  - поля: UserId string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Basket.API/IntegrationEvents/EventHandling/OrderStartedIntegrationEventHandler.cs:6 (обработчик интеграционного события → OrderStartedIntegrationEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - заметки: Заметки: публикуется внутри доменного обработчика старта заказа; Basket по нему очищает корзину пользователя. Поле только `UserId`.
  - **Решение:** не затрагивается: поле UserId хватает, очистка корзины по событию не меняется
- [ ] S-02 `BuyerAndPaymentMethodVerifiedDomainEvent` (внутреннее) <!-- key: event:BuyerAndPaymentMethodVerifiedDomainEvent -->
  - поля: Buyer Buyer, Payment PaymentMethod, OrderId int
  - подписаны: src/Ordering.API/Application/DomainEventHandlers/UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler.cs:3 (MediatR → UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: внутренняя цепочка создания заказа не меняется
- [ ] S-03 `OrderStockConfirmedIntegrationEvent` <!-- key: event:OrderStockConfirmedIntegrationEvent -->
  - поля: OrderId int
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderStockConfirmedIntegrationEventHandler.cs:3 (обработчик интеграционного события → OrderStockConfirmedIntegrationEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: публикуется как раньше для подтверждённых заказов
- [ ] S-04 `OrderStockRejectedIntegrationEvent` <!-- key: event:OrderStockRejectedIntegrationEvent -->
  - поля: OrderId int, OrderStockItems List<ConfirmedOrderStockItem>
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Ordering.API/Application/IntegrationEvents/EventHandling/OrderStockRejectedIntegrationEventHandler.cs:2 (обработчик интеграционного события → OrderStockRejectedIntegrationEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** задача 2.4
- [ ] S-05 `OrderStatusChangedToSubmittedIntegrationEvent` <!-- key: event:OrderStatusChangedToSubmittedIntegrationEvent -->
  - поля: OrderId int, OrderStatus OrderStatus, BuyerName string, BuyerIdentityGuid string
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/WebApp/Services/OrderStatus/IntegrationEvents/EventHandling/OrderStatusChangedToSubmittedIntegrationEventHandler.cs:5 (обработчик интеграционного события → OrderStatusChangedToSubmittedIntegrationEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - **Решение:** не затрагивается: поля и подписчик не меняются
- [ ] S-06 `ProductPriceChangedIntegrationEvent` <!-- key: event:ProductPriceChangedIntegrationEvent -->
  - поля: ProductId int, NewPrice decimal, OldPrice decimal
  - копий определения: 2 — новое поле добавлять во все
  - подписаны: src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs:3 (обработчик интеграционного события → ProductPriceChangedIntegrationEventHandler)
  - проверь в «Цепочке»: хватит ли этих полей новому поведению? Не хватает — задача на событие и его издателя, а не «не затрагивается»
  - заметки: Заметки: единственный подписчик — Webhooks, и его обработчик пустой (`Task.CompletedTask`, src/Webhooks.API/IntegrationEvents/ProductPriceChangedIntegrationEventHandler.cs:5-8): событие никого не уведомляет. Корзина (Basket) на изменение цены не подписана.
  - **Решение:** не затрагивается: смена цены не связана с признаком доступности

## Сущности: где поле потеряется молча

- [ ] E-01 `CatalogItem` создаётся: `CatalogApi.CreateItem` src/Catalog.API/Apis/CatalogApi.cs:419 <!-- key: create:CatalogItem:`CatalogApi.CreateItem` src/Catalog.API/Apis/CatalogApi.cs:419 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 1.1
- [ ] E-02 `CatalogItem` создаётся: `CatalogContextSeed.SeedAsync` src/Catalog.API/Infrastructure/CatalogContextSeed.cs:48 <!-- key: create:CatalogItem:`CatalogContextSeed.SeedAsync` src/Catalog.API/Infrastructure/CatalogContextSeed.cs:48 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 1.1
- [ ] E-03 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:16 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:16 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 3.2
- [ ] E-04 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:28 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:28 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 3.2
- [ ] E-05 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:40 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:40 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 3.2
- [ ] E-06 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:52 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:52 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 3.2
- [ ] E-07 `CatalogItem` создаётся: `CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:64 <!-- key: create:CatalogItem:`CatalogMockService` src/ClientApp/Services/Catalog/CatalogMockService.cs:64 -->
  - новое поле здесь не заполнится само
  - **Решение:** задача 3.2
- [ ] E-08 `CatalogItem` → копия `CatalogItem` (src/ClientApp/Models/Catalog/CatalogItem.cs:3) <!-- key: copy:CatalogItem:CatalogItem:src/ClientApp/Models/Catalog/CatalogItem.cs -->
  - общих полей 8 из 9, нет: availablestock, embedding, maxstockthreshold, onreorder, picturefilename, restockthreshold
  - **Решение:** задача 3.2
- [ ] E-09 `CatalogItem` → копия `CatalogItem` (src/WebAppComponents/Catalog/CatalogItem.cs:3) <!-- key: copy:CatalogItem:CatalogItem:src/WebAppComponents/Catalog/CatalogItem.cs -->
  - общих полей 8 из 9, нет: availablestock, embedding, maxstockthreshold, onreorder, picturefilename, restockthreshold
  - **Решение:** задача 3.1
- [ ] E-10 `CatalogItem` → копия `CatalogContextSeed` (src/Catalog.API/Infrastructure/CatalogContextSeed.cs:7) <!-- key: copy:CatalogItem:CatalogContextSeed:src/Catalog.API/Infrastructure/CatalogContextSeed.cs -->
  - общих полей 4 из 6, нет: availablestock, catalogbrand, catalogbrandid, catalogtype, catalogtypeid, embedding
  - **Решение:** задача 1.1
- [ ] E-11 `CatalogItem` → копия `CatalogSourceEntry` (src/Catalog.API/Infrastructure/CatalogContextSeed.cs:77) <!-- key: copy:CatalogItem:CatalogSourceEntry:src/Catalog.API/Infrastructure/CatalogContextSeed.cs -->
  - общих полей 4 из 6, нет: availablestock, catalogbrand, catalogbrandid, catalogtype, catalogtypeid, embedding
  - **Решение:** задача 1.1
- [ ] E-12 `CatalogItem` засев: src/Catalog.API/Infrastructure/CatalogContextSeed.cs (только в пустую таблицу) <!-- key: seed:CatalogItem:src/Catalog.API/Infrastructure/CatalogContextSeed.cs (только в пустую таблицу) -->
  - засев только в пустую таблицу — существующим данным нужна миграция данных
  - **Решение:** задача 1.1
- [ ] E-13 `CatalogItem` уходит в модель ИИ: src/Catalog.API/Services/CatalogAI.cs:40 <!-- key: ai:CatalogItem:src/Catalog.API/Services/CatalogAI.cs:40 -->
  - новое поле может попасть в промпт или эмбеддинг само
  - **Решение:** не затрагивается: CatalogItemToString строит строку только из Name и Description (CatalogAI.cs:75), поле в текст эмбеддинга не попадает
- [ ] E-14 `CatalogItem` уходит в модель ИИ: src/Catalog.API/Services/CatalogAI.cs:75 <!-- key: ai:CatalogItem:src/Catalog.API/Services/CatalogAI.cs:75 -->
  - новое поле может попасть в промпт или эмбеддинг само
  - **Решение:** не затрагивается: CatalogItemToString строит строку только из Name и Description (CatalogAI.cs:75), поле в текст эмбеддинга не попадает
- [ ] E-15 `CatalogItem` миграция схемы: src/Catalog.API/Infrastructure/Migrations: миграций 3, последние: 20231018163051_RemoveHiLoAndIndexCatalogName.cs, 20231026091140_Outbox.cs; схема или снимок: s <!-- key: migr:CatalogItem -->
  - новая миграция, снимок схемы сверить с моделью
  - **Решение:** задача 1.1

## Блокирующие вопросы затронутых возможностей — опирается ли на них изменение?

- [ ] Q-001 [блокирует] Должны ли API принимать любой токен Identity — аудитория и scope не проверяются? <!-- key: q:Q-001 -->
  - допущение: принимается любой токен Identity, как в коде
  - статус: открыт
  - **Решение:** не затрагивается: изменение не меняет проверку доступа и не опирается на её результат
- [ ] Q-014 [блокирует] Должны ли изменения каталога требовать вход и роль? <!-- key: q:Q-014 -->
  - допущение: как в коде: изменения доступны без проверки аутентификации и роли
  - статус: открыт
  - **Решение:** не затрагивается: снятие с продажи выполняется тем же PUT, чьи права этим изменением не меняются; нужен ли отдельный доступ на снятие — новый вопрос в proposal
- [ ] Q-030 [блокирует] Нужно ли резервировать остаток между проверкой и оплатой? <!-- key: q:Q-030 -->
  - допущение: как в коде и комментарии: остаток не резервируется; два заказа могут пройти проверку на один и тот же остаток, а при оплате второй получит частичное списание или ошибку
  - статус: открыт
  - **Решение:** не затрагивается: отказ по недоступности не зависит от резервирования остатка
- [ ] Q-035 [блокирует] Данные карты (номер, код безопасности) попадают в токены и журналы — допустимо? <!-- key: q:Q-035 -->
  - допущение: код безопасности и номер карты передаются клиентам, как в коде
  - статус: открыт
  - **Решение:** не затрагивается: данные карты не задеты
- [ ] Q-049 [блокирует] Шина подтверждает сообщение даже при ошибке обработки — без повтора и очереди ошибок: так задумано? <!-- key: q:Q-049 -->
  - допущение: событие теряется, заказ остаётся в AwaitingValidation, как в коде
  - статус: открыт
  - **Решение:** не затрагивается: изменение не опирается на доставку шины; потеря события проверки оставляет заказ в AwaitingValidation, как и сейчас
- [ ] Q-058 [блокирует] Повтор с тем же x-requestid после неудачи должен повторить действие? <!-- key: q:Q-058 -->
  - допущение: спека описывает код: повтор после неудачи даёт 200 и не выполняет команду
  - статус: открыт
  - **Решение:** не затрагивается: идемпотентность создания заказа не меняется
- [ ] Q-064 [блокирует] Оплата — заглушка (исход из настроек, фиксированная тестовая карта): какой будет реальная оплата? <!-- key: q:Q-064 -->
  - допущение: оплата имитируется, внешний платёжный шлюз не используется и не описан
  - статус: открыт
  - **Решение:** не затрагивается: платёжные данные не задеты
- [ ] Q-067 [блокирует] Должен ли сервер брать UserId покупателя из токена, а не из тела запроса? <!-- key: q:Q-067 -->
  - допущение: заказ создаётся на UserId из тела, как написано в коде
  - статус: открыт
  - **Решение:** не затрагивается: источник UserId не меняется
- [ ] Q-068 [блокирует] Создание заказа не сообщает об ошибке: API отвечает 200, витрина очищает корзину без заказа — так задумано? <!-- key: q:Q-068 -->
  - допущение: клиент видит успех при любом исходе, как в коде; витрина по этому ответу удаляет корзину (src/WebApp/Services/BasketState.cs, после CreateOrder)
  - статус: открыт
  - **Решение:** не затрагивается: блокировка витриной происходит до отправки заказа; поведение ответа 200 не меняется

## Смежные возможности — связаны событиями или той же сущностью

- [ ] N-01 `catalog-semantic-search` — Каталог: семантический поиск (ИИ) <!-- key: cap:catalog-semantic-search -->
  - связь: меняет ту же сущность `CatalogItem`
  - открой карточку system-context/caps/catalog-semantic-search.md: её требования с «возможная ошибка», блокирующие вопросы — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: выдача поиска не фильтруется, как и списки; `available` приходит в той же сущности CatalogItem, поведение поиска не меняется
- [ ] N-02 `order-lifecycle` — Жизненный цикл заказа (события и статусы) <!-- key: cap:order-lifecycle -->
  - связь: подписана на `OrderStockConfirmedIntegrationEvent`; подписана на `OrderStockRejectedIntegrationEvent`; публикует `OrderStartedDomainEvent`, на которое подписано изменяемое; публикует `OrderStatusChangedToAwaitingValidationIntegrationEvent`, на которое подписано изменяемое
  - открой карточку system-context/caps/order-lifecycle.md: её требования с «возможная ошибка», блокирующие вопросы (Q-049) — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: получает существующий OrderStockRejected (теперь и от снятого товара, задача 2.4) и отменяет заказ без правок кода
- [ ] N-03 `order-management` — Заказы: просмотр, отмена, отгрузка <!-- key: cap:order-management -->
  - связь: публикует `OrderStartedDomainEvent`, на которое подписано изменяемое
  - открой карточку system-context/caps/order-management.md: её требования с «возможная ошибка», блокирующие вопросы (Q-055, Q-058) — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: входы и данные заказов не меняются
- [ ] N-04 `order-payment` — Оплата заказа <!-- key: cap:order-payment -->
  - связь: публикует `OrderStartedDomainEvent`, на которое подписано изменяемое
  - открой карточку system-context/caps/order-payment.md: её требования с «возможная ошибка», блокирующие вопросы (Q-049, Q-064) — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: недоступный заказ отклоняется проверкой остатков (задача 2.4) до оплаты
- [ ] N-05 `order-status-notifications` — Уведомления о статусе заказа в интерфейсе <!-- key: cap:order-status-notifications -->
  - связь: подписана на `OrderStatusChangedToSubmittedIntegrationEvent`
  - открой карточку system-context/caps/order-status-notifications.md: её требования с «возможная ошибка», блокирующие вопросы — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: события статусов прежние
- [ ] N-06 `webhook-delivery` — Вебхуки: рассылка событий <!-- key: cap:webhook-delivery -->
  - связь: подписана на `ProductPriceChangedIntegrationEvent`
  - открой карточку system-context/caps/webhook-delivery.md: её требования с «возможная ошибка», блокирующие вопросы (Q-049, Q-095) — не держится ли изменение на них
  - решение: добавить её в --cap (меняется её поведение), задача, или «не затрагивается: почему»
  - **Решение:** не затрагивается: набор и поля событий вебхуков не меняются

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
- Q-029 Что делать, если заказ оплачен, а товара на складе не хватает?
- Q-031 Что делать, если товара заказа уже нет в каталоге?
- Q-034 Нужны ли порог перезаказа, признак перезаказа и добавление остатка?
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

- basket: tests/Basket.UnitTests/BasketServiceTests.cs
- catalog-management: tests/Catalog.FunctionalTests/CatalogApiTests.cs, tests/Application.UnitTests/CatalogAITests.cs
- catalog-browsing: tests/Catalog.FunctionalTests/CatalogApiTests.cs
- storefront: e2e/cart-helpers.ts, e2e/CartTest.spec.ts, e2e/BrowseItemTest.spec.ts, e2e/CheckoutTest.spec.ts, e2e/login.setup.ts
- order-placement: tests/Ordering.FunctionalTests/OrderingApiTests.cs, tests/Ordering.UnitTests/Application/IdentifiedCommandHandlerTest.cs, tests/Ordering.UnitTests/Application/NewOrderCommandHandlerTest.cs, tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs, tests/Ordering.UnitTests/Domain/BuyerAggregateTest.cs, tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs

## Сущности в коде затронутых возможностей (если меняешь их поля — добавь --entity)

- Buyer, Order, OrderItem, PaymentMethod

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
- src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToAwaitingValidationIntegrationEventHandler.cs
- src/Catalog.API/IntegrationEvents/EventHandling/OrderStatusChangedToPaidIntegrationEventHandler.cs
- src/Catalog.API/IntegrationEvents/Events/ConfirmedOrderStockItem.cs
- src/Catalog.API/IntegrationEvents/Events/OrderStockConfirmedIntegrationEvent.cs
- src/Catalog.API/IntegrationEvents/Events/OrderStockRejectedIntegrationEvent.cs
- src/Catalog.API/IntegrationEvents/Events/ProductPriceChangedIntegrationEvent.cs
- src/Catalog.API/Model/CatalogItem.cs
- src/Catalog.API/Model/PaginatedItems.cs
- src/Catalog.API/Model/PaginationRequest.cs
- src/Catalog.API/Program.cs
- src/Catalog.API/Services/CatalogAI.cs
- src/EventBusRabbitMQ/RabbitMQEventBus.cs
- src/Ordering.API/Apis/OrdersApi.cs
- src/Ordering.API/Application/Behaviors/TransactionBehavior.cs
- src/Ordering.API/Application/Behaviors/ValidatorBehavior.cs
- src/Ordering.API/Application/Commands/CreateOrderCommandHandler.cs
- src/Ordering.API/Application/Commands/CreateOrderDraftCommandHandler.cs
- src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs
- src/Ordering.API/Application/DomainEventHandlers/UpdateOrderWhenBuyerAndPaymentMethodVerifiedDomainEventHandler.cs
- src/Ordering.API/Application/DomainEventHandlers/ValidateOrAddBuyerAggregateWhenOrderStartedDomainEventHandler.cs
- src/Ordering.API/Application/Queries/OrderQueries.cs
- src/Ordering.API/Application/Validations/CreateOrderCommandValidator.cs
- src/Ordering.API/Infrastructure/OrderingContextSeed.cs
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

## Дополнительно (найдено вне слоя)

- [x] X-01 новая зависимость `Basket.API → Catalog.API` (HTTP `GET /api/catalog/items/by`) <!-- key: x:X-01 -->
  - проверки добавляемых позиций нет в текущем вызове корзины — связь новая, появляется этим изменением
  - **Решение:** задача 2.1 (клиент и регистрация), 2.2 (проверка и fail-open при отказе каталога)
