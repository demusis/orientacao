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
from app.services import avisos, eliminacao, exportacao
from app.services import backup as backup_service
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
    resultado = backup_service.expurgar(admin)  # antes: PermissionError
    assert resultado["removidos"]["orientacao"] == 1
    assert Orientacao.query.count() == 0
    # e o arquivo que ficou é REPORTADO, não engolido no log (volta 3)
    assert resultado["arquivos_presos"] == ["c" * 32 + ".pdf"]


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


# ============================== VOLTA 3 ====================================


def test_fuso_vazio_tambem_degrada_para_utc(app):
    """ZoneInfo('') levanta ValueError, não ZoneInfoNotFoundError: um
    `FUSO_LOCAL=` em branco no .env não pode derrubar o sistema."""
    from app.services.tempo import agora, agora_local

    app.config["FUSO_LOCAL"] = ""
    resultado = agora_local()  # antes: ValueError
    assert abs((resultado - agora()).total_seconds()) < 5


def test_indicadores_contam_atraso_no_dia_local(app, orientacao):
    """O indicador usa o MESMO relógio de Marco.atrasado: com o dia UTC, o
    relatório de avaliação contava atraso que nenhuma tela mostrava."""
    from app.models import Marco
    from app.services import indicadores
    from app.services.tempo import hoje_local

    db.session.add(
        Marco(orientacao_id=orientacao.id, titulo="Hoje", data_prevista=hoje_local())
    )
    db.session.commit()
    assert indicadores.fluxo_de_marcos()["atrasados"] == 0

    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Ontem",
            data_prevista=hoje_local() - timedelta(days=1),
        )
    )
    db.session.commit()
    assert indicadores.fluxo_de_marcos()["atrasados"] == 1


def test_vinculo_nao_aceita_fim_antes_do_inicio(client, admin, orientador, orientando):
    login(client, "admin@teste.br")
    resposta = client.post(
        "/admin/orientacoes/nova",
        data={
            "orientador_id": orientador.id,
            "orientando_id": orientando.id,
            "modalidade": "mestrado",
            "titulo_projeto": "Ano trocado",
            "data_inicio": "2026-03-01",
            "data_fim_prevista": "2025-03-01",
        },
        follow_redirects=True,
    )
    assert "posterior ao início" in resposta.data.decode()
    assert Orientacao.query.count() == 0


def test_restauracao_reativa_o_executor_vindo_desativado(app, admin, orientacao):
    """Backup tirado com a conta do executor desativada (ou sem papel de
    admin): restaurá-lo não pode trancar quem restaura para fora do sistema."""
    admin.ativo = False
    admin.papel = "orientando"
    db.session.commit()
    _, conteudo = backup_service.gerar()  # pacote com o executor inutilizável

    admin.ativo = True
    admin.papel = "admin"
    db.session.commit()
    hash_corrente = admin.senha_hash

    backup_service.restaurar(io.BytesIO(conteudo), admin)
    restaurado = Usuario.query.filter_by(email="admin@teste.br").one()
    assert restaurado.ativo is True
    assert restaurado.papel == "admin"
    assert restaurado.senha_hash == hash_corrente  # a senha da sessão corrente


def test_restauracao_reporta_arquivo_que_nao_pode_regravar(
    app, admin, orientacao, monkeypatch
):
    """O arquivo que resistiu à limpeza resistiria também à regravação; a
    falha vira item de `arquivos_pendentes` no resumo, não erro 500 depois de
    o banco já ter sido substituído."""
    import builtins

    import app.services.backup as backup_module

    pasta = app.config["UPLOAD_FOLDER"]
    nome = "d" * 32 + ".pdf"
    caminho = os.path.join(pasta, nome)
    with open(caminho, "wb") as f:
        f.write(b"%PDF-1.4 preso")
    _, conteudo = backup_service.gerar()  # o pacote inclui o arquivo

    def remove_recusa(alvo):
        raise PermissionError(alvo)

    abrir_real = builtins.open

    def open_recusa(arquivo, modo="r", *args, **kwargs):
        if "w" in modo and str(arquivo).endswith(nome):
            raise PermissionError(arquivo)
        return abrir_real(arquivo, modo, *args, **kwargs)

    monkeypatch.setattr(backup_module.os, "remove", remove_recusa)
    monkeypatch.setattr(builtins, "open", open_recusa)
    resumo = backup_service.restaurar(io.BytesIO(conteudo), admin)  # sem 500
    assert nome in resumo["arquivos_pendentes"]


# ============================== VOLTA 4 ====================================


def test_restauracao_zera_senha_provisoria_do_executor(app, admin, orientacao):
    """Backup tirado quando a conta do executor ainda tinha senha provisória:
    restaurá-lo não pode prender quem restaura na tela de troca obrigatória."""
    admin.senha_provisoria = True
    db.session.commit()
    _, conteudo = backup_service.gerar()

    admin.senha_provisoria = False
    db.session.commit()

    backup_service.restaurar(io.BytesIO(conteudo), admin)
    restaurado = Usuario.query.filter_by(email="admin@teste.br").one()
    assert restaurado.senha_provisoria is False


def test_restauracao_tolera_membro_de_zip_corrompido(app, admin, orientacao):
    """Membro de uploads com CRC podre levanta BadZipFile/zlib.error, que NÃO
    é OSError: precisa virar pendência no relatório, nunca 500 depois de o
    banco já ter sido substituído."""
    import struct

    pasta = app.config["UPLOAD_FOLDER"]
    nome = "e" * 32 + ".pdf"
    with open(os.path.join(pasta, nome), "wb") as f:
        f.write(b"%PDF-1.4 " + os.urandom(300))
    _, conteudo = backup_service.gerar()

    dados = bytearray(conteudo)
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        info = z.getinfo(f"uploads/{nome}")
    nlen, elen = struct.unpack_from("<HH", dados, info.header_offset + 26)
    inicio = info.header_offset + 30 + nlen + elen
    dados[inicio + max(info.compress_size // 2, 1)] ^= 0xFF  # corrompe o meio

    resumo = backup_service.restaurar(io.BytesIO(bytes(dados)), admin)  # sem 500
    assert nome in resumo["arquivos_pendentes"]


def test_preso_na_limpeza_mas_regravado_nao_e_pendencia(
    app, admin, orientacao, monkeypatch
):
    """Arquivo que resistiu ao os.remove mas foi sobrescrito com sucesso pelo
    pacote está correto no disco — alertá-lo mandaria o admin 'consertar' (e
    talvez apagar) um upload válido."""
    import app.services.uploads as uploads_module

    pasta = app.config["UPLOAD_FOLDER"]
    nome = "f" * 32 + ".pdf"
    with open(os.path.join(pasta, nome), "wb") as f:
        f.write(b"%PDF-1.4 conteudo")
    _, conteudo = backup_service.gerar()

    def recusa(caminho):
        raise PermissionError(caminho)

    monkeypatch.setattr(uploads_module.os, "remove", recusa)
    resumo = backup_service.restaurar(io.BytesIO(conteudo), admin)
    assert resumo["arquivos_pendentes"] == []
    assert resumo["arquivos"] == 1


def test_eliminacao_raspa_o_registro_diario_de_entregas(app, admin, orientando):
    """O e-mail do titular sai de ConfiguracaoEmail.avisos_entregues; o de
    terceiros fica — sem isso, a eliminação certificada deixava dado pessoal
    num campo que tela nenhuma mostra."""
    from app.models import ConfiguracaoEmail

    config = ConfiguracaoEmail.vigente()
    config.avisos_entregues = json.dumps(
        {"dia": "2026-07-26", "emails": ["orientando@teste.br", "mari@teste.br"]}
    )
    db.session.commit()

    eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()
    guardado = json.loads(ConfiguracaoEmail.vigente().avisos_entregues)
    assert guardado["emails"] == ["mari@teste.br"]


def test_expurgo_limpa_o_registro_diario_de_entregas(app, admin, orientacao):
    """O expurgo preserva a credencial SMTP, mas não os e-mails em claro do
    registro de entregas — eles são dos usuários que acabaram de ser apagados."""
    from app.models import ConfiguracaoEmail

    config = ConfiguracaoEmail.vigente()
    config.usuario = "sistema@x.br"
    config.avisos_entregues = json.dumps(
        {"dia": "2026-07-26", "emails": ["orientando@teste.br"]}
    )
    db.session.commit()

    backup_service.expurgar(admin)
    config = ConfiguracaoEmail.vigente()
    assert config.avisos_entregues is None
    assert config.usuario == "sistema@x.br"  # a credencial fica, como sempre


# ============================== VOLTA 5 ====================================


def test_restauracao_limpa_registro_de_entregas_da_base_anterior(app, admin, orientacao):
    """A restauração troca toda a base de usuários, mas configuracao_email fica
    fora do pacote: o registro diário de entregas guardaria e-mails em claro de
    contas que deixaram de existir."""
    from app.models import ConfiguracaoEmail

    config = ConfiguracaoEmail.vigente()
    config.avisos_entregues = json.dumps(
        {"dia": "2026-07-26", "emails": ["orientando@teste.br"]}
    )
    db.session.commit()
    _, conteudo = backup_service.gerar()

    backup_service.restaurar(io.BytesIO(conteudo), admin)
    assert ConfiguracaoEmail.vigente().avisos_entregues is None


def test_login_em_conta_desativada_com_senha_certa_deixa_trilha(client, orientador):
    """A senha confere mas a conta está inativa: a tentativa confirma um par de
    credenciais válido e precisa deixar rastro (e contar para o limite), não
    sumir em silêncio."""
    orientador.ativo = False
    db.session.commit()

    resposta = client.post(
        "/auth/login",
        data={"email": "orientador@teste.br", "senha": "senha-teste-123"},
    )
    assert resposta.status_code == 403
    log = LogAuditoria.query.filter_by(acao="login_falho").one()
    assert "conta_desativada" in (log.dados_json or "")


def test_login_desativado_conta_para_o_limite(client, app, orientador):
    orientador.ativo = False
    db.session.commit()
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    for _ in range(teto):
        db.session.add(
            LogAuditoria(
                acao="login_falho", entidade="usuario", ip="127.0.0.1",
                dados_json=None,
            )
        )
    db.session.commit()
    resposta = client.post(
        "/auth/login",
        data={"email": "orientador@teste.br", "senha": "senha-teste-123"},
    )
    assert resposta.status_code == 429  # a sondagem cai no mesmo limite


def test_coletar_usa_um_unico_hoje_nas_categorias(app, orientacao, monkeypatch):
    """marcos_atrasados (< hoje) e marcos_a_vencer (>= hoje) só não se
    sobrepõem se virem o MESMO hoje; coletar() o calcula uma vez e o passa. Um
    marco na fronteira (data = hoje) tem de cair em 'a vencer', nunca em ambos
    nem em nenhum."""
    from app.models import Marco
    from app.services.tempo import hoje_local

    hoje = hoje_local()
    db.session.add(
        Marco(orientacao_id=orientacao.id, titulo="Fronteira", data_prevista=hoje)
    )
    db.session.commit()

    coletado = avisos.coletar()
    orientando = orientacao.orientando
    secoes = coletado.get(orientando, {})
    assert "marcos_a_vencer" in secoes
    assert "marcos_vencidos" not in secoes


def test_categoria_honra_o_hoje_recebido(app, orientacao):
    """A categoria usa o hoje que coletar passa, não um recalculado: é isso que
    fecha o buraco de virada de dia."""
    from datetime import date

    from app.models import Marco

    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Prevista 10/06",
            data_prevista=date(2026, 6, 10),
        )
    )
    db.session.commit()

    destino = {}
    # hoje fixado no futuro do marco: está atrasado sob ESTE hoje
    avisos.marcos_atrasados(destino, hoje=date(2026, 6, 20))
    assert "marcos_vencidos" in destino.get(orientacao.orientando, {})

    destino = {}
    # hoje fixado antes do marco: não está atrasado
    avisos.marcos_atrasados(destino, hoje=date(2026, 6, 1))
    assert destino == {}


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
