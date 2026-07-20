# ARIADNE

**A**plicativo de **R**egistro, **I**ntegração e **A**companhamento **D**ocente para **N**ivelamento **E**studantil.

Aplicação web para mediação institucional e controle de fluxo de trabalho entre orientadores acadêmicos e discentes (Iniciação Científica, Mestrado e Doutorado).

## Funcionalidades

- Controle de acesso por papel (Administrador, Orientador, Orientando), com verificação de papel e de propriedade do recurso.
- Painel de pendências: entregas aguardando confirmação, tarefas em aberto por prazo, atas em rascunho e versões de documento sem parecer.
- Cronogramas com marcos classificados por etapa do projeto e conclusão em duas fases (sinalização pelo orientando, confirmação pelo orientador). Atraso computado na leitura.
- Repositório documental com validação de upload (extensão, assinatura do arquivo, limite de 20 MB), armazenamento sob UUID e versionamento iterativo.
- Reuniões individuais e em grupo: ata única compartilhada entre os participantes, presenças e reagendamentos registrados.
- Atas com fluxo rascunho → finalizada (imutável) e pareceres imutáveis desde a emissão. Exportação em PDF assinável, com hash de integridade conferível por rota pública.
- Trilha de auditoria *append-only*, paginada e filtrável por intervalo de data e hora, usuário e ação.

## Stack

Python 3.12+ · Flask 3 · Flask-SQLAlchemy · Flask-Migrate (Alembic) · Flask-Login · Flask-WTF · reportlab · pytest.

SQLite atende ao desenvolvimento e à homologação em worker único. Para uso concorrente, veja [Migração para um banco servidor](#migração-para-um-banco-servidor).

## Requisitos

- Python 3.12 ou superior
- Git
- Para banco servidor (opcional): PostgreSQL 14+ ou MySQL 8+

## Instalação (desenvolvimento)

```bash
git clone https://github.com/demusis/orientacao.git ariadne
cd ariadne

python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
cp .env.example .env              # copy no Windows; ajuste SECRET_KEY
```

Gere uma chave para o `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Crie o esquema, o administrador inicial e execute:

```bash
export FLASK_APP=wsgi.py          # Windows: $env:FLASK_APP="wsgi.py"
flask db upgrade
flask seed-admin --email admin@exemplo.br --senha "<senha-forte>"
flask run
```

A aplicação responde em `http://127.0.0.1:5000`. O `seed-admin` recusa endereços inválidos e domínios de uso especial (`.local`, por exemplo), que impediriam o login posterior.

## Configuração

Variáveis lidas do `.env` (veja `.env.example`):

| Variável | Obrigatória | Descrição |
|---|---|---|
| `FLASK_CONFIG` | sim | `development`, `testing` ou `production` |
| `SECRET_KEY` | em produção | chave de assinatura de sessão e CSRF |
| `DATABASE_URL` | em produção | URL SQLAlchemy do banco |
| `UPLOAD_FOLDER` | recomendada | diretório dos arquivos enviados, fora da árvore do código |
| `TRUSTED_PROXY_COUNT` | atrás de proxy | número de proxies reversos confiáveis; `0` desativa a leitura de `X-Forwarded-For` |

Sobre `TRUSTED_PROXY_COUNT`: atrás de um proxy reverso, o endereço visto pela aplicação é o do próprio proxy, e a auditoria registraria um IP interno. Com o valor `1`, vale o endereço escrito pelo proxy confiável. **Mantenha `0` quando não houver proxy** — nesse caso o cabeçalho é forjável pelo cliente e aceitá-lo permitiria falsear a origem dos registros.

## Testes

```bash
python -m pytest
```

A suíte cobre autenticação, matriz de permissões, validação de upload (extensão proibida e assinatura divergente), versionamento, imutabilidade de atas e pareceres, integridade dos PDFs exportados, pendências do painel, filtros e paginação da auditoria, e a origem do IP registrado.

## Estrutura

```
app/
  blueprints/      rotas por domínio (auth, admin, main, cronogramas,
                   documentos, atas, reunioes, orientandos)
  models/          mapeamentos SQLAlchemy
  services/        regras de negócio (rbac, auditoria, uploads, atas,
                   eventos, usuarios, exportacao, painel)
  templates/       Jinja2
  static/          CSS e imagens
migrations/        migrações Alembic
scripts/           utilitários operacionais
tests/             suíte pytest
```

## Banco de dados

O esquema é gerenciado por Alembic. Após alterar modelos:

```bash
flask db migrate -m "descrição"   # revise o arquivo gerado antes de aplicar
flask db upgrade
flask db check                    # confirma que modelos e migrações coincidem
```

As migrações usam `batch_alter_table` onde o SQLite exige recriação de tabela; a operação é transparente nos demais motores.

## Migração para um banco servidor

O SQLite grava com bloqueio de arquivo e serializa as escritas, o que basta para um worker único, mas não para acesso concorrente. Para uso institucional, migre para **PostgreSQL** (recomendado) ou **MySQL 8**.

### 1. Instalar o driver

```bash
pip install "psycopg[binary]"     # PostgreSQL
# PyMySQL, para MySQL, já consta em requirements.txt
```

### 2. Criar banco e usuário

PostgreSQL:

```sql
CREATE USER ariadne WITH PASSWORD 'senha-forte';
CREATE DATABASE ariadne OWNER ariadne ENCODING 'UTF8';
```

MySQL — o conjunto de caracteres precisa ser `utf8mb4`, sob pena de truncar acentuação e emoji:

```sql
CREATE DATABASE ariadne CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ariadne'@'%' IDENTIFIED BY 'senha-forte';
GRANT ALL PRIVILEGES ON ariadne.* TO 'ariadne'@'%';
```

### 3. Criar o esquema no banco novo

Aponte `DATABASE_URL` para o banco novo e aplique as migrações:

```bash
export DATABASE_URL="postgresql+psycopg://ariadne:senha-forte@localhost:5432/ariadne"
export FLASK_APP=wsgi.py
flask db upgrade
```

Caso a reprodução do histórico falhe no PostgreSQL — o encadeamento inclui colunas de tipo enumerado acrescentadas depois da criação das tabelas, cujo tipo nem sempre é criado automaticamente pelo `ALTER TABLE` —, use o caminho equivalente, que constrói o esquema a partir dos modelos e apenas registra a versão corrente:

```bash
python -c "from wsgi import app; from app.extensions import db; \
           app.app_context().push(); db.create_all()"
flask db stamp head
```

Os dois caminhos produzem o mesmo esquema: `flask db check` não detecta diferença entre os modelos e o topo das migrações.

### 4. Transferir os dados

`scripts/migrar_banco.py` copia todas as tabelas na ordem exigida pelas chaves estrangeiras, preservando os identificadores, e ajusta as sequências no PostgreSQL — sem isso, o primeiro registro criado pela aplicação colidiria com um id existente.

```bash
python scripts/migrar_banco.py \
    --origem  "sqlite:////caminho/instance/ariadne.db" \
    --destino "postgresql+psycopg://ariadne:senha-forte@localhost:5432/ariadne"
```

O script **recusa executar sobre um destino que já contenha dados**, para não duplicar registros nem misturar bases. Ao final, compara as contagens de cada tabela entre origem e destino e sai com código diferente de zero se houver divergência.

Para conferir uma migração já feita, sem copiar nada:

```bash
python scripts/migrar_banco.py --origem <URL> --destino <URL> --conferir
```

### 5. Apontar a aplicação e verificar

Grave a nova `DATABASE_URL` no `.env`, reinicie a aplicação e confira:

- login funciona e o painel lista as orientações;
- a trilha de auditoria exibe os registros anteriores à migração;
- criar um marco e um usuário novos funciona — é o que exercita as sequências;
- baixar uma versão de documento existente funciona (os arquivos ficam em `UPLOAD_FOLDER`, **não** no banco: o diretório precisa ser copiado à parte).

Mantenha o arquivo SQLite anterior como cópia de segurança até concluir a verificação.

### Observações

- Em produção, `SQLALCHEMY_ENGINE_OPTIONS` já define `pool_pre_ping` e `pool_recycle`: bancos servidor encerram conexões ociosas, e sem isso a primeira requisição após um período de inatividade falharia.
- A rotina de backup deve cobrir **banco e diretório de uploads**; um sem o outro não restaura o sistema. O menu **Backup** da aplicação já produz um pacote com ambos (ver adiante).

## Deploy (PythonAnywhere)

Procedimento validado em homologação (conta gratuita):

1. Console Bash: `git clone <repo> ariadne && cd ariadne && python3 -m venv venv && venv/bin/pip install -r requirements.txt`.
2. Criar `.env` com `FLASK_CONFIG=production`, `SECRET_KEY`, `DATABASE_URL`, `UPLOAD_FOLDER` fora da árvore do código e `TRUSTED_PROXY_COUNT=1` (`chmod 600 .env`).
3. `FLASK_APP=wsgi.py venv/bin/flask db upgrade` e `venv/bin/flask seed-admin`.
4. Painel Web: app com configuração manual; definir source code, working directory e virtualenv; mapear `/static/` → `app/static`; ativar Force HTTPS. O diretório de uploads **não** deve ser mapeado como estático — o download é servido apenas por rota autenticada.
5. Arquivo WSGI (`/var/www/<usuario>_pythonanywhere_com_wsgi.py`): inserir o projeto e o `site-packages` do venv em `sys.path` e executar `os.chdir` para o projeto antes de `from wsgi import app as application`. Na conta gratuita o campo Virtualenv do painel pode não ser aplicado pelo uwsgi; a inserção explícita no `sys.path` é o mecanismo garantido.

### Atualização

```bash
cd ~/ariadne && git pull --ff-only && FLASK_APP=wsgi.py venv/bin/flask db upgrade
touch /var/www/<usuario>_pythonanywhere_com_wsgi.py
```

O botão *Reload* do painel é intermitente; tocar o arquivo WSGI é o gatilho confiável. O reinício demora alguns segundos — confirme em `/var/log/<dominio>.server.log`, que registra `Starting uWSGI` e `WSGI app 0 ... ready` com horário, antes de testar. Verificar apenas o CSS servido induz a erro: arquivos estáticos vêm do disco e mudam sem reload, enquanto os templates só mudam depois dele.

Ressalvas do plano gratuito: MySQL indisponível e o site expira mensalmente sem o clique em "Run until 1 month from today".

## Backup, restauração e expurgo

O menu **Backup**, privativo do administrador, oferece três operações.

**Gerar backup** produz um `.zip` com os dados de todas as tabelas em JSON, os arquivos
enviados e um manifesto com a revisão do esquema e as contagens. O formato é portátil:
permanece restaurável após a migração para PostgreSQL. O arquivo contém dados pessoais e
hashes de senha — trate-o como o próprio banco.

**Restaurar backup** substitui integralmente o conteúdo atual. É recusada, antes de tocar
nos dados, se o pacote não trouxer manifesto, se o formato for de outra versão, se
faltarem tabelas ou se a revisão do esquema divergir da aplicada ao banco. Se a conta de
quem restaura não constar do arquivo, ela é preservada, de modo que o operador não fique
sem acesso. Arquivos com nome fora do padrão `<uuid>.<ext>` são descartados, o que fecha
a porta a travessia de caminho no ZIP. O tamanho do envio é limitado por
`MAX_CONTENT_LENGTH` (20 MB por padrão).

**Apagar a base** remove todo o conteúdo, inclusive a trilha de auditoria, preservando
apenas a conta de quem executa. Um único registro novo documenta o expurgo com autor,
data e quantidade removida por tabela. As duas operações destrutivas exigem digitar uma
palavra de confirmação (`RESTAURAR` e `APAGAR`), não apenas um clique.

Para backup por linha de comando, fora da aplicação, use `scripts/migrar_banco.py`
apontando a origem para o banco em uso e o destino para um arquivo novo.

## Ciclo de avaliação

O sistema tem um procedimento próprio de avaliação periódica, acionado sob demanda pelo
comando `/avaliar` (definido em `.claude/commands/avaliar.md`). Ele examina três
dimensões — **operação** (o que mantém o sistema no ar), **uso** (o que as pessoas de
fato fazem) e **funcionalidade** (o que falta) — e produz uma proposta priorizada. O
comando **não altera a aplicação**: toda mudança depende de aprovação item a item.

A evidência de uso vem de `flask indicadores`, que agrega adesão, vínculos, fluxo de
marcos, documentos, atas e trilha de auditoria:

```bash
flask indicadores                 # legível
flask indicadores --json --dias 30
```

Os indicadores são **agregados**: contam quantos, não registram quem fez o quê. Leituras
individuais permanecem fora da auditoria por decisão registrada em
`avaliacoes/DECISOES.md`.

Cada ciclo grava `avaliacoes/AAAA-MM-DD.md`, com um anexo em JSON do snapshot dos
indicadores — é o que permite ao ciclo seguinte afirmar se algo melhorou. As decisões
tomadas sobre cada achado ficam em `avaliacoes/DECISOES.md`, o que impede que um item já
recusado seja reproposto indefinidamente.

## Segurança e operação

- Trilha de auditoria *append-only*: a aplicação não expõe alteração nem exclusão de registros.
- Uploads validados por extensão e assinatura do conteúdo, gravados sob nome UUID e servidos apenas por rota autenticada.
- Exclusão física de contas restrita ao administrador e apenas para contas sem histórico; do contrário, a via é a desativação, que preserva os registros.
- PDFs de atas e pareceres derivam de um retrato do conteúdo congelado na finalização/emissão, de modo que alterações posteriores não invalidam documentos já assinados.
