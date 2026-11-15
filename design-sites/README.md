# design-sites

Скиллы и harness для дизайна и вёрстки сайтов.

```
design-sites/
  skills/<skill-name>/SKILL.md   # скиллы этой темы (ставятся инсталлятором)
  harness/                       # (опционально) правила, команды, хуки под агентов
```

## Скиллы

| Скилл | Что делает |
|---|---|
| [site-mockups](skills/site-mockups/) | Статические HTML-мокапы готового сайта для AI-контекста: страницы, компоненты, модалки, токены, каталог. Нужен Node.js 18+ (Playwright ставится через `./install.sh deps`) |

Установить только эту тему:

```bash
./install.sh install -t design-sites
```
