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


def test_lista_limitada_a_20_registros(client, admin):
    for i in range(25):
        _log(f"acao_{i:02d}", quando=datetime(2026, 7, 20, 10, 0) + timedelta(minutes=i))
    login(client, "admin@teste.br")
    pagina = client.get("/admin/auditoria").data.decode()

    import re

    acoes = _linhas(pagina)
    assert "acao_24" in acoes  # o mais recente
    assert "acao_00" not in acoes  # o mais antigo ficou de fora
    # exatamente 20 linhas — o próprio 'login' do admin ocupa uma delas
    linhas = re.findall(r"<td>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</td>", pagina)
    assert len(linhas) == 20
    assert "Exibindo os <strong>20</strong>" in pagina


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
