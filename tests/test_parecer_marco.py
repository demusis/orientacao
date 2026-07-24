"""P-6: ao emitir parecer favorável numa versão cujo documento cumpre um marco,
o marco pode ser concluído no mesmo passo. Resultado desfavorável nunca conclui."""
from datetime import date

from app.extensions import db
from app.models import Documento, Marco, VersaoDocumento
from tests.conftest import login


def _montar_entrega_de_marco(orientacao, orientando):
    """Cria um marco, um documento ligado a ele e uma versão — a entrega que o
    parecer vai apreciar."""
    marco = Marco(
        orientacao_id=orientacao.id,
        titulo="Exame de qualificação",
        tipo="qualificacao",
        etapa=40,
        data_prevista=date(2027, 3, 1),
    )
    db.session.add(marco)
    db.session.flush()
    documento = Documento(
        orientacao_id=orientacao.id,
        marco_id=marco.id,
        titulo="Texto de qualificação",
        criado_por=orientando.id,
    )
    db.session.add(documento)
    db.session.flush()
    versao = VersaoDocumento(
        documento_id=documento.id,
        numero_versao=1,
        nome_original="qualificacao.pdf",
        nome_fisico="a" * 32 + ".pdf",
        tamanho_bytes=10,
        mimetype="application/pdf",
        enviado_por=orientando.id,
    )
    db.session.add(versao)
    db.session.commit()
    return marco, versao


def _emitir(client, orientacao, versao, *, resultado, concluir):
    dados = {
        "tipo": "documento",
        "versao_documento_id": versao.id,
        "conteudo": "Apreciação do texto.",
        "resultado": resultado,
    }
    if concluir:
        dados["concluir_marco"] = "y"
    return client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo", data=dados, follow_redirects=True
    )


def test_parecer_aprovado_conclui_marco_vinculado(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    r = _emitir(client, orientacao, versao, resultado="aprovado", concluir=True)
    assert r.status_code == 200
    assert db.session.get(Marco, marco.id).status == "concluido"


def test_parecer_reprovado_nao_conclui_marco(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    _emitir(client, orientacao, versao, resultado="reprovado", concluir=True)
    assert db.session.get(Marco, marco.id).status != "concluido"


def test_sem_checkbox_nao_conclui_marco(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    _emitir(client, orientacao, versao, resultado="aprovado", concluir=False)
    assert db.session.get(Marco, marco.id).status != "concluido"
