# Loop de revisão e correção do ARIADNE

Encontra e corrige **defeitos** no aplicativo inteiro, em voltas sucessivas, até
uma volta terminar sem achado confirmado. Complementa os outros dois ciclos sem
os duplicar: o `/avaliar` olha operação e uso em produção; o loop de engenharia
(`avaliacoes/ENGENHARIA.md`) melhora fundação preservando comportamento; este
comando caça o que está **errado** — lógica, segurança, LGPD, concorrência,
desempenho e testes frágeis.

## Alçada

- **Corrigir sem perguntar**: achado confirmado cuja correção não muda
  comportamento visível ao usuário (defeito de lógica, brecha de autorização,
  vazamento de dado, consulta N+1, teste frágil). Decisão de 2026-07-25.
- **Perguntar antes**: correção que altera comportamento visível (tela, fluxo,
  e-mail, regra de negócio) ou que exige migração de banco destrutiva.
- Respeitar `avaliacoes/DECISOES.md`: achado já **recusado** não volta como
  correção; se houver evidência nova, ela vai ao relatório, não ao código.
- Estilo técnico austero, sem adjetivação.

## Protocolo de cada volta

1. **Revisar**: acionar a revisão multi-agente (`/code-review` em nível alto)
   sobre **todo o código** de `app/` e configuração — não apenas o diff. Pedir
   as dimensões: correção/lógica, segurança (RBAC entre papéis, uploads,
   CSRF/CSP, SQLite sem `PRAGMA foreign_keys`), LGPD, concorrência (SQLite
   single-writer, avisos por tráfego), desempenho (N+1), qualidade de testes
   (afirmações fracas, flakes de fuso `date.today()` local × `agora()` UTC).
   Excluir estilo puro (ruff cobre) e o já decidido em `DECISOES.md`.
2. **Triar**: só entram achados **confirmados** pela verificação adversarial.
   Achado "plausível" não confirmado vai ao registro como hipótese, sem correção.
3. **Corrigir** cada confirmado dentro da alçada, um commit por tema, com teste
   que reproduza o defeito antes da correção sempre que couber.
4. **Verificar**: `ruff check .` limpo e suíte completa verde no ambiente de
   teste (cópia em disco local — o `.venv` do repositório não roda nesta
   máquina). Nunca prosseguir com teste vermelho.
5. **Registrar** a volta em `avaliacoes/REVISOES.md`: data, achados (com
   arquivo:linha), veredito, correção (commit) ou motivo de não corrigir.
6. **Repetir** a partir do passo 1. **Parar** quando uma volta terminar sem
   achado confirmado, ou quando os confirmados restantes estiverem todos fora
   da alçada (aguardando decisão do usuário).

## Encerramento de cada corrida

- Branch próprio (`revisao/AAAA-MM-DD`), um PR ao final com o conjunto de
  correções e o link do registro. Merge e deploy só com pedido do usuário.
- Itens fora da alçada são apresentados ao usuário como proposta priorizada
  (mesmo formato do `/avaliar`: impacto, esforço, risco), e a decisão dele vai
  para `avaliacoes/DECISOES.md`.
