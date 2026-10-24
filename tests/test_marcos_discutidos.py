"""Na edição de ata de grupo, o rótulo de cada marco discutido traz o nome do
orientando — sem isso, marcos de título igual (ex.: "Envio da última versão do
Projeto") em vínculos diferentes ficam indistinguíveis nas checkboxes."""
from datetime import date

from app.extensions import db
from app.models import Ata, AtaParticipacao, Marco
from tests.conftest import login


def test_rotulo_do_marco_traz_o_orientando(client, orientacao, orientacao2, orientador):
    # mesmo título em cada vínculo, para forçar a ambiguidade
    for o in (orientacao, orientacao2):
        db.session.add(
            Marco(
                orientacao_id=o.id,
                titulo="Envio da última versão do Projeto",
                tipo="outro",
                etapa=0,
                data_prevista=date(2026, 8, 1),
            )
        )
    ata = Ata(
        tipo="grupo",
        orientador_id=orientador.id,
        data_reuniao=date(2026, 7, 10),
        pauta="Pauta",
        deliberacoes="Deliberações",
        redigida_por=orientador.id,
        participacoes=[
            AtaParticipacao(orientacao_id=orientacao.id),
            AtaParticipacao(orientacao_id=orientacao2.id),
        ],
    )
    db.session.add(ata)
    db.session.commit()

    login(client, "orientador@teste.br")
    r = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # os dois orientandos aparecem, distinguindo os marcos de título igual
    assert "Orientando B" in html
    assert "Orientando D" in html


# --- lista enxuta: relevantes à vista, grupo uma vez, resto recolhido ------

import uuid  # noqa: E402
from datetime import timedelta  # noqa: E402


def _ata_grupo(orientador, vinculos, quando):
    ata = Ata(
        tipo="grupo", orientador_id=orientador.id, data_reuniao=quando,
        pauta="Pauta", deliberacoes="D", redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=o.id) for o in vinculos],
    )
    db.session.add(ata)
    db.session.commit()
    return ata


def _m(o, titulo, prazo, **kw):
    m = Marco(orientacao_id=o.id, titulo=titulo, data_prevista=prazo, **kw)
    db.session.add(m)
    db.session.commit()
    return m


def _antes_e_depois_do_details(html):
    corte = html.find("<details>", html.find("campo-marcos"))
    return (html, "") if corte < 0 else (html[:corte], html[corte:])


def test_tarefa_em_grupo_aparece_uma_vez_e_liga_todos(client, orientacao, orientacao2, orientador):
    hoje = date.today()
    gid = uuid.uuid4().hex
    m1 = _m(orientacao, "Fundamentos de Python", hoje + timedelta(days=10), grupo_id=gid)
    m2 = _m(orientacao2, "Fundamentos de Python", hoje + timedelta(days=10), grupo_id=gid)
    ata = _ata_grupo(orientador, [orientacao, orientacao2], hoje)
    login(client, "orientador@teste.br")
    url = f"/orientacoes/{orientacao.id}/atas/{ata.id}"
    html = client.get(url).get_data(as_text=True)
    assert html.count(f'value="g:{gid}"') == 1
    assert "Tarefas em grupo" in html
    client.post(url, data={"pauta": "Pauta", "deliberacoes": "D", "marcos": [f"g:{gid}"],
                           "submit": "Salvar alterações"})
    db.session.expire(ata)
    assert {m.id for m in ata.marcos} == {m1.id, m2.id}


def test_concluidas_e_distantes_ficam_recolhidas(client, orientacao, orientador):
    hoje = date.today()
    _m(orientacao, "Atrasada", hoje - timedelta(days=5))
    _m(orientacao, "Proxima", hoje + timedelta(days=20))
    _m(orientacao, "Distante", hoje + timedelta(days=200))
    _m(orientacao, "Feita", hoje - timedelta(days=30), status="concluido")
    ata = _ata_grupo(orientador, [orientacao], hoje)
    login(client, "orientador@teste.br")
    html = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}").get_data(as_text=True)
    visivel, recolhido = _antes_e_depois_do_details(html)
    assert "Atrasada" in visivel and "Proxima" in visivel
    assert "Distante" in recolhido and "Feita" in recolhido
    assert "Distante" not in visivel
    assert "atrasada" in visivel  # o detalhe diz a situação


def test_marco_ja_ligado_fica_a_vista_e_nao_some_ao_salvar(client, orientacao, orientador):
    hoje = date.today()
    feita = _m(orientacao, "Feita antes", hoje - timedelta(days=90), status="concluido")
    ata = _ata_grupo(orientador, [orientacao], hoje)
    ata.marcos = [feita]
    db.session.commit()
    login(client, "orientador@teste.br")
    url = f"/orientacoes/{orientacao.id}/atas/{ata.id}"
    html = client.get(url).get_data(as_text=True)
    visivel, _ = _antes_e_depois_do_details(html)
    assert "Feita antes" in visivel
    # o form reenviado com o que veio marcado preserva a ligação
    client.post(url, data={"pauta": "Pauta", "deliberacoes": "D",
                           "marcos": [f"m:{feita.id}"], "submit": "Salvar alterações"})
    db.session.expire(ata)
    assert [m.id for m in ata.marcos] == [feita.id]


def test_marco_de_outro_vinculo_e_descartado(client, orientacao, orientacao2, orientador):
    hoje = date.today()
    alheio = _m(orientacao2, "Alheio", hoje + timedelta(days=5))
    ata = _ata_grupo(orientador, [orientacao], hoje)
    login(client, "orientador@teste.br")
    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}",
                data={"pauta": "Pauta", "deliberacoes": "D", "marcos": [str(alheio.id)],
                      "submit": "Salvar alterações"})
    db.session.expire(ata)
    assert ata.marcos == []
