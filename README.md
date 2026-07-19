# ARIADNE

**A**plicativo de **R**egistro, **I**ntegração e **A**companhamento **D**ocente para **N**ivelamento **E**studantil.

Aplicação web para mediação institucional e controle de fluxo de trabalho entre orientadores acadêmicos e discentes (Iniciação Científica, Mestrado e Doutorado).

## Funcionalidades

- Controle de acesso baseado em funções (RBAC): Administrador, Orientador, Orientando, com verificação de papel e de propriedade do recurso.
- Cronogramas com marcos metodológicos, prazos e fluxo de conclusão em duas etapas (sinalização pelo orientando, confirmação pelo orientador). Atraso computado na leitura.
- Repositório documental com validação de upload (extensão, assinatura de arquivo, limite de 20 MB), armazenamento sob UUID e versionamento iterativo.
- Atas de orientação com fluxo rascunho → finalizada (imutável) e pareceres técnicos imutáveis após emissão.
- Trilha de auditoria append-only sobre todas as operações relevantes.

## Stack

Python 3.12 · Flask 3 · Flask-SQLAlchemy · Flask-Migrate (Alembic) · Flask-Login · Flask-WTF · pytest.
SQLite em desenvolvimento; MySQL (`utf8mb4`) em produção.

## Instalação (desenvolvimento)

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env           # ajustar SECRET_KEY

set FLASK_APP=wsgi.py
flask db upgrade
flask seed-admin --email admin@exemplo.br --senha <senha-forte>
flask run
```

## Testes

```
python -m pytest
```

A suíte cobre autenticação, matriz de permissões RBAC (incluindo acesso a recurso de terceiro), validação de upload (extensão proibida, assinatura divergente), versionamento de documentos, imutabilidade de atas e registro de auditoria.

## Deploy (PythonAnywhere)

Procedimento validado em homologação (conta gratuita, jul/2026):

1. Console Bash: `git clone <repo> ariadne && cd ariadne && python3 -m venv venv && venv/bin/pip install -r requirements.txt`.
2. Criar `.env` com `FLASK_CONFIG=production`, `SECRET_KEY`, `DATABASE_URL` e `UPLOAD_FOLDER` fora da árvore do código (`chmod 600 .env`).
3. Executar `venv/bin/flask db upgrade` e `venv/bin/flask seed-admin` (`FLASK_APP=wsgi.py`).
4. Painel Web: criar app com configuração manual (Python igual ao do venv); definir source code, working directory e virtualenv; mapear `/static/` → `app/static`; ativar Force HTTPS. O diretório de uploads **não** deve ser mapeado como estático: o download é servido exclusivamente por rota autenticada.
5. Arquivo WSGI (`/var/www/<usuario>_pythonanywhere_com_wsgi.py`): inserir o projeto e o `site-packages` do venv em `sys.path` e executar `os.chdir` para o projeto antes de `from wsgi import app as application`. Ressalva observada: na conta gratuita o campo Virtualenv do painel pode não ser aplicado pelo uwsgi; a inserção explícita no WSGI é o mecanismo garantido.
6. Rotina de backup: cópia do banco + diretório de uploads.

Ressalvas do plano gratuito: MySQL indisponível (usa-se SQLite — adequado ao protótipo em worker único; migrar para MySQL/planos pagos antes de uso concorrente em escala) e o site expira mensalmente sem o clique em "Run until 1 month from today".
