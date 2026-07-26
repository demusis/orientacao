"""Primeira volta do loop /revisar (2026-07-26): um teste por defeito
confirmado, reproduzindo o cenário de falha que a revisão descreveu.
Registro completo em avaliacoes/REVISOES.md."""
import io
import json
import os
import zipfile
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoRisco,
    LogAuditoria,
    ModeloDocumento,
    Orientacao,
    Parecer,
    Usuario,
)
from app.services import backup as backup_service
from app.services import eliminacao, exportacao
from app.services.atas import OperacaoInvalida, finalizar_ata
from app.services.tempo import agora_local
from tests.conftest import login


def _ata(orientacao, orientador, *, data, formato="markdown", deliberacoes="Decidido."):
    a = Ata(
        orientador_id=orientador.id,
        data_reuniao=data,
        pauta="# de participantes: 4",
        deliberacoes=deliberacoes,
        redigida_por=orientador.id,
        formato=formato,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(a)
    db.session.commit()
    return a


# --- 1. congelado preserva o formato do registro, não o corrente ---


def test_congelado_preserva_formato_texto(app, orientacao, orientador):
    """Rascunho anterior ao markdown (formato="texto") finalizado hoje: o
    snapshot precisa declarar "texto", senão o PDF assinável reinterpreta
    '# de participantes' como título — distorção permanente com hash."""
    ontem = agora_local().date() - timedelta(days=1)
    ata = _ata(orientacao, orientador, data=ontem, formato="texto")
    finalizar_ata(ata)
    db.session.commit()
    assert json.loads(ata.conteudo_congelado)["formato"] == "texto"
    assert ata.formato_conteudo == "texto"


def test_congelado_de_parecer_preserva_formato(app, orientacao, orientador):
    parecer = Parecer(
        orientacao_id=orientacao.id,
        tipo="andamento",
        conteudo="*sem ênfase*",
        resultado="aprovado",
        emitido_por=orientador.id,
        formato="texto",
    )
    db.session.add(parecer)
    db.session.flush()
    exportacao.congelar_parecer(parecer)
    db.session.commit()
    assert json.loads(parecer.conteudo_congelado)["formato"] == "texto"


# --- 4. não se finaliza reunião futura por nenhum caminho ---


def test_nao_finaliza_ata_de_reuniao_futura(app, orientacao, orientador):
    amanha = agora_local().date() + timedelta(days=1)
    ata = _ata(orientacao, orientador, data=amanha)
    with pytest.raises(OperacaoInvalida, match="data futura"):
        finalizar_ata(ata)
    assert ata.status == "rascunho"


def test_rota_de_finalizar_recusa_reuniao_futura(client, orientacao, orientador):
    amanha = agora_local().date() + timedelta(days=1)
    ata = _ata(orientacao, orientador, data=amanha)
    login(client, "orientador@teste.br")
    resposta = client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar",
        follow_redirects=True,
    )
    assert "data futura" in resposta.data.decode()
    assert ata.status == "rascunho"
    assert ata.conteudo_congelado is None


# --- 2. expurgo confirma o banco antes de tocar nos arquivos ---


def test_expurgo_confirma_banco_antes_dos_arquivos(app, admin, orientacao):
    pasta = app.config["UPLOAD_FOLDER"]
    caminho = os.path.join(pasta, "a" * 32 + ".pdf")
    with open(caminho, "wb") as f:
        f.write(b"%PDF-1.4 x")

    backup_service.expurgar(admin)
    # um rollback posterior não pode ressuscitar linha alguma: o serviço
    # comita a própria transação ANTES da remoção irreversível dos arquivos
    db.session.rollback()
    assert Orientacao.query.count() == 0
    assert Usuario.query.count() == 1  # só o executor
    assert not os.path.exists(caminho)
    assert LogAuditoria.query.filter_by(acao="expurgo_base").count() == 1


# --- 10. modelo: arquivo só some depois do commit ---


def test_exclusao_de_modelo_apaga_arquivo_so_apos_commit(client, admin, app):
    pasta = app.config["UPLOAD_FOLDER"]
    nome_fisico = "b" * 32 + ".pdf"
    with open(os.path.join(pasta, nome_fisico), "wb") as f:
        f.write(b"%PDF-1.4 modelo")
    modelo = ModeloDocumento(
        titulo="Modelo X",
        nome_original="x.pdf",
        nome_fisico=nome_fisico,
        tamanho_bytes=15,
        mimetype="application/pdf",
    )
    db.session.add(modelo)
    db.session.commit()

    from app.services.modelos import excluir_modelo

    caminho = excluir_modelo(modelo)
    # o serviço não toca no disco: uma falha do commit deixaria o registro
    # restaurado apontando para arquivo perdido
    assert os.path.exists(caminho)
    db.session.rollback()
    assert db.session.get(ModeloDocumento, modelo.id) is not None

    login(client, "admin@teste.br")
    client.post(f"/admin/modelos/{modelo.id}/excluir")
    assert db.session.get(ModeloDocumento, modelo.id) is None
    assert not os.path.exists(caminho)


# --- 3. restauração distingue pacote antigo de pacote truncado ---


def _sem_membro(conteudo_zip: bytes, remover: str, contagens_sem=None) -> io.BytesIO:
    """Reempacota o ZIP sem `remover`; opcionalmente tira a tabela das
    contagens do manifesto (simula pacote gerado antes da adoção)."""
    origem = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    destino = io.BytesIO()
    with zipfile.ZipFile(destino, "w") as z:
        for item in origem.namelist():
            if item == remover:
                continue
            dado = origem.read(item)
            if item == "manifesto.json" and contagens_sem:
                manifesto = json.loads(dado)
                manifesto["contagens"].pop(contagens_sem, None)
                dado = json.dumps(manifesto).encode()
            z.writestr(item, dado)
    destino.seek(0)
    return destino


def test_restauracao_recusa_pacote_atual_sem_ata_marco(app, admin, orientacao):
    _, conteudo = backup_service.gerar()
    truncado = _sem_membro(conteudo, "dados/ata_marco.json")
    with pytest.raises(backup_service.BackupInvalido, match="ata_marco"):
        backup_service.restaurar(truncado, admin)


def test_restauracao_aceita_pacote_anterior_a_ata_marco(app, admin, orientacao):
    """Pacote legítimo de antes de 23/07/2026: sem o JSON e sem a tabela no
    manifesto. Continua aceito, com a tabela entrando vazia."""
    _, conteudo = backup_service.gerar()
    legado = _sem_membro(
        conteudo, "dados/ata_marco.json", contagens_sem="ata_marco"
    )
    resumo = backup_service.restaurar(legado, admin)
    assert resumo["contagens"]["ata_marco"] == 0
    assert Orientacao.query.count() == 1


# --- 6. seed-admin normaliza o e-mail como o login consulta ---


def test_seed_admin_normaliza_email(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(
        args=[
            "seed-admin", "--nome", "Fulano", "--email", "  Fulano@Teste.BR ",
            "--senha", "senha-forte-para-teste-1",
        ]
    )
    assert "criado" in resultado.output
    usuario = Usuario.query.filter_by(email="fulano@teste.br").first()
    assert usuario is not None and usuario.papel == "admin"


# --- 7. /auth/esqueci com e-mail válido também é limitado ---


def test_esqueci_com_email_valido_e_limitado(client, app, orientador, monkeypatch):
    from app.services import email as email_service

    enviados = []
    monkeypatch.setattr(
        email_service, "enviar", lambda *a: enviados.append(a) or True
    )
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    for _ in range(teto):
        db.session.add(
            LogAuditoria(
                acao="recuperacao_solicitada", entidade="usuario",
                ip="127.0.0.1", dados_json=None,
            )
        )
    db.session.commit()

    r = client.post(
        "/auth/esqueci",
        data={"email": "orientador@teste.br"},
        follow_redirects=True,
    )
    assert r.status_code == 429
    assert enviados == []  # nenhum e-mail sai: era o vetor de inundação


# --- 8. eliminação LGPD anula também ConfiguracaoRisco.atualizado_por ---


def test_eliminacao_anula_configuracao_risco(app, admin):
    titular = Usuario(nome="Titular", email="titular@teste.br", papel="orientando")
    titular.set_senha("senha-forte-1234")
    db.session.add(titular)
    db.session.commit()

    config = ConfiguracaoRisco.vigente()
    config.registrar_alteracao(titular.id)
    db.session.add(config)
    db.session.commit()

    eliminacao.eliminar_usuario(titular, admin)
    db.session.commit()
    assert db.session.get(ConfiguracaoRisco, 1).atualizado_por is None


# --- 9. papel não muda com vínculo ativo; e-mail duplicado não estoura ---


def test_edicao_nao_rebaixa_orientador_com_vinculo_ativo(
    client, admin, orientacao, orientador
):
    login(client, "admin@teste.br")
    resposta = client.post(
        f"/admin/usuarios/{orientador.id}/editar",
        data={
            "nome": orientador.nome, "email": orientador.email,
            "papel": "orientando", "ativo": "y",
        },
        follow_redirects=True,
    )
    assert "recusada" in resposta.data.decode()
    db.session.expire(orientador)
    assert orientador.papel == "orientador"
    assert LogAuditoria.query.filter_by(acao="edicao_papel_recusada").count() == 1


# ============================== VOLTA 2 ====================================


def test_fuso_invalido_degrada_para_utc_sem_derrubar(app):
    """FUSO_LOCAL com typo não pode virar erro 500 no módulo inteiro de
    reuniões: degrada para UTC com aviso no log."""
    from app.services.tempo import agora, agora_local

    app.config["FUSO_LOCAL"] = "America/Nao Existe"
    resultado = agora_local()  # antes: ZoneInfoNotFoundError
    assert abs((resultado - agora()).total_seconds()) < 5


def test_recuperacao_solicitada_nao_tranca_o_login(client, app, orientador):
    """Pedidos legítimos de recuperação atrás de um NAT compartilhado não podem
    bloquear o login de quem sabe a própria senha: o limite do login conta só
    falhas; o da recuperação conta também os pedidos bem-sucedidos."""
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    for _ in range(teto):
        db.session.add(
            LogAuditoria(
                acao="recuperacao_solicitada", entidade="usuario",
                ip="127.0.0.1", dados_json=None,
            )
        )
    db.session.commit()

    resposta = client.post(
        "/auth/esqueci", data={"email": "x@y.br"}, follow_redirects=True
    )
    assert resposta.status_code == 429  # a tela de recuperação, sim, limita

    resposta = login(client, "orientador@teste.br")
    assert resposta.status_code == 200  # não é 429: o login segue aberto
    assert "Painel" in resposta.data.decode()


def test_expurgo_tolera_arquivo_preso(app, admin, orientacao, monkeypatch):
    """os.remove falhando depois do commit (arquivo em download concorrente)
    não pode virar 500 de um expurgo cujo banco já foi confirmado."""
    import app.services.backup as backup_module

    pasta = app.config["UPLOAD_FOLDER"]
    with open(os.path.join(pasta, "c" * 32 + ".pdf"), "wb") as f:
        f.write(b"%PDF-1.4 preso")

    def recusa(caminho):
        raise PermissionError(caminho)

    monkeypatch.setattr(backup_module.os, "remove", recusa)
    contagens = backup_service.expurgar(admin)  # antes: PermissionError
    assert contagens["orientacao"] == 1
    assert Orientacao.query.count() == 0


def test_desativar_orientador_com_vinculo_ativo_recusado(
    client, admin, orientacao, orientador
):
    """Mesmo estado ingerível da mudança de papel, a um checkbox do caminho
    bloqueado: desativação recusada enquanto houver vínculo ativo."""
    login(client, "admin@teste.br")
    resposta = client.post(
        f"/admin/usuarios/{orientador.id}/editar",
        data={
            "nome": orientador.nome, "email": orientador.email,
            "papel": "orientador",  # sem "ativo": desmarca o checkbox
        },
        follow_redirects=True,
    )
    assert "Desativação recusada" in resposta.data.decode()
    db.session.expire(orientador)
    assert orientador.ativo is True
    assert (
        LogAuditoria.query.filter_by(acao="desativacao_orientador_recusada").count()
        == 1
    )


def test_marco_atrasado_usa_o_dia_local(app, orientacao):
    from app.models import Marco
    from app.services.tempo import hoje_local

    em_dia = Marco(
        orientacao_id=orientacao.id, titulo="Hoje", data_prevista=hoje_local()
    )
    vencido = Marco(
        orientacao_id=orientacao.id,
        titulo="Ontem",
        data_prevista=hoje_local() - timedelta(days=1),
    )
    db.session.add_all([em_dia, vencido])
    db.session.commit()
    assert em_dia.atrasado is False
    assert vencido.atrasado is True


def test_edicao_com_email_duplicado_nao_estoura(client, admin, orientador, orientando):
    login(client, "admin@teste.br")
    resposta = client.post(
        f"/admin/usuarios/{orientando.id}/editar",
        data={
            "nome": orientando.nome, "email": orientador.email,
            "papel": "orientando", "ativo": "y",
        },
        follow_redirects=True,
    )
    assert resposta.status_code == 200  # antes: IntegrityError, erro 500
    assert "já cadastrado" in resposta.data.decode()
    db.session.expire(orientando)
    assert orientando.email == "orientando@teste.br"
