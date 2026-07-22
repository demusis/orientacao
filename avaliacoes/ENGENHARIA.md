# Loop de melhorias de engenharia

Documento vivo do loop que avalia e implementa melhorias de **engenharia** —
funcionamento, documentação e manutenção — no branch `engenharia/melhorias`.
Lido e atualizado a cada iteração.

## Alçada (decidida em 2026-07-22)

- **Só engenharia, preservando comportamento.** Refatoração que mantém o
  comportamento, documentação, testes, tooling/CI, higiene de dependências,
  remoção de código morto. **Nenhuma** mudança de funcionalidade, fluxo, regra
  de negócio ou UX sem aprovação do usuário item a item.
- Respeitar `avaliacoes/DECISOES.md` e o estilo técnico austero (sem
  adjetivação/autoelogio).
- **Segurança inalterada**: não mexer na CSP, autenticação, LGPD, nem reintroduzir
  o que foi removido por decisão.

## Protocolo de cada iteração

1. **Escolher** o item de maior valor do backlog abaixo (ou repovoar o backlog se
   estiver vazio, varrendo as três dimensões).
2. **Implementar** um único item, em escopo pequeno e revisável.
3. **Verificar**: rodar os testes afetados + um núcleo representativo
   (`.venv/Scripts/python.exe -m pytest ...`). Nunca prosseguir com teste
   vermelho. A suíte completa é lenta (rasterização de PDF); a cobertura total
   fica para a CI.
4. **Commitar** no branch `engenharia/melhorias` (um item por commit, mensagem
   clara). Sem deploy, sem tocar a main.
5. **Registrar** no changelog abaixo (o que, por quê) e **repriorizar**.
6. **Parar** ao atingir o teto (~6 itens nesta corrida) ou quando duas rodadas
   seguidas não encontrarem melhoria de alto valor.

## Backlog priorizado (semente — 2026-07-22)

Impacto/esforço/risco em alto·médio·baixo.

| # | Item | Dimensão | Impacto | Esforço | Risco |
|---|---|---|---|---|---|
| 1 | Config de lint+format (ruff) em `pyproject.toml`; corrigir achados triviais (imports não usados) | manutenção | alto | baixo | baixo |
| 2 | `requirements-dev.txt` separando dependências de desenvolvimento (pytest, ruff) | manutenção | médio | baixo | baixo |
| 3 | CI em GitHub Actions rodando pytest (+ ruff) em push/PR | manutenção | alto | médio | baixo |
| 4 | `ARCHITECTURE.md`: mapa de blueprints, services, models, CSP e deploy | documentação | alto | médio | baixo |
| 5 | Seção de desenvolvimento (setup/testes/migração no Windows/.venv) no README ou `CONTRIBUTING.md` | documentação | médio | baixo | baixo |
| 6 | Extrair a checagem repetida de gestor (`current_user.id == orientacao.orientador_id or papel == 'admin'`) para helper/global reutilizável | manutenção | médio | médio | médio |
| 7 | Marcar testes lentos (rasterização de PDF) para a suíte rodar sem estourar tempo | manutenção | médio | baixo | baixo |
| 8 | Varredura de código morto / imports não usados (apoio do ruff) | manutenção | baixo | baixo | baixo |

## Bloqueio a resolver (fora da alçada do loop — decisão do usuário)

**Teste vermelho pré-existente**, descoberto ao rodar a suíte completa (que
estourava o tempo e por isso não era rodada inteira):
`tests/test_revisao_21_07.py::test_conta_desativada_nao_recebe`.

- **Vermelho desde `24dc1ae`** (recurso "alertar o orientador dos atrasos dos
  orientandos"), não relacionado às mudanças do loop.
- **Causa:** `avisos.marcos_atrasados_dos_orientandos` alerta o orientador dos
  marcos vencidos de um orientando **mesmo quando a conta do orientando está
  desativada** (filtra só `Orientacao.status == "ativa"`, não o `Usuario.ativo`
  do orientando). O teste afirma que conta desativada não gera aviso algum.
- **Decisão de comportamento (do usuário):** (a) corrigir o recurso para excluir
  orientandos desativados — provavelmente o certo, não incomodar sobre conta
  inativa; ou (b) atualizar o teste para refletir o novo comportamento.
- **Impacto no loop:** trava a disciplina "suíte verde" e a CI (item 3) até ser
  resolvido. Loop pausado após a iteração 1 para consulta.

## Changelog

- `664d3b3` — Iteração 1: adotar ruff + higiene de imports (I001, F401) em 39
  arquivos. Verificação: suíte verde exceto o vermelho pré-existente acima.
