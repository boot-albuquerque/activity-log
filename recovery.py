#!/usr/bin/env python3
"""
Recovery: lê log.md e cria commits backdatados para entradas sem commit no git.
"""
import subprocess
import os
import sys
from datetime import datetime

MIRROR_DIR = os.path.expanduser("~/.git-mirror/activity-log")
LOG_FILE = os.path.join(MIRROR_DIR, "log.md")

# 1. Coletar subjects dos commits de atividade existentes no git
print("==> Coletando commits existentes no git...")
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--pretty=format:%s"],
    capture_output=True, text=True
)
existing = set()
for line in result.stdout.splitlines():
    if line.startswith("activity: "):
        existing.add(line[len("activity: "):])
print(f"    {len(existing)} commits de atividade no git")

# 2. Parsear log.md e identificar entradas faltantes
print("==> Analisando log.md...")
missing = []
with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Esperado: ['', date, machine, platform, repo, branch, msg, '']
        if len(parts) < 7:
            continue
        log_date = parts[1]
        platform = parts[3]
        repo = parts[4].strip("`")
        branch = parts[5].strip("`")
        msg = parts[6]

        # Pular header
        if "Data" in log_date or "---" in log_date:
            continue
        if not log_date or not platform or not repo:
            continue

        commit_subject = f"[{platform}] {repo}/{branch} — {msg}"

        if commit_subject in existing:
            continue

        # Parsear data: "2026-04-05 19:14"
        try:
            dt = datetime.strptime(log_date.strip(), "%Y-%m-%d %H:%M")
            iso_date = dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
        except ValueError:
            iso_date = "2020-01-01T00:00:00-03:00"

        missing.append((iso_date, commit_subject))

print(f"    {len(missing)} commits faltando no git")

if not missing:
    print("\n✅ Nada a fazer — log.md e git estão em sync!")
    sys.exit(0)

# Ordenar por data
missing.sort(key=lambda x: x[0])

# 3. Criar commits backdatados
BATCH = 100
count = 0
errors = 0
total = len(missing)

print(f"\n==> Criando {total} commits backdatados...")

for iso_date, subject in missing:
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = iso_date
    env["GIT_COMMITTER_DATE"] = iso_date

    result = subprocess.run(
        ["git", "-C", MIRROR_DIR, "commit", "--allow-empty", "--quiet",
         "-m", f"activity: {subject}"],
        env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        errors += 1
        if errors <= 5:
            print(f"  ERRO: {result.stderr.strip()}")
        continue

    count += 1

    if count % BATCH == 0:
        pct = int(count / total * 100)
        print(f"  [{count}/{total} — {pct}%] Fazendo push...", end=" ", flush=True)
        subprocess.run(
            ["git", "-C", MIRROR_DIR, "push", "--quiet", "origin", "main"],
            capture_output=True
        )
        print("ok")

# Push final
if count % BATCH != 0:
    print(f"  [{count}/{total} — 100%] Push final...", end=" ", flush=True)
    r = subprocess.run(
        ["git", "-C", MIRROR_DIR, "push", "origin", "main"],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print("ok")
    else:
        print(f"ERRO: {r.stderr.strip()}")

print(f"\n✅ Concluído! {count} commits criados e sincronizados no GitHub.")
if errors:
    print(f"   ⚠️  {errors} erros ignorados.")
print(f"   Ver: https://github.com/LucasGeek/activity-log")
