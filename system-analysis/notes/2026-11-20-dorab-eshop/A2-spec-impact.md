# Impact: отмена заказа после оплаты с возвратом денег

Материалы: только спецификация и system-context (кода нет). Пути файлов взяты из trace.md / contracts.md / data.md; новые файлы названы условно.

## 1. Затронутое поведение
Меняется:
- order-management, «Отмена заказа»: из Paid теперь можно отменить (было 500). Для Paid отмена владельцем даёт 200 и статус `RefundPending`, а не `Cancelled`.
- order-management, «Доступ к операциям заказа»: для отмены Paid обязательна проверка владельца (Q-055 по остальным операциям остаётся как есть).
- order-management, «Отгрузка»: из `RefundPending`/`RefundFailed` отгрузка запрещена (уже следует из «только из Paid», добавлены сценарии).
- order-lifecycle, «Устаревшее событие не меняет статус»: расширен перечень разрешённых переходов; новые переходы Paid -> RefundPending -> Cancelled / RefundFailed.
- order-status-notifications: шесть событий -> восемь.
- order-payment (новое): возврат; Purpose «настоящей платёжной системы нет» перестаёт быть верным для возврата.
- catalog-stock (новое): возврат остатка; Purpose «списывает при оплате» дополняется.
- storefront (новое): кнопка отмены в `/user/orders`.
- domain.md: диаграмма переходов (запрет «Paid -> Cancelled» отменяется, «Shipped -> Cancelled» остаётся), роли и права.

Сохраняется, но на нём стоит изменение:
- Отмена до оплаты (Submitted/AwaitingValidation/StockConfirmed -> Cancelled, `Order.cs:142-153`) без изменений.
- «Оплата не прошла» (order-payment) использует тот же `CancelOrderCommand`/`SetCancelledStatus`; запрет Paid/Shipped (`Order.cs:144-148`) обязан остаться для этого пути, иначе отказ оплаты у уже оплаченного заказа начнёт его отменять. Рекомендация: отдельный переход `Paid -> RefundPending`, существующий метод не ослаблять.
- Идемпотентность по `x-requestid` (`IdentifiedCommandHandler.cs:39-104`, `RequestManager.cs:21-37`): запись сохраняется и при неудаче, повтор даёт 200 без действия (Q-058).
- Событие смены статуса уходит после фиксации транзакции через журнал событий (`TransactionBehavior.cs:32-53`, `OrderingIntegrationEventService.cs:13-41`).
- Списание остатка при Paid (`OrderStatusChangedToPaidIntegrationEventHandler.cs:17`) и ограничение «не ниже нуля» (Q-029) — определяют, что можно вернуть.
- Задержка 10 с в обработчиках Ordering (имитация, Q-053) — для новых обработчиков решать, копировать ли.

## 2. Контракты API
HTTP `PUT /api/orders/cancel` (`OrdersApi.cs:11`, обработчик :22-49; версия API 1.0; тело `CancelOrderCommand{OrderNumber:int}`, заголовок `x-requestid`):
- Поля запроса и заголовки не меняются.
- 200: для Paid теперь означает «возврат запрошен» (статус `RefundPending`), а не «отменён». Совместимость: клиент, считающий 200 = Cancelled, ошибётся.
- 500 «Cancel order failed to process.»: остаётся для Shipped, RefundPending, RefundFailed, чужого Paid-заказа, несуществующего (Q-056: код ошибки не 4xx; менять не предлагаю, чтобы не ломать мобильный ClientApp, которому нужен 400 для «статус сменился», и так не работающий).
- 400 «Empty GUID...» без изменений.
- Новых полей и кодов в ответе нет (допущение). Ломает: клиентов, различающих итог по 200; мобильный клиент (`OrderService.cs:98-107`).

`GET /api/orders` (`OrderSummary{OrderNumber, Date, Status:string, Total:double}`) и `GET /api/orders/{orderId}` (`Order{..., Status, Description, ...}`): поля те же, но `Status` может быть `RefundPending` или `RefundFailed`. Ломает: WebApp (CSS-класс из `Status.ToLower()`, `Orders.razor:48-52`), ClientApp (кнопка CANCEL ORDER видна только при `Submitted`).

`PUT /api/orders/ship` (`OrdersApi.cs:12`): контракт не меняется, новые статусы просто дают 500.

YARP-шлюз `/api/orders/{*any}` (`eShop.AppHost/Extensions.cs:155`) пропускает только `api-version` 1.0/1; новую версию не вводим.

Новых HTTP-входов нет (допущение). Если нужен вход для ручного разбора `RefundFailed` (повтор возврата, ручное закрытие) — в материалах про него ничего нет; в изменение он не включён.

PaymentProcessor: HTTP-входов в спеке нет (только события). Внешний вызов платёжного процессора (протокол, путь, поля) в материалах не описан, придумать нельзя.

## 3. События
Интеграционные (RabbitMQ, обменник `eshop_event_bus`, direct, ключ = имя типа; все новые типы нужны как копии в каждом сервисе, как сейчас):

Новые (имена и поля предложены мной):
- `OrderRefundRequestedIntegrationEvent` — поля: `OrderId:int`, ссылка на платёж (тип и имя неизвестны), сумма, валюта (источник неизвестен). Публикует Ordering.API после фиксации транзакции перехода Paid -> RefundPending. Подписан: PaymentProcessor; вызывает возврат у процессора (или заглушка).
- `OrderRefundSucceededIntegrationEvent` — `OrderId`, ссылка на возврат. Публикует PaymentProcessor (напрямую, без журнала, как сейчас `OrderPaymentSucceeded`, `...Handler.cs:23-32`). Подписан: Ordering.API (регистрация рядом с `Extensions.cs:60-61`); переводит RefundPending -> Cancelled, публикует Cancelled и событие возврата остатка.
- `OrderRefundFailedIntegrationEvent` — `OrderId`, причина. Публикует PaymentProcessor. Подписан Ordering.API; RefundPending -> RefundFailed.
- `OrderStatusChangedToRefundPendingIntegrationEvent` и `OrderStatusChangedToRefundFailedIntegrationEvent` — по образцу Cancelled: `OrderId`, `OrderStatus`, `BuyerName`, `BuyerIdentityGuid`. Публикует Ordering.API; подписан WebApp (перезагрузка списка, регистрация рядом с `WebApp/Extensions/Extensions.cs:45-50`).
- `OrderStockRestoredIntegrationEvent` (условное имя) — `OrderId`, `OrderStockItems[{ProductId, Units}]`. Публикует Ordering.API при переходе в Cancelled из RefundPending. Подписан Catalog.API (рядом с `Catalog.API/Extensions/Extensions.cs:32-33`); вызывает `CatalogItem.AddStock`.

Начинают использоваться иначе:
- `OrderStatusChangedToCancelledIntegrationEvent` (`OrderCancelledDomainEventHandler.cs:30-31`; поля `OrderId, OrderStatus, BuyerName, BuyerIdentityGuid`; подписан только WebApp): теперь публикуется и после возврата. Поля те же. Нельзя использовать для возврата остатка: нет `OrderStockItems` и он же шлётся для заказов, отменённых до оплаты (остаток не списывался).
- `OrderPaymentFailedIntegrationEvent`: поведение не меняется; обязан по-прежнему отклоняться для Paid.
- `OrderStatusChangedToPaidIntegrationEvent` (Catalog, WebApp, Webhooks.API): не меняется; подписчики Webhooks с типом `OrderPaid` уже получили «заказ оплачен» и не узнают об отмене (нет типа вебхука для отмены; `WebhookType`: CatalogItemPriceChange, OrderShipped, OrderPaid).

Доменные (MediatR, внутри Ordering.API): новые по образцу `OrderCancelledDomainEvent` (`Order.cs:152`): запрос возврата, возврат прошёл, возврат не прошёл. Обработчики в `src/Ordering.API/Application/DomainEventHandlers/`.

Порядок/повторы: шина подтверждает сообщение и при падении обработчика, повтора нет (`RabbitMQEventBus.cs:170-180`, Q-049); публикация PaymentProcessor повторяется до 10 раз только при сетевых ошибках, потом теряется.

## 4. Потребители и сервисы
- Ordering.API: основная работа (домен, команды, события, API).
- PaymentProcessor: новый вход (запрос возврата), новый исход, настройки; сегодня обрабатывает только `OrderStatusChangedToStockConfirmed` и не имеет БД (для идемпотентности возврата негде хранить).
- Catalog.API: новая подписка, `AddStock` (мёртвый код, Q-034, не проверен).
- WebApp (Blazor Server): `OrderingService.cs` — метод отмены; `Orders.razor` — кнопка и стили; подписки на два новых события.
- ClientApp (MAUI): `OrderService.cs:92-107`, `OrderDetailViewModel.cs:38-58`, `OrderDetailView.xaml:76` — отмена только для Submitted; решить, расширять ли на Paid (ожидает 400, получит 500).
- OrderProcessor: сегодня только период ожидания. Возможный новый фоновый проход для зависших `RefundPending` (в изменение заложен как открытый вопрос, не как требование).
- Webhooks.API / WebhookClient: не меняются; проверить, что внешним получателям не нужно уведомление об отмене (Q-096 про персональные данные).
- eShop.AppHost: настройки PaymentProcessor (`AppHost.cs:52-53`), секреты процессора.
- Внешняя система: платёжный процессор (протокол, SLA, ключи — неизвестны).
- Эксплуатация: заказы в `RefundFailed` и «вечном» `RefundPending` требуют ручного процесса.

## 5. Данные
Сущность `Order` (`Order.cs`, таблица `ordering.orders`, `OrderEntityTypeConfiguration.cs`):
- Новые значения `OrderStatus` (`RefundPending`, `RefundFailed`; хранение строкой до 30 символов, `HasConversion<string>`, схема не меняется; предыдущая миграция `20240106121712_UseEnumForOrderStatus`).
- Новые колонки (предложено): ссылка на платёж, ссылка на возврат, причина отказа возврата. Откуда у заказа ссылка на платёж — неизвестно: сейчас есть только `PaymentId` (= `PaymentMethodId`, метод оплаты), PaymentProcessor ничего не возвращает при оплате.
- Токен конкурентности (версия строки/xmin): нет нигде в системе («последняя запись побеждает», data.md); нужен, чтобы отгрузка и отмена не шли одновременно.
- Миграция: `src/Ordering.Infrastructure/Migrations/` + `OrderingContextModelSnapshot.cs` (сверить со снимком до генерации).
- Данные в полёте: заказы, оплаченные до выкладки, не имеют ссылки на платёж.
- Копии полей: `OrderViewModel.cs` (Order, OrderSummary, Orderitem), `src/ClientApp/Models/Orders/Order.cs`, WebApp `OrderRecord` — проверить, нужны ли новые поля клиентам.
Журнал событий Ordering (`IntegrationEventLogEF`): новые события попадают в него автоматически; PaymentProcessor его не использует.
Каталог: `AvailableStock` растёт; потолок `MaxStockThreshold` и `OnReorder` не читаются нигде. Журнала применённых заказов у Catalog нет.
Засев: не затрагивается. Кэш: нет (Redis только корзина).

## 6. Код
Известные пути:
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/OrderStatus.cs` — два новых статуса.
- `src/Ordering.Domain/AggregatesModel/OrderAggregate/Order.cs` — новые переходы; не ослаблять `:142-153` для пути «оплата не прошла»; `:119-128` Paid (читать ссылку на платёж, если появится); общий файл для 4 возможностей.
- `src/Ordering.Domain/Events/` — новые доменные события.
- `src/Ordering.API/Apis/OrdersApi.cs` (:11, :22-49) — ветка Paid, проверка владельца, ответы.
- `src/Ordering.API/Application/Commands/CancelOrderCommand.cs`, `CancelOrderCommandHandler.cs` (:19-29, :34-48), `CancelOrderCommandValidator.cs` (:7) — логика Paid.
- `src/Ordering.API/Application/Commands/` — новые команды по образцу `SetPaidOrderStatusCommandHandler.cs` (RefundPending, Cancelled-after-refund, RefundFailed).
- `src/Ordering.API/Application/Commands/IdentifiedCommandHandler.cs` (:99-102) — глотает исключения; для отказа в отмене Paid причина не видна.
- `src/Ordering.API/Application/DomainEventHandlers/OrderCancelledDomainEventHandler.cs` (:30-31) и новые обработчики.
- `src/Ordering.API/Application/IntegrationEvents/Events/` и `.../EventHandling/` — события и обработчики результата возврата.
- `src/Ordering.API/Application/IntegrationEvents/OrderingIntegrationEventService.cs` — используется как есть.
- `src/Ordering.API/Extensions/Extensions.cs` (:57-61) — подписки.
- `src/Ordering.API/Application/Queries/OrderQueries.cs`, `OrderViewModel.cs` — проверка выдачи.
- `src/Ordering.API/Infrastructure/Services/IdentityService.cs` — владелец (`GetUserIdentity`).
- `src/Ordering.Infrastructure/EntityConfigurations/OrderEntityTypeConfiguration.cs` (:20-21), `Migrations/`, `OrderingContextModelSnapshot.cs`.
- `src/PaymentProcessor/IntegrationEvents/EventHandling/` (новый обработчик по образцу `OrderStatusChangedToStockConfirmedIntegrationEventHandler.cs:9-33`), `src/PaymentProcessor/Program.cs:6`, `PaymentOptions.cs:5`, `appsettings.json:14-16`.
- `src/Catalog.API/IntegrationEvents/EventHandling/` (новый обработчик), `src/Catalog.API/Extensions/Extensions.cs:32-33`, `src/Catalog.API/Model/CatalogItem.cs:86-105` (`AddStock`).
- `src/WebApp/Services/OrderingService.cs`, `src/WebApp/Components/Pages/User/Orders.razor` (:48-52), `src/WebApp/Services/OrderStatus/IntegrationEvents/Events/` и `.../EventHandling/`, `src/WebApp/Extensions/Extensions.cs:45-50`, `OrdersRefreshOnStatusChange.razor`.
- `src/ClientApp/Services/Order/OrderService.cs:92-107`, `src/ClientApp/ViewModels/OrderDetailViewModel.cs:38-58`, `src/ClientApp/Views/OrderDetailView.xaml:76`.
- `src/eShop.AppHost/AppHost.cs:52-53` — настройки процессора.
- `src/EventBusRabbitMQ/RabbitMQEventBus.cs` — менять не нужно, но общий файл (волны: возможности конфликтуют по нему).
Неизвестно: точные имена и сигнатуры методов `Order.cs` (названия есть только по описанию: `SetCancelledStatus`, `SetShippedStatus`), содержимое `PaymentOptions`, формат ссылки на платёж.

## 7. Тесты и проверка
Обновить:
- `tests/Ordering.UnitTests/Domain/OrderAggregateTest.cs` — новые переходы; запрет Shipped -> Cancelled; сохранение запрета Paid для пути отказа оплаты.
- `tests/Ordering.UnitTests/Application/OrdersWebApiTest.cs` (Cancel_order_*; мок медиатора).
- `tests/Ordering.FunctionalTests/OrderingApiTests.cs` (`CancelWithEmptyGuidFails`, `CancelNonExistentOrderFails`): добавить Paid/Shipped. Внимание: `AutoAuthorizeMiddleware.cs` подменяет пользователя фиксированным id — для проверки владельца настроить заказ с этим BuyerId.
- `tests/Application.UnitTests/PaymentProcessorTests.cs` (`PublishesConfiguredPaymentOutcome`) — аналог для возврата.
- Новые: идемпотентность результата возврата; обработчик Catalog; `tests/Catalog.FunctionalTests`; e2e (`e2e/CheckoutTest.spec.ts` не проверяет оплату — оплата -> отмена -> возврат придётся строить с нуля).
Поднять: через Aspire AppHost PostgreSQL (orderingdb, catalogdb), RabbitMQ, Redis, Identity; запущенные Ordering.API, PaymentProcessor, Catalog.API, WebApp. Для сквозной проверки учесть задержки: 1 мин период ожидания, 10 с на каждый переход, 30 с проход OrderProcessor.
Тестов отгрузки Paid -> Shipped нет вообще (trace.md) — добавить заодно, иначе гонка отмены и отгрузки не проверяется.

## 8. Риски
- Деньги: возврат идёт асинхронно через событие, которое при сбое теряется без повтора (Q-049/Q-054/Q-076): заказ навсегда в `RefundPending`, деньги не возвращены, пользователь не информирован.
- Двойной возврат: повтор события запроса (OrderProcessor-стиль повторов не относится сюда, но redelivery брокера и повтор HTTP возможны); у PaymentProcessor нет хранилища для идемпотентности.
- Гонка отмена/отгрузка: нет токена конкурентности; последняя запись побеждает; возможен заказ отгруженный и с возвратом.
- Гонка с самой оплатой: заказ можно отменить в StockConfirmed, когда событие оплаты уже летит (Q-061: оплата принята молча для Cancelled — деньги списаны, заказ отменён, возврата нет). Это уже существующий дефект; после изменения станет заметнее: оплата «после отмены» должна приводить к возврату, в материалах не определено.
- Остаток: списание при оплате могло быть неполным или не выполненным (Q-029); возврат остатка по тем же количествам даст завышение. Идемпотентности возврата остатка нет.
- Идемпотентность по `x-requestid`: запись остаётся при неудаче, повтор после неудачной отмены даёт 200 и ничего не делает (Q-058): покупатель думает, что отмена идёт.
- Транзакция: исключение в обработчике доменного события не откатывает статус (Q-057): ответ 500, а статус уже `RefundPending`, событие возврата может не уйти.
- Права: любой вошедший может отменить любой заказ (Q-055); для Paid добавляем проверку владельца, но владелец берётся по IdentityGuid покупателя, а `IdentityGuid` при создании заказа берётся из тела запроса, а не из токена (Q-067) — проверка может быть обойдена/неверна для старых заказов.
- Совместимость: ClientApp/WebApp с новыми статусами (CSS, видимость кнопки), мобильный клиент ждёт 400.
- Безопасность и ПДн: в событиях возврата не должно быть данных карты (Q-035 — номер и CVV уже попадают в журналы и токены).
- Веб-хуки: подписчики `OrderPaid` получат «оплачен» без последующей отмены.
- Выкладка: при деплое Ordering.API раньше PaymentProcessor/Catalog события возврата остаются без подписчиков (direct exchange без очереди — сообщение теряется); порядок выкладки: PaymentProcessor, Catalog, Ordering.
- Тихие переходы (`Order.cs:101,110,121,157`) vs исключения: новые переходы нужно сделать согласованными (в материалах асимметрия отмечена).

## 9. Чего не хватило
(Агент, работавший по спекам и контексту, без кода.)

1. Платёжный процессор. Нет ни названия, ни API, ни способа аутентификации, ни полей возврата, ни кодов ошибок (Q-064: оплата вообще заглушка, «внешнего шлюза нет»). Пришлось предположить: возврат — тоже заглушка по настройке (`RefundSucceeded`), реальный вызов — за интерфейсом. Влияние: критическое; без него плана реального возврата нет, а ответ на «через платёжный процессор» нельзя реализовать.
2. Ссылка на платёж. У заказа есть только `PaymentId` (id метода оплаты); PaymentProcessor не возвращает идентификатор транзакции, события `OrderPaymentSucceeded` несут лишь `OrderId`. Пришлось придумать колонку «ссылка на платёж» и протащить её через событие оплаты. Влияние: высокое (меняет и уже существующий путь оплаты, миграция старых заказов не продумана).
3. Сумма и валюта возврата. В материалах есть `Total` заказа (decimal/double в разных ответах), но формулы (скидки `Discount`, доставка), валюты и частичных возвратов нет. Допущена полная сумма заказа. Влияние: высокое (в событии запроса возврата поля сумма/валюта — выдумка).
4. Статусная модель. Что должно быть с заказом, пока возврат идёт и если он не удался: новый статус или Cancelled + флаг; что видит покупатель; кто разбирает `RefundFailed`. В материалах нет требований бизнеса. Придуманы `RefundPending`, `RefundFailed`, тексты описаний. Влияние: высокое для UX и для клиентов (WebApp, ClientApp), заметное для объёма работ.
5. Возврат остатка. Нет ответа, нужно ли вообще возвращать остаток при отмене оплаченного (Q-030: резерва нет, Q-029: списание может быть неполным, Q-034: `AddStock` — мёртвый код, `MaxStockThreshold` не читается). Допущено: возвращать и без защит. Влияние: среднее/высокое (можно завысить остаток).
6. Права. Q-055 открыт (блокирует): неизвестно, должна ли быть проверка владельца только для Paid или для всех отмен, и как считать владельца при Q-067 (UserId из тела запроса). Выбрана проверка только для Paid. Влияние: высокое (безопасность денег), но решение локальное.
7. Коды ответа и контракт клиента. Q-056 (500 vs 4xx) и ожидания ClientApp (400) расходятся; неизвестно, нужен ли новый код для «возврат принят» (202?) и как отличать причины отказа. Допущено: оставить 200/500. Влияние: среднее.
8. Надёжность обмена. Q-049/Q-054/Q-076: потерянные события не повторяются, у PaymentProcessor нет БД и журнала. Не определены таймаут `RefundPending`, повторная отправка запроса возврата, сверка с процессором, оповещение при зависании. В tasks.md это вынесено в «решить до кода». Влияние: высокое (риск неотправленных денег), объём работ может вырасти на фоновый процесс сверки.
9. Конкурентность. В data.md сказано, что токенов конкурентности нет нигде; как принято решать гонки в этом проекте (xmin? ручная проверка?) неизвестно. Допущена версия строки EF. Влияние: среднее.
10. Идемпотентность `x-requestid`. Q-058 блокирует: как должен вести себя повтор после неудачи. Не знаю точной схемы `RequestManager` (только описание). Влияние: среднее; от этого зависит, можно ли повторить отмену после отказа.
11. Заказы, отменённые во время оплаты (Q-061): деньги списаны, заказ Cancelled, возврата нет. Непонятно, входит ли это в задачу. Не включил. Влияние: среднее (дефект рядом с новым функционалом).
12. UI. В спеке storefront нет ни кнопки отмены в WebApp (отмена есть только в мобильном ClientApp для Submitted), ни макета, ни текстов, ни подтверждения «Вы уверены?». Допущены кнопка и сообщение об ошибке. Влияние: среднее.
13. Мобильный клиент. Нет указаний, трогать ли ClientApp (MAUI); и как он поведёт себя на новые статусы (JSON-имена `status`, `items` vs `OrderItems` уже расходятся). Влияние: низкое/среднее.
14. Вебхуки и уведомления. Нет типа вебхука для отмены; неизвестно, нужно ли внешним получателям (OrderPaid) знать об отмене; уведомление покупателю по почте отсутствует в системе. Не включено. Влияние: низкое.
15. Точные сигнатуры и тела методов (`Order.cs`, `CancelOrderCommandHandler`, `PaymentOptions`, `IdentityService`): в материалах только номера строк и словесное описание. Не знаю, как проверить владельца заказа в обработчике (`Order.BuyerId` -> `Buyer.IdentityGuid`, доступ через репозиторий?), как устроены тексты описаний, есть ли общий хелпер для 10-секундной задержки. Влияние: среднее (оценки трудоёмкости неточны, имена в tasks.md условные).
16. Нефункциональное: срок возврата, максимальный возраст оплаты для возврата (окно процессора), лимит попыток, логирование. Не указано. Влияние: низкое/среднее.
17. Порядок выкладки и версионирование событий (прямой обменник без очередей до подписки): не описано, как катить межсервисные изменения без простоя. Принял «PaymentProcessor, Catalog, затем Ordering». Влияние: низкое.
18. Формат: в config.yaml правила «требования без имён файлов и классов»; в моих дельтах упомянуты имена событий и настроек (как в существующих спеках). Если это нарушение — поправить при ревью. Влияние: низкое.
