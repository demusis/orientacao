# ARIADNE — Plano incremental: camada institucional

Decorrente do parecer técnico-acadêmico de 19/07/2026. Ordena as lacunas
identificadas para uso em programa stricto sensu em sprints incrementais sobre a
base existente (69 testes; homologação em produção). Estimativas assumem um
desenvolvedor em dedicação parcial, uma semana por sprint, com critério de
aceite objetivo ao fim de cada uma. Nenhuma sprint exige refatoração estrutural
do modelo atual.

## Ordem e dependências

```
A (tipologia/eventos) ──► B (notificações) ──► F (LGPD/infra: recuperação de senha)
        │                                        ▲
        └──► D (coordenação/painel)              │
C (coorientação) — independente                  │
E (exportação PDF) — independente ───────────────┘ (backup/upgrade independem de B)
```

## Sprint A — Tipologia de marcos e eventos do vínculo

Fundação de dados para relatórios e notificações.

- `Marco.tipo` ENUM: `qualificacao | defesa | relatorio_anual | proficiencia | publicacao | outro` (default `outro`; migração com backfill).
- Nova entidade `EventoVinculo`: `orientacao_id`, `tipo` ENUM (`prorrogacao | trancamento | destrancamento | mudanca_titulo`), `fundamentacao` TEXT, `data_inicio`, `data_fim` (nullable), `registrado_por`, `registrado_em`. Prorrogação atualiza `data_fim_prevista` mantendo o histórico; trancamento suspende o vínculo com fundamento datado.
- Formulários e telas correspondentes (admin registra eventos; partes visualizam).
*Aceite: prorrogação altera o prazo com histórico consultável; marcos filtráveis por tipo; auditoria integral.*

## Sprint B — Notificações de prazo

Item de maior impacto: sem lembrete ativo, o controle de fluxo esvazia-se.

- Serviço `notificacoes.py`: composição de avisos por destinatário — marcos a vencer (7 dias) e vencidos, reuniões agendadas (48 h), pendências de presença.
- Envio por e-mail via API HTTP de provedor transacional (Mailgun/SendGrid); no plano gratuito do PythonAnywhere o SMTP é bloqueado, mas as APIs desses provedores constam da lista de domínios permitidos — validar na Sprint.
- Disparo pela Task diária agendada do PythonAnywhere (1 disponível no plano gratuito): comando `flask enviar-notificacoes`, idempotente, com registro em auditoria do que foi enviado.
- Preferência de opt-out por usuário (campo simples em `usuario`).
*Aceite: execução da task envia resumo diário correto em cenário de teste; reexecução no mesmo dia não duplica envios.*
*Risco: dependência de provedor externo (chave de API); mitigação: modo "log-only" configurável para ambientes sem provedor.*

## Sprint C — Coorientação

- Nova associação `orientacao_orientador` (`orientacao_id`, `usuario_id`, `funcao` ENUM `principal | coorientador`), com backfill do orientador atual como `principal`; `Orientacao.orientador_id` preservado como principal (compatibilidade) ou substituído pela associação — decidir na sprint pela via de menor ruptura.
- RBAC: coorientador enxerga o vínculo e assina presenças/atas conforme regra a definir (proposta: coorientador tem leitura integral e pode redigir ata; finalização e pareceres permanecem com o principal).
- Reuniões em grupo: convocação continua restrita ao orientador principal.
*Aceite: vínculo com coorientador funcional em todos os módulos; matriz de permissões coberta por testes.*

## Sprint D — Papel Coordenação e painel agregado

- Novo papel `coordenacao` (RBAC): leitura de todos os vínculos e relatórios, sem edição de conteúdo acadêmico; gestão de eventos de vínculo (Sprint A) migra do admin para a coordenação.
- Painel: discentes por status; marcos vencidos por orientador; tempo desde o início sem marco `qualificacao` concluído; exportação CSV.
*Aceite: coordenação acessa painel e relatórios; admin técnico deixa de acumular função acadêmica; testes de permissão.*

## Sprint E — Exportação assinável

- Geração de PDF de ata finalizada e de parecer (WeasyPrint ou reportlab — avaliar peso da dependência no plano gratuito), com identificador do documento, hash do conteúdo e carimbo de data/hora, destinado a assinatura eletrônica externa (gov.br/SEI).
- Rota de verificação: dado o identificador, confirma hash e status do registro interno.
*Aceite: PDF fiel ao registro; hash publicado confere com o conteúdo; download restrito às partes.*

## Sprint F — LGPD e saneamento de infraestrutura

Pré-requisito para adoção institucional; itens em parte condicionados a decisões externas (jurídico da instituição; upgrade de plano).

- Termo de ciência/uso no primeiro acesso, com aceite datado e versionado.
- Recuperação de senha por e-mail (token expirável; depende da infraestrutura da Sprint B).
- Backup automatizado: task agendada com dump do banco + espelho de `ariadne-uploads/`, retenção definida; instrução de restauração testada.
- Política de retenção e eliminação de dados documentada (inclui justificativas de ausência — potencial dado sensível).
- Condicionais a upgrade de plano: migração SQLite→MySQL (`utf8mb4`), execução da suíte contra MySQL (risco R1 do plano original), remoção da expiração mensal.
*Aceite: aceite do termo registrado; fluxo de recuperação de senha funcional; backup gerado e restauração ensaiada em ambiente limpo.*

## Fora de escopo deliberado

Integração com Sucupira/CAPES, controle de créditos e disciplinas, detecção de
plágio e assinatura eletrônica embutida — pertencem a sistemas institucionais
adjacentes; o ARIADNE deve interoperar (exportação), não os replicar.

## Riscos transversais

| Risco | Mitigação |
|---|---|
| Plano gratuito: 1 task diária, sem SMTP, 512 MB | Sprints B e F projetadas dentro desses limites; upgrade recomendado antes da adoção real |
| Crescimento do esquema sem partição de responsabilidades | Papel `coordenacao` (D) antes de relatórios avançados |
| Dependência de provedor de e-mail | Modo log-only e abstração de provedor no serviço de notificações |
| LGPD sem respaldo jurídico formal | Sprint F entrega o instrumental técnico; enquadramento legal é ato institucional |
