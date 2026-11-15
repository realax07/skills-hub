# Формат plan.json

План лежит в папке результата (`<out>/plan.json`) — так съёмку можно повторить одной командой.
Относительные пути внутри плана (`out`, `serve`, `storageState`) считаются от папки plan.json.
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
| `defaults` | object | нет | см. ниже |
| `pages` | array | нет | страницы целиком |
| `components` | array | нет | отдельные элементы |
| `modals` | array | нет | модалки, дропдауны, состояния — всё, что появляется после действия |

### defaults

| Поле | По умолчанию | Что |
|---|---|---|
| `waitUntil` | `"load"` | событие загрузки для `goto` (`load`, `domcontentloaded`, `networkidle`) |
| `settle` | `600` | пауза (мс) после подготовки страницы |
| `disableAnimations` | `true` | отключить анимации и transition (служебный стиль в мокап не попадает) |
| `lazyScroll` | `true` | проскроллить страницу, чтобы подгрузились ленивые картинки |
| `hide` | `[]` | селекторы, которые удалить перед снимком (cookie-баннеры, чаты поддержки, A/B-плашки) |
| `steps` | `[]` | шаги для каждой страницы до снимка (например, закрыть баннер) |
| `timeout` | `8000` | таймаут одного шага, мс |
| `screenshots` | `true` | снимать PNG оригинала (нужны для verify и каталога) |

## Элементы

Общие поля для `pages`, `components`, `modals`:

| Поле | Что |
|---|---|
| `id` | kebab-case, становится именем файла |
| `title` | человекочитаемое название для каталога и README |
| `notes` | что это, где встречается, как открывается — для следующего агента |
| `steps` | действия перед снимком (см. ниже). Элемент со steps снимается в свежей вкладке |
| `settle` | пауза после steps, мс (по умолчанию 300) |
| `viewports` | список имён вьюпортов, если не все: `["desktop"]` |

`pages`: + `path` — путь от `baseUrl` (`/`, `/pricing`, `/blog/first-post`).

`components` и `modals`: + `page` — id страницы из `pages` или путь (`"/pricing"`); `selector` — CSS-селектор;
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
