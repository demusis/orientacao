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

## Ciclo de 2026-07-21

| Data | Achado | Decisão | Justificativa |
|---|---|---|---|
| 2026-07-21 | O-1 — nenhum backup guardado, com conteúdo real em produção | adiado | Sem condição de desbloqueio declarada. Registre-se o que está em risco: os `.docx` são cópias que os discentes possuem, mas a trilha de auditoria (68 lançamentos), o histórico dos vínculos e os carimbos de data/hora não têm segunda cópia em lugar algum. Reaparece em todo ciclo enquanto não houver pacote recente. |
| 2026-07-21 | Infraestrutura de envio de e-mail | aceito e **concluído** | Implementada em `ae1ab07` (tela `/admin/email`, senha cifrada, fora do backup) e corrigida em `fc412b8`. **Verificada em produção no mesmo dia: o worker entrega pelo `smtp.gmail.com:587` com senha de app.** O remetente precisa ser Gmail; `smtp.office365.com` é bloqueado. Não foi preciso mudar de plano. |
| 2026-07-21 | Diagnóstico da conectividade SMTP — registro de método | — | Vale para os próximos ciclos, porque me custou várias conclusões erradas. Medições feitas **no console não valem para o worker** e vice-versa: em 21/07 o console recusava conexão direta (IPv4 `ConnectionRefused`, IPv6 `Network unreachable`, 4 tentativas cada) enquanto o worker entregava normalmente. As falhas iniciais do worker eram **e-mail digitado incorretamente**, não bloqueio de rede. Diante de sintoma resumido, pedir a mensagem exata da tela antes de inferir causa. |
| 2026-07-21 | Tarefas agendadas para automatizar avisos | **inviável no plano atual** | Verificado na aba Tasks do PythonAnywhere: "Scheduled tasks … only enabled for paid accounts". Vale também para always-on. Consequência: a recuperação de senha permanece viável (parte de requisição web), mas o lembrete **diário automático** não. Desbloqueia com plano pago ou outra hospedagem. |
| 2026-07-21 | Gatilho dos avisos de pendência | aceito — **automático pelo tráfego**, sem botão | Descartados: o botão manual (revisto na mesma conversa) e o endpoint chamado por serviço externo, que exporia porta acionável de fora protegida só por token. A cada requisição verifica-se se os avisos do dia já saíram; em caso negativo, saem. Trava de concorrência por UPDATE condicional em `configuracao_email.avisos_enviados_em`; verificação em memória para que o banco seja consultado uma vez por dia por processo. **Limitação assumida:** promete "no máximo um envio por dia, havendo ao menos uma visita" — não "todo dia às 8h". Com 583 requisições no mês, o risco de um dia sem acesso é baixo. |
| 2026-07-21 | Escopo dos avisos | aceito — **todas as categorias** | Ao orientando, marcos com prazo vencido. Ao orientador, entregas aguardando confirmação, entregas aguardando parecer e atas em rascunho há mais de 15 dias. Cada pessoa recebe **uma** mensagem reunindo o que lhe cabe — quatro e-mails no mesmo minuto seriam lidos como ruído. Cobre o achado U-6 (3 entregas sem parecer), que a decisão anterior, restrita a marcos atrasados, deixaria descoberto. |
| 2026-07-21 | F-3 — sem página de erro 404/500 própria | aceito | Sem dependências, esforço baixo, risco baixo. `errorhandler` para 404 e 500 na identidade visual, com orientação ao usuário. |
| 2026-07-21 | U-6 — 3 entregas sem parecer; U-7 — 5 de 7 contas nunca acessaram; U-1 — atas em uso zero | em aberto | Não são alterações de sistema, e sim apuração de uso que cabe ao responsável. Ficam registrados para que o próximo ciclo compare os mesmos indicadores e verifique se o quadro se moveu. |
