from datetime import date, timedelta

from app.extensions import db
from app.models import Documento, Marco
from tests.conftest import login, pdf_falso, texto_com_extensao_pdf


def _criar_marco(orientacao, dias=30):
    marco = Marco(
        orientacao_id=orientacao.id,
        titulo="Qualificação",
        data_prevista=date.today() + timedelta(days=dias),
    )
    db.session.add(marco)
    db.session.commit()
    return marco


def test_orientador_cria_marco(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Revisão bibliográfica",
            "descricao": "",
            "data_prevista": "2026-09-30",
            "tipo": "outro",
            "etapa": 20,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Marco.query.count() == 1
    assert Marco.query.one().etapa == 20


# --- etapa do projeto (substitui a antiga "ordem" numérica) ---


def test_formulario_oferece_etapas_em_lista(client, orientacao, orientador):
    from app.models.cronograma import ETAPA_MARCO_LABEL

    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/novo").data.decode()
    assert '<select id="etapa"' in pagina
    for rotulo in ETAPA_MARCO_LABEL.values():
        assert rotulo in pagina
    # não resta campo numérico de ordem
    assert 'name="ordem"' not in pagina


def test_etapa_fora_da_lista_e_recusada(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Código inválido",
            "descricao": "",
            "data_prevista": "2026-09-30",
            "tipo": "outro",
            "etapa": 7,  # não pertence a ETAPAS_MARCO
        },
        follow_redirects=True,
    )
    assert Marco.query.count() == 0


def test_marco_sem_etapa_fica_nao_classificado(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Sem etapa",
            "descricao": "",
            "data_prevista": "2026-09-30",
            "tipo": "outro",
        },
        follow_redirects=True,
    )
    assert Marco.query.one().etapa == 0


def test_cronograma_ordena_por_etapa_e_depois_por_data(client, orientacao, orientador):
    """Empate de etapa é a regra, não a exceção: sem desempate por data a
    listagem sairia em ordem indefinida."""
    for titulo, etapa, dia in [
        ("Redação final", 60, 5),
        ("Coleta B", 40, 20),
        ("Coleta A", 40, 10),
        ("Pendente de classificação", 0, 1),
    ]:
        db.session.add(
            Marco(
                orientacao_id=orientacao.id,
                titulo=titulo,
                data_prevista=date(2026, 9, dia),
                etapa=etapa,
            )
        )
    db.session.commit()

    assert [m.titulo for m in orientacao.marcos.all()] == [
        "Pendente de classificação",
        "Coleta A",
        "Coleta B",
        "Redação final",
    ]


def test_listagem_exibe_rotulo_da_etapa(client, orientacao, orientador):
    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Escrita",
            data_prevista=date(2026, 9, 30),
            etapa=50,
        )
    )
    db.session.commit()
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/", follow_redirects=True
    ).data.decode()
    assert "Redação" in pagina


def test_listas_de_classificacao_nao_se_sobrepoem():
    """Tipo e etapa respondem a perguntas distintas — o ato datado e o período.
    Rótulo repetido nas duas listas permitiria registrar a mesma informação em
    dois lugares, ou em nenhum, que foi o defeito corrigido em d7b3f915a6c8.
    Sem esta asserção a sobreposição volta no primeiro rótulo acrescentado."""
    from app.models.cronograma import ETAPA_MARCO_LABEL, TIPO_MARCO_LABEL

    def normaliza(rotulos):
        # "Relatório (parcial, anual ou final)" compara pelo termo, não pela glosa
        return {r.split(" (")[0].strip().casefold() for r in rotulos}

    comuns = normaliza(TIPO_MARCO_LABEL.values()) & normaliza(
        ETAPA_MARCO_LABEL.values()
    )
    assert not comuns, f"rótulos em ambas as listas: {sorted(comuns)}"


def test_tipo_novo_e_aceito_pelo_formulario(client, orientacao, orientador):
    """Cobre o Enum novo: comitê de ética não existia na tipologia anterior."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Submissão ao CEP",
            "descricao": "",
            "tipo": "comite_etica",
            "data_prevista": "2026-09-30",
            "etapa": 10,
        },
    )
    db.session.commit()
    assert Marco.query.one().tipo == "comite_etica"


def test_tipo_fora_da_lista_e_recusado(client, orientacao, orientador):
    """Proficiência saiu da tipologia; o SelectField não pode mais aceitá-la."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Exame de idioma",
            "descricao": "",
            "tipo": "proficiencia",
            "data_prevista": "2026-09-30",
            "etapa": 10,
        },
    )
    assert Marco.query.count() == 0


def test_fluxo_sinalizacao_e_confirmacao(client, orientacao, orientador, orientando):
    marco = _criar_marco(orientacao)

    login(client, "orientando@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/sinalizar")
    assert marco.conclusao_sinalizada is True
    assert marco.status == "em_andamento"

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/confirmar")
    assert marco.status == "concluido"
    assert marco.data_conclusao == date.today()


# --- página da tarefa (abrir o marco) ---


def test_pagina_da_tarefa_renderiza_e_o_titulo_linka(client, orientacao, orientador, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    # o título no cronograma linka para a página da tarefa
    lista = client.get(f"/orientacoes/{orientacao.id}/cronograma/").data.decode()
    assert f"/cronograma/{marco.id}\"" in lista
    # a página abre e traz as seções
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}").data.decode()
    assert "Qualificação" in pagina
    assert "Anexar documento" in pagina
    assert "Entregas ligadas" in pagina


def test_sinalizar_com_nota_grava_a_nota(client, orientacao, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/sinalizar",
        data={"nota": "Entreguei o capítulo revisado."},
    )
    assert marco.conclusao_sinalizada is True
    assert marco.nota_conclusao == "Entreguei o capítulo revisado."


def test_anexar_documento_cria_documento_ligado_ao_marco(client, orientacao, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/anexar",
        data={"titulo": "Capítulo 1", "arquivo": pdf_falso("cap1.pdf"), "comentario": ""},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    doc = Documento.query.one()
    assert doc.marco_id == marco.id
    assert doc.versao_atual.numero_versao == 1
    # aparece na página da tarefa
    assert "Capítulo 1" in resp.data.decode()


def test_anexo_invalido_e_recusado_sem_documento(client, orientacao, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/anexar",
        data={"titulo": "Falso", "arquivo": texto_com_extensao_pdf(), "comentario": ""},
        content_type="multipart/form-data",
    )
    assert Documento.query.count() == 0


def test_intruso_nao_abre_a_pagina_da_tarefa(client, orientacao, intruso):
    marco = _criar_marco(orientacao)
    login(client, "intruso@teste.br")
    assert client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).status_code == 403


def test_orientando_nao_confirma_conclusao(client, orientacao, orientando):
    marco = _criar_marco(orientacao)
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/confirmar"
    )
    assert resp.status_code == 403
    assert marco.status == "pendente"


def test_marco_atrasado_computado_na_leitura(app, orientacao):
    marco = _criar_marco(orientacao, dias=-5)
    assert marco.atrasado is True
    marco.status = "concluido"
    assert marco.atrasado is False
