#!/usr/bin/env bash
# skills-hub installer — ставит скиллы из этого репо в код-агентов.
# Совместим с bash 3.2 (macOS). Запуск без клона:
#   curl -fsSL https://raw.githubusercontent.com/realax07/skills-hub/main/install.sh | bash -s -- install
set -euo pipefail

REPO_URL="${SKILLS_HUB_REPO:-https://github.com/realax07/skills-hub.git}"
HUB_HOME="${SKILLS_HUB_HOME:-$HOME/.skills-hub}"
MARKER=".skills-hub"

# --- bootstrap: если скрипт запущен не из клона (curl | bash) — клонируем и перезапускаем
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
  REPO="$(cd "$(dirname "$SCRIPT_PATH")" && pwd -P)"
else
  REPO=""
fi
if [ -z "$REPO" ] || [ ! -f "$REPO/agents.conf" ]; then
  if [ -d "$HUB_HOME/.git" ]; then
    git -C "$HUB_HOME" pull --ff-only --quiet
  else
    git clone --quiet "$REPO_URL" "$HUB_HOME"
  fi
  exec bash "$HUB_HOME/install.sh" "$@"
fi

usage() {
  cat <<'EOF'
Usage: install.sh <command> [options]

Commands:
  list                 показать темы и скиллы
  agents               показать агентов, их пути и найдены ли они
  install              установить скиллы (по умолчанию)
  uninstall            удалить скиллы, поставленные из этого репо
  status               что и куда установлено
  update               git pull (симлинки обновятся сами, копии — переустанови)

Options:
  -a, --agent LIST     claude,codex,... | all | auto (по умолчанию: auto = найденные)
  -t, --topic LIST     только эти темы (design-sites,...)
  -s, --skill LIST     только эти скиллы
  -p, --project DIR    ставить в проект DIR, а не глобально
      --copy           копировать вместо симлинка
      --force          перезаписать чужую папку с тем же именем (старая -> .bak)
  -n, --dry-run        только показать, что будет сделано
  -h, --help

Examples:
  ./install.sh list
  ./install.sh install
  ./install.sh install -a claude,codex -t design-sites
  ./install.sh install -a all -p ~/code/my-site --copy
  ./install.sh uninstall -a all
EOF
}

# --- args
CMD="install"
AGENTS_SEL="auto"; TOPICS_SEL=""; SKILLS_SEL=""; PROJECT=""
MODE="link"; FORCE=0; DRY=0
if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then CMD="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    -a|--agent)   AGENTS_SEL="$2"; shift 2 ;;
    -t|--topic)   TOPICS_SEL="$2"; shift 2 ;;
    -s|--skill)   SKILLS_SEL="$2"; shift 2 ;;
    -p|--project) PROJECT="$(cd "$2" && pwd -P)"; shift 2 ;;
    --copy)       MODE="copy"; shift ;;
    --force)      FORCE=1; shift ;;
    -n|--dry-run) DRY=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

in_list() { # in_list item "a,b,c"
  [ -z "$2" ] && return 0
  case ",$2," in *",$1,"*) return 0 ;; esac
  return 1
}
run() { if [ "$DRY" = 1 ]; then echo "  [dry] $*"; else "$@"; fi; }
expand() { case "$1" in "~") echo "$HOME" ;; "~/"*) echo "$HOME/${1#\~/}" ;; *) echo "$1" ;; esac; }

# --- реестр агентов: строки "id|user_dir|project_dir|layout"
load_agents() {
  local f line id u p l out=""
  for f in "$REPO/agents.conf" "$REPO/agents.local.conf"; do
    [ -f "$f" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"
      read -r id u p l _ <<<"$line" || true
      [ -z "${id:-}" ] && continue
      out="$(printf '%s\n' "$out" | grep -v "^$id|" || true)"
      out="$out"$'\n'"$id|$(expand "$u")|$p|${l:-flat}"
    done <"$f"
  done
  printf '%s\n' "$out" | sed '/^$/d'
}
AGENT_ROWS="$(load_agents)"
case "$AGENTS_SEL" in all|auto) ;; *)
  for _a in $(echo "$AGENTS_SEL" | tr ',' ' '); do
    printf '%s\n' "$AGENT_ROWS" | grep -q "^$_a|" || {
      echo "Неизвестный агент: $_a. Доступны: $(printf '%s\n' "$AGENT_ROWS" | cut -d'|' -f1 | tr '\n' ' ')" >&2; exit 2; }
  done ;;
esac

agent_present() { [ -d "$(dirname "$1")" ]; }

selected_agents() {
  local id u p l
  while IFS='|' read -r id u p l; do
    case "$AGENTS_SEL" in
      all) echo "$id|$u|$p|$l" ;;
      auto) agent_present "$u" && echo "$id|$u|$p|$l" || true ;;
      *) in_list "$id" "$AGENTS_SEL" && echo "$id|$u|$p|$l" || true ;;
    esac
  done <<<"$AGENT_ROWS"
}

# --- скиллы: строки "topic|skill|abs_path". Тема = папка верхнего уровня, скиллы в <topic>/skills/<skill>/SKILL.md
all_skills() {
  local f rel topic skill
  for f in "$REPO"/*/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    rel="${f#$REPO/}"; topic="${rel%%/*}"
    case "$topic" in _*|.*) continue ;; esac
    skill="$(basename "$(dirname "$f")")"
    echo "$topic|$skill|$(dirname "$f")"
  done
}
selected_skills() {
  local t s d
  all_skills | while IFS='|' read -r t s d; do
    in_list "$t" "$TOPICS_SEL" && in_list "$s" "$SKILLS_SEL" && echo "$t|$s|$d" || true
  done
}

check_unique() {
  local dups
  dups="$(all_skills | cut -d'|' -f2 | sort | uniq -d)"
  if [ -n "$dups" ]; then
    echo "ERROR: имена скиллов должны быть уникальны во всём репо, дубли: $dups" >&2; exit 1
  fi
}

dest_for() { # dest_for root layout topic skill
  if [ "$2" = "category" ]; then echo "$1/$3/$4"; else echo "$1/$4"; fi
}
root_for() { # root_for user_dir project_dir -> печатает корень или ничего
  if [ -n "$PROJECT" ]; then
    [ "$2" = "-" ] && return 0
    echo "$PROJECT/$2"
  else
    echo "$1"
  fi
}
is_ours() { # путь установлен из этого репо?
  local d="$1"
  if [ -L "$d" ]; then
    case "$(readlink "$d")" in "$REPO"/*) return 0 ;; esac
    return 1
  fi
  [ -f "$d/$MARKER" ]
}

# --- команды
cmd_list() {
  local t s d desc last=""
  all_skills | while IFS='|' read -r t s d; do
    [ "$t" != "$last" ] && { echo "$t/"; last="$t"; }
    desc="$(sed -n 's/^description:[[:space:]]*//p' "$d/SKILL.md" | head -1 | cut -c1-90)"
    printf '  %-28s %s\n' "$s" "$desc"
  done
}

cmd_agents() {
  local id u p l mark
  printf '%-10s %-6s %-36s %s\n' AGENT FOUND USER_DIR PROJECT_DIR
  while IFS='|' read -r id u p l; do
    agent_present "$u" && mark=yes || mark=-
    printf '%-10s %-6s %-36s %s\n' "$id" "$mark" "${u/#$HOME/~}" "$p"
  done <<<"$AGENT_ROWS"
}

cmd_install() {
  check_unique
  local agents skills id u p l root t s d dest n=0
  agents="$(selected_agents)"; skills="$(selected_skills)"
  [ -z "$agents" ] && { echo "Агенты не найдены. Укажи явно: -a claude,codex или -a all" >&2; exit 1; }
  [ -z "$skills" ] && { echo "Нет скиллов под фильтр (см. ./install.sh list)" >&2; exit 1; }
  while IFS='|' read -r id u p l; do
    root="$(root_for "$u" "$p")"
    [ -z "$root" ] && { echo "~ $id: project-скиллы не поддерживаются, пропуск"; continue; }
    echo "> $id -> ${root/#$HOME/~}"
    while IFS='|' read -r t s d; do
      dest="$(dest_for "$root" "$l" "$t" "$s")"
      if [ -e "$dest" ] || [ -L "$dest" ]; then
        if is_ours "$dest"; then
          run rm -rf "$dest"
        elif [ "$FORCE" = 1 ]; then
          run mv "$dest" "$dest.bak.$(date +%s)"
        else
          echo "  ! $s: $dest уже существует и не из skills-hub (используй --force)"; continue
        fi
      fi
      run mkdir -p "$(dirname "$dest")"
      if [ "$MODE" = "copy" ]; then
        run cp -R "$d" "$dest"
        [ "$DRY" = 1 ] || echo "$REPO" >"$dest/$MARKER"
      else
        run ln -s "$d" "$dest"
      fi
      echo "  + $t/$s ($MODE)"; n=$((n+1))
    done <<<"$skills"
  done <<<"$agents"
  echo "Готово: $n установок. Перезапусти агента, чтобы он подхватил скиллы."
}

cmd_uninstall() {
  local agents id u p l root t s d dest
  # при удалении берём все скиллы репо (с фильтрами), а агентов по умолчанию — все
  [ "$AGENTS_SEL" = "auto" ] && AGENTS_SEL="all"
  agents="$(selected_agents)"
  while IFS='|' read -r id u p l; do
    root="$(root_for "$u" "$p")"; [ -z "$root" ] && continue
    while IFS='|' read -r t s d; do
      [ -z "$s" ] && continue
      dest="$(dest_for "$root" "$l" "$t" "$s")"
      if { [ -e "$dest" ] || [ -L "$dest" ]; } && is_ours "$dest"; then
        run rm -rf "$dest"; echo "  - $id: $t/$s"
      fi
    done <<<"$(selected_skills)"
  done <<<"$agents"
}

cmd_status() {
  local id u p l root t s d dest any
  [ "$AGENTS_SEL" = "auto" ] && AGENTS_SEL="all"
  while IFS='|' read -r id u p l; do
    root="$(root_for "$u" "$p")"; [ -z "$root" ] && continue
    any=""
    while IFS='|' read -r t s d; do
      [ -z "$s" ] && continue
      dest="$(dest_for "$root" "$l" "$t" "$s")"
      if { [ -e "$dest" ] || [ -L "$dest" ]; } && is_ours "$dest"; then
        [ -L "$dest" ] && any="$any $s(link)" || any="$any $s(copy)"
      fi
    done <<<"$(selected_skills)"
    [ -n "$any" ] && echo "$id:$any"
  done <<<"$(selected_agents)"
  return 0
}

case "$CMD" in
  list) cmd_list ;;
  agents) cmd_agents ;;
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
  status) cmd_status ;;
  update) git -C "$REPO" pull --ff-only ;;
  help) usage ;;
  *) echo "Unknown command: $CMD" >&2; usage >&2; exit 2 ;;
esac
