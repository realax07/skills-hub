# skills-hub

Личный хаб скиллов и harness для код-агентов, разложенный по темам.
Скиллы в формате [Agent Skills](https://agentskills.io) (`SKILL.md` + frontmatter), поэтому один и тот же скилл работает в любом агенте.

## Карта

```
skills-hub/
  README.md          # эта карта
  AGENTS.md          # инструкция для агентов: как ставить и как добавлять скиллы
  agents.conf        # реестр агентов и путей к их скиллам
  install.sh         # инсталлятор macOS / Linux
  install.ps1        # инсталлятор Windows
  docs/skill-guide.md  # как писать скиллы
  tools/
    new_skill.py     # создать скилл из шаблона
    validate.py      # проверить скиллы
  _template/skill-name/  # шаблон скилла
  design-sites/      # тема: дизайн и вёрстка сайтов
    skills/<skill-name>/
```

Устройство одного скилла:

```
<skill-name>/
  SKILL.md       # frontmatter (name, description) + процесс, ключевые правила, ресурсы
  references/    # подробные правила и справка, читаются по необходимости
  examples/      # разобранные примеры: запрос → ход работы → результат, плохо/хорошо
  scripts/       # скрипты для детерминированных шагов
  assets/        # шаблоны и файлы для результата
  evals/         # тест-кейсы (агентам не ставятся)
```

| Тема | Что внутри |
|---|---|
| [design-sites](design-sites/) | дизайн и вёрстка сайтов |

## Поддерживаемые агенты

| id | Агент | Глобально | В проекте |
|---|---|---|---|
| `claude` | Claude Code | `~/.claude/skills` | `.claude/skills` |
| `codex` | Codex CLI | `~/.codex/skills` | `.agents/skills` |
| `opencode` | OpenCode | `~/.config/opencode/skills` | `.opencode/skills` |
| `qwen` | Qwen Code | `~/.qwen/skills` | `.qwen/skills` |
| `hermes` | Hermes Agent | `~/.hermes/skills/<тема>/` | — |
| `zcode` | Z Code | `~/.zcode/skills` (не проверено) | `.zcode/skills` |
| `agents` | общий стандарт | `~/.agents/skills` | `.agents/skills` |

Новый агент или другой путь — одна строка в [agents.conf](agents.conf)
(или в `agents.local.conf`, он не коммитится).

## Установка

macOS / Linux:

```bash
git clone https://github.com/realax07/skills-hub.git ~/.skills-hub
```

```bash
~/.skills-hub/install.sh install
```

Или одной командой без клона (склонирует в `~/.skills-hub`):

```bash
curl -fsSL https://raw.githubusercontent.com/realax07/skills-hub/main/install.sh | bash -s -- install
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/realax07/skills-hub/main/install.ps1 | iex
```

По умолчанию ставится всё во всех найденных агентах, симлинками —
`git pull` (`./install.sh update`) сразу обновляет скиллы везде.

```bash
./install.sh list                                  # темы и скиллы
./install.sh agents                                # какие агенты найдены
./install.sh install -a claude,codex -t design-sites
./install.sh install -a all -p ~/code/site --copy  # в проект, копией
./install.sh status
./install.sh uninstall                             # снимает только то, что ставил хаб
```

Опции: `-a` агенты (`auto` | `all` | список), `-t` темы, `-s` скиллы,
`-p` проект, `--copy`, `--force`, `-n` dry-run. В PowerShell те же: `-Agent`, `-Topic`, `-Skill`, `-Project`, `-Copy`, `-Force`, `-DryRun`.

## Добавить скилл

Подробно — в [docs/skill-guide.md](docs/skill-guide.md).

```bash
python3 tools/new_skill.py design-sites hero-section     # каркас со всей структурой + строка в README темы
python3 tools/validate.py design-sites/skills/hero-section --strict
./install.sh install -s hero-section
```

Имена скиллов уникальны во всём репо (агенты кладут их в одну плоскую папку).
Новая тема создаётся тем же `new_skill.py` — останется добавить её в таблицу тем выше.
