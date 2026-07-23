"""Regressão: backup e restauração preservam a tabela ata_marco (os marcos
discutidos em cada reunião), e a restauração tolera pacotes antigos gerados
antes de a tabela passar a ser incluída.

A tabela ficava de fora de ORDEM_TABELAS: gerar() não a copiava e restaurar()
não a repunha, perdendo em silêncio quais marcos cada reunião discutiu."""
import io
import json
import zipfile
from datetime import date

from app.extensions import db
from app.models import Ata, Marco, Usuario


def _montar_reuniao_com_marco(orientacao):
    marco = Marco(
        orientacao_id=orientacao.id, titulo="Marco discutido", data_prevista=date(2026, 3, 1)
    )
    db.session.add(marco)
    ata = Ata(
        orientador_id=orientacao.orientador_id,
        data_reuniao=date(2026, 3, 2),
        pauta="pauta",
        deliberacoes="deliberações",
        redigida_por=orientacao.orientador_id,
    )
    ata.marcos.append(marco)
    db.session.add(ata)
    db.session.commit()
    return ata, marco


def _admin_executor():
    admin = Usuario(nome="Admin Backup", email="admin.backup@teste.br", papel="admin")
    admin.set_senha("senha-teste-123")
    db.session.add(admin)
    db.session.commit()
    return admin


def test_backup_inclui_e_restaura_ata_marco(app, orientacao):
    from app.services import backup

    admin = _admin_executor()
    ata, marco = _montar_reuniao_com_marco(orientacao)
    ata_id, marco_id = ata.id, marco.id

    _, conteudo = backup.gerar()

    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        assert "dados/ata_marco.json" in z.namelist()
        linhas = json.loads(z.read("dados/ata_marco.json"))
    assert {"ata_id": ata_id, "marco_id": marco_id} in [
        {"ata_id": r["ata_id"], "marco_id": r["marco_id"]} for r in linhas
    ]

    # restaura sobre a própria base e confirma que a ligação sobrevive
    backup.restaurar(io.BytesIO(conteudo), admin)
    db.session.commit()
    ata_restaurada = db.session.get(Ata, ata_id)
    assert [m.id for m in ata_restaurada.marcos] == [marco_id]


def test_restauracao_tolera_pacote_sem_ata_marco(app, orientacao):
    """Pacote gerado antes da adoção da tabela não traz dados/ata_marco.json;
    restaurar não deve recusá-lo, apenas tratar a tabela como vazia."""
    from app.services import backup

    admin = _admin_executor()
    _montar_reuniao_com_marco(orientacao)
    _, conteudo = backup.gerar()

    # reescreve o pacote sem o JSON da tabela nova, simulando um backup antigo
    antigo = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(conteudo)) as origem, zipfile.ZipFile(
        antigo, "w", zipfile.ZIP_DEFLATED
    ) as destino:
        for item in origem.namelist():
            if item == "dados/ata_marco.json":
                continue
            destino.writestr(item, origem.read(item))
    antigo.seek(0)

    resumo = backup.restaurar(antigo, admin)  # não deve levantar BackupInvalido
    db.session.commit()
    assert resumo["contagens"]["ata_marco"] == 0
    # a ligação some (não estava no pacote antigo), mas a restauração conclui
    assert db.session.execute(db.text("SELECT COUNT(*) FROM ata_marco")).scalar() == 0
