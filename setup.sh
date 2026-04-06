#!/usr/bin/env bash
# setup.sh — Instala git-mirror no macOS/Linux/Git Bash (Windows)
# Para Windows PowerShell nativo, use setup.ps1
set -euo pipefail

MIRROR_DIR="$HOME/.git-mirror"
REPO_DIR="$MIRROR_DIR/activity-log"
HOOKS_DIR="$HOME/.config/git/hooks"
HOOK_FILE="$HOOKS_DIR/post-commit"
ACTIVITY_REPO="${ACTIVITY_REPO:-git@github.com:LucasGeek/activity-log.git}"

# Detectar Python
PYTHON=""
for py in python3 python python3.exe; do
  if command -v "$py" &>/dev/null; then
    PYTHON=$(command -v "$py")
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "❌ Python 3 não encontrado. Instale Python 3 antes de continuar."
  exit 1
fi

echo "==> Configurando git-mirror..."
echo "    Repo:   $ACTIVITY_REPO"
echo "    Python: $PYTHON"

# 1. Clonar/atualizar o repo de atividade
mkdir -p "$MIRROR_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  echo "    Atualizando activity-log..."
  git -C "$REPO_DIR" pull --quiet --rebase 2>/dev/null || true
else
  echo "    Clonando activity-log..."
  git clone --quiet "$ACTIVITY_REPO" "$REPO_DIR"
fi

# 2. Criar diretório de hooks globais
mkdir -p "$HOOKS_DIR"

# 3. Escrever o post-commit hook (usa Python para date parsing cross-platform)
cat > "$HOOK_FILE" << HOOK
#!/usr/bin/env bash
# post-commit hook — git-mirror activity log

REPO_DIR="\$HOME/.git-mirror/activity-log"
LOG_FILE="\$REPO_DIR/log.md"

# Ignorar commits dentro do próprio activity-log
REMOTE_URL=\$(git remote get-url origin 2>/dev/null || echo "")
echo "\$REMOTE_URL" | grep -qi "activity-log" && exit 0

# Coletar metadados
REPO_NAME=\$(basename "\$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")
BRANCH=\$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
MSG=\$(git log -1 --pretty=%s 2>/dev/null | head -c 120 | tr '|' '-')
HOSTNAME_S=\$(hostname -s 2>/dev/null || hostname)

# Data atual (hook usa data do commit — sem necessidade de parsear ISO)
DATE=\$(date "+%Y-%m-%d %H:%M" 2>/dev/null || \\
  python3 -c "from datetime import datetime; print(datetime.now().strftime('%Y-%m-%d %H:%M'))" 2>/dev/null || \\
  echo "unknown")

# Detectar plataforma
if echo "\$REMOTE_URL" | grep -qi "gitlab";    then PLATFORM="GitLab"
elif echo "\$REMOTE_URL" | grep -qi "bitbucket"; then PLATFORM="Bitbucket"
elif echo "\$REMOTE_URL" | grep -qi "github";   then PLATFORM="GitHub"
elif [ -z "\$REMOTE_URL" ];                     then PLATFORM="Local"
else                                                  PLATFORM="Git"
fi

# Garantir repo atualizado
git -C "\$REPO_DIR" pull --quiet --rebase 2>/dev/null || true

# Registrar no log
echo "| \$DATE | \$HOSTNAME_S | \$PLATFORM | \`\$REPO_NAME\` | \`\$BRANCH\` | \$MSG |" >> "\$LOG_FILE"

# Commitar e fazer push
cd "\$REPO_DIR"
git add log.md
git commit --quiet -m "activity: [\$PLATFORM] \$REPO_NAME/\$BRANCH — \$MSG" 2>/dev/null || true
git push --quiet origin main 2>/dev/null || true
HOOK

chmod +x "$HOOK_FILE"

# 4. Configurar git global para usar hooks globais
git config --global core.hooksPath "$HOOKS_DIR"

# 5. Criar log.md se não existir
if [ ! -f "$REPO_DIR/log.md" ]; then
  cat > "$REPO_DIR/log.md" << 'EOF'
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
echo ""
echo "   Hook:      $HOOK_FILE"
echo "   Log:       $REPO_DIR/log.md"
echo "   Repo:      https://github.com/LucasGeek/activity-log"
echo ""
echo "   Próximos passos:"
echo "   • Backfill histórico completo:"
echo "     python3 $REPO_DIR/backfill.py"
echo "   • Ou usando bash:"
echo "     bash $REPO_DIR/backfill.sh"
echo ""
echo "   A partir de agora, todo commit será espelhado automaticamente."
