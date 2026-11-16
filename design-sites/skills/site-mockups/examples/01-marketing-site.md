# Пример 1: маркетинговый сайт с dev-сервером

## Запрос

> Сделай мокапы нашего сайта, чтобы агенту было на что опираться при новых лендингах.
> Дев-сервер `npm run dev` на 5173, код в `apps/web/src`.

## Ход работы

1. `node scripts/setup.mjs --check` — ок.
2. Куда класть: работаем в репозитории сайта → `mockups/` в корне репозитория.
   Указатель: `node scripts/link-context.mjs --suggest --root .` → есть `AGENTS.md` и `CLAUDE.md` с `@AGENTS.md`.
   Спросил пользователя: «Впишу в AGENTS.md блок о мокапах — когда их открывать и путь до mockups/GUIDE.md. Ок?» → да.
3. Пользователь сам запустил dev-сервер. Разведка:
   ```bash
   node scripts/discover.mjs --url http://localhost:5173 --src apps/web/src --out mockups/discovery.json
   ```
   Нашлись 7 страниц: `/`, `/pricing`, `/features`, `/blog`, `/blog/<3 статьи>`, `/contact`.
   В исходниках: `<Dialog>` в `DemoRequestDialog.tsx`, `<Sheet>` в `MobileNav.tsx`, `toast()` в `ContactForm.tsx`.
4. Чтение кода: `DemoRequestDialog` открывает `setDemoOpen(true)` из кнопки «Запросить демо» в hero и в шапке;
   `MobileNav` — бургер `aria-label="Меню"`, только на мобиле; тост — после успешной отправки контактной формы
   (без бэкенда не открыть → отмечено как пропуск).
5. План (`mockups/plan.json`), сокращённо:
   ```json
   {
     "baseUrl": "http://localhost:5173",
     "context": "../AGENTS.md",
     "viewports": { "desktop": { "width": 1440, "height": 900 }, "mobile": { "width": 390, "height": 844, "isMobile": true, "deviceScaleFactor": 2 } },
     "defaults": { "hide": ["#cookie-consent"] },
     "pages": [
       { "id": "home", "path": "/" }, { "id": "pricing", "path": "/pricing" }, { "id": "features", "path": "/features" },
       { "id": "blog", "path": "/blog" }, { "id": "blog-post", "path": "/blog/launch-week", "notes": "представитель статей блога" },
       { "id": "contact", "path": "/contact" },
       { "id": "home--demo-open", "path": "/", "steps": [{ "click": "header >> text=Запросить демо" }, { "waitFor": "[role=dialog]" }] }
     ],
     "components": [
       { "id": "header", "group": "layout", "page": "home", "selector": "header" },
       { "id": "footer", "group": "layout", "page": "home", "selector": "footer" },
       { "id": "hero", "group": "sections", "page": "home", "selector": "[data-section=hero]" },
       { "id": "pricing-card", "group": "content", "page": "pricing", "selector": "[data-testid=plan]", "all": true, "limit": 3 },
       { "id": "button-primary", "group": "controls", "page": "home", "selector": "[data-variant=primary]", "viewports": ["desktop"] },
       { "id": "contact-form", "group": "forms", "page": "contact", "selector": "form" }
     ],
     "modals": [
       { "id": "demo-request", "page": "home", "selector": "[role=dialog]", "title": "Запрос демо",
         "notes": "Кнопки «Запросить демо» в шапке и hero",
         "steps": [{ "click": "header >> text=Запросить демо" }, { "waitFor": "[role=dialog]" }] },
       { "id": "mobile-nav", "group": "menus", "page": "home", "selector": "[role=dialog]", "viewports": ["mobile"],
         "steps": [{ "click": "[aria-label=Меню]" }, { "waitFor": "[role=dialog] nav" }] },
       { "id": "contact-form--errors", "group": "forms-states", "page": "contact", "selector": "form",
         "steps": [{ "click": "form [type=submit]" }, { "waitFor": "[aria-invalid=true]" }] }
     ]
   }
   ```
6. `node scripts/capture.mjs mockups/plan.json` → 1 ошибка: `mobile-nav` — бургер перекрыт
   cookie-баннером в шаге. `defaults.hide` удаляет баннер только перед снимком, поэтому добавил в `defaults.steps`
   `{ "click": "#cookie-consent button" }` → `--only mobile-nav` → ок.
7. `node scripts/verify.mjs mockups` → 41/42; `footer`: «картинка не загрузилась: _media/….svg» —
   иконка соцсети с внешнего CDN, который отдаёт её только своему домену. В `capture-log.json` тот же warning.
   Обойти со своей стороны нельзя — не подделывал, указал в отчёте как известный пропуск.

## Результат (сообщение пользователю)

```
Мокапы в mockups/ — гайд для агентов: mockups/GUIDE.md, карта разделов: mockups/README.md, каталог: mockups/_catalog.html
В AGENTS.md добавлен блок «Мокапы дизайна сайта» со ссылкой на гайд (обновляется при пересъёмке).
Разделы: / (главная), pricing/, features/, blog/ (+ launch-week/), contact/
- 7 страниц (+ главная с открытым «Запросить демо»), desktop и mobile
- 14 компонентов: layout, sections, content, controls, forms
- 3 состояния: окно запроса демо, мобильное меню, ошибки контактной формы
- tokens.json: 12 CSS-переменных, палитра из 9 цветов, шрифт Inter
Не снято: тост после отправки формы — нужен ответ бэкенда.
verify: 41/42 — в футере не загрузилась иконка соцсети с внешнего CDN (CORS).
Переснять: node <skill>/scripts/capture.mjs mockups/plan.json
```

## Почему так

- Место — `mockups/` в корне репозитория сайта (правило «куда класть»).
- Указатель вписан туда, что агенты читают всегда (`AGENTS.md`), и только с согласия пользователя: это его файл.
- Блог представлен одной статьёй — остальные однотипны.
- Модалки открыты реальными кликами, у каждой есть `notes` — следующий агент поймёт, откуда она.
- Тост не стали подделывать через `eval` — честно отметили пропуск.
