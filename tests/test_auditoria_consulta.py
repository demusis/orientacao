"""Trilha de auditoria: recorte de 20 registros, filtros e origem do IP."""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import LogAuditoria

from tests.conftest import login


def _log(acao, *, usuario=None, quando=None, ip="203.0.113.10"):
    registro = LogAuditoria(
        usuario_id=usuario.id if usuario else None,
        acao=acao,
        entidade="usuario",
        ip=ip,
        timestamp=quando or datetime(2026, 7, 20, 12, 0),
    )
    db.session.add(registro)
    db.session.commit()
    return registro


def _linhas(pagina):
    """Ações presentes nas linhas da tabela. Comparar com a página inteira
    daria falso positivo: os nomes também figuram nas opções do seletor."""
    import re

    return set(re.findall(r"<td>([a-z_0-9]+)</td>", pagina))


def _conta_linhas(pagina):
    import re

    return len(re.findall(r"<td>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</td>", pagina))


def test_pagina_traz_20_registros_do_mais_recente_ao_mais_antigo(client, admin):
    for i in range(25):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria").data.decode()

    acoes = _linhas(pagina)
    assert "acao_24" in acoes  # o mais recente
    assert "acao_00" not in acoes  # o mais antigo ficou para a página seguinte
    # exatamente 20 linhas — o próprio 'login' do admin ocupa uma delas
    assert _conta_linhas(pagina) == 20
    assert "página <strong>1</strong> de <strong>2</strong>" in pagina


def test_segunda_pagina_traz_os_registros_seguintes(client, admin):
    for i in range(25):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    acoes = _linhas(client.get("/admin/auditoria?pagina=2").data.decode())
    assert "acao_00" in acoes  # o mais antigo
    assert "acao_24" not in acoes


def test_rodape_oferece_primeira_e_ultima(client, admin):
    for i in range(45):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria?pagina=2").data.decode()

    for rotulo in ("« Primeira", "‹ Anterior", "Próxima ›", "Última »"):
        assert rotulo in pagina
    # na página 2 de 3, os quatro são links ativos e apontam aos extremos
    assert 'class="inativo"' not in pagina
    assert 'pagina=1"' in pagina  # primeira
    assert 'pagina=3"' in pagina  # última


def test_primeira_pagina_desativa_retrocesso(client, admin):
    for i in range(25):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria").data.decode()
    assert '<span class="inativo">« Primeira</span>' in pagina
    assert '<span class="inativo">‹ Anterior</span>' in pagina


def test_pagina_alem_do_fim_leva_a_ultima(client, admin):
    for i in range(25):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    resp = client.get("/admin/auditoria?pagina=99")
    assert resp.status_code == 302
    assert "pagina=2" in resp.headers["Location"]


def test_filtro_preservado_ao_mudar_de_pagina(client, admin, orientador):
    for i in range(25):
        _log(
            "acao_filtrada",
            usuario=orientador,
            quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i),
        )
    _log("acao_de_outro", usuario=admin)
    login(client, "admin@teste.br")
    pagina = client.get(f"/admin/auditoria?usuario_id={orientador.id}").data.decode()

    # os links de página carregam o filtro adiante
    assert f"usuario_id={orientador.id}" in pagina
    acoes = _linhas(
        client.get(
            f"/admin/auditoria?usuario_id={orientador.id}&pagina=2"
        ).data.decode()
    )
    assert "acao_de_outro" not in acoes


def test_sem_paginacao_quando_cabe_em_uma_pagina(client, admin):
    _log("unica")
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria").data.decode()
    assert 'class="paginacao"' not in pagina


def test_filtro_por_acao(client, admin):
    _log("login")
    _log("exclusao_usuario")
    login(client, "admin@teste.br")
    acoes = _linhas(client.get("/admin/auditoria?acao=exclusao_usuario").data.decode())
    assert "exclusao_usuario" in acoes
    assert "login" not in acoes


def test_filtro_por_usuario(client, admin, orientador):
    _log("acao_do_admin", usuario=admin)
    _log("acao_do_orientador", usuario=orientador)
    login(client, "admin@teste.br")
    acoes = _linhas(
        client.get(f"/admin/auditoria?usuario_id={orientador.id}").data.decode()
    )
    assert "acao_do_orientador" in acoes
    assert "acao_do_admin" not in acoes


def test_filtro_por_intervalo_de_data_e_hora(client, admin):
    _log("antiga", quando=datetime(2026, 7, 1, 8, 0))
    _log("dentro", quando=datetime(2026, 7, 15, 14, 30))
    _log("posterior", quando=datetime(2026, 7, 30, 9, 0))
    login(client, "admin@teste.br")
    acoes = _linhas(
        client.get("/admin/auditoria?de=2026-07-10T00:00&ate=2026-07-20T00:00").data.decode()
    )
    assert "dentro" in acoes
    assert "antiga" not in acoes
    assert "posterior" not in acoes


def test_intervalo_invertido_e_recusado(client, admin):
    _log("qualquer")
    login(client, "admin@teste.br")
    pagina = client.get(
        "/admin/auditoria?de=2026-07-20T00:00&ate=2026-07-01T00:00"
    ).data.decode()
    assert "posterior ao início" in pagina


def test_auditoria_restrita_ao_admin(client, orientador, orientando):
    login(client, "orientador@teste.br")
    assert client.get("/admin/auditoria").status_code == 403


# --- coluna Dados: JSON cru apresentado como pares rótulo → valor ---


def test_dados_itens_formata_chaves_valores_e_fallback(app):
    import json

    registro = LogAuditoria(
        acao="criacao_marco_grupo",
        entidade="marco",
        dados_json=json.dumps(
            {"marcos": [12, 13], "ativo": False, "chave_nova": "x"},
            ensure_ascii=False,
        ),
    )
    itens = dict(registro.dados_itens)
    assert itens["Marcos"] == "#12, #13"       # lista de ids ganha #
    assert itens["Ativo"] == "não"             # booleano vira sim/não
    assert itens["Chave nova"] == "x"          # chave não prevista, humanizada
    # dados ausentes ou ilegíveis não quebram
    assert LogAuditoria(dados_json=None).dados_itens == []
    assert LogAuditoria(dados_json="{quebrado").dados_itens == []


def test_coluna_dados_apresenta_pares_e_esconde_json_cru(client, admin):
    import json

    registro = LogAuditoria(
        acao="criacao_marco_grupo",
        entidade="marco",
        entidade_id=12,
        dados_json=json.dumps(
            {"grupo_id": "ba4bf885f89f", "marcos": [12, 13], "orientacoes": [1, 2]},
            ensure_ascii=False,
        ),
        timestamp=datetime(2026, 7, 20, 12, 0),
    )
    db.session.add(registro)
    db.session.commit()
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria").data.decode()

    assert "Marcos" in pagina           # rótulo em português
    assert "#12, #13" in pagina         # ids formatados
    assert '"marcos":' not in pagina    # a chave crua do JSON não aparece


# --- origem do IP ---


def test_sem_proxy_confiavel_x_forwarded_for_e_ignorado(client, orientacao):
    """Sem proxy declarado, o cabeçalho é forjável e não pode virar origem."""
    client.post(
        "/auth/login",
        data={"email": "inexistente@teste.br", "senha": "x"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    registro = LogAuditoria.query.filter_by(acao="login_falho").one()
    assert registro.ip != "198.51.100.7"


def test_com_proxy_confiavel_o_ip_do_cliente_e_registrado(app_com_proxy):
    """Com TRUSTED_PROXY_COUNT=1, vale o valor escrito pelo proxy — o último
    da lista —, e não o que o cliente tenha inserido antes dele."""
    cliente = app_com_proxy.test_client()
    cliente.post(
        "/auth/login",
        data={"email": "inexistente@teste.br", "senha": "x"},
        headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.42"},
        environ_overrides={"REMOTE_ADDR": "10.0.4.160"},
    )
    with app_com_proxy.app_context():
        registro = LogAuditoria.query.filter_by(acao="login_falho").one()
        assert registro.ip == "203.0.113.42"
        assert not registro.ip.startswith("10.")
