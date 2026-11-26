# Данные

Сущности и их поля, где они создаются и куда копируются, схема и миграции, засев, конкурентность и транзакции.
Новое поле сущности — пройди по «Создаётся», «Копии полей» и «Засев»: там оно потеряется молча.

Блоки `sa:auto` собирает `contracts.py scan` (эвристики — сверяй с кодом), пересканирование их переписывает.
Свои уточнения пиши **вне** блоков. Места с комментарием «заполнить» заполняет агент.

## Сущности

### `User` (Prisma)
<!-- sa:auto id="entity:User" -->
- Определение: `User` (prisma/schema.prisma:3)
- Поля: id String, email String, role Role, orders Order[]
- Атрибуты полей:
  - `id @id @default(uuid())`
  - `email @unique`
  - `role @default(CUSTOMER)`
- Создаётся: явных мест не найдено (фабрика, маппер, ORM?)
<!-- sa:auto-end -->

### `Order` (Prisma)
<!-- sa:auto id="entity:Order" -->
- Определение: `Order` (prisma/schema.prisma:10)
- Поля: id String, userId String, status OrderStatus, totalCents Int, paymentId String?, createdAt DateTime, items OrderItem[], user User
- Атрибуты полей:
  - `id @id @default(uuid())`
  - `status @default(NEW)`
  - `createdAt @default(now())`
  - `user @relation(fields: [userId], references: [id])`
- Создаётся:
  - src/routes/orders.ts:18
<!-- sa:auto-end -->

### `OrderItem` (Prisma)
<!-- sa:auto id="entity:OrderItem" -->
- Определение: `OrderItem` (prisma/schema.prisma:21)
- Поля: id String, orderId String, sku String, qty Int, priceCents Int, order Order
- Атрибуты полей:
  - `id @id @default(uuid())`
  - `order @relation(fields: [orderId], references: [id])`
- Создаётся: явных мест не найдено (фабрика, маппер, ORM?)
<!-- sa:auto-end -->

## Миграции и схема

### Где лежат
<!-- sa:auto id="migrations" -->
- prisma: файлов миграций рядом не найдено; схема или снимок: prisma/schema.prisma — сверь с моделью перед новой миграцией (расхождение уйдёт в миграцию)
<!-- sa:auto-end -->

## Засев и справочники

### Файлы засева
<!-- sa:auto id="seeds" -->
- засева не найдено
<!-- sa:auto-end -->

## Конкурентность и транзакции

### Конкурентность
<!-- sa:auto id="concurrency" -->
- ⚠ токенов конкурентности (версия строки, xmin), SELECT … FOR UPDATE и распределённых блокировок не найдено: параллельные изменения одной записи — «последняя запись побеждает»
<!-- sa:auto-end -->

### Транзакции
<!-- sa:auto id="transactions" -->
- явных транзакций не найдено
<!-- sa:auto-end -->
- **Что это значит:** <!-- заполнить: что защищено от параллельных изменений, а что нет (последняя запись побеждает?); границы транзакций; что публикуется вне транзакции -->

## Валидация входных данных

### Где проверяется
<!-- sa:auto id="validation" -->
- ⚠ валидации не найдено
<!-- sa:auto-end -->
- **Что это значит:** <!-- заполнить: где проверяются входные данные и что не проверяется (подключена ли валидация вообще) -->
