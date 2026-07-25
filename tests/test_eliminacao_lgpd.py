"""Eliminação de dados de um usuário (LGPD, art. 18): apaga o privado do titular
e anonimiza o que deve sobreviver (trilha, registros de terceiros)."""
import json
from datetime import UTC, date, datetime

import pytest

from app.extensions import db
from app.models import (
    Ata,
    ConfiguracaoEmail,
    Documento,
    LogAuditoria,
    Marco,
    ModeloDocumento,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Usuario,
    VersaoDocumento,
)
from app.models.ata import AtaParticipacao
from app.services import eliminacao
from app.services.exportacao import congelar_ata, congelar_parecer
from app.services.usuarios import GestaoUsuarioInvalida
from tests.conftest import login


def _versao(orientacao, autor, nome_fisico):
    doc = Documento(
        orientacao_id=orientacao.id, titulo="Texto", criado_por=autor.id
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id, numero_versao=1, nome_original="t.pdf",
        nome_fisico=nome_fisico, tamanho_bytes=10, mimetype="application/pdf",
        enviado_por=autor.id,
    )
    db.session.add(v)
    db.session.flush()
    return doc, v


def _ata(orientador, orientacoes, tipo):
    ata = Ata(
        tipo=tipo, orientador_id=orientador.id, redigida_por=orientador.id,
        data_reuniao=date(2026, 3, 1), pauta="Pauta", deliberacoes="Delib",
        status="finalizada", finalizada_em=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        participacoes=[AtaParticipacao(orientacao_id=o.id) for o in orientacoes],
    )
    db.session.add(ata)
    db.session.flush()
    congelar_ata(ata)  # embute os nomes no conteudo_congelado
    return ata


# ---------------------------------------------------------------------------
# Orientando com histórico


def test_orientando_com_historico(app, orientacao, orientacao2, orientador, orientando, orientando2, admin):
    marco = Marco(orientacao_id=orientacao.id, titulo="M", tipo="outro", etapa=0,
                  data_prevista=date(2026, 8, 1))
    db.session.add(marco)
    _, versao = _versao(orientacao, orientando, "a" * 32 + ".pdf")
    parecer = Parecer(orientacao_id=orientacao.id, versao_documento_id=versao.id,
                      tipo="documento", conteudo="ok", resultado="aprovado",
                      emitido_por=orientador.id)
    db.session.add(parecer)
    db.session.flush()
    congelar_parecer(parecer)
    ata_ind = _ata(orientador, [orientacao], "individual")
    ata_grupo = _ata(orientador, [orientacao, orientacao2], "grupo")
    db.session.add(LogAuditoria(usuario_id=orientando.id, acao="login", entidade="usuario"))
    db.session.add(LogAuditoria(usuario_id=None, acao="login_falho", entidade="usuario",
                                dados_json=json.dumps({"email": orientando.email})))
    db.session.commit()

    b_id, o_id, ind_id, grupo_id = orientando.id, orientacao.id, ata_ind.id, ata_grupo.id
    resumo = eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()

    # conta e dados privados sumiram
    assert db.session.get(Usuario, b_id) is None
    assert db.session.get(Orientacao, o_id) is None
    assert db.session.get(Ata, ind_id) is None
    assert Parecer.query.filter_by(orientacao_id=o_id).count() == 0
    assert Marco.query.filter_by(orientacao_id=o_id).count() == 0
    assert "a" * 32 + ".pdf" in resumo["arquivos"]

    # ata de grupo sobrevive, sem a participação dele e com o nome raspado
    grupo = db.session.get(Ata, grupo_id)
    assert grupo is not None
    assert [p.orientacao_id for p in grupo.participacoes] == [orientacao2.id]
    congelado = json.loads(grupo.conteudo_congelado)
    nomes = [p["orientando"] for p in congelado["participacoes"]]
    assert eliminacao.REMOVIDO in nomes
    assert orientando2.nome in nomes
    assert orientando.nome not in grupo.conteudo_congelado

    # trilha anonimizada
    assert LogAuditoria.query.filter_by(usuario_id=b_id).count() == 0
    falho = LogAuditoria.query.filter_by(acao="login_falho").first()
    assert orientando.email not in (falho.dados_json or "")
    assert eliminacao.REMOVIDO in falho.dados_json


# ---------------------------------------------------------------------------
# Orientador


def test_orientador_sem_vinculo_ativo_reatribui(app, orientacao, orientador, admin):
    orientacao.status = "concluida"  # nenhum vínculo ativo sob este orientador
    ata = _ata(orientador, [orientacao], "individual")
    db.session.commit()
    ata_id, orientador_nome = ata.id, orientador.nome

    eliminacao.eliminar_usuario(orientador, admin)
    db.session.commit()

    sentinela = Usuario.query.filter_by(email=eliminacao._SENTINELA_EMAIL).one()
    ata = db.session.get(Ata, ata_id)  # sobrevive (é registro do orientando)
    assert ata.orientador_id == sentinela.id
    assert ata.redigida_por == sentinela.id
    congelado = json.loads(ata.conteudo_congelado)
    assert congelado["orientador"] == eliminacao.REMOVIDO
    assert orientador_nome not in ata.conteudo_congelado


def test_orientador_com_vinculo_ativo_recusa(app, orientacao, orientador, admin):
    # a fixture orientacao nasce ativa
    with pytest.raises(GestaoUsuarioInvalida):
        eliminacao.eliminar_usuario(orientador, admin)
    db.session.rollback()
    assert db.session.get(Usuario, orientador.id) is not None


# ---------------------------------------------------------------------------
# Guardas


def test_autoeliminacao_recusada(app, admin):
    with pytest.raises(GestaoUsuarioInvalida):
        eliminacao.eliminar_usuario(admin, admin)


def test_ultimo_admin_recusado(app, admin):
    outro_admin = Usuario(nome="Admin 2", email="admin2@teste.br", papel="admin", ativo=False)
    outro_admin.set_senha("x")
    db.session.add(outro_admin)
    db.session.commit()
    # `admin` é o único admin ATIVO; eliminá-lo é recusado
    with pytest.raises(GestaoUsuarioInvalida):
        eliminacao.eliminar_usuario(admin, outro_admin)


# ---------------------------------------------------------------------------
# Nenhuma FK pendente após eliminar


def test_sem_fk_pendente_ao_id(app, orientacao, orientacao2, orientador, orientando, admin):
    _ata(orientador, [orientacao, orientacao2], "grupo")
    db.session.commit()
    b_id = orientando.id
    eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()

    pendentes = (
        Orientacao.query.filter((Orientacao.orientando_id == b_id) | (Orientacao.orientador_id == b_id)).count()
        + Documento.query.filter_by(criado_por=b_id).count()
        + VersaoDocumento.query.filter_by(enviado_por=b_id).count()
        + Ata.query.filter((Ata.orientador_id == b_id) | (Ata.redigida_por == b_id) | (Ata.cancelada_por == b_id)).count()
        + Parecer.query.filter_by(emitido_por=b_id).count()
        + AtaParticipacao.query.filter_by(presenca_registrada_por=b_id).count()
        + OrientacaoOrientador.query.filter_by(usuario_id=b_id).count()
        + LogAuditoria.query.filter_by(usuario_id=b_id).count()
        + Usuario.query.filter_by(criado_por=b_id).count()
    )
    assert pendentes == 0


# ---------------------------------------------------------------------------
# Rota: confirmação por e-mail


def test_rota_confirmacao_por_email(client, orientacao, orientando, admin):
    db.session.commit()
    b_id, email = orientando.id, orientando.email
    login(client, "admin@teste.br")
    url = f"/admin/usuarios/{b_id}/eliminar"

    # e-mail errado não elimina
    r = client.post(url, data={"confirmacao": "errado@x.br"}, follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Usuario, b_id) is not None

    # e-mail certo elimina
    r = client.post(url, data={"confirmacao": email}, follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Usuario, b_id) is None


# ---------------------------------------------------------------------------
# A conta-sentinela é infraestrutura: nem eliminável, nem gerível


def test_sentinela_nao_eliminavel(app, orientacao, orientando, admin):
    db.session.commit()
    eliminacao.eliminar_usuario(orientando, admin)  # faz a sentinela nascer
    db.session.commit()
    sentinela = Usuario.query.filter_by(email=eliminacao._SENTINELA_EMAIL).one()
    with pytest.raises(GestaoUsuarioInvalida):
        eliminacao.eliminar_usuario(sentinela, admin)
    db.session.rollback()
    assert db.session.get(Usuario, sentinela.id) is not None


def test_sentinela_fora_da_gestao(client, orientacao, orientando, admin):
    db.session.commit()
    login(client, "admin@teste.br")
    client.post(
        f"/admin/usuarios/{orientando.id}/eliminar",
        data={"confirmacao": orientando.email},
    )
    sentinela = Usuario.query.filter_by(email=eliminacao._SENTINELA_EMAIL).one()
    s_id = sentinela.id

    # fora da lista de usuários
    r = client.get("/admin/usuarios")
    assert "lgpd.invalid" not in r.get_data(as_text=True)
    # rotas de gestão desviam sem tocar na conta
    assert client.get(f"/admin/usuarios/{s_id}/editar").status_code == 302
    assert client.get(f"/admin/usuarios/{s_id}/eliminar").status_code == 302
    client.post(
        f"/admin/usuarios/{s_id}/eliminar",
        data={"confirmacao": eliminacao._SENTINELA_EMAIL},
    )
    client.post(
        f"/admin/usuarios/{s_id}/editar",
        data={
            "nome": "X",
            "email": eliminacao._SENTINELA_EMAIL,
            "papel": "orientador",
            "ativo": "y",
        },
    )
    client.post(f"/admin/usuarios/{s_id}/senha-temporaria", data={})
    sentinela = db.session.get(Usuario, s_id)
    assert sentinela is not None
    assert sentinela.ativo is False


# ---------------------------------------------------------------------------
# FKs anuláveis fora do circuito de orientação


def test_fk_modelo_e_configuracao_anulados(app, orientador, admin):
    modelo = ModeloDocumento(
        titulo="Modelo", nome_original="m.pdf", nome_fisico="f" * 32 + ".pdf",
        tamanho_bytes=1, mimetype="application/pdf", enviado_por=orientador.id,
    )
    db.session.add(modelo)
    config = ConfiguracaoEmail.vigente()
    config.registrar_alteracao(orientador.id)
    db.session.commit()

    eliminacao.eliminar_usuario(orientador, admin)
    db.session.commit()

    assert modelo.enviado_por is None
    assert config.atualizado_por is None


# ---------------------------------------------------------------------------
# Ata de grupo que só envolve vínculos do próprio titular não é "de terceiros"


def test_ata_grupo_so_do_titular_some(app, orientacao, orientador, orientando, admin):
    segundo = Orientacao(
        orientador_id=orientador.id, orientando_id=orientando.id,
        modalidade="doutorado", titulo_projeto="Segundo Projeto do Titular",
        data_inicio=date(2026, 2, 2), status="concluida",
    )
    db.session.add(segundo)
    db.session.flush()
    ata = _ata(orientador, [orientacao, segundo], "grupo")
    db.session.commit()
    ata_id = ata.id

    eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()

    # nenhum terceiro participava: a ata some inteira, sem sobrar pauta órfã
    assert db.session.get(Ata, ata_id) is None


# ---------------------------------------------------------------------------
# Raspagem guiada por papel/id: alcança nome congelado antes de renomeação


def test_raspagem_alcanca_nome_antigo(app, orientacao, orientador, admin):
    orientacao.status = "concluida"
    ata = _ata(orientador, [orientacao], "individual")  # congela o nome atual
    db.session.commit()
    nome_congelado = orientador.nome
    orientador.nome = "Nome Novo Depois do Congelamento"
    db.session.commit()
    ata_id = ata.id

    eliminacao.eliminar_usuario(orientador, admin)
    db.session.commit()

    congelado = json.loads(db.session.get(Ata, ata_id).conteudo_congelado)
    assert congelado["orientador"] == eliminacao.REMOVIDO
    assert congelado["redator"] == eliminacao.REMOVIDO
    assert nome_congelado not in db.session.get(Ata, ata_id).conteudo_congelado


# ---------------------------------------------------------------------------
# Trilha: igualdade de valor (não substring) e sem diferenciar caixa


def test_trilha_preserva_terceiro_e_alcanca_caixa(app, orientacao, orientando, admin):
    email_terceiro = "mari" + orientando.email  # contém o do titular por dentro
    db.session.add(LogAuditoria(
        usuario_id=None, acao="login_falho", entidade="usuario",
        dados_json=json.dumps({"email": email_terceiro}),
    ))
    db.session.add(LogAuditoria(
        usuario_id=None, acao="login_falho", entidade="usuario",
        dados_json=json.dumps({"email": orientando.email.upper()}),  # caixa alta
    ))
    # lançamento de gestão SOBRE a conta: dados descartados por inteiro
    db.session.add(LogAuditoria(
        usuario_id=admin.id, acao="edicao_usuario", entidade="usuario",
        entidade_id=orientando.id,
        dados_json=json.dumps({"email": "antigo@teste.br"}),
    ))
    db.session.commit()

    eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()

    falhos = LogAuditoria.query.filter_by(acao="login_falho").all()
    dados = [json.loads(log.dados_json) for log in falhos]
    # o e-mail do terceiro fica intacto (nada de "mari[removido]")
    assert {"email": email_terceiro} in dados
    # a variante em caixa alta do titular foi raspada
    assert {"email": eliminacao.REMOVIDO} in dados
    edicao = LogAuditoria.query.filter_by(acao="edicao_usuario").one()
    assert edicao.dados_json is None
