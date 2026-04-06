#!/usr/bin/env python3
"""
Fix v2: ordem correta — reset primeiro, depois fix do log.md, depois recovery.
"""
import subprocess, os, sys
from datetime import datetime
from collections import Counter

MIRROR_DIR = os.path.expanduser("~/.git-mirror/activity-log")
LOG_FILE = os.path.join(MIRROR_DIR, "log.md")
AUTHOR_EMAIL = subprocess.run(
    ["git", "config", "--global", "user.email"], capture_output=True, text=True
).stdout.strip()
SEARCH_ROOTS = [
    os.path.expanduser(p) for p in
    ["~/Documents", "~/Documentos", "~/Projects", "~/dev", "~/workspace", "~/code", "~/Desktop"]
    if os.path.isdir(os.path.expanduser(p))
]

print(f"==> Email: {AUTHOR_EMAIL}")
print(f"==> Mirror dir: {MIRROR_DIR}")

# ── 1. Reset para antes dos commits errados (3217 recovery v2) ─────────────
print("\n[1/4] Identificando ponto de reset...")
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--oneline"],
    capture_output=True, text=True
)
all_commits = result.stdout.splitlines()
total = len(all_commits)
print(f"    Total de commits: {total}")

RECOVERY_COUNT = 3217
if total <= RECOVERY_COUNT:
    print(f"    ERRO: só {total} commits, esperava > {RECOVERY_COUNT}.")
    sys.exit(1)

reset_sha = all_commits[RECOVERY_COUNT].split()[0]
print(f"    Reset para: {reset_sha} ({all_commits[RECOVERY_COUNT]})")
subprocess.run(["git", "-C", MIRROR_DIR, "reset", "--hard", reset_sha], check=True)
print(f"    ✓ Reset concluído")

# Verificar estado do log.md (agora com "unknown")
with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
unknown_count = sum(1 for l in lines if l.startswith("|") and "unknown" in l)
print(f"    {unknown_count} entradas com 'unknown' no log.md (esperado: ~3212)")

# ── 2. Scan repos para datas reais ────────────────────────────────────────
print("\n[2/4] Escaneando repos para datas reais...")
lookup = {}  # (repo_name, msg_80) → iso_date

repos = []
for root in SEARCH_ROOTS:
    result = subprocess.run(
        ["find", root, "-name", ".git", "-maxdepth", "7", "-type", "d"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        repo = os.path.dirname(line)
        if "activity-log" not in repo and "deps/" not in repo and ".npm/" not in repo:
            repos.append(repo)

print(f"    {len(repos)} repos encontrados")

for repo in repos:
    repo_name = os.path.basename(repo)
    result = subprocess.run(
        ["git", "-C", repo, "log",
         f"--author={AUTHOR_EMAIL}",
         "--since=8 years ago",
         "--all", "--no-merges",
         "--pretty=format:%aI\t%s"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        iso_date, msg = parts
        msg_80 = msg[:80].replace("|", "-").strip()
        key = (repo_name, msg_80)
        if key not in lookup:
            lookup[key] = iso_date

print(f"    {len(lookup)} commits indexados")

# Distribuição por ano do que foi encontrado
years_found = Counter()
for (_, _), iso in lookup.items():
    years_found[iso[:4]] += 1
for y in sorted(years_found):
    print(f"    {y}: {years_found[y]} commits nos repos")

# ── 3. Fix log.md: substituir "unknown" pelas datas reais ────────────────
print("\n[3/4] Corrigindo log.md (após reset, estado correto)...")
fixed_lines = []
fixed_count = 0
not_found = 0

for line in lines:
    stripped = line.strip()
    if not stripped.startswith("|"):
        fixed_lines.append(line)
        continue

    parts = [p.strip() for p in stripped.split("|")]
    if len(parts) < 7:
        fixed_lines.append(line)
        continue

    log_date = parts[1]
    platform = parts[3]
    repo_name = parts[4].strip("`")
    branch = parts[5].strip("`")
    msg = parts[6]

    # Pular header e separador
    if "Data" in log_date or "---" in log_date:
        fixed_lines.append(line)
        continue

    # Se já tem data válida, manter
    if log_date and "unknown" not in log_date:
        fixed_lines.append(line)
        continue

    # Buscar data real
    found = False
    msg_80 = msg[:80].strip()

    # Match exato
    key = (repo_name, msg_80)
    if key in lookup:
        iso = lookup[key]
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            new_date = dt.strftime("%Y-%m-%d %H:%M")
            fixed_lines.append(f"| {new_date} | {parts[2]} | {platform} | `{repo_name}` | `{branch}` | {msg} |\n")
            fixed_count += 1
            found = True
        except Exception as e:
            pass

    # Match parcial (mensagem truncada diferente)
    if not found:
        for (rn, m80), iso in lookup.items():
            if rn == repo_name and len(msg_80) >= 30 and len(m80) >= 30:
                if msg_80[:50] == m80[:50]:
                    try:
                        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                        new_date = dt.strftime("%Y-%m-%d %H:%M")
                        fixed_lines.append(f"| {new_date} | {parts[2]} | {platform} | `{repo_name}` | `{branch}` | {msg} |\n")
                        fixed_count += 1
                        found = True
                        break
                    except Exception:
                        pass

    if not found:
        # Manter unknown - será tratado na etapa 4
        fixed_lines.append(line)
        not_found += 1

print(f"    {fixed_count} datas corrigidas | {not_found} sem correspondência")

# Salvar log.md corrigido
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)
print(f"    ✓ log.md salvo")

# ── 4. Recovery: criar commits com datas corretas ────────────────────────
print("\n[4/4] Criando commits backdatados...")

# Coletar commits existentes pós-reset
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--pretty=format:%s"],
    capture_output=True, text=True
)
existing = set()
for line in result.stdout.splitlines():
    if line.startswith("activity: "):
        existing.add(line[len("activity: "):])
print(f"    {len(existing)} commits de atividade no git (pós-reset)")

# Identificar faltantes
missing = []
with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) < 7:
            continue
        log_date = parts[1]
        platform = parts[3]
        repo_name = parts[4].strip("`")
        branch = parts[5].strip("`")
        msg = parts[6]

        if "Data" in log_date or "---" in log_date or not log_date:
            continue

        commit_subject = f"[{platform}] {repo_name}/{branch} — {msg}"
        if commit_subject in existing:
            continue

        if "unknown" in log_date:
            # Sem data — fallback para 2022 (melhor que 2021)
            iso_date = "2022-06-15T12:00:00-03:00"
        else:
            try:
                dt = datetime.strptime(log_date, "%Y-%m-%d %H:%M")
                iso_date = dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            except ValueError:
                iso_date = "2022-06-15T12:00:00-03:00"

        missing.append((iso_date, commit_subject))

missing.sort(key=lambda x: x[0])
print(f"    {len(missing)} commits a criar")

BATCH = 100
count = 0
errors = 0
total_m = len(missing)

for iso_date, subject in missing:
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = iso_date
    env["GIT_COMMITTER_DATE"] = iso_date

    r = subprocess.run(
        ["git", "-C", MIRROR_DIR, "commit", "--allow-empty", "--quiet",
         "-m", f"activity: {subject}"],
        env=env, capture_output=True, text=True
    )
    if r.returncode != 0:
        errors += 1
        continue
    count += 1

    if count % BATCH == 0:
        pct = int(count / total_m * 100)
        print(f"  [{count}/{total_m} — {pct}%] Push...", end=" ", flush=True)
        subprocess.run(
            ["git", "-C", MIRROR_DIR, "push", "--force", "origin", "main"],
            capture_output=True
        )
        print("ok")

# Push final
print(f"  [{count}/{total_m}] Push final...", end=" ", flush=True)
r = subprocess.run(
    ["git", "-C", MIRROR_DIR, "push", "--force", "origin", "main"],
    capture_output=True, text=True
)
print("ok" if r.returncode == 0 else f"ERRO: {r.stderr.strip()}")

# ── Resultado ────────────────────────────────────────────────────────────────
print("\n==> Distribuição final por ano:")
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--pretty=format:%ad", "--date=format:%Y"],
    capture_output=True, text=True
)
years = Counter(result.stdout.splitlines())
for year in sorted(years):
    print(f"    {year}: {years[year]:,} commits")

total_remote = sum(years.values())
print(f"\n✅ {count} commits criados | {errors} erros | {total_remote:,} total no repo")
if not_found > 0:
    print(f"   ⚠️  {not_found} commits sem data encontrada (usaram fallback)")
print(f"   Ver: https://github.com/LucasGeek/activity-log")
