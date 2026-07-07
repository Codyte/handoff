# Handoff · handoff skill · 2026-07-07 (2ª sessão)

## Goal
Elevar a skill `handoff` a estado-da-arte: 3 melhorias implementadas + fixes do verify ultracode.
Repo: `c:\Users\Carlos_Ortiz\.agents\skills\handoff`.

## State
- HEAD: 74e4a3e (mudanças desta sessão NÃO commitadas — working tree suja de propósito)
- Done:
  - **Matcher `startup|clear`** no hook SessionStart (`ensure_hook`): não dispara em resume/compact.
    Docs oficiais confirmam pipe = lista de strings exatas (não regex, funciona igual). Migração
    aplicada no settings.json real: entry compartilhado (session_inject + cache-widget) preservado
    sem matcher; handoff em entry próprio com matcher, command reparado pro path `.agents`.
  - **Nota de idade no boot**: handoff com mtime ≥1 dia injeta `(written N days ago — verify
    against live state)`; guard `age > 0` evita "-1 days ago" com mtime futuro.
  - **`HEAD:` no template** do SKILL.md (## State) pra detectar drift no resume + nota "sem secrets".
  - Fixes do verify: reparo de command path morto em `--ensure-hook` (skill movida); fail-closed
    em settings.json com shape inesperado (entry não-dict, command:null, hooks:null); README
    alinhado (matcher, migração, "startup e após /clear").
  - Selftest ampliado: _section, install fresh, migração in-place, idempotência, split de entry
    compartilhado, reparo de path, shape inesperado. Tudo verde + smoke FUTURE/STALE/FRESH ok.
  - navindex refeito (header 13 símbolos + __navi__.md + root tree).
- In progress: nada.

## Decisions (and why)
- `.claude/skills/handoff` e `.agents/skills/handoff` = MESMO diretório (junction) — sem sync
  necessário; hook e skill já rodam o código novo.
- Migração de entry compartilhado SEPARA o comando do handoff em entry próprio — matcher in-place
  restringiria session_inject + cache-widget silenciosamente.
- Fail-closed (try amplo + mensagem) em vez de tolerar shapes estranhos — nunca corromper settings.
- YAGNI rejeitados: PreCompact reminder, handoff por branch, `--prune`, `--grep` no ativo.
- Usuário: deixar agentes em curso terminarem, **não spawnar mais agentes** (pedido explícito).
- Não commitado — fluxo do usuário é commitar sob demanda ("commit").

## Next steps (ordered)
1. Se aprovar: `git add -A && git commit` (load_handoff.py, SKILL.md, README.md, __navi__.md,
   .handoff/; conferir se `.navindex-cache.json` está no .gitignore antes do add -A).
2. Nada mais aberto.

## Key files
- load_handoff.py:81 — `ensure_hook(settings=None)`: matcher + migração + reparo de path + fail-closed.
- load_handoff.py:238 — `main()` hook mode com nota de idade (guard `age > 0`).
- load_handoff.py:195 — `_selftest()` com os 7 casos.
- SKILL.md — step 0 (matcher/migração), template `HEAD:`, nota secrets.
- README.md:20-30 — install do hook atualizado.

## Open / blockers
- Nenhum. Mudanças aguardando "commit".
