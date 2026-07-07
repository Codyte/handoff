# Handoff · handoff skill · 2026-07-07

## Goal
Auditar a skill `handoff` (funções não usadas) e aplicar melhorias no estilo ponytail (só o que
vale). Repo: `c:\Users\Carlos_Ortiz\.agents\skills\handoff`.

## State
- Done:
  - Auditoria de funções mortas → **zero**. Os 12 símbolos de `load_handoff.py` são alcançáveis;
    cada modo CLI wired + documentado no SKILL.md. `_selftest` é dev-only (via `--selftest`),
    intencional (check rodável do ponytail).
  - Dedup aplicado: extraído `_archive_files(cwd)` (load_handoff.py:74); `history` (:135) e
    `grep` (:165) chamam ele; `open_items` intacto (lê o active, não o archive). Header navindex
    refeito → 13 símbolos.
  - Documentada portabilidade no SKILL.md (seção Notes): o que viaja com o repo (arquivos
    `.handoff/`) vs por-máquina (o hook); máquina nova = `--ensure-hook` 1×.
  - Improvement "hook per-project commitado" **avaliado e rejeitado** (não implementado).
  - Testes desta sessão: `--selftest` ok, `compileall` ok, smoke de `--open/--history/--grep` ok.
- In progress: nada aberto.

## Decisions (and why)
- **Não implementar hook de projeto** (`.claude/settings.json` commitado) — o trust-gate do Claude
  Code pede aprovação da pasta clonada de qualquer jeito, então não pouparia o setup: só troca
  "1 comando por máquina" por "1 trust prompt por clone" (mais fricção), e custaria reader + guard
  de dupla-injeção em cada repo. Net loss / YAGNI.
- **Manter o dedup `_archive_files`** apesar de marginal — o usuário pediu explicitamente pra
  aplicar (ponytail: usuário insiste → faz, sem re-argumentar).
- **Não commitado** — fluxo do usuário é commitar sob demanda; esperar "commit".

## Next steps (ordered)
1. Se aprovar: `git add -A && git commit` das mudanças (load_handoff.py + SKILL.md + .handoff/).
2. Opcional: rodar `navindex` no repo root se quiser o `__navi__.md` global (hoje só há header
   in-file no load_handoff.py).

## Key files
- load_handoff.py:74 — `_archive_files(cwd)`, novo helper (fonte única do glob do archive).
- load_handoff.py:131,161 — `history`/`grep` usando o helper.
- SKILL.md (seção Notes, ~linha 88) — nota "New machine / portability" + rejeição do hook de projeto.

## Open / blockers
- Nenhum. Mudanças não commitadas aguardando "commit".
