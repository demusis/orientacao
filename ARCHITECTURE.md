# Arquitetura do ARIADNE

Mapa da engenharia do sistema. Descreve o que existe; para as decisões e o seu
porquê, ver `avaliacoes/DECISOES.md` e as docstrings de cada módulo.

## Visão geral

Aplicação Flask 3 no padrão *app factory*, organizada em blueprints e uma camada
de serviços. Persistência em SQLAlchemy 3.1 com migrações Alembic (Flask-Migrate)
sobre SQLite. Hospedagem em PythonAnywhere (plano gratuito, worker único, sem
agendador). O servidor opera em UTC; as colunas de data/hora são UTC ingênuo.

## App factory (`app/__init__.py`)

`create_app(config_name)` monta a aplicação a partir de `config.py`
(`config_by_name`) e registra, nesta ordem: extensões (`db`, `migrate`,
`login_manager`, `csrf`), os blueprints, a CLI, os *template globals*, o disparo
de avisos diários (`before_request`), os cabeçalhos de segurança
(`after_request`) e as páginas de erro (403/404/413/500).

## Blueprints (rota → prefixo)

| Blueprint | Prefixo | Responsabilidade |
|---|---|---|
| `auth` | `/auth` | login, logout, troca e recuperação de senha |
| `admin` | `/admin` | usuários, vínculos, auditoria, modelos, e-mail, backup |
| `main` | `/` | painel, página do vínculo (linha do tempo embutida), relatório PDF, ajuda, verificação pública de hash, download de modelo |
| `cronogramas` | `/orientacoes/<id>/cronograma` | marcos: lista, criação, edição, página da tarefa, sinalização, confirmação, anexo |
| `documentos` | `/orientacoes/<id>/documentos` | documentos, versões, download |
| `atas` | `/orientacoes/<id>` | atas, pareceres, presenças, reagendamento |
| `reunioes` | `/reunioes` | atas e tarefas em grupo (orientador) |
| `orientandos` | `/orientandos` | criação de orientando com vínculo (orientador) |

## Modelos (`app/models/`)

`user` (Usuario), `orientacao` (Orientacao, OrientacaoOrientador para
coorientadores, EventoVinculo), `cronograma` (Marco), `documento` (Documento,
VersaoDocumento, ModeloDocumento), `ata` (Ata, AtaParticipacao, Parecer,
Reagendamento), `configuracao` (ConfiguracaoEmail, singleton), `auditoria`
(LogAuditoria, *append-only*).

## Camada de serviços (`app/services/`)

- **rbac** — `role_required` (decorator de papel) e `orientacao_autorizada`
  (propriedade do recurso; admin acessa tudo, orientador/orientando só os seus).
- **uploads** — validação (extensão + assinatura de *magic bytes*) e
  armazenamento sob nome UUID; **modelos** — acervo de arquivos-modelo.
- **avisos** — avisos diários de pendência por e-mail, disparados pelo tráfego
  (sem agendador); **email** (SMTP), **cripto** (Fernet, senha SMTP),
  **recuperacao** (token assinado), **seguranca** (limite de tentativas por
  origem), **tempo** (UTC).
- **auditoria** — trilha; **backup** — exportação/restauração/expurgo;
  **exportacao** — PDF assinável de ata/parecer com hash de verificação;
  **relatorio** — PDF consolidado do vínculo; **marcacao** — markdown → HTML e
  *flowables* de PDF de uma única leitura.
- **linha_tempo**, **painel**, **indicadores**, **usuarios**, **eventos**,
  **atas** — leitura e regras de domínio das respectivas telas.

## Segurança

- **CSP estrita** (`script-src 'none'`, sem `unsafe-inline`): o projeto não usa
  JavaScript nem estilo embutido, o que permite a política sem brechas. Todo
  estilo vive em `app/static/style.css`; submenus usam `<details>`.
- Limite de tentativas de login/recuperação por origem; sessão de 12 h;
  `Usuario.get_id()` inclui um trecho do hash da senha (trocar a senha encerra as
  sessões); trilha de auditoria append-only.

## Uploads e templates

`UPLOAD_FOLDER` guarda os arquivos sob `<uuid>.<ext>`; `MAX_CONTENT_LENGTH` de
20 MB (erro 413 tratado). Templates Jinja: `base.html` (menu por papel com
submenus `<details>`), `_macros.html` (`render_form`, `nav_modulos`,
`paginacao_nav`).

## Migrações

Alembic em `migrations/versions/` (SQLite exige `batch_alter_table`). As
migrações **não** importam modelos ORM — `tests/test_migracoes_integridade.py`
guarda a cadeia do zero e essa regra.

## Deploy (PythonAnywhere)

```bash
cd ~/ariadne && git pull --ff-only \
  && FLASK_APP=wsgi.py venv/bin/flask db upgrade \
  && touch /var/www/orientacao_pythonanywhere_com_wsgi.py
```

O `db upgrade` só é necessário quando há migração nova. No plano gratuito o
primeiro `touch` às vezes não recicla o worker — repetir se a primeira leitura
vier antiga.

## Desenvolvimento

Ambiente (Windows, `.venv`):

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` traz só as dependências de runtime; `requirements-dev.txt`
(que o inclui) acrescenta `pytest` e `ruff`.

Comandos:

```bash
.venv/Scripts/python.exe -m pytest            # suíte completa
.venv/Scripts/python.exe -m ruff check .       # lint
.venv/Scripts/python.exe -m flask db upgrade   # aplicar migrações (FLASK_APP=wsgi.py)
```

`tests/test_relatorio.py` é lento (geração de PDF); localmente pode-se rodar a
suíte com `--ignore=tests/test_relatorio.py` e deixar a cobertura completa para a
CI. **CI**: `.github/workflows/ci.yml` roda `ruff check` e `pytest` (suíte
inteira) a cada push e pull request, em Python 3.12.
