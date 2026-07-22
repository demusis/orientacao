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

## Bloqueio resolvido

**Teste vermelho pré-existente** descoberto ao rodar a suíte completa:
`tests/test_revisao_21_07.py::test_conta_desativada_nao_recebe`, vermelho desde
`24dc1ae`. Causa: `avisos.marcos_atrasados_dos_orientandos` alertava o orientador
sobre marcos vencidos de orientando com **conta desativada**.

Decisão do usuário: **corrigir o recurso**. Corrigido em `c06fabb` (na main,
por ser defeito de produto; trazido ao branch via merge `bab4216`) — passou a
exigir `Orientacao.orientando.has(ativo=True)`. Suíte verde restaurada. CI
(item 3) desbloqueada.

## Changelog

- `664d3b3` — Iteração 1: adotar ruff + higiene de imports (I001, F401) em 39
  arquivos. Verificação: suíte verde exceto o vermelho pré-existente acima.
- `493fe39` — Iteração 2: `requirements-dev.txt` (pytest + ruff), removendo
  pytest do runtime. Verificação: suíte verde.
- `89ed235` — Iteração 3: modernizações UP do ruff (UP017 datetime.UTC, UP012
  encode) + limpeza de imports. Verificação: suíte verde; lint I/F401/UP limpo.
- `80ec6a0` — Iteração 4: resolver os 10 achados manuais do ruff (B904, E741,
  B011, B018, F841, E702). `ruff check .` passa sem achados. Verificação: testes
  dos arquivos tocados verdes.

Restam: CI (GitHub Actions, agora com pytest + ruff como gates) e docs
(ARCHITECTURE.md, seção de desenvolvimento).

## Backlog restante (repriorizado)

| # | Item | Dimensão | Impacto | Esforço | Risco |
|---|---|---|---|---|---|
| 3 | CI em GitHub Actions (pytest + ruff) — desbloqueada | manutenção | alto | médio | baixo |
| 4 | `ARCHITECTURE.md` | documentação | alto | médio | baixo |
| 5 | Seção de desenvolvimento (setup/testes/migração) no README/CONTRIBUTING | documentação | médio | baixo | baixo |
| — | Modernizações do ruff (UP017, UP012) — autofix seguro | manutenção | baixo | baixo | baixo |
| 6 | Extrair checagem de gestor repetida para helper/global | manutenção | médio | médio | médio |
| — | Manuais do ruff (E702, F841, B011/B018/B904, E741) | manutenção | baixo | baixo | baixo |
