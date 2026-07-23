"""Senha gerada, enviada por e-mail e trocada à força no primeiro acesso.

O que estes testes guardam é a cadeia inteira: ninguém digita senha alheia, a
senha gerada chega ao titular, e a conta fica presa à tela de troca enquanto a
senha que trafegou por e-mail continuar valendo.
"""
import pytest

from app.extensions import db
from app.models import LogAuditoria, Usuario
from app.services import credenciais, senhas
from app.services.usuarios import GestaoUsuarioInvalida, repor_senha
from tests.conftest import _criar_usuario, login

NOVO = {
    "nome": "Recém-chegada",
    "email": "recem@teste.br",
    "papel": "orientando",
    "ativo": "y",
}


@pytest.fixture
def smtp(monkeypatch):
    """Captura as mensagens em vez de abrir conexão. Devolve a lista enviada."""
    capturadas = []

    def _lote(mensagens):
        capturadas.extend(mensagens)
        return [m[0] for m in mensagens], []

    monkeypatch.setattr("app.services.email.enviar_lote", _lote)
    return capturadas


@pytest.fixture
def smtp_falho(monkeypatch):
    monkeypatch.setattr(
        "app.services.email.enviar_lote",
        lambda mensagens: ([], [m[0] for m in mensagens]),
    )


# ---------------------------------------------------------------------------
# Geração


def test_senha_gerada_nao_repete_e_evita_caracteres_ambiguos():
    amostra = {senhas.gerar() for _ in range(200)}
    assert len(amostra) == 200  # colisão em 200 sorteios denunciaria alfabeto raso

    juntas = "".join(amostra).replace("-", "")
    # o titular transcreve à mão de um celular; estes pares se confundem
    for ambiguo in "0O1lI5S2Z":
        assert ambiguo not in juntas
    assert len(senhas.gerar().replace("-", "")) == senhas.COMPRIMENTO


# ---------------------------------------------------------------------------
# Criação pelo administrador


def test_criacao_gera_senha_e_envia_ao_titular(client, admin, smtp):
    login(client, "admin@teste.br")
    resposta = client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)

    novo = Usuario.query.filter_by(email="recem@teste.br").one()
    assert novo.senha_provisoria is True
    assert [m[0] for m in smtp] == ["recem@teste.br"]

    texto, html = smtp[0][2], smtp[0][3]
    assert "recem@teste.br" in texto and "recem@teste.br" in html
    # a senha vai nas duas partes: sem ela no texto simples, quem lê em cliente
    # sem HTML fica sem acesso
    senha = _senha_do_corpo(texto)
    assert senha and senha in html
    assert novo.verificar_senha(senha)

    # a senha não é exibida quando o envio deu certo, nem entra na trilha
    assert senha.encode() not in resposta.data
    assert "Credenciais enviadas" in resposta.data.decode()
    log = LogAuditoria.query.filter_by(acao="envio_credenciais").one()
    assert senha not in (log.dados_json or "")


def _senha_do_corpo(texto: str) -> str:
    """Extrai a senha da linha seguinte ao rótulo, no corpo em texto simples."""
    linhas = [linha.strip() for linha in texto.splitlines()]
    return linhas[linhas.index("Senha temporária:") + 1]


def _senha_da_tela(corpo: str) -> str:
    return corpo.split('<p class="senha-gerada"><code>')[1].split("</code>")[0]


def test_senha_aparece_na_tela_quando_o_email_falha(client, admin, smtp_falho):
    """Sem isto, uma falha de rede deixaria a conta cadastrada e inacessível,
    sem caminho de volta a não ser gerar outra senha."""
    login(client, "admin@teste.br")
    resposta = client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)

    novo = Usuario.query.filter_by(email="recem@teste.br").one()
    assert novo.verificar_senha(_senha_da_tela(resposta.data.decode()))


def test_senha_da_tela_nao_entra_no_cookie_de_sessao(client, admin, smtp_falho):
    """A flash viaja na sessão, que é um cookie assinado mas NÃO cifrado: a
    senha de terceiro ficaria gravada no navegador do administrador. Daí a
    página ser renderizada como resposta direta do POST."""
    login(client, "admin@teste.br")
    resposta = client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)

    senha = _senha_da_tela(resposta.data.decode())
    cookies = "".join(
        cabecalho for nome, cabecalho in resposta.headers if nome == "Set-Cookie"
    )
    assert senha not in cookies
    with client.session_transaction() as sessao:
        assert senha not in str(dict(sessao))


def test_sem_envio_configurado_a_tela_diz_o_que_fazer(client, admin):
    """Numa instalação recém-implantada este é o caso normal, não uma falha
    transitória: mandar "tentar de novo" desviaria da ação correta."""
    login(client, "admin@teste.br")
    corpo = client.post(
        "/admin/usuarios/novo", data=NOVO, follow_redirects=True
    ).data.decode()
    assert "não está configurado" in corpo
    assert Usuario.query.filter_by(email="recem@teste.br").one()


def test_conta_criada_desativada_nao_recebe_credenciais(client, admin, smtp):
    """A senha chegaria ao titular sem servir para nada: conta inativa não
    autentica. Mesma guarda que `repor_senha` já impunha."""
    login(client, "admin@teste.br")
    inativa = {**NOVO}
    inativa.pop("ativo")  # caixa desmarcada
    resposta = client.post(
        "/admin/usuarios/novo", data=inativa, follow_redirects=True
    )

    novo = Usuario.query.filter_by(email="recem@teste.br").one()
    assert novo.ativo is False
    assert smtp == []
    assert "nenhuma credencial foi enviada" in resposta.data.decode()


def test_formulario_nao_aceita_mais_senha_digitada(client, admin, smtp):
    """Campo removido: senha alheia digitada por terceiro tende a ser fraca,
    repetida entre contas e conhecida por quem a digitou."""
    login(client, "admin@teste.br")
    assert "Senha inicial" not in client.get("/admin/usuarios/novo").data.decode()

    client.post(
        "/admin/usuarios/novo", data={**NOVO, "senha": "escolhida-por-mim"},
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="recem@teste.br").one()
    assert not novo.verificar_senha("escolhida-por-mim")


# ---------------------------------------------------------------------------
# Criação pelo orientador


def test_orientador_cria_orientando_e_a_senha_segue_por_email(
    client, orientador, smtp
):
    login(client, "orientador@teste.br")
    client.post(
        "/orientandos/novo",
        data={
            "nome": "Calouro",
            "email": "calouro@teste.br",
            "modalidade": "mestrado",
            "titulo_projeto": "Projeto do Calouro",
            "data_inicio": "2026-03-01",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="calouro@teste.br").one()
    assert novo.senha_provisoria is True
    assert [m[0] for m in smtp] == ["calouro@teste.br"]
    assert novo.verificar_senha(_senha_do_corpo(smtp[0][2]))


# ---------------------------------------------------------------------------
# Troca obrigatória no primeiro acesso


def test_senha_provisoria_prende_a_tela_de_troca(client, admin, smtp):
    login(client, "admin@teste.br")
    client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)
    senha = _senha_do_corpo(smtp[0][2])
    client.post("/auth/logout")

    login(client, "recem@teste.br", senha)
    # qualquer destino desvia para a troca, e não só o primeiro
    for destino in ("/dashboard", "/ajuda", "/orientacoes/1"):
        resposta = client.get(destino)
        assert resposta.status_code == 302
        assert resposta.headers["Location"].endswith("/auth/senha")

    pagina = client.get("/auth/senha").data.decode()
    assert "A troca é obrigatória" in pagina


def test_troca_libera_o_sistema_e_limpa_a_marca(client, admin, smtp):
    login(client, "admin@teste.br")
    client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)
    senha = _senha_do_corpo(smtp[0][2])
    client.post("/auth/logout")

    login(client, "recem@teste.br", senha)
    client.post(
        "/auth/senha",
        data={
            "senha_atual": senha,
            "nova_senha": "escolhida-por-mim-9",
            "confirmacao": "escolhida-por-mim-9",
        },
        follow_redirects=True,
    )
    novo = Usuario.query.filter_by(email="recem@teste.br").one()
    assert novo.senha_provisoria is False
    assert client.get("/dashboard").status_code == 200

    # A sessão precisa acompanhar o hash novo. `get_id` carrega um trecho dele
    # para que a troca encerre sessões abertas; sem reemitir a identidade, isso
    # derrubava justamente quem acabou de trocar, no primeiro acesso. O status
    # 200 acima não pega: a suíte mantém um contexto de aplicação aberto e o
    # Flask-Login serve o usuário guardado em `g` sem consultar o carregador.
    with client.session_transaction() as sessao:
        assert sessao["_user_id"] == novo.get_id()


def test_repetir_a_provisoria_nao_cumpre_a_troca(client, admin, smtp):
    """Do contrário a obrigação se cumpriria com a mesma senha, e a que
    trafegou por e-mail seguiria valendo."""
    login(client, "admin@teste.br")
    client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)
    senha = _senha_do_corpo(smtp[0][2])
    client.post("/auth/logout")

    login(client, "recem@teste.br", senha)
    resposta = client.post(
        "/auth/senha",
        data={"senha_atual": senha, "nova_senha": senha, "confirmacao": senha},
        follow_redirects=True,
    )
    assert "diferente da atual" in resposta.data.decode()
    assert Usuario.query.filter_by(email="recem@teste.br").one().senha_provisoria


def test_sair_continua_possivel_com_senha_provisoria(client, admin, smtp):
    """O bloqueio não pode aprisionar: quem não quer trocar agora precisa poder
    encerrar a sessão."""
    login(client, "admin@teste.br")
    client.post("/admin/usuarios/novo", data=NOVO, follow_redirects=True)
    senha = _senha_do_corpo(smtp[0][2])
    client.post("/auth/logout")

    login(client, "recem@teste.br", senha)
    assert client.post("/auth/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302  # deslogado, vai ao login


def test_contas_existentes_nao_sao_prendidas(client, orientador):
    """O backfill grava 0: marcar as contas antigas prenderia todo mundo na
    tela de troca no primeiro acesso após a implantação."""
    assert orientador.senha_provisoria is False
    login(client, "orientador@teste.br")
    assert client.get("/dashboard").status_code == 200


# ---------------------------------------------------------------------------
# Reposição pelo administrador


def test_admin_repoe_senha_e_o_titular_recebe(client, admin, orientando, smtp):
    login(client, "admin@teste.br")
    resposta = client.post(
        f"/admin/usuarios/{orientando.id}/senha-temporaria", follow_redirects=True
    )
    assert "Credenciais enviadas" in resposta.data.decode()
    assert [m[0] for m in smtp] == [orientando.email]

    senha = _senha_do_corpo(smtp[0][2])
    assert orientando.senha_provisoria is True
    assert orientando.verificar_senha(senha)
    assert not orientando.verificar_senha("senha-teste-123")  # a anterior morreu
    assert LogAuditoria.query.filter_by(acao="reposicao_senha").count() == 1


def test_reposicao_derruba_a_sessao_aberta_da_conta(app, admin, orientando):
    """O hash entra em `Usuario.get_id`: reposta a senha, a sessão do eventual
    invasor deixa de casar. É o que torna a reposição útil na suspeita de
    acesso indevido.

    Verificado no `load_user`, e não por requisição, pela mesma razão de
    `test_recuperacao.test_troca_de_senha_encerra_sessoes`: a suíte mantém um
    contexto de aplicação aberto, o Flask reaproveita-o entre requisições do
    test client, e o Flask-Login serve o usuário guardado em `g` sem consultar o
    carregador. Em produção cada requisição tem contexto próprio."""
    from app.models.user import load_user

    identidade_antiga = orientando.get_id()
    assert load_user(identidade_antiga) is orientando  # sessão válida

    repor_senha(orientando, admin)
    db.session.commit()

    assert load_user(identidade_antiga) is None  # sessão anterior encerrada
    assert load_user(orientando.get_id()).id == orientando.id


def test_admin_nao_repoe_a_propria_senha(client, admin, smtp):
    login(client, "admin@teste.br")
    resposta = client.post(
        f"/admin/usuarios/{admin.id}/senha-temporaria", follow_redirects=True
    )
    assert "use o menu Senha" in resposta.data.decode()
    assert admin.senha_provisoria is False
    assert smtp == []


def test_nao_repoe_senha_de_conta_desativada(app, admin):
    """A senha chegaria ao titular sem servir para nada: conta inativa não
    autentica."""
    inativo = _criar_usuario("Inativo", "inativo@teste.br", "orientando")
    inativo.ativo = False
    db.session.commit()

    with pytest.raises(GestaoUsuarioInvalida):
        repor_senha(inativo, admin)
    assert inativo.senha_provisoria is False


def test_botao_some_para_conta_desativada_e_para_a_propria(
    client, admin, orientando
):
    orientando.ativo = False
    db.session.commit()
    login(client, "admin@teste.br")

    pagina = client.get("/admin/usuarios").data.decode()
    assert f"/admin/usuarios/{orientando.id}/senha-temporaria" not in pagina
    assert f"/admin/usuarios/{admin.id}/senha-temporaria" not in pagina


def test_evento_de_credencial_desconhecido_e_recusado(app, orientando):
    with pytest.raises(ValueError):
        credenciais.enviar(orientando, "x", "inventado")


def test_ajuda_nao_promete_mais_senha_digitada(client, orientando):
    """A ajuda mandava o administrador informar a senha inicial e definir outra
    manualmente quando o e-mail falhasse. Instrução que descreve um campo
    inexistente é pior que instrução nenhuma."""
    login(client, "orientando@teste.br")
    ajuda = client.get("/ajuda").data.decode()

    assert "senha temporária" in ajuda.lower()
    assert "A troca é obrigatória" in ajuda
    assert "Senha temporária" in ajuda  # o botão do administrador
    assert "senha inicial" not in ajuda
