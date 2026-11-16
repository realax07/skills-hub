# skill-authoring

Скиллы для создания и улучшения самих скиллов.

```
skill-authoring/
  skills/<skill-name>/   # скиллы этой темы (ставятся инсталлятором)
```

## Скиллы

| Скилл | Что делает |
|---|---|
| [skill-author](skills/skill-author/) | Создаёт и улучшает скиллы по полной анатомии (SKILL.md, references, examples, scripts, assets, evals) и проверяет их. Свои скрипты: каркас, тест-кейсы, валидатор — работает и вне этого репо |

Установить только эту тему:

```bash
./install.sh install -t skill-authoring
```
