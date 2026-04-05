#!/usr/bin/env bash
set -e

AUTHOR_EMAIL="lucas.albuquerque.gk@gmail.com"
MIRROR_DIR="$HOME/.git-mirror/activity-log"
LOG_FILE="$MIRROR_DIR/log.md"
SINCE="3 years ago"
SEARCH_ROOTS=("$HOME/Documents" "$HOME/Projects" "$HOME/dev" "$HOME/workspace" "$HOME/code" "$HOME/Desktop")

echo "==> Backfill de histórico git para activity-log"
echo "    Autor:  $AUTHOR_EMAIL"
echo "    Desde:  $SINCE"
echo ""

# Garantir que o repo está atualizado
git -C "$MIRROR_DIR" pull --quiet --rebase 2>/dev/null || true

# Carregar commits já registrados no log para evitar duplicatas
EXISTING=$(grep -oP '\d{4}-\d{2}-\d{2} \d{2}:\d{2} \| \S+ \| \S+ \| `[^`]+` \| `[^`]+` \| .+' "$LOG_FILE" 2>/dev/null || true)

# Coletar todos os repos git na máquina
echo "==> Buscando repositórios git..."
REPOS=()
for ROOT in "${SEARCH_ROOTS[@]}"; do
  if [ -d "$ROOT" ]; then
    while IFS= read -r repo; do
      REPOS+=("$(dirname "$repo")")
    done < <(find "$ROOT" -name ".git" -maxdepth 6 -type d 2>/dev/null)
  fi
done

# Adicionar repos extras comuns
for EXTRA in "$HOME/.git-mirror/activity-log"; do
  [ -d "$EXTRA/.git" ] && REPOS+=("$EXTRA")
done

echo "    ${#REPOS[@]} repositórios encontrados."
echo ""

# Coletar todos os commits históricos
SEEN_HASHES_FILE=$(mktemp)
COMMIT_LINES=()

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

  # Obter commits do autor no período
  while IFS=$'\x01' read -r hash iso_date branch_hint msg; do
    [ -z "$hash" ] && continue
    grep -qxF "$hash" "$SEEN_HASHES_FILE" && continue
    echo "$hash" >> "$SEEN_HASHES_FILE"

    # Branch: tentar obter do hash (aproximado)
    BRANCH=$(git -C "$REPO" name-rev --name-only "$hash" 2>/dev/null | sed 's/remotes\/origin\///' | sed 's/~.*//' | sed 's/\^.*//' || echo "main")
    [ -z "$BRANCH" ] || [ "$BRANCH" = "undefined" ] && BRANCH="main"

    # Formatar data para o log
    LOG_DATE=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${iso_date%+*}" "+%Y-%m-%d %H:%M" 2>/dev/null \
      || date -d "$iso_date" "+%Y-%m-%d %H:%M" 2>/dev/null \
      || echo "unknown")

    # Checar duplicata no log existente (por data+repo+msg)
    DUP_KEY="$LOG_DATE | $(hostname -s) | $PLATFORM | \`$REPO_NAME\` | \`$BRANCH\`"
    echo "$EXISTING" | grep -qF "$DUP_KEY" && continue

    MSG_CLEAN=$(echo "$msg" | head -c 80 | tr '|' '-')

    COMMIT_LINES+=("$iso_date|$LOG_DATE|$(hostname -s)|$PLATFORM|$REPO_NAME|$BRANCH|$MSG_CLEAN")
  done < <(git -C "$REPO" log \
    --author="$AUTHOR_EMAIL" \
    --since="$SINCE" \
    --pretty=format:"%H%x01%aI%x01%D%x01%s" \
    --no-merges 2>/dev/null)

done
rm -f "$SEEN_HASHES_FILE"

TOTAL=${#COMMIT_LINES[@]}
echo "==> $TOTAL commits históricos encontrados."
echo ""

if [ "$TOTAL" -eq 0 ]; then
  echo "Nenhum commit novo para sincronizar."
  exit 0
fi

# Ordenar por data ISO (campo 1)
IFS=$'\n' SORTED=($(printf '%s\n' "${COMMIT_LINES[@]}" | sort -t'|' -k1,1))
unset IFS

# Commitar cada entrada backdatada
COUNT=0
BATCH=20

for LINE in "${SORTED[@]}"; do
  IFS='|' read -r ISO_DATE LOG_DATE MACHINE PLATFORM REPO_NAME BRANCH MSG <<< "$LINE"

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

  # Push a cada 20 commits para não acumular
  if [ $((COUNT % BATCH)) -eq 0 ]; then
    echo "    [$COUNT/$TOTAL] Fazendo push..."
    git push --quiet origin main 2>/dev/null || true
  fi
done

# Push final
echo "    [$COUNT/$TOTAL] Push final..."
git -C "$MIRROR_DIR" push --quiet origin main 2>/dev/null || true

echo ""
echo "✅ Backfill concluído! $COUNT commits sincronizados."
echo "   Veja: https://github.com/LucasGeek/activity-log"
