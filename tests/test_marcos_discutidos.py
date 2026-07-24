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
