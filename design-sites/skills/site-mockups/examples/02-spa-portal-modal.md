# Пример 2: SPA с порталами и хэш-классами

## Запрос

> Вот прод https://app.example.com (я залогинен, сессия в auth.json) и исходники в ./frontend.
> Нужны мокапы всех модалок и дропдаунов личного кабинета.

Особенности: React + styled-components (классы вида `sc-gKclnd`), модалки рендерятся
порталом в `#modal-root`, меню профиля — абсолютный дропдаун.

## Плохо

```json
{ "id": "profile-menu", "page": "/dashboard", "selector": ".sc-gKclnd.kXaQzz",
  "steps": [{ "eval": "document.querySelector('.sc-gKclnd').style.display='block'" }] }
```

```bash
curl https://app.example.com/dashboard > dashboard.html   # «мокап» страницы
```

Почему плохо:
- `curl` вернёт пустой `<div id="root">` — интерфейс строит JS.
- Хэш-классы styled-components поменяются при следующей сборке — план нельзя будет переиграть.
- `eval` с `display:block` показывает меню не так, как его открывает пользователь:
  не выставлены `aria-expanded`, не подставлены данные, не сработала логика позиционирования.

## Хорошо

1. Читаем `frontend/src/components/ProfileMenu.tsx`: открывается по кнопке `aria-label="Профиль"`,
   рендерит `<ul role="menu">`. Модалки — `<Modal>` через `createPortal(..., modalRoot)`.
2. План:
   ```json
   {
     "baseUrl": "https://app.example.com",
     "storageState": "../../auth.json",
     "pages": [{ "id": "dashboard", "path": "/dashboard" }],
     "modals": [
       { "id": "profile-menu", "group": "dropdowns", "page": "dashboard", "selector": "[role=menu]",
         "notes": "Аватар в правом верхнем углу",
         "steps": [{ "click": "[aria-label=Профиль]" }, { "waitFor": "[role=menu]" }] },
       { "id": "invite-member", "page": "/team", "selector": "#modal-root [role=dialog]",
         "steps": [{ "click": "role=button[name='Пригласить']" }, { "waitFor": "#modal-root [role=dialog]" }] }
     ]
   }
   ```
3. Сессию `auth.json` пользователь сохранил сам; файл добавлен в `.gitignore`, в отчёте об этом сказано.

## Результат

`dashboard/_modals/profile-menu.html` — меню в потоке, с атрибутом
`data-mockup-position="absolute; top:48px; right:0px; …"` (исходное позиционирование);
расположение относительно страницы видно на `dashboard/_states/dashboard--profile-open.html`, если его добавить.
`team/_modals/invite-member.html` — скелет `html > body > #modal-root > диалог`, стили портала сохранены.

## Почему так

- Селекторы по ролям и `aria-label` переживут пересборку.
- Реальные клики дают реальное состояние (ARIA-атрибуты, данные, позиционирование).
- Портал не проблема: «скелет предков» берёт цепочку до `body`, а CSS собирается из CSSOM, включая стили styled-components.
