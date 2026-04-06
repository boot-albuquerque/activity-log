#!/usr/bin/env bash
# backfill.sh — Sincroniza histórico git local → activity-log (macOS + Linux + Git Bash/WSL)
# Fixes: date parsing cross-platform via Python, delimiter seguro, validação de msg
set -euo pipefail

AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-$(git config --global user.email)}"
MIRROR_DIR="$HOME/.git-mirror/activity-log"
LOG_FILE="$MIRROR_DIR/log.md"
SINCE="${BACKFILL_SINCE:-5 years ago}"
SEARCH_ROOTS=("$HOME/Documents" "$HOME/Documentos" "$HOME/Projects" "$HOME/dev"
               "$HOME/workspace" "$HOME/code" "$HOME/Desktop" "$HOME/src")

# Detectar Python disponível
PYTHON=""
for py in python3 python python3.exe; do
  if command -v "$py" &>/dev/null; then
    PYTHON="$py"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "❌ Python não encontrado. Instale Python 3 e tente novamente."
  exit 1
fi

# Função cross-platform para parsear datas ISO 8601
# Suporta: +03:00, -03:00, Z, +0300, -0300, etc.
iso_to_display() {
  local iso="$1"
  "$PYTHON" - <<PYEOF
import sys
from datetime import datetime
iso = """$iso"""
try:
    # Normalizar: remover segundos fracionários e padronizar offset
    clean = iso.strip()
    # Substituir Z por +00:00
    clean = clean.replace('Z', '+00:00')
    # Garantir separador T
    if ' ' in clean[:19]:
        clean = clean[:10] + 'T' + clean[11:]
    # Extrair apenas YYYY-MM-DDTHH:MM:SS (sem timezone, sem frações)
    dt_part = clean[:19]
    dt = datetime.strptime(dt_part, '%Y-%m-%dT%H:%M:%S')
    print(dt.strftime('%Y-%m-%d %H:%M'))
except Exception as e:
    print('unknown')
PYEOF
}

echo "==> Backfill de histórico git para activity-log"
echo "    Autor:  $AUTHOR_EMAIL"
echo "    Desde:  $SINCE"
echo "    Python: $PYTHON"
echo ""

# Atualizar repo local
git -C "$MIRROR_DIR" pull --quiet --rebase 2>/dev/null || true

# Carregar commits já no log para dedup
EXISTING_LOG=""
if [ -f "$LOG_FILE" ]; then
  EXISTING_LOG=$(cat "$LOG_FILE")
fi

# Coletar repos
echo "==> Buscando repositórios git..."
REPOS=()
for ROOT in "${SEARCH_ROOTS[@]}"; do
  if [ -d "$ROOT" ]; then
    while IFS= read -r repo; do
      REPOS+=("$(dirname "$repo")")
    done < <(find "$ROOT" -name ".git" -maxdepth 7 -type d 2>/dev/null \
              | grep -v "/deps/" | grep -v "/.npm/" | grep -v "/node_modules/")
  fi
done

echo "    ${#REPOS[@]} repositórios encontrados."
echo ""

# Usar arquivo temporário com delimiter \x01 (SOH) — seguro contra msgs com |, ; etc.
DELIM=$'\x01'
TMPFILE=$(mktemp)
SEEN_HASHES=$(mktemp)
trap 'rm -f "$TMPFILE" "$SEEN_HASHES"' EXIT

for REPO in "${REPOS[@]}"; do
  [ ! -d "$REPO/.git" ] && continue

  # Ignorar o próprio activity-log
  REMOTE=$(git -C "$REPO" remote get-url origin 2>/dev/null || echo "")
  echo "$REMOTE" | grep -qi "activity-log" && continue

  # Detectar plataforma
  if echo "$REMOTE" | grep -qi "gitlab"; then
    PLATFORM="GitLab"
  elif echo "$REMOTE" | grep -qi "bitbucket"; then
    PLATFORM="Bitbucket"
  elif echo "$REMOTE" | grep -qi "github"; then
    PLATFORM="GitHub"
  elif [ -z "$REMOTE" ]; then
    PLATFORM="Local"
  else
    PLATFORM="Git"
  fi

  REPO_NAME=$(basename "$REPO")

  while IFS=$'\x01' read -r hash iso_date ref_hint msg; do
    [ -z "$hash" ] && continue

    # Dedup por hash
    grep -qxF "$hash" "$SEEN_HASHES" && continue
    echo "$hash" >> "$SEEN_HASHES"

    # Branch
    BRANCH=$(git -C "$REPO" name-rev --name-only "$hash" 2>/dev/null \
      | sed 's|remotes/origin/||;s|~.*||;s|\^.*||' || echo "main")
    [ -z "$BRANCH" ] || [ "$BRANCH" = "undefined" ] && BRANCH="main"

    # Data cross-platform via Python
    LOG_DATE=$(iso_to_display "$iso_date")

    # Checar duplicata no log
    DUP_KEY="$LOG_DATE${DELIM}$(hostname -s)${DELIM}$PLATFORM${DELIM}$REPO_NAME${DELIM}$BRANCH"
    echo "$EXISTING_LOG" | grep -qF "$LOG_DATE | $(hostname -s) | $PLATFORM | \`$REPO_NAME\` | \`$BRANCH\`" && continue

    # Limpar mensagem: max 120 chars, sem chars problemáticos
    MSG_CLEAN=$(echo "$msg" | head -c 120 | tr '|' '-' | tr '\001' '-' | tr '\n' ' ')

    # Guardar: iso_date \x01 log_date \x01 machine \x01 platform \x01 repo \x01 branch \x01 msg
    printf '%s%s%s%s%s%s%s%s%s%s%s%s%s\n' \
      "$iso_date"   "$DELIM" \
      "$LOG_DATE"   "$DELIM" \
      "$(hostname -s)" "$DELIM" \
      "$PLATFORM"   "$DELIM" \
      "$REPO_NAME"  "$DELIM" \
      "$BRANCH"     "$DELIM" \
      "$MSG_CLEAN" >> "$TMPFILE"

  done < <(git -C "$REPO" log \
    --author="$AUTHOR_EMAIL" \
    --since="$SINCE" \
    --all \
    --no-merges \
    --pretty=format:"%H%x01%aI%x01%D%x01%s" 2>/dev/null)
done

TOTAL=$(wc -l < "$TMPFILE" | tr -d ' ')
echo "==> $TOTAL commits históricos encontrados."
echo ""

if [ "$TOTAL" -eq 0 ]; then
  echo "Nenhum commit novo para sincronizar."
  exit 0
fi

# Ordenar por data ISO (campo 1)
SORTED_FILE=$(mktemp)
trap 'rm -f "$TMPFILE" "$SEEN_HASHES" "$SORTED_FILE"' EXIT
sort -t"$DELIM" -k1,1 "$TMPFILE" > "$SORTED_FILE"

COUNT=0
BATCH=50

while IFS=$'\x01' read -r ISO_DATE LOG_DATE MACHINE PLATFORM REPO_NAME BRANCH MSG; do
  [ -z "$ISO_DATE" ] && continue

  # Escrever no log
  echo "| $LOG_DATE | $MACHINE | $PLATFORM | \`$REPO_NAME\` | \`$BRANCH\` | $MSG |" >> "$LOG_FILE"

  # Commit backdatado
  cd "$MIRROR_DIR"
  git add log.md

  GIT_AUTHOR_DATE="$ISO_DATE" \
  GIT_COMMITTER_DATE="$ISO_DATE" \
  git commit --quiet \
    -m "activity: [$PLATFORM] $REPO_NAME/$BRANCH — $MSG" \
    --date="$ISO_DATE" 2>/dev/null || true

  COUNT=$((COUNT + 1))

  if [ $((COUNT % BATCH)) -eq 0 ]; then
    echo "    [$COUNT/$TOTAL] Push..."
    git push --quiet origin main 2>/dev/null || true
  fi
done < "$SORTED_FILE"

# Push final
echo "    [$COUNT/$TOTAL] Push final..."
git -C "$MIRROR_DIR" push --quiet origin main 2>/dev/null || true

echo ""
echo "✅ Backfill concluído! $COUNT commits sincronizados."
echo "   Ver: https://github.com/LucasGeek/activity-log"
