"""Materiais de consulta: o orientador publica uma vez para os orientandos
escolhidos; só eles (e a equipe do vínculo) veem; não são entregas."""
import io
import os
import uuid
import zipfile
from datetime import date, timedelta

from app.extensions import db
from app.models import Documento, LogAuditoria, Marco, Material
from app.services import eliminacao
from tests.conftest import login, pdf_falso


def _publicar(client, vinculos, titulo="Apostila de Python", tarefa="", arquivo=None):
    return client.post("/materiais/", data={
        "titulo": titulo, "descricao": "Leia os capítulos 1 a 4.",
        "arquivo": arquivo or pdf_falso("apostila.pdf"),
        "orientacoes": [str(o.id) for o in vinculos], "tarefa": tarefa,
    }, content_type="multipart/form-data", follow_redirects=True)


def _disco(app):
    return set(os.listdir(app.config["UPLOAD_FOLDER"]))


def test_publica_para_os_escolhidos_e_so_eles_veem(
    client, app, orientacao, orientacao2, orientador, orientando, orientando2
):
    login(client, "orientador@teste.br")
    resp = _publicar(client, [orientacao])
    assert "disponível para" in resp.data.decode()
    material = Material.query.one()
    assert [o.id for o in material.orientacoes] == [orientacao.id]
    assert LogAuditoria.query.filter_by(acao="publicacao_material").count() == 1
    client.post("/auth/logout")

    login(client, "orientando@teste.br")  # escolhido: vê em Documentos e baixa
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/").data.decode()
    assert "Materiais de consulta" in pagina and "Apostila de Python" in pagina
    assert client.get(f"/materiais/{material.id}/download").status_code == 200
    client.post("/auth/logout")

    login(client, "orientando2@teste.br")  # não escolhido: não vê nem baixa
    pagina = client.get(f"/orientacoes/{orientacao2.id}/documentos/").data.decode()
    assert "Apostila de Python" not in pagina
    assert client.get(f"/materiais/{material.id}/download").status_code == 404


def test_material_nao_e_documento_nem_entrega(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    _publicar(client, [orientacao])
    assert Documento.query.count() == 0


def test_tarefa_em_grupo_compartilha_com_os_dois_e_aparece_na_tarefa(
    client, orientacao, orientacao2, orientador, orientando
):
    gid = uuid.uuid4().hex
    marcos = []
    for o in (orientacao, orientacao2):
        m = Marco(orientacao_id=o.id, titulo="Fundamentos de Python", grupo_id=gid,
                  data_prevista=date.today() + timedelta(days=20))
        db.session.add(m)
        marcos.append(m)
    db.session.commit()
    login(client, "orientador@teste.br")
    pagina = client.get("/materiais/").data.decode()
    assert f'value="g:{gid}"' in pagina and "(grupo:" in pagina  # uma opção só
    _publicar(client, [], tarefa=f"g:{gid}")
    material = Material.query.one()
    assert {o.id for o in material.orientacoes} == {orientacao.id, orientacao2.id}
    assert {m.id for m in material.marcos} == {m.id for m in marcos}
    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/{marcos[0].id}").data.decode()
    assert "Material de consulta" in pagina and "Apostila de Python" in pagina


def test_exige_destinatario(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _publicar(client, [])
    assert "Escolha ao menos um orientando" in resp.data.decode()
    assert Material.query.count() == 0


def test_arquivo_invalido_e_recusado(client, app, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _publicar(client, [orientacao], arquivo=(io.BytesIO(b"MZ"), "virus.exe"))
    assert "não permitida" in resp.data.decode()
    assert Material.query.count() == 0
    assert _disco(app) == set()


def test_tarefa_de_outro_orientador_e_ignorada(client, orientacao, orientador):
    from app.models import Orientacao, Usuario

    outro = Usuario(nome="Outro", email="outro@teste.br", papel="orientador")
    outro.set_senha("senha-teste-123")
    db.session.add(outro)
    db.session.flush()
    alheia = Orientacao(orientador_id=outro.id, orientando_id=orientacao.orientando_id,
                        modalidade="ic", titulo_projeto="Alheio", data_inicio=date(2026, 1, 1))
    db.session.add(alheia)
    db.session.flush()
    marco = Marco(orientacao_id=alheia.id, titulo="X", data_prevista=date(2027, 1, 1))
    db.session.add(marco)
    db.session.commit()
    login(client, "orientador@teste.br")
    resp = _publicar(client, [orientacao], tarefa=f"m:{marco.id}")  # forjado
    assert "Tarefa inválida" in resp.data.decode()
    assert Material.query.count() == 0


def test_autor_exclui_e_o_arquivo_some(client, app, orientacao, orientador, orientando):
    login(client, "orientador@teste.br")
    _publicar(client, [orientacao])
    material = Material.query.one()
    assert len(_disco(app)) == 1
    client.post("/auth/logout")
    login(client, "orientando@teste.br")  # quem recebeu não exclui
    assert client.post(f"/materiais/{material.id}/excluir").status_code == 403
    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    client.post(f"/materiais/{material.id}/excluir")
    assert Material.query.count() == 0
    assert _disco(app) == set()
    assert LogAuditoria.query.filter_by(acao="exclusao_material").count() == 1


def test_orientando_nao_publica(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get("/materiais/").status_code == 403


def test_eliminacao_lgpd_remove_so_o_compartilhamento(
    client, orientacao, orientador, orientando, admin
):
    login(client, "orientador@teste.br")
    _publicar(client, [orientacao])
    client.post("/auth/logout")
    eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()
    material = Material.query.one()  # o material é do orientador: fica
    assert material.orientacoes == []


def test_backup_leva_os_materiais(client, orientacao, orientador, admin):
    login(client, "orientador@teste.br")
    _publicar(client, [orientacao])
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    pacote = client.post("/admin/backup/gerar").data
    with zipfile.ZipFile(io.BytesIO(pacote)) as z:
        nomes = z.namelist()
    assert {"dados/material.json", "dados/material_orientacao.json",
            "dados/material_marco.json"} <= set(nomes)
