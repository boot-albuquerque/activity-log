#!/usr/bin/env python3
"""
Fix v3: Mensagens estão vazias nas entradas unknown.
Estratégia: match por posição (ordem cronológica por repo).
Para cada repo, conta entradas unknown, pega N commits reais ordenados e usa as datas.
"""
import subprocess, os, sys
from datetime import datetime
from collections import defaultdict, Counter

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

print(f"Email: {AUTHOR_EMAIL}")

# ── 1. Reset: remover commits errados ────────────────────────────────────────
print("\n[1/5] Reset...")
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--oneline"],
    capture_output=True, text=True
)
all_commits = result.stdout.splitlines()
total = len(all_commits)
print(f"    Total: {total} commits")

RECOVERY_COUNT = 3217
if total > RECOVERY_COUNT:
    reset_sha = all_commits[RECOVERY_COUNT].split()[0]
    print(f"    Reset para: {reset_sha}")
    subprocess.run(["git", "-C", MIRROR_DIR, "reset", "--hard", reset_sha], check=True)
    print(f"    ✓ Reset concluído")
else:
    print(f"    Já está no estado correto (< {RECOVERY_COUNT} commits)")

# Ler log.md após reset (com "unknown")
with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

unknown_count = sum(1 for l in lines if l.startswith("|") and "| unknown |" in l)
print(f"    {unknown_count} entradas unknown no log.md")

# ── 2. Scan repos e coletar datas por repo (ordenadas) ───────────────────────
print("\n[2/5] Escaneando repos...")
# Mapear repo_name → lista de iso_dates ordenadas
repo_dates = defaultdict(list)
repo_paths = {}  # repo_name → caminho (pode ter múltiplos, guarda todos)

repos = []
for root in SEARCH_ROOTS:
    result = subprocess.run(
        ["find", root, "-name", ".git", "-maxdepth", "7", "-type", "d"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        repo = os.path.dirname(line)
        if "activity-log" not in repo and "/deps/" not in repo and "/.npm/" not in repo:
            repos.append(repo)

print(f"    {len(repos)} repos encontrados")

for repo in repos:
    repo_name = os.path.basename(repo)
    result = subprocess.run(
        ["git", "-C", repo, "log",
         f"--author={AUTHOR_EMAIL}",
         "--since=8 years ago",
         "--all", "--no-merges",
         "--pretty=format:%aI\t%s",
         "--reverse"],  # cronológico: mais antigo primeiro
        capture_output=True, text=True
    )
    dates_msgs = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) >= 1 and parts[0]:
            iso_date = parts[0].strip()
            msg = (parts[1].strip() if len(parts) > 1 else "")[:80]
            dates_msgs.append((iso_date, msg))

    if dates_msgs:
        # Acumular datas para este repo (múltiplos repos com mesmo nome são mergeados)
        if repo_name not in repo_paths:
            repo_paths[repo_name] = []
        repo_paths[repo_name].append(repo)
        repo_dates[repo_name].extend(dates_msgs)

# Ordenar datas de cada repo (mais antigo primeiro)
for name in repo_dates:
    repo_dates[name].sort(key=lambda x: x[0])

print(f"    Repos com dados: {len(repo_dates)}")
for name, entries in sorted(repo_dates.items(), key=lambda x: -len(x[1]))[:10]:
    years = Counter(e[0][:4] for e in entries)
    print(f"      {name}: {len(entries)} commits — {dict(sorted(years.items()))}")

# ── 3. Fix log.md: atribuir datas por posição ────────────────────────────────
print("\n[3/5] Corrigindo log.md por posição...")

# Contar entradas unknown por repo (mantendo ordem)
repo_unknown_idx = defaultdict(int)  # repo_name → próximo índice a usar no repo_dates

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

    # Pular header/separator e entradas com data válida
    if "Data" in log_date or "---" in log_date:
        fixed_lines.append(line)
        continue
    if log_date and "unknown" not in log_date:
        fixed_lines.append(line)
        continue
    if not repo_name:
        fixed_lines.append(line)
        continue

    # Buscar próxima data disponível para este repo
    idx = repo_unknown_idx[repo_name]
    if repo_name in repo_dates and idx < len(repo_dates[repo_name]):
        iso_date, real_msg = repo_dates[repo_name][idx]
        repo_unknown_idx[repo_name] += 1

        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            new_date = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            # Fallback manual parsing
            try:
                # "2026-03-30T21:46:13-04:00" → strip timezone
                date_part = iso_date[:19]  # "2026-03-30T21:46:13"
                dt = datetime.strptime(date_part, "%Y-%m-%dT%H:%M:%S")
                new_date = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                new_date = "2024-01-01 12:00"

        # Usar mensagem real se a do log.md está vazia
        use_msg = msg if msg.strip() else real_msg
        fixed_lines.append(
            f"| {new_date} | {parts[2]} | {platform} | `{repo_name}` | `{branch}` | {use_msg} |\n"
        )
        fixed_count += 1
    else:
        fixed_lines.append(line)
        not_found += 1

print(f"    {fixed_count} datas corrigidas | {not_found} sem correspondência")

# Salvar log.md corrigido
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)
print(f"    ✓ log.md salvo")

# Verificar distribuição no log.md
year_dist = Counter()
for l in fixed_lines:
    if l.startswith("|") and "| Data |" not in l and "unknown" not in l:
        parts = l.split("|")
        if len(parts) > 2:
            d = parts[1].strip()
            if len(d) >= 4 and d[:4].isdigit():
                year_dist[d[:4]] += 1
print("    Distribuição por ano no log.md:")
for y in sorted(year_dist):
    print(f"      {y}: {year_dist[y]:,}")

# ── 4. Recovery: criar commits backdatados ────────────────────────────────────
print("\n[4/5] Criando commits backdatados...")

result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--pretty=format:%s"],
    capture_output=True, text=True
)
existing = set()
for line in result.stdout.splitlines():
    if line.startswith("activity: "):
        existing.add(line[len("activity: "):])
print(f"    {len(existing)} commits existentes no git")

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
            iso_date = "2024-01-15T12:00:00-03:00"
        else:
            try:
                dt = datetime.strptime(log_date, "%Y-%m-%d %H:%M")
                iso_date = dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")
            except ValueError:
                iso_date = "2024-01-15T12:00:00-03:00"

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

print(f"  [{count}/{total_m}] Push final...", end=" ", flush=True)
r = subprocess.run(
    ["git", "-C", MIRROR_DIR, "push", "--force", "origin", "main"],
    capture_output=True, text=True
)
print("ok" if r.returncode == 0 else f"ERRO: {r.stderr.strip()}")

# ── 5. Resultado ────────────────────────────────────────────────────────────
print("\n[5/5] Distribuição final:")
result = subprocess.run(
    ["git", "-C", MIRROR_DIR, "log", "--pretty=format:%ad", "--date=format:%Y"],
    capture_output=True, text=True
)
years = Counter(result.stdout.splitlines())
total_commits = 0
for year in sorted(years):
    print(f"    {year}: {years[year]:,} commits")
    total_commits += years[year]

print(f"\n✅ {count} commits criados | {errors} erros | {total_commits:,} total")
if not_found > 0:
    print(f"   ⚠️  {not_found} sem data real encontrada")
print(f"   Ver: https://github.com/LucasGeek/activity-log")
