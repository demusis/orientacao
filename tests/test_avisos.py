"""Avisos diários de pendência.

Duas coisas importam aqui e são fáceis de errar em silêncio: **cada pessoa
receber uma só mensagem**, com tudo o que lhe cabe, e o disparo **acontecer uma
única vez por dia**, mesmo com requisições concorrentes.
"""
import json
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoEmail,
    Documento,
    LogAuditoria,
    Marco,
    VersaoDocumento,
)
from app.services import avisos, cripto
from app.services import email as email_service

from tests.conftest import login


@pytest.fixture
def envio_habilitado(app):
    config = ConfiguracaoEmail.vigente()
    config.ativo = True
    config.usuario = "ariadne.sistema@gmail.com"
    config.senha_cifrada = cripto.cifrar("abcd efgh ijkl mnop")
    db.session.commit()
    return config


@pytest.fixture
def lote_capturado(monkeypatch):
    """Substitui o envio real: a suíte não pode depender de rede."""
    capturado = []

    def falso_lote(mensagens):
        capturado.extend(mensagens)
        return [m[0] for m in mensagens], []

    monkeypatch.setattr(email_service, "enviar_lote", falso_lote)
    return capturado


def _marco_atrasado(orientacao, dias=3):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Entregar capítulo 1",
        data_prevista=date.today() - timedelta(days=dias),
    )
    db.session.add(m)
    db.session.commit()
    return m


def _marco_sinalizado(orientacao):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Coleta concluída",
        data_prevista=date.today() + timedelta(days=10),
        conclusao_sinalizada=True,
    )
    db.session.add(m)
    db.session.commit()
    return m


def _versao_sem_parecer(orientacao, titulo="Projeto de pesquisa"):
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
        nome_original="p.pdf",
        # nome_fisico é único no esquema; deriva-se do id para não colidir
        nome_fisico=f"{doc.id:032x}.pdf",
        tamanho_bytes=1024,
        mimetype="application/pdf",
        enviado_por=orientacao.orientando_id,
    )
    db.session.add(v)
    db.session.commit()
    return v


def _ata_rascunho_velha(orientacao, orientador, dias=30):
    a = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() - timedelta(days=dias),
        pauta="p",
        deliberacoes="d",
        redigida_por=orientador.id,
    )
    db.session.add(a)
    db.session.flush()
    db.session.add(AtaParticipacao(ata_id=a.id, orientacao_id=orientacao.id))
    db.session.commit()
    return a


# --- categorias ---


def test_marco_atrasado_vai_para_o_orientando(client, orientacao, orientando):
    _marco_atrasado(orientacao)
    coletado = avisos.coletar()
    assert orientando in coletado
    assert "marcos_vencidos" in coletado[orientando]


def test_marco_no_prazo_nao_gera_aviso(client, orientacao, orientando):
    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Futuro",
            data_prevista=date.today() + timedelta(days=5),
        )
    )
    db.session.commit()
    assert avisos.coletar() == {}


def test_categorias_do_orientador(client, orientacao, orientador, orientando):
    _marco_sinalizado(orientacao)
    _versao_sem_parecer(orientacao)
    _ata_rascunho_velha(orientacao, orientador)

    secoes = avisos.coletar()[orientador]
    assert "a_confirmar" in secoes
    assert "sem_parecer" in secoes
    assert "atas_rascunho" in secoes


def test_uma_mensagem_por_pessoa_reunindo_tudo(
    client, orientacao, orientador, orientando, envio_habilitado, lote_capturado
):
    """Quatro pendências do orientador precisam virar UM e-mail: quatro
    mensagens no mesmo minuto seriam lidas como ruído e ignoradas."""
    _marco_atrasado(orientacao)
    _marco_sinalizado(orientacao)
    _versao_sem_parecer(orientacao)
    _ata_rascunho_velha(orientacao, orientador)

    resumo = avisos.enviar_pendentes()
    assert resumo["destinatarios"] == 2  # orientador e orientando
    assert len(lote_capturado) == 2

    para_orientador = [m for m in lote_capturado if m[0] == orientador.email][0]
    corpo = para_orientador[2]
    assert corpo.count("AGUARDANDO SUA CONFIRMAÇÃO") == 1
    assert "AGUARDANDO PARECER" in corpo
    assert "ATAS EM RASCUNHO" in corpo


def test_vinculo_encerrado_nao_gera_aviso(client, orientacao, orientando):
    _marco_atrasado(orientacao)
    orientacao.status = "concluida"
    db.session.commit()
    assert avisos.coletar() == {}


# --- trava do disparo diário ---


def test_tentativas_respeitam_o_intervalo(client, envio_habilitado):
    assert avisos.reservar_tentativa() is True
    db.session.commit()
    assert avisos.reservar_tentativa() is False  # cedo demais


def test_intervalo_vencido_libera_nova_tentativa(client, envio_habilitado):
    assert avisos.reservar_tentativa() is True
    config = ConfiguracaoEmail.vigente()
    config.avisos_tentados_em = avisos._agora() - avisos.INTERVALO_ENTRE_TENTATIVAS - timedelta(minutes=1)
    db.session.commit()
    assert avisos.reservar_tentativa() is True


def test_dia_ja_entregue_nao_tenta_de_novo(client, envio_habilitado):
    config = ConfiguracaoEmail.vigente()
    config.avisos_enviados_em = date.today()
    db.session.commit()
    assert avisos.reservar_tentativa() is False


def test_novo_dia_libera_o_disparo(client, envio_habilitado):
    config = ConfiguracaoEmail.vigente()
    config.avisos_enviados_em = date.today() - timedelta(days=1)
    db.session.commit()
    assert avisos.reservar_tentativa() is True


def test_falha_de_rede_nao_consome_o_dia(
    client, orientacao, orientando, envio_habilitado, monkeypatch
):
    """Regressão do defeito observado em produção em 21/07/2026.

    O marcador do dia era gravado **antes** do envio, de modo que um lote
    perdido por `Network is unreachable` consumia o aviso do dia inteiro — e
    ninguém era avisado, sem que nada parecesse errado. A marca de sucesso agora
    só avança havendo entrega."""
    _marco_atrasado(orientacao)
    monkeypatch.setattr(
        email_service, "enviar_lote", lambda m: ([], [m0[0] for m0 in m])
    )

    resumo = avisos.disparar_se_devido()
    db.session.commit()

    assert resumo["falhas"] and not resumo["enviados"]
    # o dia continua em aberto
    assert ConfiguracaoEmail.vigente().avisos_enviados_em != date.today()
    # e, vencido o intervalo, tenta-se de novo
    ConfiguracaoEmail.vigente().avisos_tentados_em = (
        avisos._agora() - avisos.INTERVALO_ENTRE_TENTATIVAS - timedelta(minutes=1)
    )
    db.session.commit()
    assert avisos.reservar_tentativa() is True


def test_entrega_bem_sucedida_encerra_o_dia(
    client, orientacao, orientando, envio_habilitado, lote_capturado
):
    _marco_atrasado(orientacao)
    avisos.disparar_se_devido()
    db.session.commit()

    assert ConfiguracaoEmail.vigente().avisos_enviados_em == date.today()
    assert avisos.reservar_tentativa() is False


def test_sem_pendencia_tambem_encerra_o_dia(client, envio_habilitado, lote_capturado):
    """Nada a enviar não é falha: insistir o dia todo consultaria o banco à toa."""
    resumo = avisos.disparar_se_devido()
    db.session.commit()

    assert resumo["destinatarios"] == 0
    assert ConfiguracaoEmail.vigente().avisos_enviados_em == date.today()


# --- gatilho por requisição ---


def test_requisicao_dispara_e_registra(
    app, client, orientacao, orientando, envio_habilitado, lote_capturado
):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)

    client.get("/auth/login")

    assert len(lote_capturado) == 1
    registro = LogAuditoria.query.filter_by(acao="envio_avisos").one()
    dados = json.loads(registro.dados_json)
    assert dados["destinatarios"] == 1
    assert ConfiguracaoEmail.vigente().avisos_enviados_em == date.today()


def test_segunda_requisicao_do_dia_nao_reenvia(
    app, client, orientacao, orientando, envio_habilitado, lote_capturado
):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)

    client.get("/auth/login")
    client.get("/auth/login")
    client.get("/auth/login")

    assert len(lote_capturado) == 1
    assert LogAuditoria.query.filter_by(acao="envio_avisos").count() == 1


def test_envio_desabilitado_nao_dispara(app, client, orientacao, orientando, lote_capturado):
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)  # há pendência, mas o envio está desligado

    client.get("/auth/login")

    assert lote_capturado == []
    assert LogAuditoria.query.filter_by(acao="envio_avisos").count() == 0


def test_falha_no_disparo_nao_derruba_a_requisicao(
    app, client, orientacao, orientando, envio_habilitado, monkeypatch
):
    """A pessoa que abriu a página nada tem a ver com o envio: se ele estourar,
    a requisição dela precisa seguir normalmente."""
    app.config["AVISOS_DIARIOS"] = True
    _marco_atrasado(orientacao)
    monkeypatch.setattr(
        avisos, "enviar_pendentes",
        lambda: (_ for _ in ()).throw(RuntimeError("erro inesperado")),
    )

    resposta = client.get("/auth/login")
    assert resposta.status_code == 200


def test_tela_mostra_falhas_do_ultimo_disparo(client, admin, envio_habilitado):
    from app.services import auditoria

    auditoria.registrar(
        "envio_avisos", "configuracao_email", 1,
        {"destinatarios": 2, "itens": 3, "enviados": ["a@x.br"], "falhas": ["b@x.br"]},
    )
    db.session.commit()

    login(client, "admin@teste.br")
    pagina = client.get("/admin/email").data.decode()
    assert "b@x.br" in pagina
    assert "não foi(ram) entregue(s)" in pagina or "entregue" in pagina


# --- conteúdo das mensagens ---


def test_mensagem_leva_o_endereco_do_sistema(app, client, orientacao, orientando):
    """Regressão do defeito da primeira versão: a mensagem dizia 'acesse o
    sistema' sem endereço algum, informando a pendência sem dar como tratá-la."""
    app.config["URL_BASE"] = "https://orientacao.pythonanywhere.com"
    _marco_atrasado(orientacao)
    secoes = avisos.coletar()[orientando]
    url = avisos.endereco_do_sistema()

    texto = avisos.corpo_texto(orientando, secoes, url)
    html = avisos.corpo_html(orientando, secoes, url)
    assert "https://orientacao.pythonanywhere.com" in texto
    assert 'href="https://orientacao.pythonanywhere.com"' in html


def test_assunto_informa_a_quantidade(client, orientacao, orientando):
    _marco_atrasado(orientacao)
    assert avisos.assunto(avisos.coletar()[orientando]).startswith(
        "ARIADNE — 1 pendência"
    )


def test_assunto_no_plural(client, orientacao, orientando):
    _marco_atrasado(orientacao, dias=3)
    _marco_atrasado(orientacao, dias=9)
    assert "2 pendências" in avisos.assunto(avisos.coletar()[orientando])


def test_providencias_sem_repeticao(client, orientacao, orientador, orientando):
    """Duas entregas sem parecer geram uma providência, não duas."""
    _versao_sem_parecer(orientacao)
    _versao_sem_parecer(orientacao)
    secoes = avisos.coletar()[orientador]
    texto = avisos.corpo_texto(orientador, secoes, "")
    # duas entregas, uma seção: o passo a passo aparece uma vez só
    assert texto.count("Como proceder:") == 1
    assert texto.count("Baixe a versão enviada") == 1


def test_texto_simples_e_autossuficiente(client, orientacao, orientando):
    """A parte em texto não pode remeter ao HTML: é o que aparece em leitor de
    tela, em cliente sem HTML e na pré-visualização da caixa de entrada."""
    _marco_atrasado(orientacao)
    secoes = avisos.coletar()[orientando]
    texto = avisos.corpo_texto(orientando, secoes, "https://x.br")

    assert "Entregar capítulo 1" in texto
    assert "dias de atraso" in texto
    assert "Como proceder:" in texto
    for proibido in ("versão HTML", "<div", "<p>", "&nbsp;"):
        assert proibido not in texto


def test_html_escapa_dados_do_usuario(client, orientacao, orientando):
    orientando.nome = 'André <script>alert(1)</script>'
    db.session.commit()
    _marco_atrasado(orientacao)
    html = avisos.corpo_html(orientando, avisos.coletar()[orientando], "")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_mensagem_vai_em_duas_partes(client, orientacao, orientando):
    from app.services import email as es

    msg = es.montar("x@y.br", "assunto", "texto simples", "<p>html</p>")
    assert msg.is_multipart()
    tipos = [p.get_content_type() for p in msg.walk() if not p.is_multipart()]
    assert tipos == ["text/plain", "text/html"]


def test_sem_html_permanece_texto_simples(client):
    from app.services import email as es

    msg = es.montar("x@y.br", "assunto", "só texto")
    assert not msg.is_multipart()
    assert msg.get_content_type() == "text/plain"


def test_texto_preserva_a_indentacao_dos_itens(client, orientacao, orientando):
    """O Jinja consome espaços à esquerda quando o bloco usa `-%}`, e num e-mail
    em texto simples a indentação é a única hierarquia visível. Ao editar
    `emails/pendencias.txt`, é este teste que avisa se ela se perdeu."""
    _marco_atrasado(orientacao)
    texto = avisos.corpo_texto(orientando, avisos.coletar()[orientando], "")

    assert "\n  - Entregar capítulo 1\n" in texto
    assert "\n    Previsto para " in texto
    assert "\n  1. Abra o sistema" in texto  # passo numerado, mesma indentação


def test_texto_traz_a_marca_de_assinatura(client, orientacao, orientando):
    """RFC 3676: "-- " seguido de espaço delimita a assinatura, e clientes de
    e-mail a usam para recolher o rodapé. O espaço final é significativo e some
    fácil ao editar o template."""
    _marco_atrasado(orientacao)
    texto = avisos.corpo_texto(orientando, avisos.coletar()[orientando], "")
    assert "\n-- \n" in texto


def test_mensagem_se_identifica_como_automatica(client, orientacao, orientando):
    """Quem recebe precisa saber que não adianta responder. O aviso aparece duas
    vezes de propósito: no topo, porque o rodapé pode ser recolhido pelo cliente
    de e-mail em razão da marca "-- "; e no rodapé, com a explicação completa."""
    _marco_atrasado(orientacao)
    secoes = avisos.coletar()[orientando]

    texto = avisos.corpo_texto(orientando, secoes, "")
    html = avisos.corpo_html(orientando, secoes, "")

    for corpo in (texto, html):
        assert corpo.count("Não responda a este e-mail") == 2
        assert "ninguém lê as respostas" in corpo
    # e diz a quem recorrer, já que responder não serve
    assert "escreva diretamente ao seu orientador" in texto
    assert "procure o administrador" in texto


def test_cada_secao_ensina_o_que_fazer(client, orientacao, orientador, orientando):
    """Aviso que informa a pendência sem ensinar a resolvê-la deixa o trabalho
    pela metade. Toda seção presente precisa trazer seu passo a passo."""
    _marco_sinalizado(orientacao)
    _versao_sem_parecer(orientacao)
    _ata_rascunho_velha(orientacao, orientador)

    secoes = avisos.coletar()[orientador]
    texto = avisos.corpo_texto(orientador, secoes, "")

    assert texto.count("Como proceder:") == len(secoes)
    for chave in secoes:
        assert avisos.SECOES[chave]["explicacao"] in texto
        for passo in avisos.SECOES[chave]["passos"]:
            assert passo in texto


def test_assinatura_separada_do_conteudo(client, orientacao, orientando):
    """Linha em branco antes da marca de assinatura. Some com facilidade: um
    comentário Jinja aberto com `{#-` engole o branco que o precede."""
    _marco_atrasado(orientacao)
    texto = avisos.corpo_texto(orientando, avisos.coletar()[orientando], "")
    assert "\n\n-- \n" in texto
