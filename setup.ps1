# setup.ps1 — Instala git-mirror no Windows (PowerShell 5.1+ / PowerShell 7+)
# Para macOS/Linux, use setup.sh
#
# Uso:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned  # (uma vez)
#   .\setup.ps1
#   .\setup.ps1 -ActivityRepo "git@github.com:SeuUser/activity-log.git"

param(
    [string]$ActivityRepo = "git@github.com:LucasGeek/activity-log.git",
    [string]$MirrorDir = "$HOME\.git-mirror"
)

$ErrorActionPreference = "Stop"
$RepoDir = "$MirrorDir\activity-log"
$HooksDir = "$HOME\.config\git\hooks"
$HookFile = "$HooksDir\post-commit"

# ── Verificar dependências ────────────────────────────────────────────────────
Write-Host "==> Verificando dependências..." -ForegroundColor Cyan

# Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Git não encontrado. Instale Git for Windows: https://git-scm.com/download/win" -ForegroundColor Red
    exit 1
}

# Python
$PythonCmd = $null
foreach ($py in @("python", "python3", "py")) {
    if (Get-Command $py -ErrorAction SilentlyContinue) {
        $PythonCmd = $py
        break
    }
}
if (-not $PythonCmd) {
    Write-Host "❌ Python não encontrado. Instale Python 3: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

$PythonVersion = & $PythonCmd --version 2>&1
Write-Host "    Git:    $(git --version)" -ForegroundColor Green
Write-Host "    Python: $PythonVersion" -ForegroundColor Green

# ── 1. Clonar/atualizar repo ─────────────────────────────────────────────────
Write-Host "`n==> Configurando git-mirror..." -ForegroundColor Cyan

if (-not (Test-Path $MirrorDir)) {
    New-Item -ItemType Directory -Path $MirrorDir -Force | Out-Null
}

if (Test-Path "$RepoDir\.git") {
    Write-Host "    Atualizando activity-log..."
    & git -C $RepoDir pull --quiet --rebase 2>$null
} else {
    Write-Host "    Clonando activity-log..."
    & git clone --quiet $ActivityRepo $RepoDir
}

# ── 2. Criar diretório de hooks ───────────────────────────────────────────────
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir -Force | Out-Null
}

# ── 3. Criar post-commit hook (bash — Git for Windows usa Git Bash para hooks)
$HookContent = @'
#!/usr/bin/env bash
# post-commit hook — git-mirror (Windows/Git Bash compatible)

REPO_DIR="$HOME/.git-mirror/activity-log"
LOG_FILE="$REPO_DIR/log.md"

REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
echo "$REMOTE_URL" | grep -qi "activity-log" && exit 0

REPO_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
MSG=$(git log -1 --pretty=%s 2>/dev/null | head -c 120 | tr '|' '-')
HOSTNAME_S=$(hostname -s 2>/dev/null || hostname)

# Data atual cross-platform
DATE=$(python3 -c "from datetime import datetime; print(datetime.now().strftime('%Y-%m-%d %H:%M'))" 2>/dev/null || \
       python  -c "from datetime import datetime; print(datetime.now().strftime('%Y-%m-%d %H:%M'))" 2>/dev/null || \
       date "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")

if echo "$REMOTE_URL" | grep -qi "gitlab";     then PLATFORM="GitLab"
elif echo "$REMOTE_URL" | grep -qi "bitbucket"; then PLATFORM="Bitbucket"
elif echo "$REMOTE_URL" | grep -qi "github";    then PLATFORM="GitHub"
elif [ -z "$REMOTE_URL" ];                      then PLATFORM="Local"
else                                                  PLATFORM="Git"
fi

git -C "$REPO_DIR" pull --quiet --rebase 2>/dev/null || true
echo "| $DATE | $HOSTNAME_S | $PLATFORM | \`$REPO_NAME\` | \`$BRANCH\` | $MSG |" >> "$LOG_FILE"
cd "$REPO_DIR"
git add log.md
git commit --quiet -m "activity: [$PLATFORM] $REPO_NAME/$BRANCH — $MSG" 2>/dev/null || true
git push --quiet origin main 2>/dev/null || true
'@

Set-Content -Path $HookFile -Value $HookContent -Encoding UTF8 -NoNewline

# ── 4. Configurar git global ──────────────────────────────────────────────────
# Converter path Windows para formato Git (forward slashes)
$HooksDirGit = $HooksDir -replace '\\', '/'
& git config --global core.hooksPath $HooksDirGit

# ── 5. Criar log.md se não existir ───────────────────────────────────────────
$LogFile = "$RepoDir\log.md"
if (-not (Test-Path $LogFile)) {
    $LogHeader = @"
# Log de Atividade

| Data | Máquina | Plataforma | Repositório | Branch | Commit |
|------|---------|-----------|-------------|--------|--------|
"@
    Set-Content -Path $LogFile -Value $LogHeader -Encoding UTF8
    & git -C $RepoDir add log.md
    & git -C $RepoDir commit --quiet -m "chore: init activity log"
    & git -C $RepoDir push --quiet origin main
}

# ── Resultado ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "✅ git-mirror instalado com sucesso!" -ForegroundColor Green
Write-Host ""
Write-Host "   Hook:   $HookFile" -ForegroundColor Gray
Write-Host "   Log:    $LogFile" -ForegroundColor Gray
Write-Host "   Repo:   https://github.com/LucasGeek/activity-log" -ForegroundColor Gray
Write-Host ""
Write-Host "   Próximos passos:" -ForegroundColor Yellow
Write-Host "   • Backfill histórico completo:"
Write-Host "     python $RepoDir\backfill.py"
Write-Host ""
Write-Host "   A partir de agora, todo commit será espelhado automaticamente." -ForegroundColor Cyan
