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
  _template/skill/   # шаблон нового скилла
  design-sites/      # тема: дизайн и вёрстка сайтов
    skills/<name>/SKILL.md
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

1. `cp -R _template/skill <тема>/skills/<имя-скилла>`
2. Заполнить `SKILL.md`: `name` = имя папки, `description` — что делает и когда применять.
3. Добавить строку в README темы.
4. `./install.sh install -s <имя-скилла>`

Имена скиллов уникальны во всём репо (агенты кладут их в одну плоскую папку).
Новая тема — просто новая папка верхнего уровня с `skills/` внутри и строкой в таблице выше.
