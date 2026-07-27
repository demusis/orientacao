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

Varredura integral com atenção aos patches da volta 2. A primeira execução
também caiu no limite de sessão (21 verificadores pendentes); os **9 achados
já confirmados** (6 distintos após fusão de duplicatas) foram corrigidos
enquanto a retomada completa as verificações restantes — se elas confirmarem
algo novo, entra em volta complementar.

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `indicadores.py:118` — `fluxo_de_marcos` contava atraso pelo dia UTC: o relatório de avaliação divergia de todas as telas entre 20h e 24h locais | `hoje_local()` também no indicador (único ponto do módulo que compara data digitada) |
| 2 | `admin/routes.py:664` — restaurar backup em que a conta do executor vem desativada/sem papel de admin trancava o operador para fora (login_user silenciosamente falha em conta inativa) | `restaurar()` garante a linha do executor ativa, admin e com a senha da sessão corrente — mesmo espírito da inserção quando ela nem consta do pacote |
| 3 | `admin/forms.py:82` — criação de vínculo aceitava fim previsto anterior ao início; o relógio de risco ficava mudo exatamente para o vínculo com data errada | mesmo validador do `AjusteDatasForm` no `OrientacaoForm` |
| 4 | `tempo.py:31` — `ZoneInfo("")` levanta `ValueError`, não `ZoneInfoNotFoundError`: `FUSO_LOCAL=` em branco ainda derrubava tudo | `_fuso` captura também `ValueError` |
| 5 | `backup.py:206/340` — arquivo preso engolido só no log: expurgo anunciado como completo com dado pessoal remanescente; e na restauração o mesmo arquivo estourava 500 na regravação, pós-commit | `_limpar_uploads` devolve os presos; expurgo e restauração os REPORTAM na tela (`arquivos_presos`/`arquivos_pendentes`); a regravação é guardada por arquivo |
| 6 | `avisos.py:637` — trocar o portão diário para `hoje_local` sem migração: marcador gravado na janela 20h–24h (dia UTC seguinte) calaria os avisos de um dia local inteiro | migração `e7a1c94d20b8` anula o marcador apenas quando está no futuro do dia local (`avisos_entregues` fica, evitando duplicatas) |

**Complemento (retomada das 21 verificações pendentes):** os 5 achados graves
coincidiram com os já corrigidos acima; 3 refutados; sobraram e foram
corrigidos:

| # | Achado | Correção |
|---|---|---|
| 7 | `tempo.py:54` — aviso de fuso inválido a cada chamada (50 marcos = 50 linhas por requisição) | aviso movido para dentro do `_fuso` cacheado: uma linha por nome inválido |
| 8 | quatro cópias divergentes do os.remove tolerante pós-commit (modelo, eliminação LGPD, backup, rollback de upload) | `uploads.remover_do_disco` único, devolvendo os presos; TODAS as telas passam a exibi-los (eliminação LGPD e modelo inclusive — antes só o log sabia) |
| 9 | (plausível) normalização de e-mail exigida de cada chamador de `criar_usuario`/`validar_edicao` | normalização dentro dos dois serviços (idempotente) |
| 10 | `validar_edicao` consultava `orienta_vinculo_ativo` duas vezes no mesmo submit | fato calculado uma vez |

Verificação: `ruff check .` limpo; testes da corrida + backup verdes; suíte
completa verde (ver commit).

### Volta 4

Varredura integral com atenção aos patches da volta 3. Também caiu no limite
de sessão na primeira execução (10 verificações pendentes, retomadas do
cache); os achados já confirmados — todos sobre os patches de `restaurar()`,
a migração e o registro de entregas — foram corrigidos: **10 confirmados, 6
distintos**.

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `backup.py:365` — a guarda da regravação só capturava OSError; membro de ZIP com CRC podre levanta `BadZipFile`/`zlib.error` — 500 pós-commit de novo, uma classe de exceção ao lado | guarda ampliada para `(OSError, BadZipFile, zlib.error)`; falha vira pendência no relatório |
| 2 | `backup.py:330` — o reforço do executor não zerava `senha_provisoria` vinda do pacote: o restaurador ficava preso na tela de troca obrigatória | `senha_provisoria=False` no mesmo UPDATE |
| 3 | `backup.py:311` — no PostgreSQL, a inserção do executor (sem id) rodava ANTES de `_ajustar_sequencias`: sequência defasada colidia com id explícito do pacote | sequências ajustadas antes da inserção |
| 4 | `backup.py:378` — preso na limpeza mas regravado com sucesso entrava em `arquivos_pendentes`: alerta falso mandava o admin "corrigir" arquivo correto | pendência = (presos − regravados) ∪ não-gravados |
| 5 | migração `e7a1c94d20b8` — `>` deixava vivo o marcador igual a hoje (gravado ontem à noite pelo relógio antigo), calando um dia de avisos; e anular sem realinhar o dia de `avisos_entregues` reenviaria o lote inteiro | migração usa `>=` E realinha o dia do registro de entregues ao dia local, preservando a lista que evita duplicatas |
| 6 | `eliminacao.py`/expurgo — e-mail do titular sobrevivia em `ConfiguracaoEmail.avisos_entregues` (campo fora do expurgo pela credencial SMTP): retenção silenciosa após eliminação certificada | eliminação raspa o e-mail do titular do registro; expurgo anula o registro inteiro (a credencial fica) |

Verificação: `ruff check .` limpo; testes da corrida + backup + eliminação
verdes; suíte completa verde (ver commit).

### Volta 5

Retomada das 10 verificações pendentes da volta 4 (o restante caiu no limite
de sessão e o modelo passou a Opus 4.8). **7 confirmados, 2 refutados** (a
migração `>=` que a própria volta 4 já corrigira); os confirmados eram 2
defeitos substantivos + cleanups sobre os patches recentes.

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `backup.py` (restaurar) — a restauração troca toda a base mas deixa `ConfiguracaoEmail.avisos_entregues` (fora do pacote) com e-mails em claro de contas que deixaram de existir: mesma retenção silenciosa que expurgo/eliminação já tratam | `restaurar()` anula `avisos_entregues` antes do commit |
| 2 | `auth/routes.py:86` — login em conta desativada com a senha CERTA confirmava um par de credenciais válido sem deixar trilha nem contar para o limite por origem | registra `login_falho` (motivo `conta_desativada`) e passa a ser limitado |
| 3 | `avisos.py` — cada categoria recalculava `hoje_local()`; se a coleta cruzasse a meia-noite local, um marco do dia que virou não caía nem em "vencidos" (`< hoje`) nem "a vencer" (`>= hoje`) — a virada de dia que o módulo evita | `coletar()` calcula `hoje` uma vez e o passa a todas as categorias (fecha o buraco e o recálculo por iteração em `atas_em_rascunho`) |
| 4 | `admin/routes.py` — quatro blocos de flash divergentes para arquivo preso pós-commit | helper único `_avisar_arquivos_presos(nomes, acao)`; o caso da restauração (semântica de "regravado", não "removido") fica à parte |
| 5 | `admin/routes.py:86`, `orientandos/routes.py:49` — `normalizar_email` repetido na rota, já que `criar_usuario` normaliza no ponto único | chamadas redundantes removidas (a de `editar` fica: o valor também alimenta a gravação) |

**Refutados:** os dois achados sobre o `>` da migração — a volta 4 já a mudara
para `>=` e realinhara `avisos_entregues`; a revisão leu o diff antes desse
commit.

**Hipóteses (PLAUSIBLE, sem correção):**

- Migração `e7a1c94d20b8` para fuso **a leste de UTC**: o realinhamento de
  `avisos_entregues` só dispara para dia futuro; num fuso onde o dia UTC antigo
  cai no passado local, poderia reenviar o lote no dia do deploy. ARIADNE roda
  em Cuiabá (UTC−4, a oeste), onde o caso não ocorre; anotado para quem mudar
  `FUSO_LOCAL` para leste.
- Regra "não finalizar reunião futura" existe no validador do formulário de ata
  rápida (UX, momento da criação) e em `finalizar_ata` (momento da
  finalização): pontos de ciclo de vida distintos, mensagens contextuais. Sem
  ponto único comum aos dois; mantida a duplicação deliberada.

Verificação: `ruff check .` limpo; testes das áreas tocadas verdes; suíte
completa verde (ver commit).

**Correção de processo (descoberta na volta 5).** Ao rodar a suíte completa
capturando o código de saída real, veio à luz que
`tests/test_backup_ata_marco.py::test_restauracao_tolera_pacote_sem_ata_marco`
estava **vermelho desde a volta 1** e passou despercebido: os comandos
`pytest ... | tail` faziam o código de saída ser o do `tail` (sempre 0), e as
notificações de tarefa reportavam "exit code 0" enganosamente. O teste é
pré-existente e sua premissa foi (corretamente) invalidada pela volta 1: ele
simulava um "pacote antigo" tirando só o `ata_marco.json` mas deixando a tabela
no manifesto — que é justamente o **pacote moderno truncado** que a volta 1
passou a recusar para não apagar em silêncio as ligações reunião↔marco. Um
pacote antigo de verdade também não traz a tabela no manifesto. O teste foi
corrigido para simular o pacote antigo fielmente (as duas facetas — aceitar
antigo, recusar truncado — já estão cobertas em `test_revisao_26_07.py`).
Daqui em diante a suíte é executada sem `| tail`, para o código de saída do
`pytest` não ser mascarado. As afirmações "suíte completa verde" das voltas 1
a 4 valem para todo o resto da suíte, exceto este único teste.

### Volta 6

Primeira volta a rodar **sem cair no limite de sessão**, e a mais enxuta: 6
candidatos, **4 achados (2 confirmados, 2 plausíveis)**, 2 refutados. Os dois
confirmados são, de novo, extensões triviais dos patches de `backup.py`
(restaurar) — o poço fundo desta corrida —, agora mecânicas:

| # | Achado (arquivo:linha) | Correção |
|---|---|---|
| 1 | `backup.py:383` — a guarda da regravação cobria `OSError/BadZipFile/zlib.error`, mas não `EOFError`, que o `zipfile` levanta para membro com payload truncado — 500 pós-commit outra vez, uma exceção ao lado | `EOFError` somado à tupla do `except` |
| 2 | `backup.py:348` — a restauração anulava `avisos_entregues` (volta 5), mas não `avisos_enviados_em`/`avisos_tentados_em`: marcador de "hoje" da base anterior calaria os avisos do dia para os usuários recém-restaurados | os três marcadores do disparo diário zerados na restauração |
| 3 (PLAUSIBLE) | `eliminacao.py:281` — `_raspar_registro_de_avisos` tratava `ValueError` do `json.loads` mas chamaria `.get()` sobre JSON válido não-objeto (`null`, `[]`) → `AttributeError` num caminho LGPD | guarda `isinstance(guardado, dict)`, como a migração já fazia |

**Refutados (bom sinal de convergência):** o `hoje=` uniforme nas três
categorias que o ignoram (uniformidade intencional, não código morto) e a
suposta duplicação do validador de datas entre formulários (é a mesma regra
simples, não defeito).

**Hipótese (PLAUSIBLE, sem correção):** a regra "fim posterior ao início" vive
só na camada de formulário; um chamador futuro não-formulário poderia gravar
intervalo invertido. Todos os pontos de entrada atuais (formulários de admin e
de orientandos) validam; sem chamador não-formulário, não há falha
reproduzível. Anotada para quando surgir uma via programática (import, API).

Verificação: `ruff check .` limpo; `pytest` sem `| tail`, exit 0 (ver commit).
