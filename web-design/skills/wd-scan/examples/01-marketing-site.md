# Пример 1: маркетинговый сайт с dev-сервером

## Запрос

> Подготовь дизайн-контекст нашего сайта, чтобы агенты делали новые лендинги и фичи в том же стиле.
> Дев-сервер `npm run dev` на 5173, код в `apps/web/src`.

## Ход работы

1. `node scripts/setup.mjs --check` — ок.
2. Куда класть: репозиторий сайта → `design-context/` в корне.
   `link-context.mjs --suggest --root .` → есть `AGENTS.md` и `CLAUDE.md` с `@AGENTS.md`.
   Вопросы пользователю одним сообщением:
   - «Впишу в AGENTS.md блок про дизайн-контекст со ссылкой на design-context/GUIDE.md — ок?» → да.
   - «Новое повторяем как есть или приводим к канону?» → «к канону, у нас набралось легаси».
3. Разведка: `discover.mjs --url http://localhost:5173 --src apps/web/src --out design-context/discovery.json` —
   7 страниц, `<Dialog>` в `DemoRequestDialog.tsx`, `<Sheet>` в `MobileNav.tsx`;
   дизайн в коде: tailwindcss, class-variance-authority, framer-motion, lucide-react, 42 CSS-переменные.
4. План (`design-context/plan.json`), сокращённо:
   ```json
   {
     "baseUrl": "http://localhost:5173",
     "src": "../apps/web/src",
     "context": "../AGENTS.md",
     "stance": "normalize",
     "viewports": { "desktop": { "width": 1440, "height": 900 }, "mobile": { "width": 390, "height": 844, "isMobile": true, "deviceScaleFactor": 2 } },
     "defaults": { "hide": ["#cookie-consent"] },
     "pages": [
       { "id": "home", "path": "/" }, { "id": "pricing", "path": "/pricing" }, { "id": "features", "path": "/features" },
       { "id": "blog", "path": "/blog" }, { "id": "blog-post", "path": "/blog/launch-week", "notes": "представитель статей" },
       { "id": "contact", "path": "/contact" },
       { "id": "home--demo-open", "path": "/", "steps": [{ "click": "header >> text=Запросить демо" }, { "waitFor": "[role=dialog]" }] }
     ],
     "components": [
       { "id": "header", "group": "layout", "page": "home", "selector": "header", "title": "Шапка" },
       { "id": "footer", "group": "layout", "page": "home", "selector": "footer", "title": "Футер" },
       { "id": "hero", "group": "sections", "page": "home", "selector": "[data-section=hero]", "title": "Hero" },
       { "id": "pricing-card", "group": "content", "page": "pricing", "selector": "[data-testid=plan]", "title": "Карточка тарифа" },
       { "id": "contact-form", "group": "forms", "page": "contact", "selector": "form", "title": "Форма контакта" }
     ],
     "modals": [
       { "id": "demo-request", "page": "home", "selector": "[role=dialog]", "title": "Запрос демо",
         "steps": [{ "click": "header >> text=Запросить демо" }, { "waitFor": "[role=dialog]" }] },
       { "id": "mobile-nav", "group": "menus", "page": "home", "selector": "[role=dialog]", "viewports": ["mobile"],
         "steps": [{ "click": "[aria-label=Меню]" }, { "waitFor": "[role=dialog] nav" }] }
     ]
   }
   ```
   Кнопки, поля и бейджи в план не перечислены — их найдёт извлечение на всех страницах.
5. `node scripts/capture.mjs design-context/plan.json` → разброс: кнопки 14/4, поля 3/2, типографика 19/7;
   исходники: `source.md`, деталей привязано к файлам 11 из 23.
6. Разбор: `node scripts/parts.mjs design-context --group buttons` (или вырезки в `reference/parts.html`). Из 14 вариантов кнопок:
   - канон: `1k3x9a` «Кнопка основная» (синяя, 31× на 7 стр.), `0zq2mf` «Кнопка вторичная» (обводка), `2c8u1w` «Иконочная»;
   - вариант: `1q7b0d` «Основная на тёмном» (hero, футер);
   - шум: 8 штук — пункты меню, табы тарифов, одноразовая кнопка «Подробнее» с подчёркиванием из старой статьи.
   У трёх канонов исходник — `components/ui/button.tsx` (`cva`, варианты `default`, `outline`, `icon`): имена берём оттуда.
   `parts.mjs design-context --set 1k3x9a=canon:"Кнопка основная" 0zq2mf=canon:"Кнопка вторичная" 2c8u1w=canon:"Иконочная" 1q7b0d=variant:"Основная на тёмном"`,
   затем `--group buttons --rest noise` — слой пересобран.
7. `verify.mjs design-context` → 41/42; иконка соцсети в футере с внешнего CDN не скачалась (CORS) — в отчёт.

## Результат (сообщение пользователю)

```
Дизайн-контекст — design-context/GUIDE.md; в AGENTS.md добавлен блок со ссылкой на него.
Позиция: приводить к канону.
Основы: 4 цвета текста и 6 фонов (все через CSS-переменные --color-*), Inter 7 размеров, переходы 150 мс ease-out.
Детали: кнопки — канон 3 из 14 (основная, вторичная, иконочная), поля — канон 2, карточки — канон 2.
Код: Tailwind 3 + cva; токены — src/styles/globals.css (:root и .dark), примитивы — components/ui (Button, Input, Card…),
анимации — framer-motion в 6 файлах. Расхождение: --muted в коде #f4f4f5, на сайте применяется #f5f5f5 (переопределён в layout).
Разделы: 6 схем + состояние «окно запроса демо»; компоненты: шапка, футер, hero, карточка тарифа, форма.
Не снято: тост после отправки формы — нужен ответ бэкенда.
Темы: в коде `.dark` — в план добавлено `"themes": { "dark": { "htmlClass": "dark" } }`, снята: меняются 9 переменных (foundations.md, «Темы»).
Скриншоты эталона (34 МБ) лучше не коммитить — добавить `design-context/reference/**/*.jpg` и `*.png` в .gitignore?
```

## Почему так

- Позиция проекта и место указателя спрошены до съёмки — это решения владельца.
- Мелкие детали не перечислялись вручную: извлечение по всем страницам находит их полнее.
- Разбор сделан по вырезкам, а не по названиям классов: «шум» видно глазами.
- Компоненты из плана в схемах разделов стали ссылками — схемы короче.
- Исходники дали имена вариантов и файлы: агент-потребитель правит `button.tsx`, а не копирует классы со страницы.
