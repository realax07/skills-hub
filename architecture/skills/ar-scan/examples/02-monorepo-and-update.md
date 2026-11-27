# Пример 2: монорепозиторий (eShop) и обновление слоя

Запрос: «Это наш eShop — один репозиторий, внутри сервисы. Нарисуй, как они друг от друга зависят, документации нет».

## Сборка

```
python3 <skill>/scripts/landscape.py init architecture
python3 <skill>/scripts/landscape.py add-repo architecture . --name eshop
python3 <skill>/scripts/landscape.py build architecture
```

Вывод (реальный прогон на dotnet/eShop):

```
✓ систем 11 (внешних 0), связей в коде 23, событий между системами 13, HTTP с потребителями 3, gRPC 2
✓ документов 0, связей из документов 0, ADR 0
✓ RECONCILE.md: пунктов 1, решения сохранены у 0
  eshop: split=packages → basket-api, catalog-api, clientapp, hybridapp, identity-api, orderprocessor, ordering-api, paymentprocessor, webapp, webhookclient, webhooks-api
```

`auto` выбрал системы по пакетам: у 11 пакетов есть входы. `Ordering.Domain` и `Ordering.Infrastructure` скрипт отдал `ordering-api`
(ссылки ProjectReference), `EventBus` и `ServiceDefaults` — общий код, не системы, `eShop.AppHost` — хост развёртывания.
Из AppHost (Aspire) — алиасы (`ordering-api`, `order-processor`), зависимости `WithReference`, базы и брокер.

Единственный пункт сверки (документов нет, поэтому «код без документа» не строится):

```
## Общие базы данных
- [ ] R-01 orderingdb: ordering-api, orderprocessor
  - ordering-api: eshop:src/eShop.AppHost/AppHost.cs
  - orderprocessor: eshop:src/eShop.AppHost/AppHost.cs
```

**Плохо:** `ок: это одна система`. Так можно сказать только с источником: в AppHost это два процесса с разной выкаткой.
**Хорошо:** открыть OrderProcessor — он читает заказы напрямую SQL-запросом `SELECT "Id" FROM ordering.orders` для периода отмены (`src/OrderProcessor/Services/GracePeriodOrdersRepository.cs:25`),
а схему ведёт ordering-api (миграции EF) → `вопрос Q-001`: «OrderProcessor читает таблицы ordering-api в обход контракта: согласуется ли
с ним изменение схемы заказов?», затрагивает ordering-api и orderprocessor.

Карточка `systems/catalog-api.md` — то, что откроет dev-агент перед изменением каталога:

```
**Кто зависит от неё** (меняешь её вход или событие — эти сломаются первыми, выкатываются отдельно):
- `clientapp` вызывает её: HTTP /api/catalog — eshop:src/ClientApp/Services/Catalog/CatalogService.cs:11
- `ordering-api` слушает её событие: OrderStockConfirmedIntegrationEvent, OrderStockRejectedIntegrationEvent — …
- `webapp` вызывает её: HTTP /api/catalog, адрес catalog-api, зависимость при запуске (Aspire) — eshop:src/WebApp/Program.cs:32
- `webhooks-api` слушает её событие: ProductPriceChangedIntegrationEvent — eshop:src/Catalog.API/Apis/CatalogApi.cs:399 → …
```

Мобильный клиент (`clientapp`) в этом списке — главная находка для sa-change: он ходит в каталог напрямую и выкатывается через магазин приложений.

## Обновление

Через месяц добавили репозиторий партнёрского сервиса доставки:

```
python3 <skill>/scripts/landscape.py status architecture
python3 <skill>/scripts/landscape.py add-repo architecture ../delivery
python3 <skill>/scripts/landscape.py build architecture
```

Решение R-01 сохранилось по ключу; новые пункты (например, `OrderStatusChangedToShippedIntegrationEvent` теперь слушает и `delivery`)
— без решения. `check` покажет только их. После сборки — `link` в репозитории, чьи карточки изменились.
