# Contexto: activity-log & git-mirror

## O que é este repositório

`LucasGeek/activity-log` é um repositório **privado** que espelha automaticamente toda a atividade git do Lucas em qualquer plataforma (GitLab, Bitbucket, repos corporativos, local) para o gráfico de contribuições do GitHub.

O problema: Lucas trabalha em empresas que usam GitLab e Bitbucket. Esses commits **não aparecem no GitHub**, deixando o perfil público vazio apesar de anos de trabalho real.

A solução: um `post-commit` hook global que, a cada commit feito em qualquer repo, faz automaticamente um commit correspondente neste repo — com a data original preservada, sem expor código proprietário.

---

## Arquitetura

```
Commit no GitLab/Bitbucket/local
        ↓
~/.config/git/hooks/post-commit  (hook global)
        ↓
~/.git-mirror/activity-log/      (clone local deste repo)
        ↓
LucasGeek/activity-log (GitHub)  → contribuição aparece no gráfico
```

---

## Arquivos importantes

| Arquivo | Propósito |
|---|---|
| `setup.sh` | Instala o hook e configura a máquina (rodar uma vez por notebook) |
| `backfill.sh` | Sincroniza histórico dos últimos 3 anos de todos os repos da máquina |
| `log.md` | Registro de toda a atividade: data, máquina, plataforma, repo, branch, mensagem |
| `CLAUDE.md` | Este arquivo — contexto para a LLM |

---

## Objetivo ao trabalhar neste repo

Quando o usuário pedir ajuda relacionada a este projeto, o objetivo é:

1. **Garantir que o hook funcione** em qualquer máquina macOS/Linux com bash 3.2+
2. **Não expor informações sensíveis** — o log registra apenas: data, hostname, plataforma, nome do repo, branch e primeira linha da mensagem de commit
3. **Evitar loops** — commits dentro do próprio `activity-log` são ignorados pelo hook
4. **Suportar múltiplas máquinas** — o log usa `git pull --rebase` antes de cada commit para evitar conflitos

---

## Como instalar em um novo notebook

```bash
# Pré-requisito: gh CLI autenticado e SSH configurado para o GitHub
gh repo clone LucasGeek/activity-log /tmp/activity-log-install
bash /tmp/activity-log-install/setup.sh

# Backfill do histórico (opcional, rodar uma vez)
bash /tmp/activity-log-install/backfill.sh
```

---

## Arquivos sensíveis

- `log.md` contém hostnames das máquinas e mensagens de commit — **não tornar este repo público**
- O hook nunca lê conteúdo de arquivos, apenas metadados do commit

---

## Manutenção

- O hook roda automaticamente a cada `git commit` em qualquer repo
- O backfill pode ser re-executado sem duplicar entradas (dedup por hash)
- Para desinstalar: `git config --global --unset core.hooksPath`
