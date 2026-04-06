#!/usr/bin/env python3
"""
backfill.py — Sincroniza histórico git local → activity-log
Cross-platform: macOS, Linux, Windows (PowerShell + Git Bash + WSL)

Uso:
  python3 backfill.py
  python backfill.py          # Windows
  python3 backfill.py --since "3 years ago"
"""
import subprocess
import os
import sys
import argparse
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

# ── Configuração ─────────────────────────────────────────────────────────────
def get_config():
    p = argparse.ArgumentParser(description="Backfill git activity")
    p.add_argument("--since", default="5 years ago", help="How far back to scan (default: '5 years ago')")
    p.add_argument("--batch", type=int, default=50, help="Push every N commits (default: 50)")
    p.add_argument("--dry-run", action="store_true", help="Show stats without committing")
    return p.parse_args()

def run(cmd, cwd=None, env=None, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd, env=env)
    return r.stdout.strip() if capture else r.returncode == 0

def git(args, cwd=None, env=None, capture=True):
    return run(["git"] + args, cwd=cwd, env=env, capture=capture)

# ── Detecção de plataforma ────────────────────────────────────────────────────
def detect_platform(remote_url: str) -> str:
    url = remote_url.lower()
    if "gitlab" in url:    return "GitLab"
    if "bitbucket" in url: return "Bitbucket"
    if "github" in url:    return "GitHub"
    if not remote_url:     return "Local"
    return "Git"

# ── Parsing de data ISO 8601 (cross-platform) ────────────────────────────────
def parse_iso(iso: str) -> datetime:
    """Parseia qualquer variação de ISO 8601: +03:00, -04:00, Z, sem timezone."""
    iso = iso.strip()
    # Substituições para compatibilidade
    iso = iso.replace("Z", "+00:00")
    # Remover microsegundos
    if "." in iso:
        iso = iso[:iso.index(".")] + iso[iso.rindex("+") if "+" in iso[10:] else iso.rindex("-") if "-" in iso[10:] else len(iso):]
    # Garantir separador T
    if len(iso) > 10 and iso[10] == " ":
        iso = iso[:10] + "T" + iso[11:]
    # Python < 3.11 não suporta fromisoformat com offset, usar strptime
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        # Fallback: extrair parte sem timezone
        dt_part = iso[:19]  # YYYY-MM-DDTHH:MM:SS
        return datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

def iso_to_display(iso: str) -> str:
    try:
        dt = parse_iso(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown"

# ── Encontrar repos ───────────────────────────────────────────────────────────
def find_repos(search_roots):
    repos = []
    skip = {".npm", "node_modules", "deps", ".cargo", ".gem", "vendor",
            "site-packages", "__pycache__", ".git-mirror"}
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Verificar .git ANTES de filtrar (começa com ponto)
            if ".git" in dirnames:
                repos.append(dirpath)
                dirnames.clear()  # não descer dentro de um repo
                continue
            # Pular diretórios de dependências e ocultos
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
    return repos

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = get_config()

    mirror_dir = str(Path.home() / ".git-mirror" / "activity-log")
    log_file = os.path.join(mirror_dir, "log.md")

    author_email = (
        os.environ.get("GIT_AUTHOR_EMAIL")
        or git(["config", "--global", "user.email"])
    )
    if not author_email:
        print("❌ Email não configurado. Execute: git config --global user.email 'seu@email.com'")
        sys.exit(1)

    machine = run(["hostname", "-s"] if sys.platform != "win32" else ["hostname"])

    print(f"==> Backfill de histórico git para activity-log")
    print(f"    Autor:   {author_email}")
    print(f"    Desde:   {args.since}")
    print(f"    Máquina: {machine}")
    print(f"    Dry run: {args.dry_run}")
    print()

    # Atualizar repo
    if not args.dry_run:
        subprocess.run(["git", "-C", mirror_dir, "pull", "--quiet", "--rebase"],
                       capture_output=True)

    # Carregar log existente para dedup
    existing_entries: set[str] = set()
    if os.path.isfile(log_file):
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("|") and "| Data |" not in line and "---" not in line:
                    existing_entries.add(line.strip())

    # Encontrar repos
    search_roots = [
        str(Path.home() / d)
        for d in ["Documents", "Documentos", "Projects", "dev",
                  "workspace", "code", "Desktop", "src", "repos"]
    ]
    print("==> Buscando repositórios git...")
    repos = find_repos(search_roots)
    print(f"    {len(repos)} repositórios encontrados.")
    print()

    # Coletar commits
    commits = []  # (iso_date, log_date, machine, platform, repo, branch, msg)
    seen_hashes: set[str] = set()

    for repo in repos:
        repo_name = os.path.basename(repo)
        remote = git(["remote", "get-url", "origin"], cwd=repo) or ""

        if "activity-log" in remote.lower():
            continue

        platform = detect_platform(remote)

        result = subprocess.run(
            ["git", "-C", repo, "log",
             f"--author={author_email}",
             f"--since={args.since}",
             "--all", "--no-merges",
             "--pretty=format:%H\t%aI\t%D\t%s"],
            capture_output=True, text=True
        )

        for line in result.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) < 4:
                continue
            hash_val, iso_date, _, msg = parts

            if hash_val in seen_hashes:
                continue
            seen_hashes.add(hash_val)

            # Branch
            branch = git(
                ["name-rev", "--name-only", hash_val],
                cwd=repo
            )
            branch = branch.replace("remotes/origin/", "").split("~")[0].split("^")[0]
            if not branch or branch == "undefined":
                branch = "main"

            log_date = iso_to_display(iso_date)
            msg_clean = msg[:120].replace("|", "-").replace("\n", " ").strip()

            # Dedup por conteúdo da linha
            line_key = f"| {log_date} | {machine} | {platform} | `{repo_name}` | `{branch}` | {msg_clean} |"
            if line_key in existing_entries:
                continue

            commits.append((iso_date, log_date, machine, platform, repo_name, branch, msg_clean))

    # Ordenar por data
    commits.sort(key=lambda x: x[0])

    total = len(commits)
    print(f"==> {total} commits históricos encontrados.")
    print()

    if total == 0:
        print("Nenhum commit novo para sincronizar.")
        return

    if args.dry_run:
        from collections import Counter
        years = Counter(c[1][:4] for c in commits)
        for y in sorted(years):
            print(f"    {y}: {years[y]:,} commits")
        print(f"\n    Total: {total:,} (dry run — nada foi escrito)")
        return

    # Criar commits backdatados
    count = 0
    errors = 0

    for iso_date, log_date, mach, platform, repo_name, branch, msg in commits:
        log_line = f"| {log_date} | {mach} | {platform} | `{repo_name}` | `{branch}` | {msg} |\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)

        commit_msg = f"activity: [{platform}] {repo_name}/{branch} — {msg}"
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = iso_date
        env["GIT_COMMITTER_DATE"] = iso_date

        r = subprocess.run(
            ["git", "-C", mirror_dir, "add", "log.md"],
            capture_output=True
        )
        r = subprocess.run(
            ["git", "-C", mirror_dir, "commit", "--quiet",
             "-m", commit_msg, f"--date={iso_date}"],
            env=env, capture_output=True, text=True
        )
        if r.returncode != 0:
            errors += 1
            continue

        count += 1

        if count % args.batch == 0:
            print(f"    [{count}/{total}] Push...", end=" ", flush=True)
            subprocess.run(
                ["git", "-C", mirror_dir, "push", "--quiet", "origin", "main"],
                capture_output=True
            )
            print("ok")

    # Push final
    print(f"    [{count}/{total}] Push final...", end=" ", flush=True)
    r = subprocess.run(
        ["git", "-C", mirror_dir, "push", "--quiet", "origin", "main"],
        capture_output=True, text=True
    )
    print("ok" if r.returncode == 0 else f"ERRO: {r.stderr.strip()}")

    print(f"\n✅ Backfill concluído! {count} commits sincronizados.")
    if errors:
        print(f"   ⚠️  {errors} erros ignorados.")
    print(f"   Ver: https://github.com/LucasGeek/activity-log")


if __name__ == "__main__":
    main()
