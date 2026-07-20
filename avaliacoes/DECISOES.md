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
