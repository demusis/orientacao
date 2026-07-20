---
description: Ciclo de avaliação do ARIADNE — diagnostica operação, uso e funcionalidade e propõe ajustes
---

# Ciclo de avaliação do ARIADNE

Produz um diagnóstico fundamentado em evidência e uma proposta priorizada de ajustes.

**Este comando não altera a aplicação.** Ele apenas lê, mede e propõe. Qualquer mudança
depende de aprovação explícita do usuário, item a item, em conversa posterior. Os únicos
arquivos que ele escreve são o relatório do ciclo e o registro de decisões.

Se qualquer etapa não puder ser cumprida (produção fora do ar, console indisponível),
**registre a lacuna no relatório** em vez de suprimi-la ou de substituí-la por conjetura.
Um indicador ausente é um achado sobre o ciclo, não um detalhe a omitir.

## 1. Memória do ciclo anterior

Leia `avaliacoes/DECISOES.md` e o relatório mais recente em `avaliacoes/`.

- Um achado **recusado** não volta como proposta. Só reaparece se houver evidência nova, e
  nesse caso o relatório deve dizer qual é a evidência nova e que houve recusa anterior.
- Um achado **adiado** volta, indicando desde quando aguarda.
- Um achado **aceito** vira item de verificação: foi implementado? o indicador
  correspondente se moveu?

Se `avaliacoes/` não existir, este é o primeiro ciclo: crie o diretório e o
`DECISOES.md` com o cabeçalho da tabela.

## 2. Evidência

Colete o snapshot de **produção** pelo console do PythonAnywhere:

```bash
cd ~/ariadne && set -a && . ./.env && set +a && venv/bin/flask indicadores --json --dias 30
```

Se a produção estiver inacessível, use a base local e **declare isso no relatório** —
números de desenvolvimento não sustentam conclusões sobre adesão.

Compare cada número com o snapshot em anexo do relatório anterior. Variação é o principal
gerador de achados: o que piorou vira achado; o que melhorou fecha o item que o originou.

## 3. Operação

Verifique, pelo console e pelos logs:

- **Expiração do site** (plano gratuito): quantos dias faltam. Menos de 7 é achado urgente.
- **Log de erros**: `ls -l` e `tail` em `/var/log/<dominio>.error.log`; compare o horário
  com `date`. Entradas novas desde o último ciclo são achado.
- **Reinícios**: `grep "Starting uWSGI" /var/log/<dominio>.server.log | tail` — reinícios
  não explicados por deploy merecem investigação.
- **Divergência repositório × servidor**: `git log --oneline -1` em ambos.
- **Tamanho**: banco (`ls -lh instance/`) e uploads (`du -sh`), contra o limite do plano.
- **Backup**: existe cópia recente do banco e da pasta de uploads? A ausência é achado
  permanente até que a Sprint F o resolva.
- **Senha do administrador de produção**: continua em texto claro em
  `deploy-credenciais.txt`?

## 4. Uso

Interprete os indicadores — não os repita. Cada leitura abaixo é um achado potencial:

- `adesao.nunca_acessaram` > 0 em conta ativa: alguém recebeu credencial e não entrou.
  Distinga conta recém-criada de conta antiga ociosa.
- `adesao.sem_acesso_ha_30d` / `_90d`: abandono.
- `vinculos.ativos_sem_marco` > 0: vínculo formalizado sem cronograma — o núcleo do
  sistema não está sendo usado naquele vínculo.
- `marcos.atrasados` e `marcos.aguardando_confirmacao`: o segundo indica que o orientando
  entregou e o orientador não fechou o ciclo.
- `marcos.sem_etapa_classificada`: campo introduzido e não adotado.
- `documentos.versoes_correntes_sem_parecer`: trabalho entregue à espera de avaliação.
- `atas.rascunhos_ha_mais_de_15d`: reunião registrada e nunca formalizada.
- `trilha.acoes_no_periodo`: funcionalidade **sem nenhuma ocorrência** no período é
  candidata a problema de descoberta ou a remoção. Confronte com a lista de rotas: o que
  existe no sistema e não aparece na trilha?

Cuidado com amostra pequena: com poucos usuários, um número isolado não sustenta
conclusão. Diga "1 de 3 vínculos", não "33% dos vínculos".

## 5. Funcionalidade

- Coteje com `ROADMAP.md`: Sprints B (notificações), D (coordenação/painel agregado) e F
  (LGPD/infra) seguem pendentes. O uso real justifica antecipar alguma?
- Pontos cegos conhecidos: nenhuma leitura é auditada (decisão deliberada de 20/07/2026 —
  não reabrir sem evidência nova); não há tratamento de erro 404/500 personalizado; não há
  recuperação de senha.
- O que o uso sugere que falta e não está no ROADMAP?

## 6. Qualidade

Se houve mudança relevante de código desde o ciclo anterior, acione `/code-review` e use
o resultado como entrada — não refaça essa análise à mão. Havendo poucos commits, diga
que não se aplicou e por quê.

## 7. Síntese

Monte a proposta priorizada. Regras:

- **Todo item cita evidência concreta**: número do indicador, arquivo:linha, ou entrada de
  log. Item sem evidência não entra no relatório — vai, no máximo, para uma seção de
  "hipóteses a observar no próximo ciclo".
- Classifique **impacto** (alto/médio/baixo), **esforço** (alto/médio/baixo) e **risco da
  mudança** (alto/médio/baixo).
- Ordene por impacto e, em empate, por menor esforço.
- Máximo de 7 itens na proposta. Uma lista longa não é priorização.

## 8. Registro

Grave `avaliacoes/AAAA-MM-DD.md` com esta estrutura:

```markdown
# Avaliação — AAAA-MM-DD

## 1. Verificação do ciclo anterior
## 2. Indicadores          (tabela: indicador | agora | ciclo anterior | variação)
## 3. Achados
### 3.1 Operação
### 3.2 Uso
### 3.3 Funcionalidade
## 4. Proposta priorizada  (tabela: item | dimensão | evidência | impacto | esforço | risco)
## 5. Lacunas deste ciclo  (o que não foi possível medir e por quê)

<details><summary>Anexo: snapshot dos indicadores</summary>

```json
{ ... }
```
</details>
```

O anexo em JSON é obrigatório: é o que permite ao ciclo seguinte afirmar que algo melhorou.

Apresente ao usuário o diagnóstico e a proposta. **Depois que ele decidir**, registre as
decisões em `avaliacoes/DECISOES.md`:

```markdown
| Data | Achado | Decisão | Justificativa |
|---|---|---|---|
| 2026-08-15 | Backup não automatizado | adiado | aguarda upgrade de plano |
```
