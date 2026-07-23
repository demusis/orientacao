"""Transfere os dados do ARIADNE de um banco para outro (por exemplo, de
SQLite para PostgreSQL), preservando identificadores.

O esquema do destino deve já existir — crie-o com `flask db upgrade` apontando
DATABASE_URL para o banco novo. Este script copia apenas linhas, na ordem em
que as chaves estrangeiras exigem, e recusa executar sobre um destino que já
contenha dados, para não duplicar registros nem misturar bases.

Uso:
    python scripts/migrar_banco.py --origem <URL> --destino <URL>
    python scripts/migrar_banco.py --origem <URL> --destino <URL> --conferir

Exemplo:
    python scripts/migrar_banco.py \
        --origem  sqlite:///instance/ariadne.db \
        --destino postgresql+psycopg://ariadne:senha@localhost/ariadne
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, insert, select, text, update

from app import create_app
from app.extensions import db

# Ordem ditada pelas chaves estrangeiras: uma tabela só entra depois daquelas
# a que se refere. 'usuario' tem auto-referência (criado_por), tratada à parte.
# Espelha ORDEM_TABELAS de services/backup.py: toda tabela portadora de dado
# entra aqui, senão a cópia a deixa para trás e a conferência — que percorre
# esta mesma lista — não acusa a falta. 'configuracao_email' fica de fora de
# propósito (credencial de SMTP pertence à instalação, não ao acervo; mesmo
# critério do backup).
ORDEM = [
    "usuario",
    "orientacao",
    "orientacao_orientador",
    "evento_vinculo",
    "marco",
    "documento",
    "versao_documento",
    "modelo_documento",
    "ata",
    "ata_orientacao",
    "ata_marco",
    "reagendamento",
    "parecer",
    "log_auditoria",
]

LOTE = 500


def _linhas(conexao, tabela):
    for bloco in conexao.execute(select(tabela)).partitions(LOTE):
        yield [dict(linha._mapping) for linha in bloco]


def _destino_vazio(conexao, metadata) -> bool:
    for nome in ORDEM:
        total = conexao.execute(
            select(func.count()).select_from(metadata.tables[nome])
        ).scalar()
        if total:
            print(f"  destino já contém {total} linha(s) em '{nome}'")
            return False
    return True


def _ajustar_sequencias(conexao, metadata):
    """PostgreSQL: as sequências de chave primária não avançam quando os ids
    são inseridos explicitamente; sem este ajuste, o primeiro INSERT feito pela
    aplicação colidiria com um id existente."""
    for nome in ORDEM:
        tabela = metadata.tables[nome]
        pks = list(tabela.primary_key.columns)
        if len(pks) != 1:  # chave composta não usa sequência
            continue
        coluna = pks[0].name
        conexao.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{nome}', '{coluna}'), "
                f"COALESCE((SELECT MAX({coluna}) FROM {nome}), 1))"
            )
        )


def _conferir(origem, destino, metadata) -> bool:
    print("\nConferência de contagens (origem → destino):")
    tudo_certo = True
    with origem.connect() as co, destino.connect() as cd:
        for nome in ORDEM:
            tabela = metadata.tables[nome]
            a = co.execute(select(func.count()).select_from(tabela)).scalar()
            b = cd.execute(select(func.count()).select_from(tabela)).scalar()
            marca = "ok" if a == b else "DIVERGENTE"
            if a != b:
                tudo_certo = False
            print(f"  {nome:<24} {a:>6} → {b:>6}  {marca}")
    return tudo_certo


def migrar(url_origem: str, url_destino: str, apenas_conferir: bool = False) -> int:
    app = create_app("development")  # só para registrar os mapeamentos
    with app.app_context():
        metadata = db.metadata

    origem = create_engine(url_origem)
    destino = create_engine(url_destino)

    if apenas_conferir:
        return 0 if _conferir(origem, destino, metadata) else 1

    with destino.begin() as cd:
        if not _destino_vazio(cd, metadata):
            print(
                "\nRecusado: o destino não está vazio. Aponte para um banco novo "
                "com o esquema criado por 'flask db upgrade' e sem dados."
            )
            return 1

    with origem.connect() as co, destino.begin() as cd:
        for nome in ORDEM:
            tabela = metadata.tables[nome]
            copiadas = 0
            for lote in _linhas(co, tabela):
                if nome == "usuario":
                    # a auto-referência é preenchida depois que todos existem
                    for linha in lote:
                        linha["criado_por"] = None
                cd.execute(insert(tabela), lote)
                copiadas += len(lote)
            print(f"  {nome:<24} {copiadas:>6} linha(s)")

        # segunda passada: restabelece usuario.criado_por
        usuario = metadata.tables["usuario"]
        vinculos = co.execute(
            select(usuario.c.id, usuario.c.criado_por).where(
                usuario.c.criado_por.isnot(None)
            )
        ).all()
        for uid, autor in vinculos:
            cd.execute(
                update(usuario).where(usuario.c.id == uid).values(criado_por=autor)
            )
        if vinculos:
            print(f"  usuario.criado_por       {len(vinculos):>6} vínculo(s) restaurado(s)")

        if destino.dialect.name == "postgresql":
            _ajustar_sequencias(cd, metadata)
            print("  sequências ajustadas (PostgreSQL)")

    return 0 if _conferir(origem, destino, metadata) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origem", required=True, help="URL SQLAlchemy de origem")
    p.add_argument("--destino", required=True, help="URL SQLAlchemy de destino")
    p.add_argument(
        "--conferir",
        action="store_true",
        help="apenas compara as contagens, sem copiar nada",
    )
    args = p.parse_args()
    return migrar(args.origem, args.destino, args.conferir)


if __name__ == "__main__":
    raise SystemExit(main())
