# Handoff · handoff skill · 2026-07-31

## Goal
Checkpoint de contexto na skill `handoff`: avisar quando handoff+clear compensa, sem travar sessão.
Repo: `c:\Users\Carlos_Ortiz\.agents\skills\handoff` (= `.claude/skills/handoff`, junction — mesmo
diretório).

## State
- HEAD: f65c9f4 — nada commitado (working tree acumula esta sessão **e** a de 2026-07-07: matcher
  `startup|clear`, nota de idade no boot, `HEAD:` no template, fail-closed no settings).
- Live state: os hooks já estão gravados no `~/.claude/settings.json` real (SessionStart + o novo
  UserPromptSubmit). Sessão rodando na UI da extensão VS Code (`CLAUDE_CODE_ENTRYPOINT=claude-vscode`).
- Done nesta sessão:
  - `--check-context` (hook UserPromptSubmit) + `--context` (leitura manual). Silencioso: só fala se
    ctx ≥ `CTX_WARN_AT` 120k **e** breakeven ≤ `TURNS_WARN` 8 turnos, 1x por banda de 20k
    (estado em `~/.claude/.handoff_ctx_warn`). Nunca bloqueia; disparou de verdade a 123k.
  - `breakeven()`: economia/turno = (ctx − boot) × preço cache-read; custo único = ctx×cr +
    HANDOFF_OUT×out + REDERIVE×cw. Preços do `prices.json` do cache-widget (fallback embutido).
  - `boot_context()`: primeiro turno da própria sessão (cabeça do transcript). Mede ~44k aqui.
  - `_wire()` genérico: `--ensure-hook` fia os 2 hooks (migração/reparo/fail-closed preservados).
  - `spawn_session()` / `--spawn` + `/handoff -f`: em VS Code devolve o atalho (Ctrl+Shift+P >
    Claude Code: New Conversation); fora dele abre console novo com `claude`.
  - Selftest verde (breakeven, context_tokens, entry UserPromptSubmit). navindex regenerado.
- In progress: nada.

## Decisions (and why)
- Limiar fixo NÃO decide — decide o breakeven em turnos restantes. 200k perto do fim = continuar.
- Crescimento por turno cancela dos dois lados da conta → fora do modelo.
- Boot medido do próprio transcript, não mediana de 10 sessões (lia 1.2MB/prompt, mesmo resultado:
  44k vs 41k). Pedido explícito: "saudável, não cirúrgico".
- Bug: `boot_context` lia a CAUDA do arquivo (77k inflado) — o que interessa é a CABEÇA.
- Bug: `$0.087` no corpo do SKILL.md virava o argumento do slash-command (saiu `--spawn.087`);
  escrito "USD 0.087". Cuidado com `$0`/`$1` em exemplos dentro de SKILL.md.
- `/clear` automático é impossível: skill/hook não invocam comandos do harness. A extensão VS Code
  expõe `claude-vscode.newConversation`, mas VS Code não dispara comando de extensão por CLI e a
  extensão não registra handler `vscode://` (activationEvents só `onStartupFinished` + webview).
  Máximo automatizável = keybinding do usuário.
- Rejeitados (YAGNI): calibrar REDERIVE medindo sessões pós-handoff, breakeven em output tokens,
  contar itens de `--open` como proxy de trabalho restante.

## Next steps (ordered)
1. Keybinding opcional no `keybindings.json` do VS Code: tecla → `claude-vscode.newConversation`
   (usuário escolhe a tecla; skill `keybindings-help` cobre o formato).
2. `git add -A && git commit` (load_handoff.py, SKILL.md, README.md, __navi__.md, .handoff/);
   conferir se `.navindex-cache.json` está no .gitignore antes do `-A`.

## Key files
- load_handoff.py:252 — `breakeven()`; :244 `boot_context()`; :277 `spawn_session()`;
  :320 `check_context()`; :172-177 constantes (CTX_WARN_AT, TURNS_WARN, HANDOFF_OUT, REDERIVE).
- load_handoff.py:112 — `_wire()`; :147 `ensure_hook()` (os 2 hooks).
- SKILL.md — seção "Context checkpoint (automatic)"; step 4 com `/handoff -f` + nota VS Code.
- __navi__.md — mapa da pasta, regenerado; ler antes de busca ampla aqui.

## Open / blockers
- Nenhum. Só o commit pendente (2 sessões acumuladas).

## Effort
low para o passo 1 — editar um JSON de keybinding com a tecla que o usuário disser; passo 2 é
mecânico. Suba para medium se o commit exigir mexer no .gitignore ou se o settings.json real
parecer fora do lugar. Raciocínio não é o gargalo aqui.
