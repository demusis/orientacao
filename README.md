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

1. Clonar o repositório e criar o virtualenv com `requirements.txt` (adicionar `PyMySQL`).
2. Criar banco MySQL no painel e definir `DATABASE_URL` (dialeto `mysql+pymysql`, `charset=utf8mb4`) e `SECRET_KEY` no arquivo `.env`.
3. Definir `FLASK_CONFIG=production` e `UPLOAD_FOLDER` para diretório fora da árvore do código.
4. Apontar o WSGI file da plataforma para `wsgi.app`.
5. Executar `flask db upgrade` e `flask seed-admin` no console.
6. Mapear `/static/` para `app/static/` no painel. O diretório de uploads **não** deve ser mapeado como estático: o download é servido exclusivamente por rota autenticada.
7. Rotina de backup: dump do MySQL + cópia do diretório de uploads.
