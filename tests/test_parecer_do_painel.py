"""O Painel leva quem avalia direto ao parecer da versão.

O quadro "Versões aguardando parecer" existe para fechar o ciclo de uma entrega,
mas o link levava à página do documento — a mesma para qualquer papel. Quem
avaliava tinha de navegar até Pareceres e reencontrar na lista a versão que
acabara de ver. Atrito plausível para o achado U-6 do ciclo de 21/07/2026: três
entregas sem parecer.
"""

from app.extensions import db
from app.models import Documento, Parecer, VersaoDocumento
from tests.conftest import login


def _versao(orientacao, titulo="Projeto de pesquisa", nome="p.pdf"):
    doc = Documento(
        orientacao_id=orientacao.id,
        titulo=titulo,
        criado_por=orientacao.orientando_id,
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        nome_original=nome,
        nome_fisico=f"{doc.id:032x}.pdf",
        tamanho_bytes=2048,
        mimetype="application/pdf",
        enviado_por=orientacao.orientando_id,
    )
    db.session.add(v)
    db.session.commit()
    return v


# --- o destino depende do papel ---


def test_painel_do_orientador_leva_ao_parecer(client, orientacao, orientador):
    v = _versao(orientacao)
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()

    assert f"/pareceres/novo?versao={v.id}" in pagina
    assert "Emitir parecer" in pagina


def test_painel_do_orientando_leva_ao_documento(client, orientacao, orientando):
    _versao(orientacao)
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()

    assert "Abrir documento" in pagina
    assert "pareceres/novo" not in pagina


# --- pré-seleção ---


def test_versao_vem_preselecionada_e_tipo_documento(client, orientacao, orientador):
    v = _versao(orientacao)
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={v.id}"
    ).data.decode()

    assert f'<option selected value="{v.id}">' in pagina
    assert '<option selected value="documento">' in pagina


def test_formulario_identifica_o_que_se_avalia(client, orientacao, orientador, orientando):
    """Emitir parecer sem poder ler o que se avalia seria caminho pela metade."""
    v = _versao(orientacao, titulo="Relatório parcial", nome="relatorio.pdf")
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={v.id}"
    ).data.decode()

    assert "Relatório parcial" in pagina
    assert "relatorio.pdf" in pagina
    assert orientando.nome in pagina
    assert f"versoes/{v.id}/download" in pagina


def test_sem_versao_o_formulario_segue_como_antes(client, orientacao, orientador):
    _versao(orientacao)
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo"
    ).data.decode()

    assert "Emitir parecer" in pagina
    assert "Baixar arquivo" not in pagina


# --- a versão precisa ser desta orientação ---


def test_versao_de_outro_vinculo_e_ignorada(client, orientacao, orientacao2, orientador):
    """O acesso já passou por `orientacao_autorizada`, mas identificador de
    outro vínculo não pode ser pré-selecionado nem revelar na tela o título de
    documento alheio."""
    alheia = _versao(orientacao2, titulo="Documento Sigiloso De Outro Vinculo")
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={alheia.id}"
    ).data.decode()

    assert "Documento Sigiloso De Outro Vinculo" not in pagina
    assert f'<option selected value="{alheia.id}">' not in pagina


def test_versao_inexistente_nao_quebra(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.get(f"/orientacoes/{orientacao.id}/pareceres/novo?versao=99999")
    assert resp.status_code == 200


def test_versao_nao_numerica_nao_quebra(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.get(f"/orientacoes/{orientacao.id}/pareceres/novo?versao=abc")
    assert resp.status_code == 200


# --- link envelhecido ---


def test_versao_ja_avaliada_exibe_aviso(client, orientacao, orientador):
    """O Painel é leitura de momento: pode-se chegar por link antigo depois de
    já ter avaliado. Aviso, não bloqueio."""
    v = _versao(orientacao)
    db.session.add(
        Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=v.id,
            tipo="documento",
            conteudo="Adequado.",
            resultado="aprovado",
            emitido_por=orientador.id,
        )
    )
    db.session.commit()

    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={v.id}"
    ).data.decode()

    assert "já recebeu parecer" in pagina
    # continua sendo possível emitir
    assert 'name="conteudo"' in pagina


# --- o ciclo fecha ---


def test_emitir_pelo_painel_remove_a_pendencia(client, orientacao, orientador):
    v = _versao(orientacao)
    login(client, "orientador@teste.br")

    client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={v.id}",
        data={
            "tipo": "documento",
            "versao_documento_id": v.id,
            "conteudo": "Aprovado com pequenas ressalvas.",
            "resultado": "aprovado_com_ressalvas",
        },
        follow_redirects=True,
    )

    parecer = Parecer.query.one()
    assert parecer.versao_documento_id == v.id
    # a linha some do Painel — é o ciclo se fechando, do ponto de vista de quem usa
    assert "Emitir parecer" not in client.get("/dashboard").data.decode()


def test_atalho_tambem_na_pagina_do_documento(client, orientacao, orientador):
    v = _versao(orientacao)
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{v.documento_id}"
    ).data.decode()

    assert f"/pareceres/novo?versao={v.id}" in pagina


def test_orientando_nao_ve_o_atalho_no_documento(client, orientacao, orientando):
    v = _versao(orientacao)
    login(client, "orientando@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{v.documento_id}"
    ).data.decode()

    assert "pareceres/novo" not in pagina
