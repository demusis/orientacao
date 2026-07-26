# Registro do loop de revisão e correção

Uma seção por corrida (`/revisar`), uma subseção por volta. Cada achado traz
arquivo:linha, o veredito da verificação adversarial e o destino: commit da
correção, "fora da alçada" (aguardando decisão) ou "hipótese" (não confirmado).
O protocolo do loop está em `.claude/commands/revisar.md`.

## Corrida 2026-07-26 (branch `revisao/2026-07-25`)

### Volta 1

Revisão multi-agente do aplicativo inteiro (4 frentes, 29 candidatos, 24
verificadores; 1 refutado). **10 achados confirmados**, todos dentro da alçada,
todos corrigidos; mais 2 defeitos menores citados fora do teto do relatório,
também corrigidos. Cada correção tem teste que reproduz o cenário em
`tests/test_revisao_26_07.py`.

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `exportacao.py:68/105` — congelado gravava sempre `formato: markdown`, reinterpretando como marcação ata/parecer redigidos como texto — distorção permanente em registro com hash | snapshot grava a coluna `formato` do próprio registro |
| 2 | `backup.py` (expurgo) — uploads apagados antes do commit; falha do commit devolvia o banco com todos os downloads quebrados | `expurgar()` comita a própria transação antes de tocar no disco, espelhando `restaurar()` |
| 3 | `backup.py:55` — isenção de `ata_marco` era incondicional: pacote atual truncado restaurava "com sucesso" apagando as ligações reunião–marco | isenção só vale para pacote cujo manifesto não lista a tabela em `contagens` |
| 4 | `atas.py` (finalizar) — reunião com data futura podia ser finalizada pela tela de detalhe, congelando registro imutável de encontro inexistente | invariante restabelecida no serviço `finalizar_ata`, único ponto por onde toda finalização passa |
| 5 | `avisos.py:334` — lembrete comparava hora de parede da reunião com relógio UTC: reunião de hoje às 08:00 "passava" às 04:00 locais | novo `tempo.agora_local()` (fuso `FUSO_LOCAL`, padrão America/Cuiaba); usado no lembrete, em `Ata.realizada` e nos validadores de finalização. Dependência nova: `tzdata` (Windows/ambientes sem base nativa) |
| 6 | `app/__init__.py:277` — `seed-admin` gravava o e-mail como digitado; com maiúsculas, o único admin nunca autenticava | normaliza `strip().lower()` como o login consulta |
| 7 | `seguranca.py:23` — `/auth/esqueci` com e-mail válido nunca era limitado: vetor de inundação da caixa da vítima e da cota diária de envio | `recuperacao_solicitada` entra na contagem por origem (`ACOES_LIMITADAS`) |
| 8 | `eliminacao.py` — eliminação LGPD não anulava `ConfiguracaoRisco.atualizado_por` (FK pendurada) | coluna incluída no lote de anuláveis |
| 9 | `admin/routes.py` (editar) — admin podia rebaixar orientador com vínculos ativos, deixando orientandos ingeríveis | mudança de papel recusada enquanto houver vínculo ativo no papel atual, com trilha `edicao_papel_recusada` |
| 10 | `modelos.py:50` — arquivo do modelo apagado antes do commit (mesma classe do nº 2) | serviço devolve o caminho; a rota remove após o commit |
| 11 | (fora do teto) editar usuário com e-mail de outra conta → IntegrityError 500 | checagem com mensagem antes de gravar |
| 12 | (fora do teto) flake de fuso em `test_reunioes_agenda.py:836` (`date.today()` local × relógio do modelo) | teste e módulo ancoram no mesmo relógio (`agora_local`) |

Verificação: `ruff check .` limpo; suíte completa verde (ver commit).
Observação de deploy: no PythonAnywhere (Linux) o `zoneinfo` usa a base nativa;
`tzdata` do requirements é para Windows/dev e CI.

### Volta 2

Primeira execução caiu no limite de sessão (3 frentes e 19 verificadores
falharam) — resultado descartado como inconclusivo; retomada do cache em
26/07. **8 achados confirmados** (a maioria nos patches da volta 1 — o loop
revisando a si mesmo), todos corrigidos; **2 plausíveis** registrados como
hipóteses, sem correção.

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `tempo.py:28` — `FUSO_LOCAL` com typo levantava `ZoneInfoNotFoundError` sem tratamento: todo o módulo de reuniões caía em 500 | `agora_local` degrada para UTC com aviso no log (fuso resolvido uma vez, com cache) |
| 2 | `seguranca.py:27` — contar `recuperacao_solicitada` no MESMO teto do login trancava, atrás de um NAT de campus, o login de quem sabe a senha | limite por tela: login conta só falhas (`ACOES_FALHA`); `/auth/esqueci` conta também os pedidos bem-sucedidos (`ACOES_RECUPERACAO`) |
| 3 | `backup.py` — `_limpar_uploads` depois do commit sem guarda de `OSError`: arquivo preso virava 500 de um expurgo já consumado | remoção por arquivo com `try/OSError` e aviso no log (vale também para a restauração) |
| 4 | `admin/routes.py:309` — a guarda da volta 1 barrava mudar o papel, mas não DESATIVAR orientador com vínculo ativo — mesmo estado ingerível, a um checkbox | `validar_edicao` recusa também a desativação (`desativacao_orientador_recusada`) |
| 5 | `avisos.py`/`cronograma.py:90`/`painel.py` — a correção de fuso parou nas reuniões; marcos, rascunhos velhos e o portão diário seguiam em `date.today()` | `tempo.hoje_local()` único para toda data digitada: `Marco.atrasado`, categorias de avisos, `painel.relogio`, `data_conclusao`, portão diário |
| 6 | `admin/routes.py:714` — `db.session.commit()` morto na rota de expurgo (o serviço passou a comitar) | removido, com comentário do porquê |
| 7 | `admin/routes.py:274` — regras novas (papel preso a vínculo, e-mail único) na rota, contrariando o padrão serviços-donos-das-regras | movidas para `usuarios.validar_edicao`; `orienta_vinculo_ativo` unificado (a eliminação usava cópia própria) |
| 8 | `app/__init__.py:266` — sexta cópia inline de `.strip().lower()`; a deriva já tinha se materializado uma vez | `usuarios.normalizar_email` único, usado no login, recuperação, criação (admin e orientador), edição, confirmação de eliminação e seed-admin |

**Hipóteses (PLAUSIBLE, sem correção — reavaliá-las se houver evidência):**

- `exportacao.py:68` — trocar o `formato` do fallback de hash poderia invalidar
  hash de PDF antigo **se** existisse ata/parecer finalizado sem
  `conteudo_congelado` e com `formato="texto"`. O congelamento acontece na
  finalização desde que o snapshot existe, e a produção não tem atas
  finalizadas; sem população afetada, corrigir "de volta" é que reintroduziria
  o defeito nº 1 da volta 1.
- `admin/routes.py` — a pré-checagem de e-mail único é check-then-write; duas
  submissões no mesmo instante ainda estourariam IntegrityError. Com SQLite
  de escritor único e um admin só, a janela é teórica; capturar IntegrityError
  no commit fica anotado para quando houver banco servidor.

### Volta 3

Pendente: nova varredura integral (escopo decidido: aplicativo inteiro a cada
volta), com atenção especial aos patches da volta 2, a caminho do critério de
parada (volta sem achado confirmado).
