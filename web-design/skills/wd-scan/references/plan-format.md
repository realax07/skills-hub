# Формат plan.json

План лежит в папке результата (`<out>/plan.json`) — так съёмку можно повторить одной командой.
Относительные пути внутри плана (`out`, `serve`, `storageState`, `context`, `src`) считаются от папки plan.json.
Заготовка — `assets/plan.example.json`.

## Верхний уровень

| Поле | Тип | Обяз. | Что |
|---|---|---|---|
| `baseUrl` | string | одно из двух | адрес сайта: `http://localhost:3000`, `https://staging.example.com` |
| `serve` | string | одно из двух | папка со сборкой — раннер сам поднимет локальный сервер (SPA-фолбэк на index.html) |
| `out` | string | нет | куда писать; по умолчанию `.` (папка плана) |
| `viewports` | object | нет | `{ имя: { width, height, isMobile?, deviceScaleFactor?, userAgent?, colorScheme? } }`. Первый — основной (без суффикса в именах файлов). По умолчанию `{ "desktop": { "width": 1440, "height": 900 } }` |
| `storageState` | string | нет | файл сессии Playwright для страниц за логином |
| `locale` | string | нет | `ru-RU`, `en-US` |
| `colorScheme` | string | нет | `light` / `dark` для всех вьюпортов |
| `themes` | object | нет | другие темы сайта (тёмная и т.п.): `{ "dark": { "htmlClass": "dark" } }` — см. «Темы» ниже |
| `defaults` | object | нет | см. ниже |
| `media` | object | нет | что считать контентом и не скачивать, см. ниже |
| `src` | string \| string[] | нет | исходники фронтенда (`"../src"`, `["../apps/web", "../packages/ui"]`): из них строится `source.md` и ссылки «деталь → файл». Только чтение. Подробно — rules.md, «Исходники» |
| `stance` | string | нет | позиция проекта: `preserve` — новое повторяет существующее как есть; `normalize` — только канон из разбора. Спроси владельца (rules.md, «Позиция проекта») |
| `parts` | object | нет | разбор деталей: `{ "<id варианта>": { "status": "canon" \| "variant" \| "noise", "name": "Кнопка основная", "note": "…" } }`. id — из `parts/*.md` или `reference/parts.html`. Удобнее — `scripts/parts.mjs <out> --set id=status:Имя` (пишет сюда и пересобирает); после ручной правки — `capture.mjs plan.json --rebuild` |
| `context` | string \| string[] | нет | файл(ы) инструкций проекта (`"../AGENTS.md"`), куда вписать блок-указатель на `GUIDE.md`; выбирает пользователь (см. rules.md, «Указатель в контексте проекта»). Нет поля — файлы проекта не трогаются |
| `cssBundle` | bool | нет | только для эталона: `true` (по умолчанию) — стили каждого уровня дерева `reference/` собираются в один `_css/styles.css`. `false` — исходные файлы сайта по отдельности: если после сборки `verify` показывает расхождения из-за чужих правил на странице |
| `pages` | array | нет | страницы целиком: источник основ, деталей и схем разделов |
| `components` | array | нет | отдельные элементы |
| `modals` | array | нет | модалки, дропдауны, состояния — всё, что появляется после действия |

### defaults

| Поле | По умолчанию | Что |
|---|---|---|
| `waitUntil` | `"load"` | событие загрузки для `goto` (`load`, `domcontentloaded`, `networkidle`) |
| `navTimeout` | `45000` | таймаут загрузки страницы, мс (при таймауте — одна повторная попытка) |
| `settle` | `600` | пауза (мс) после подготовки страницы |
| `disableAnimations` | `true` | отключить анимации и transition на время снимка эталона (движение извлекается до отключения; служебный стиль в эталон не попадает) |
| `lazyScroll` | `true` | проскроллить страницу, чтобы подгрузились ленивые картинки |
| `hide` | `[]` | селекторы, которые удалить перед снимком (cookie-баннеры, чаты поддержки, A/B-плашки) |
| `steps` | `[]` | шаги для каждой страницы до снимка (например, закрыть баннер) |
| `timeout` | `8000` | таймаут одного шага, мс |
| `screenshots` | `true` | снимать оригинал: страницы — JPEG, детали — PNG (нужны для verify и разбора) |

### media

Картинки и видео делятся на **дизайн** (скачиваются) и **контент** (не скачиваются: тег остаётся,
`src`/`poster` — заглушка тех же пропорций с атрибутом `data-mockup-placeholder`, исходный URL — в `data-mockup-src`).

| Поле | По умолчанию | Что |
|---|---|---|
| `mode` | `"placeholder"` | `"keep"` — скачивать всё, как есть |
| `design` | `[]` | селекторы, внутри которых медиа — всегда дизайн (`".logo-wall"`, `"[class*=_hero]"`) |
| `content` | `[]` | селекторы, внутри которых медиа — всегда контент (`"article"`, `".blog-post"`) |
| `iconMax` | `64` | картинки не больше этого размера (px) на экране и не больше ×4 по исходному — дизайн (иконки). Фото, показанное мелко (аватарка 512px в кружке 20px), — контент; JPEG, фотостоки и аватары (`avatar`, `author`, `gravatar`, `unsplash` в адресе или классе) — контент при любом размере |

Без переопределений: дизайн — SVG и data-URI, всё в `header`/`nav`/`footer`, картинки с `logo|icon|brand|wordmark`
в имени файла, классе или alt, мелкие картинки (см. `iconMax`), фоновые видео (`autoplay muted loop` без `controls`),
фоны из CSS и шрифты. Остальные `<img>` и `<video>` — контент.
Фон из CSS скачивается, только если его правило срабатывает хотя бы на одной снятой странице:
утилиты из примеров документации и стили неснятых страниц остаются в CSS с `url("")`.

## Темы

Основная съёмка — в теме по умолчанию. Каждая тема из `themes` снимается дополнительно: все страницы без `steps` на основном
вьюпорте — цвета, действующие значения CSS-переменных (сравниваются с основной) и скриншот первого экрана
(`reference/_themes/<тема>/`). Результат: раздел «Темы» в `foundations.md` (как включается, таблица «переменная → значение»),
блок темы в `assets/tokens.css`, палитра темы в `reference/kit.json` — по ней wd-fit проверяет новый код в каждой теме.

| Поле темы | Что делает | Когда |
|---|---|---|
| `htmlClass` | класс на `<html>` после загрузки | Tailwind `darkMode: "class"`, `.dark { --… }` в CSS |
| `htmlAttr` | атрибуты на `<html>`: `{ "data-theme": "dark" }` | `[data-theme=dark]`, `[data-bs-theme=dark]` |
| `colorScheme` | `prefers-color-scheme` браузера | `@media (prefers-color-scheme: dark)` |
| `localStorage` | ключи до загрузки: `{ "theme": "dark" }` | next-themes и самописные переключатели, которые читают выбор при старте |
| `steps` | шаги после загрузки (как в «Шаги») | только кнопка переключения, без класса и хранилища |

Поля сочетаются: next-themes — `{ "localStorage": { "theme": "dark" }, "htmlClass": "dark" }`. Указывай класс или атрибут,
которым тема реально включается в CSS, даже если сайт ставит его сам: так тему можно включить и на статичных копиях (мокапы wd-fit).
Тема не включилась (значения переменных не изменились) — предупреждение в `capture-log.json`: проверь способ.

```json
"themes": { "dark": { "htmlClass": "dark" } }
```

## Элементы

Общие поля для `pages`, `components`, `modals`:

| Поле | Что |
|---|---|
| `id` | kebab-case, становится именем файла |
| `title` | человекочитаемое название — в `parts/`, `compositions/` и README эталона |
| `notes` | что это, где встречается, как открывается — для следующего агента |
| `steps` | действия перед снимком (см. ниже). Элемент со steps снимается в свежей вкладке |
| `settle` | пауза после steps, мс (по умолчанию 300) |
| `viewports` | список имён вьюпортов, если не все: `["desktop"]` |

`pages`: + `path` — путь от `baseUrl` (`/`, `/pricing`, `/blog/first-post`). **Путь определяет папку**
в эталоне и в схемах разделов: `/` → корень, `/blog/first-post` → `blog/first-post/index.html`. Страница с `steps` —
это состояние страницы: файл `_states/<id>.html` в папке своего `path`. Две страницы без `steps`
с одним `path` — ошибка.

`components` и `modals`: + `page` — id страницы из `pages` или путь (`"/pricing"`); компонент ложится в папку этой страницы (`_components/<группа>/`), модалка — в её `_modals/`; `selector` — CSS-селектор;
`group` — папка (`layout`, `controls`, …; для modals по умолчанию `modals`);
`index` — какой из совпавших элементов брать (по умолчанию 0);
`all: true` + `limit` — снять все совпадения как варианты `id--1`, `id--2`…;
`fitSize: false` — не фиксировать ширину и высоту элемента (по умолчанию фиксируются как на странице).

## Шаги

Каждый шаг — объект с одним действием. `nth` — индекс элемента, если селектор находит несколько.
`settle` — пауза после шага (по умолчанию 150 мс).

| Шаг | Пример |
|---|---|
| click | `{ "click": "[data-open=login]" }` |
| dblclick | `{ "dblclick": ".cell" }` |
| hover | `{ "hover": ".has-tooltip", "nth": 1 }` |
| focus | `{ "focus": "input[name=email]" }` |
| fill | `{ "fill": "input[name=email]", "value": "anna@example.com" }` |
| select | `{ "select": "select[name=country]", "value": "RU" }` |
| check | `{ "check": "#agree" }` |
| press | `{ "press": "Escape" }` |
| waitFor | `{ "waitFor": "[role=dialog]" }` — ждать видимости |
| wait | `{ "wait": 500 }` |
| scroll | `{ "scroll": "#pricing" }` или `{ "scroll": "bottom" }` |
| goto | `{ "goto": "/account" }` |
| eval | `{ "eval": "document.querySelector('.x').classList.add('open')" }` — крайний случай |

## Пример

```json
{
  "baseUrl": "http://localhost:5173",
  "viewports": {
    "desktop": { "width": 1440, "height": 900 },
    "mobile": { "width": 390, "height": 844, "isMobile": true, "deviceScaleFactor": 2 }
  },
  "defaults": { "hide": ["#cookie-banner", ".intercom-launcher"] },
  "pages": [
    { "id": "home", "path": "/", "title": "Главная" },
    { "id": "pricing", "path": "/pricing", "title": "Тарифы" },
    { "id": "home--menu-open", "path": "/", "title": "Главная, мобильное меню", "viewports": ["mobile"],
      "steps": [{ "click": "[aria-label='Открыть меню']" }, { "waitFor": "nav[aria-label='Мобильное меню']" }] }
  ],
  "components": [
    { "id": "header", "group": "layout", "page": "home", "selector": "header" },
    { "id": "pricing-card", "group": "content", "page": "pricing", "selector": "[data-testid=plan-card]", "all": true, "limit": 3 },
    { "id": "button-primary", "group": "controls", "page": "home", "selector": ".btn-primary", "viewports": ["desktop"] }
  ],
  "modals": [
    { "id": "login", "page": "home", "title": "Окно входа", "selector": "[role=dialog]",
      "notes": "Кнопка «Войти» в шапке; закрывается Esc и кликом по фону",
      "steps": [{ "click": "header >> text=Войти" }, { "waitFor": "[role=dialog]" }] },
    { "id": "signup--errors", "group": "forms-states", "page": "/signup", "selector": "form",
      "steps": [{ "click": "form [type=submit]" }, { "waitFor": ".field-error" }] }
  ]
}
```

Селекторы шагов — это селекторы Playwright: кроме CSS работают `text=Войти`, `role=button[name="Войти"]`
и цепочки через `>>`. В `selector` элементов (то, что снимается) — только CSS.
