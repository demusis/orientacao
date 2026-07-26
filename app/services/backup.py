"""Backup completo, restauração e expurgo da base — operações privativas do
administrador.

O backup é **portátil**: os dados vão em JSON por tabela, não como cópia binária
do arquivo SQLite, de modo que continuem restauráveis depois de uma eventual
migração para PostgreSQL (ver README, "Migração para um banco servidor"). O
pacote leva também os arquivos enviados, porque banco sem uploads não restaura o
sistema.

O arquivo gerado contém dados pessoais e hashes de senha: trate-o como o próprio
banco.
"""
import io
import json
import os
import re
import zipfile
from datetime import UTC, date, datetime, time

from flask import current_app
from sqlalchemy import Date, DateTime, Time, delete, func, insert, select, text, update

from app.extensions import db
from app.models import Usuario
from app.services import auditoria
from app.services.uploads import remover_do_disco

VERSAO_FORMATO = 1

# Ordem ditada pelas chaves estrangeiras: uma tabela só entra depois daquelas a
# que se refere. A remoção percorre o inverso. `usuario` tem auto-referência
# (criado_por), tratada em duas passadas.
ORDEM_TABELAS = [
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

# Tabelas acrescentadas à lista depois que pacotes de backup já circulavam. Um
# pacote gerado antes não traz o JSON correspondente; recusá-lo por isso seria
# perder a compatibilidade com backups legítimos já baixados. Na restauração,
# tabela opcional ausente entra vazia — mas SÓ quando o próprio manifesto do
# pacote não a lista em `contagens`: pacote que a declara e não traz o JSON está
# truncado, e aceitá-lo apagaria a tabela em silêncio. (ata_marco — os marcos
# discutidos em cada reunião — passou a ser incluída em 23/07/2026; antes disso,
# backup e migração a deixavam de fora, perdendo essa ligação em silêncio.)
TABELAS_OPCIONAIS_NA_RESTAURACAO = {"ata_marco"}

# `configuracao_email` está deliberadamente FORA da lista acima, por dois
# motivos que se somam:
#
# 1. Segurança. O pacote de backup sai do servidor e é guardado noutro lugar —
#    é a via de vazamento mais provável do sistema, muito mais que a invasão.
#    Incluir a tabela levaria a senha de app do Gmail (ainda que cifrada) para
#    dentro de todo arquivo baixado. Mantendo-a fora, o pacote nada contém.
# 2. Natureza do dado. Credencial de SMTP pertence à instalação, não ao acervo
#    acadêmico. Restaurar um backup noutro servidor deve trazer os vínculos e as
#    atas, não reapontar o envio de e-mail para a conta de origem.
#
# Consequência aceita: a configuração sobrevive ao expurgo e à restauração, e
# precisa ser reinformada ao migrar de servidor.

# nome_fisico é sempre "<uuid hex>.<ext>" (services/uploads.py). Restaurar só o
# que casa com esse padrão fecha a porta a travessia de caminho no ZIP.
NOME_FISICO = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9]{1,10}$")


class BackupInvalido(Exception):
    pass


def _revisao_atual() -> str | None:
    """Revisão Alembic aplicada ao banco. Restaurar dados sobre um esquema de
    outra versão produziria erro obscuro ou perda silenciosa de colunas."""
    try:
        return db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None


def _pasta_uploads() -> str:
    return current_app.config["UPLOAD_FOLDER"]


def _tabela(nome):
    return db.metadata.tables[nome]


def _contagens() -> dict:
    return {
        nome: db.session.execute(
            select(func.count()).select_from(_tabela(nome))
        ).scalar()
        or 0
        for nome in ORDEM_TABELAS
    }


# ---------------------------------------------------------------------------
# Geração


def gerar() -> tuple[str, bytes]:
    """Devolve (nome_do_arquivo, conteúdo do ZIP)."""
    contagens = _contagens()
    manifesto = {
        "versao_formato": VERSAO_FORMATO,
        "gerado_em": datetime.now(UTC).isoformat(),
        "revisao_alembic": _revisao_atual(),
        "contagens": contagens,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2)
        )
        for nome in ORDEM_TABELAS:
            linhas = [
                dict(linha._mapping)
                for linha in db.session.execute(select(_tabela(nome)))
            ]
            z.writestr(
                f"dados/{nome}.json",
                json.dumps(linhas, ensure_ascii=False, indent=1, default=str),
            )

        pasta = _pasta_uploads()
        if os.path.isdir(pasta):
            for arquivo in sorted(os.listdir(pasta)):
                caminho = os.path.join(pasta, arquivo)
                if os.path.isfile(caminho):
                    z.write(caminho, f"uploads/{arquivo}")

    carimbo = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
    return f"backup-ariadne-{carimbo}.zip", buffer.getvalue()


# ---------------------------------------------------------------------------
# Restauração


def _desserializar(tabela, linha: dict) -> dict:
    """JSON traz datas como texto; devolve-as ao tipo da coluna para que o
    driver não receba string onde espera data."""
    convertida = {}
    for coluna, valor in linha.items():
        tipo = tabela.columns[coluna].type
        if valor is None or not isinstance(valor, str):
            convertida[coluna] = valor
        elif isinstance(tipo, DateTime):
            convertida[coluna] = datetime.fromisoformat(valor)
        elif isinstance(tipo, Date):
            convertida[coluna] = date.fromisoformat(valor)
        elif isinstance(tipo, Time):
            convertida[coluna] = time.fromisoformat(valor)
        else:
            convertida[coluna] = valor
    return convertida


def _ajustar_sequencias():
    """PostgreSQL: as sequências não avançam com ids inseridos explicitamente."""
    if db.engine.dialect.name != "postgresql":
        return
    for nome in ORDEM_TABELAS:
        pks = list(_tabela(nome).primary_key.columns)
        if len(pks) != 1:
            continue
        coluna = pks[0].name
        db.session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{nome}', '{coluna}'), "
                f"COALESCE((SELECT MAX({coluna}) FROM {nome}), 1))"
            )
        )


def _apagar_tudo():
    for nome in reversed(ORDEM_TABELAS):
        db.session.execute(delete(_tabela(nome)))


def _limpar_uploads() -> list[str]:
    """Roda DEPOIS do commit (ver restaurar/expurgar). Devolve os nomes que
    ficaram para trás, e o chamador os REPORTA na tela: engolir a falha só no
    log faria o administrador certificar um expurgo como completo enquanto um
    PDF com dado pessoal segue no disco (e voltaria a entrar em todo backup
    futuro, que empacota a pasta inteira). A política de tolerância é a de
    `uploads.remover_do_disco`, comum a todo pós-commit."""
    pasta = _pasta_uploads()
    if not os.path.isdir(pasta):
        return []
    return remover_do_disco(
        caminho
        for arquivo in os.listdir(pasta)
        if os.path.isfile(caminho := os.path.join(pasta, arquivo))
    )


def restaurar(arquivo, executor: Usuario) -> dict:
    """Substitui integralmente o conteúdo da base pelo do pacote.

    A conta de quem executa é preservada: um backup anterior à sua criação
    deixaria o operador trancado do lado de fora.

    **Confirma o banco antes de tocar nos arquivos.** As operações de disco
    (apagar os uploads atuais e gravar os do pacote) são irreversíveis e não
    participam da transação. Fossem elas antes do commit, uma falha ao confirmar
    o banco — disco cheio, `database is locked` — reverteria as linhas mas
    deixaria os uploads já substituídos, e as versões antigas apontariam para
    arquivos inexistentes. Comitando primeiro, a falha provável (a do commit)
    ocorre com os uploads ainda intactos: banco e disco permanecem ambos no
    estado anterior. Por isso esta função confirma sua própria transação, ao
    contrário das demais do módulo."""
    # capturado antes de qualquer exclusão: depois de apagar a linha, o objeto
    # ORM fica obsoleto e qualquer leitura de atributo falha
    credencial = {
        "nome": executor.nome,
        "email": executor.email,
        "senha_hash": executor.senha_hash,
    }

    try:
        pacote = zipfile.ZipFile(arquivo)
    except zipfile.BadZipFile as exc:
        raise BackupInvalido("O arquivo enviado não é um ZIP válido.") from exc

    with pacote:
        if "manifesto.json" not in pacote.namelist():
            raise BackupInvalido("Pacote sem manifesto: não parece um backup do ARIADNE.")
        manifesto = json.loads(pacote.read("manifesto.json"))

        if manifesto.get("versao_formato") != VERSAO_FORMATO:
            raise BackupInvalido(
                f"Formato de backup incompatível (pacote: {manifesto.get('versao_formato')}, "
                f"esperado: {VERSAO_FORMATO})."
            )
        revisao_pacote = manifesto.get("revisao_alembic")
        revisao_banco = _revisao_atual()
        if revisao_pacote != revisao_banco:
            raise BackupInvalido(
                "O backup foi gerado sob outra versão do esquema "
                f"({revisao_pacote or 'desconhecida'}); o banco está em "
                f"{revisao_banco or 'desconhecida'}. Aplique as migrações "
                "correspondentes antes de restaurar."
            )
        faltando = [
            nome
            for nome in ORDEM_TABELAS
            if f"dados/{nome}.json" not in pacote.namelist()
            and not (
                nome in TABELAS_OPCIONAIS_NA_RESTAURACAO
                # opcional só para pacote anterior à adoção da tabela: o gerado
                # depois a declara no manifesto, e a ausência do JSON é truncamento
                and nome not in manifesto.get("contagens", {})
            )
        ]
        if faltando:
            raise BackupInvalido(
                "Pacote incompleto; faltam as tabelas: " + ", ".join(faltando)
            )

        # tabela opcional ausente (pacote anterior à sua adoção) entra vazia
        dados = {
            nome: (
                json.loads(pacote.read(f"dados/{nome}.json"))
                if f"dados/{nome}.json" in pacote.namelist()
                else []
            )
            for nome in ORDEM_TABELAS
        }

        # tudo validado antes de tocar nos dados
        _apagar_tudo()

        for nome in ORDEM_TABELAS:
            linhas = dados[nome]
            if not linhas:
                continue
            tabela = _tabela(nome)
            convertidas = [_desserializar(tabela, linha) for linha in linhas]
            if nome == "usuario":
                for linha in convertidas:
                    linha["criado_por"] = None  # segunda passada abaixo
            db.session.execute(insert(tabela), convertidas)

        usuario = _tabela("usuario")
        for linha in dados["usuario"]:
            if linha.get("criado_por") is not None:
                db.session.execute(
                    update(usuario)
                    .where(usuario.c.id == linha["id"])
                    .values(criado_por=linha["criado_por"])
                )

        emails = {linha["email"] for linha in dados["usuario"]}
        executor_preservado = credencial["email"] not in emails
        if executor_preservado:
            db.session.execute(
                insert(usuario),
                [
                    {
                        **credencial,
                        "papel": "admin",
                        "ativo": True,
                        "criado_em": datetime.now(UTC),
                        "criado_por": None,
                        "ultimo_acesso": None,
                    }
                ],
            )
        else:
            # A linha vinda do pacote pode estar desativada, sem papel de
            # administrador ou com uma senha que o operador já não conhece (o
            # backup pode ser antigo). Quem restaura não pode sair trancado:
            # a conta volta ativa, admin e com a senha da sessão corrente —
            # o mesmo espírito da inserção acima, quando ela nem existe.
            db.session.execute(
                update(usuario)
                .where(usuario.c.email == credencial["email"])
                .values(
                    ativo=True,
                    papel="admin",
                    senha_hash=credencial["senha_hash"],
                )
            )

        _ajustar_sequencias()

        # Fronteira deliberada: confirma o banco antes das operações de disco
        # irreversíveis abaixo. Uma falha aqui reverte o banco com os uploads
        # ainda intactos (ver docstring).
        db.session.commit()

        presos = _limpar_uploads()
        pasta = _pasta_uploads()
        os.makedirs(pasta, exist_ok=True)
        arquivos_restaurados = 0
        nao_gravados: list[str] = []
        for item in pacote.namelist():
            if not item.startswith("uploads/"):
                continue
            nome_arquivo = os.path.basename(item)
            if not NOME_FISICO.match(nome_arquivo):
                continue  # nome fora do padrão: descartado por segurança
            # o mesmo arquivo que resistiu à limpeza resistiria à regravação:
            # sem esta guarda, o 500 pós-commit voltava um passo adiante
            try:
                with pacote.open(item) as origem, open(
                    os.path.join(pasta, nome_arquivo), "wb"
                ) as destino:
                    destino.write(origem.read())
            except OSError:
                current_app.logger.warning("upload não gravado: %s", nome_arquivo)
                nao_gravados.append(nome_arquivo)
                continue
            arquivos_restaurados += 1

    # a auditoria fica a cargo do chamador: a linha do executor foi apagada e
    # reinserida, de modo que `current_user` só volta a ser utilizável depois de
    # reautenticado com o novo identificador
    return {
        "contagens": {nome: len(dados[nome]) for nome in ORDEM_TABELAS},
        "arquivos": arquivos_restaurados,
        # o que ficou fora do lugar no disco — a rota exibe, não só o log
        "arquivos_pendentes": sorted(set(presos) | set(nao_gravados)),
        "executor_preservado": executor_preservado,
        "email_executor": credencial["email"],
        "gerado_em": manifesto.get("gerado_em"),
    }


# ---------------------------------------------------------------------------
# Expurgo


def expurgar(executor: Usuario) -> dict:
    """Apaga todo o conteúdo, preservando apenas a conta de quem executa.

    A trilha de auditoria é apagada junto — é parte da base — e um único
    registro novo documenta o ato, para que o expurgo não seja invisível.

    **Confirma o banco antes de tocar nos arquivos**, pela mesma fronteira de
    `restaurar()`: a remoção dos uploads é irreversível e não participa da
    transação. Apagando-os antes, uma falha do commit (`database is locked`)
    reverteria as linhas — inclusive `versao_documento` — mas os arquivos já
    teriam sumido, e todo download voltaria quebrado num sistema aparentemente
    intacto. Por isso esta função confirma a própria transação."""
    contagens = _contagens()

    for nome in reversed(ORDEM_TABELAS):
        if nome == "usuario":
            continue
        db.session.execute(delete(_tabela(nome)))

    usuario = _tabela("usuario")
    db.session.execute(delete(usuario).where(usuario.c.id != executor.id))
    # o criador da conta preservada pode ter sido removido
    db.session.execute(
        update(usuario).where(usuario.c.id == executor.id).values(criado_por=None)
    )

    _ajustar_sequencias()

    auditoria.registrar(
        "expurgo_base",
        "sistema",
        None,
        {"removidos": contagens, "conta_preservada": executor.email},
    )
    # fronteira deliberada: banco confirmado antes do disco (ver docstring)
    db.session.commit()
    presos = _limpar_uploads()
    return {"removidos": contagens, "arquivos_presos": presos}
