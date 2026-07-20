from datetime import date, timedelta

from app.extensions import db
from app.models import Marco

from tests.conftest import login


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
            etapa=60,
        )
    )
    db.session.commit()
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/", follow_redirects=True
    ).data.decode()
    assert "Redação" in pagina


def test_tipo_derivado_da_etapa_quando_nao_especificado(client, orientacao, orientador):
    """Etapa de ato formal preenche o tipo deixado em 'outro'; tipo escolhido
    explicitamente é preservado."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Banca de qualificação",
            "descricao": "",
            "tipo": "outro",
            "data_prevista": "2026-09-30",
            "etapa": 30,
        },
    )
    assert Marco.query.one().tipo == "qualificacao"

    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/novo",
        data={
            "titulo": "Relatório antes da defesa",
            "descricao": "",
            "tipo": "relatorio_anual",  # explícito: não pode ser sobrescrito
            "data_prevista": "2026-10-30",
            "etapa": 80,
        },
    )
    marco = Marco.query.filter_by(titulo="Relatório antes da defesa").one()
    assert marco.tipo == "relatorio_anual"


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
