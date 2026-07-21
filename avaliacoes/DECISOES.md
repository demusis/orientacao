# Registro de decisões dos ciclos de avaliação

Este arquivo dá memória ao ciclo. Sem ele, cada rodada reapresentaria achados já
recusados. Preenchido ao fim de cada `/avaliar`, depois que o responsável decide.

Valores de **Decisão**: `aceito` (será implementado), `recusado` (não será feito; só volta
à pauta mediante evidência nova) ou `adiado` (fica na fila, com a condição que o
desbloqueia registrada na justificativa).

| Data | Achado | Decisão | Justificativa |
|---|---|---|---|
| 2026-07-20 | Auditar leituras (quem visualizou ata, documento, painel) | recusado | Criaria rastro de comportamento individual dos orientandos, ampliando o dever de proteção sob a LGPD sem ganho proporcional. A medição de uso passa a ser agregada (`services/indicadores.py`). |
| 2026-07-20 | Ciclo de avaliação agendado automaticamente | recusado | Optou-se por disparo sob demanda (`/avaliar`): com um operador, relatórios automáticos se acumulariam sem leitura. |
| 2026-07-20 | Ciclo implementar sozinho itens de baixo risco | recusado | O sistema está em uso real; toda alteração passa por aprovação explícita. |
| 2026-07-21 | Tipo e etapa do marco compartilhavam três rótulos (qualificação, publicação, defesa) | aceito | Separados por natureza: tipo é o ato datado, etapa é o período. Intersecção vazia por construção, protegida por teste. Migração `d7b3f915a6c8`. |
| 2026-07-21 | Tipos de marco "apresentação em evento" e "proficiência em idioma" | recusado | O tipo não altera comportamento algum do sistema; só se justifica para ato que o orientador aprecia, assina ou julga em banca. Proficiência é exame institucional sem participação do orientador. Ambos permanecem registráveis como "outro". |
| 2026-07-21 | Registro de eventos do vínculo (prorrogação, trancamento, destrancamento) | aceito | Removidos: registravam decisões que o sistema depois ignorava. O trancamento não impedia nada nem suspendia a contagem de atraso; a prorrogação concorria com o ajuste de datas, que passou a exigir fundamentação. Mudança de título permanece, pela tela do orientador. |
| 2026-07-21 | Remover "suspensa" de `STATUS_ORIENTACAO` | adiado | Nenhuma tela a apõe desde a remoção do trancamento, mas retirá-la do Enum custa mais uma migração sobre `orientacao` e quebraria a leitura de registro legado. Desbloqueia junto de outra migração que já toque essa tabela. |
| 2026-07-21 | `sa.Enum` não gera `CHECK` no banco (`create_constraint=False` desde SQLAlchemy 1.4) | adiado | Descoberto ao testar `d7b3f915a6c8`: as tipologias são impostas só pelo `SelectField`, e o banco aceita qualquer texto. Vale rever ao migrar para PostgreSQL, onde o tipo nativo passaria a valer. |
