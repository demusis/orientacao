"""Backup, restauração e expurgo — operações privativas do administrador."""
import io
import json
import zipfile

from app.models import Ata, Documento, LogAuditoria, Marco, Usuario
from app.services import backup as servico
from tests.conftest import login, pdf_falso


def _povoar(client, orientacao):
    """Cria conteúdo em vários módulos para que o ciclo cubra o esquema."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Revisão",
            "descricao": "",
            "tipo": "outro",
            "data_prevista": "2026-09-30",
            "etapa": 20,
        },
    )
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={
            "titulo": "Projeto",
            "marco_id": 0,
            "arquivo": pdf_falso("projeto.pdf"),
            "comentario": "",
        },
        content_type="multipart/form-data",
    )
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "P", "deliberacoes": "D"},
    )
    client.post("/auth/logout")


def test_backup_contem_todas_as_tabelas_e_os_arquivos(client, admin, orientacao, orientador):
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    resp = client.post("/admin/backup/gerar")

    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    assert "backup-ariadne-" in resp.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.data)) as z:
        nomes = z.namelist()
        assert "manifesto.json" in nomes
        for tabela in servico.ORDEM_TABELAS:
            assert f"dados/{tabela}.json" in nomes
        assert any(n.startswith("uploads/") for n in nomes)

        manifesto = json.loads(z.read("manifesto.json"))
        assert manifesto["versao_formato"] == servico.VERSAO_FORMATO
        assert manifesto["contagens"]["marco"] == 1
        assert manifesto["contagens"]["documento"] == 1


def test_ciclo_completo_apagar_e_restaurar(client, admin, orientacao, orientador, orientando):
    """O que importa: depois de apagar tudo, o backup devolve o sistema ao
    estado anterior, inclusive os arquivos enviados."""
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    pacote = client.post("/admin/backup/gerar").data
    usuarios_antes = Usuario.query.count()

    client.post("/admin/backup/expurgar", data={"confirmacao": "APAGAR"})
    assert Usuario.query.count() == 1  # só o admin executor
    assert Marco.query.count() == 0
    assert Documento.query.count() == 0
    assert Ata.query.count() == 0

    resp = client.post(
        "/admin/backup/restaurar",
        data={"arquivo": (io.BytesIO(pacote), "b.zip"), "confirmacao": "RESTAURAR"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Backup restaurado".encode() in resp.data
    assert Usuario.query.count() == usuarios_antes
    assert Marco.query.one().titulo == "Revisão"
    assert Documento.query.one().titulo == "Projeto"
    assert Ata.query.count() == 1
    # o vínculo entre entidades sobrevive ao trajeto
    assert Marco.query.one().orientacao.orientando.email == "orientando@teste.br"


def test_expurgo_preserva_a_conta_do_executor_e_registra(client, admin, orientacao, orientador):
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    client.post("/admin/backup/expurgar", data={"confirmacao": "APAGAR"})

    restantes = Usuario.query.all()
    assert [u.email for u in restantes] == ["admin@teste.br"]
    assert restantes[0].criado_por is None

    registros = LogAuditoria.query.all()
    assert len(registros) == 1  # a trilha some, menos o registro do próprio ato
    assert registros[0].acao == "expurgo_base"
    dados = json.loads(registros[0].dados_json)
    assert dados["conta_preservada"] == "admin@teste.br"
    assert dados["removidos"]["marco"] == 1


def test_expurgo_exige_a_palavra_exata(client, admin, orientacao, orientador):
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    resp = client.post(
        "/admin/backup/expurgar", data={"confirmacao": "apagar tudo"},
        follow_redirects=True,
    )
    assert "digite exatamente".encode() in resp.data
    assert Marco.query.count() == 1  # nada foi tocado


def test_restauracao_exige_a_palavra_exata(client, admin, orientacao, orientador):
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    pacote = client.post("/admin/backup/gerar").data
    client.post(
        "/admin/backup/restaurar",
        data={"arquivo": (io.BytesIO(pacote), "b.zip"), "confirmacao": "sim"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert Marco.query.count() == 1  # continua o original, não houve restauração


def test_restauracao_recusa_esquema_divergente(client, admin, orientacao, orientador):
    """Restaurar sobre esquema de outra versão gravaria dados numa estrutura
    incompatível; a recusa vem antes de tocar nos dados."""
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    original = client.post("/admin/backup/gerar").data

    adulterado = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as fonte, zipfile.ZipFile(
        adulterado, "w"
    ) as destino:
        for item in fonte.namelist():
            conteudo = fonte.read(item)
            if item == "manifesto.json":
                manifesto = json.loads(conteudo)
                manifesto["revisao_alembic"] = "revisao_de_outra_epoca"
                conteudo = json.dumps(manifesto).encode()
            destino.writestr(item, conteudo)

    resp = client.post(
        "/admin/backup/restaurar",
        data={
            "arquivo": (io.BytesIO(adulterado.getvalue()), "b.zip"),
            "confirmacao": "RESTAURAR",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "outra versão do esquema".encode() in resp.data
    assert Marco.query.count() == 1  # base intacta


def test_restauracao_recusa_arquivo_que_nao_e_backup(client, admin):
    login(client, "admin@teste.br")
    resp = client.post(
        "/admin/backup/restaurar",
        data={
            "arquivo": (io.BytesIO(b"nao sou um zip"), "x.zip"),
            "confirmacao": "RESTAURAR",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "não é um ZIP válido".encode() in resp.data


def test_restauracao_preserva_conta_ausente_do_backup(client, admin, orientacao, orientador):
    """Backup anterior à criação do operador não pode trancá-lo do lado de fora."""
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    original = client.post("/admin/backup/gerar").data

    sem_admin = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as fonte, zipfile.ZipFile(
        sem_admin, "w"
    ) as destino:
        for item in fonte.namelist():
            conteudo = fonte.read(item)
            if item == "dados/usuario.json":
                usuarios = [
                    u for u in json.loads(conteudo) if u["email"] != "admin@teste.br"
                ]
                conteudo = json.dumps(usuarios, default=str).encode()
            destino.writestr(item, conteudo)

    resp = client.post(
        "/admin/backup/restaurar",
        data={
            "arquivo": (io.BytesIO(sem_admin.getvalue()), "b.zip"),
            "confirmacao": "RESTAURAR",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "conta foi preservada".encode() in resp.data
    preservado = Usuario.query.filter_by(email="admin@teste.br").one()
    assert preservado.papel == "admin" and preservado.ativo
    # e continua sendo possível entrar com ela
    client.post("/auth/logout")
    assert login(client, "admin@teste.br").status_code == 200


def test_arquivo_com_nome_fora_do_padrao_e_descartado(client, admin, orientacao, orientador):
    """Defesa contra travessia de caminho: só nomes no padrão UUID.ext entram."""
    _povoar(client, orientacao)
    login(client, "admin@teste.br")
    original = client.post("/admin/backup/gerar").data

    malicioso = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as fonte, zipfile.ZipFile(
        malicioso, "w"
    ) as destino:
        for item in fonte.namelist():
            destino.writestr(item, fonte.read(item))
        destino.writestr("uploads/../../../invadido.txt", b"conteudo")

    client.post(
        "/admin/backup/restaurar",
        data={
            "arquivo": (io.BytesIO(malicioso.getvalue()), "b.zip"),
            "confirmacao": "RESTAURAR",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    import os

    pasta = client.application.config["UPLOAD_FOLDER"]
    assert "invadido.txt" not in os.listdir(pasta)
    assert not os.path.exists(os.path.join(pasta, "..", "..", "..", "invadido.txt"))


def test_operacoes_restritas_ao_admin(client, orientador, orientando):
    for email in ("orientador@teste.br", "orientando@teste.br"):
        login(client, email)
        assert client.get("/admin/backup").status_code == 403
        assert client.post("/admin/backup/gerar").status_code == 403
        assert (
            client.post(
                "/admin/backup/expurgar", data={"confirmacao": "APAGAR"}
            ).status_code
            == 403
        )
        client.post("/auth/logout")
