# Как найти модалки и состояния

`discover.mjs` даёт подсказки (`source.modals`, триггеры на страницах), но список неполный:
открытие модалки часто спрятано в обработчике. Задача — для каждой модалки понять
**где она живёт** (какая страница), **что её открывает** (действие) и **как её найти** (селектор).

## Общий порядок

1. Возьми `discovery.json → source.modals`: файлы и строки с `<Modal`, `role="dialog"`, `showModal()` и т.п.
2. Для каждого компонента модалки найди, кто его рендерит, и переменную/событие открытия
   (`isOpen`, `open`, `visible`, `show`, стор, URL-параметр). Поиск по имени компонента и по сеттеру (`setLoginOpen(true)`).
3. Найди триггер в разметке страницы: кнопку, на которой висит этот сеттер. Сверь с `discovery.json → pages[].candidates`
   (`kind: "trigger"`, поле `controls` — id управляемого элемента).
4. Запиши шаги: `click` по триггеру → `waitFor` по модалке. Селектор снимка — сам диалог (`[role=dialog]`),
   а если важен затемнённый фон — его обёртка.
5. Если модалка открывается по URL (`?modal=login`, `#login`, роут `/login` с фоном) — используй `goto` или `path`.

## По фреймворкам и библиотекам

| Стек | Как выглядит в коде | Где в DOM после открытия | Селектор |
|---|---|---|---|
| нативный `<dialog>` | `dialog.showModal()` | на месте | `dialog[open]` |
| Bootstrap | `data-bs-toggle="modal" data-bs-target="#x"` | на месте, класс `.show` | `#x.show .modal-dialog` |
| React + портал | `createPortal(..., document.body)` | конец `body` | `body > [role=dialog]` или класс обёртки |
| Radix / shadcn | `<Dialog.Root>`, `<DialogContent>` | портал, `[data-state=open]` | `[role=dialog][data-state=open]` |
| Headless UI | `<Dialog open={...}>` | портал `#headlessui-portal-root` | `#headlessui-portal-root [role=dialog]` |
| MUI | `<Modal>`, `<Dialog>`, `<Drawer>`, `<Menu>` | портал, `.MuiDialog-root` | `.MuiDialog-paper`, `.MuiMenu-paper` |
| Ant Design | `<Modal open>`, `Modal.confirm()` | портал, `.ant-modal-root` | `.ant-modal-content` |
| Chakra | `<Modal>`, `<Drawer>` | портал `.chakra-portal` | `.chakra-modal__content` |
| Vue | `<Teleport to="body">`, `v-if="show"` | цель телепорта | класс модалки |
| Nuxt UI / Vuetify | `<UModal v-model>`, `<v-dialog>` | портал / `.v-overlay-container` | `.v-overlay--active .v-card` |
| Svelte | `{#if open}<Modal/>{/if}` | на месте или портал-экшен | класс модалки |
| Поиск Algolia DocSearch | кнопка `⌘K`, `@docsearch/react` | портал `.DocSearch-Container` (фон), **без `role=dialog`** | `.DocSearch-Modal`; ждать `.DocSearch-Input` |
| Alpine.js | `x-data="{open:false}" @click="open=true" x-show="open"` | на месте | элемент с `x-show` |
| jQuery-плагины | `$('#x').modal('show')`, fancybox, magnific | конец `body` | `.fancybox-container`, `.mfp-content` |
| Tailwind UI (vanilla) | `classList.remove('hidden')` | на месте | элемент без `.hidden` |

## Другие состояния, которые легко пропустить

- **Мобильное меню** — бургер только на mobile-вьюпорте: `viewports: ["mobile"]`.
- **Ошибки форм** — сабмит пустой формы; иногда ошибки только после `blur`: `focus` → `press Tab`.
- **Тосты** — появляются после действия и исчезают: сними сразу после `waitFor`, без паузы.
- **Пустые состояния и лоадеры** — часто только при определённых данных; ищи в коде `isEmpty`, `skeleton`, `Spinner`.
- **Вкладки и аккордеоны** — каждая значимая вкладка/секция как отдельное состояние, если контент различается по виду.
- **Cookie-баннер / онбординг** — сними один раз как модалку, а для остального скрой через `defaults.hide`.
- **Тёмная тема** — второй вьюпорт с `colorScheme: "dark"` или шаг переключения темы.

Если селектор по роли не находится (`waitFor` по `[role=dialog]` упал по таймауту), открой страницу,
выполни шаги и посмотри, что появилось в конце `body`: многие библиотеки (DocSearch, самописные модалки)
ставят только классы. В шаге клика добавляй `>> visible=true`, если кнопка продублирована для мобилки и десктопа.
