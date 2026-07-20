"""Indicadores agregados que alimentam o ciclo de avaliação."""
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    Documento,
    LogAuditoria,
    Marco,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Usuario,
    VersaoDocumento,
)
from app.services import indicadores

from tests.conftest import _criar_usuario, login, pdf_falso


def test_adesao_distingue_quem_nunca_acessou(app, admin, orientador, orientando):
    orientador.ultimo_acesso = datetime.utcnow()
    orientando.ultimo_acesso = datetime.utcnow() - timedelta(days=45)
    db.session.commit()

    a = indicadores.adesao()
    assert a["contas_por_papel"] == {"admin": 1, "orientador": 1, "orientando": 1}
    assert a["contas_ativas"] == 3
    assert a["nunca_acessaram"] == 1  # apenas o admin
    assert a[f"sem_acesso_ha_{indicadores.OCIOSO_CURTO}d"] == 1  # o orientando
    assert a[f"sem_acesso_ha_{indicadores.OCIOSO_LONGO}d"] == 0


def test_conta_desativada_sai_da_adesao(app, orientador):
    orientador.ativo = False
    db.session.commit()
    a = indicadores.adesao()
    assert a["contas_ativas"] == 0
    assert a["contas_inativas"] == 1
    assert a["nunca_acessaram"] == 0


def test_vinculo_ativo_sem_marco_e_contado(app, orientacao, orientador, orientando):
    v = indicadores.vinculos()
    assert v["por_status"] == {"ativa": 1}
    assert v["por_modalidade"] == {"mestrado": 1}
    assert v["ativos_sem_marco"] == 1
    assert v["com_coorientador"] == 0

    db.session.add(
        Marco(orientacao_id=orientacao.id, titulo="M", data_prevista=date(2026, 9, 1))
    )
    co = _criar_usuario("Co", "co@teste.br", "orientador")
    db.session.add(
        OrientacaoOrientador(
            orientacao_id=orientacao.id, usuario_id=co.id, funcao="coorientador"
        )
    )
    db.session.commit()

    v = indicadores.vinculos()
    assert v["ativos_sem_marco"] == 0
    assert v["com_coorientador"] == 1


def test_fluxo_separa_atraso_de_espera_por_confirmacao(app, orientacao):
    ontem = date.today() - timedelta(days=3)
    db.session.add_all(
        [
            Marco(orientacao_id=orientacao.id, titulo="Vencido", data_prevista=ontem),
            Marco(
                orientacao_id=orientacao.id,
                titulo="Entregue",
                data_prevista=date.today() + timedelta(days=10),
                conclusao_sinalizada=True,
                status="em_andamento",
                etapa=60,
            ),
            Marco(
                orientacao_id=orientacao.id,
                titulo="Pronto",
                data_prevista=ontem,
                status="concluido",
                etapa=60,
            ),
        ]
    )
    db.session.commit()

    f = indicadores.fluxo_de_marcos()
    assert f["total"] == 3
    assert f["atrasados"] == 1  # o concluído não conta, mesmo vencido
    assert f["aguardando_confirmacao"] == 1
    assert f["sem_etapa_classificada"] == 1  # só o "Vencido", que ficou em 0
    assert f["por_etapa"][60] == 2


def test_versao_superada_nao_conta_como_sem_parecer(client, orientacao, orientador):
    """Mesma regra do painel: pendência é a versão corrente, não o histórico."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={
            "titulo": "Projeto",
            "marco_id": 0,
            "arquivo": pdf_falso("v1.pdf"),
            "comentario": "",
        },
        content_type="multipart/form-data",
    )
    doc = Documento.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "comentario": ""},
        content_type="multipart/form-data",
    )

    d = indicadores.documentos()
    assert d["versoes"] == 2
    assert d["versoes_correntes_sem_parecer"] == 1  # só a v2

    versao_atual = doc.versao_atual
    db.session.add(
        Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=versao_atual.id,
            tipo="documento",
            conteudo="C",
            resultado="aprovado",
            emitido_por=orientador.id,
        )
    )
    db.session.commit()
    assert indicadores.documentos()["versoes_correntes_sem_parecer"] == 0


def test_rascunho_antigo_e_sinalizado(app, orientacao, orientador):
    antiga = datetime.utcnow() - timedelta(days=indicadores.RASCUNHO_VELHO + 5)
    db.session.add_all(
        [
            Ata(
                tipo="individual",
                orientador_id=orientador.id,
                data_reuniao=date(2026, 6, 1),
                pauta="P",
                deliberacoes="D",
                redigida_por=orientador.id,
                criada_em=antiga,
                participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
            ),
            Ata(
                tipo="individual",
                orientador_id=orientador.id,
                data_reuniao=date(2026, 7, 1),
                pauta="P2",
                deliberacoes="D2",
                redigida_por=orientador.id,
                status="finalizada",
                participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
            ),
        ]
    )
    db.session.commit()

    a = indicadores.atas()
    assert a["por_status"] == {"rascunho": 1, "finalizada": 1}
    assert a[f"rascunhos_ha_mais_de_{indicadores.RASCUNHO_VELHO}d"] == 1


def test_trilha_agrupa_por_acao_dentro_da_janela(app, orientador):
    agora = datetime.utcnow()
    db.session.add_all(
        [
            LogAuditoria(usuario_id=orientador.id, acao="login", entidade="usuario",
                         timestamp=agora),
            LogAuditoria(usuario_id=orientador.id, acao="login", entidade="usuario",
                         timestamp=agora - timedelta(days=2)),
            LogAuditoria(usuario_id=orientador.id, acao="criacao_marco", entidade="marco",
                         timestamp=agora - timedelta(days=1)),
            LogAuditoria(usuario_id=orientador.id, acao="acao_antiga", entidade="marco",
                         timestamp=agora - timedelta(days=60)),
        ]
    )
    db.session.commit()

    t = indicadores.trilha(dias=30)
    assert t["acoes_no_periodo"] == {"login": 2, "criacao_marco": 1}
    assert t["registros_no_periodo"] == 3
    assert t["registros_totais"] == 4
    # o vocabulário completo vem do banco e inclui o que está fora da janela
    assert "acao_antiga" in t["acoes_ja_registradas"]


def test_coletar_funciona_fora_de_requisicao(app, orientacao, orientador):
    """A distinção em relação a painel.pendencias(): não depende de current_user,
    o que permite executar por linha de comando."""
    snapshot = indicadores.coletar(dias=7)
    assert snapshot["janela_dias"] == 7
    assert set(snapshot) >= {
        "gerado_em",
        "adesao",
        "vinculos",
        "marcos",
        "documentos",
        "atas",
        "trilha",
    }
    # serializável: o relatório guarda o snapshot para o ciclo seguinte comparar
    import json

    assert json.dumps(snapshot, ensure_ascii=False, default=str)
