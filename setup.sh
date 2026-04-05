#!/usr/bin/env bash
set -e

MIRROR_DIR="$HOME/.git-mirror"
REPO_DIR="$MIRROR_DIR/activity-log"
HOOKS_DIR="$HOME/.config/git/hooks"
HOOK_FILE="$HOOKS_DIR/post-commit"
ACTIVITY_REPO="git@github.com:LucasGeek/activity-log.git"

echo "==> Configurando git-mirror..."

# 1. Clonar/atualizar o repo de atividade
mkdir -p "$MIRROR_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  echo "    Atualizando activity-log..."
  git -C "$REPO_DIR" pull --quiet
else
  echo "    Clonando activity-log..."
  git clone --quiet "$ACTIVITY_REPO" "$REPO_DIR"
fi

# 2. Criar diretório de hooks globais
mkdir -p "$HOOKS_DIR"

# 3. Escrever o post-commit hook
cat > "$HOOK_FILE" << 'HOOK'
#!/usr/bin/env bash

REPO_DIR="$HOME/.git-mirror/activity-log"
LOG_FILE="$REPO_DIR/log.md"

# Coletar metadados do commit atual
REPO_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
MSG=$(git log -1 --pretty=%s 2>/dev/null | head -c 80)
DATE=$(date "+%Y-%m-%d %H:%M")
HOSTNAME=$(hostname -s)

# Detectar plataforma pelo remote
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if echo "$REMOTE_URL" | grep -qi "gitlab"; then
  PLATFORM="GitLab"
elif echo "$REMOTE_URL" | grep -qi "bitbucket"; then
  PLATFORM="Bitbucket"
elif echo "$REMOTE_URL" | grep -qi "github"; then
  PLATFORM="GitHub"
elif [ -z "$REMOTE_URL" ]; then
  PLATFORM="Local"
else
  PLATFORM="Git"
fi

# Ignorar commits dentro do próprio activity-log para evitar loop
if echo "$REMOTE_URL" | grep -qi "activity-log"; then
  exit 0
fi

# Garantir que o repo está atualizado antes de commitar
git -C "$REPO_DIR" pull --quiet --rebase 2>/dev/null || true

# Registrar no log
echo "| $DATE | $HOSTNAME | $PLATFORM | \`$REPO_NAME\` | \`$BRANCH\` | $MSG |" >> "$LOG_FILE"

# Commitar e fazer push
cd "$REPO_DIR"
git add log.md
git commit --quiet -m "activity: [$PLATFORM] $REPO_NAME/$BRANCH — $MSG"
git push --quiet origin main 2>/dev/null || true
HOOK

chmod +x "$HOOK_FILE"

# 4. Configurar git global para usar hooks globais
git config --global core.hooksPath "$HOOKS_DIR"

# 5. Criar o arquivo de log se não existir
LOG_FILE="$REPO_DIR/log.md"
if [ ! -f "$LOG_FILE" ]; then
  cat > "$LOG_FILE" << 'EOF'
# Log de Atividade

| Data | Máquina | Plataforma | Repositório | Branch | Commit |
|------|---------|-----------|-------------|--------|--------|
EOF
  git -C "$REPO_DIR" add log.md
  git -C "$REPO_DIR" commit --quiet -m "chore: init activity log"
  git -C "$REPO_DIR" push --quiet origin main
fi

echo ""
echo "✅ git-mirror instalado com sucesso!"
echo "   Hook:    $HOOK_FILE"
echo "   Log:     $REPO_DIR/log.md"
echo "   Repo:    https://github.com/LucasGeek/activity-log"
echo ""
echo "   A partir de agora, todo commit em qualquer repo"
echo "   será espelhado automaticamente no GitHub."
