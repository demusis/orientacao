"""Sinal de risco do prazo com limiares e tipos críticos configuráveis.

O relógio (`painel.relogio`) lê `ConfiguracaoRisco.vigente()`: sem linha
gravada valem os padrões (75/90, qualificação e defesa); com linha, valem os
parâmetros do administrador, imediatamente e sem reprocessamento."""
from datetime import date, timedelta

from app.extensions import db
from app.models import ConfiguracaoRisco, LogAuditoria, Marco
from app.services import painel
from tests.conftest import login


def _prazo_80_por_cento(orientacao):
    """Vínculo com exatamente 80% do prazo decorrido (80 de 100 dias)."""
    orientacao.data_inicio = date.today() - timedelta(days=80)
    orientacao.data_fim_prevista = date.today() + timedelta(days=20)
    db.session.commit()


def _marco_vencido(orientacao, tipo):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo=f"Marco {tipo}",
        tipo=tipo,
        data_prevista=date.today() - timedelta(days=1),
    )
    db.session.add(m)
    db.session.commit()
    return m


def test_padroes_sem_linha_gravada(app, orientacao):
    """Sem configuração salva, a regra é a histórica: amarelo acima de 75%."""
    _prazo_80_por_cento(orientacao)
    r = painel.relogio(orientacao)
    assert r["risco"] == "medio"
    assert r["marco_critico_vencido"] is False
    # e nada foi gravado pelo caminho de leitura
    assert db.session.get(ConfiguracaoRisco, 1) is None


def test_limiares_configurados_mudam_a_cor(app, orientacao):
    _prazo_80_por_cento(orientacao)
    config = ConfiguracaoRisco.vigente()
    config.limiar_medio = 85
    config.limiar_alto = 95
    db.session.add(config)
    db.session.commit()
    assert painel.relogio(orientacao)["risco"] == "baixo"

    config.limiar_medio = 50
    config.limiar_alto = 70
    db.session.commit()
    assert painel.relogio(orientacao)["risco"] == "alto"


def test_tipos_criticos_configurados(app, orientacao):
    _prazo_80_por_cento(orientacao)
    _marco_vencido(orientacao, "publicacao")
    # publicação não é crítica por padrão: segue amarelo (80% > 75%)
    assert painel.relogio(orientacao)["risco"] == "medio"

    config = ConfiguracaoRisco.vigente()
    config.definir_criticos(["publicacao"])
    db.session.add(config)
    db.session.commit()
    r = painel.relogio(orientacao)
    assert r["risco"] == "alto"
    assert r["marco_critico_vencido"] is True

    # defesa saiu da lista: vencida, deixa de acender o vermelho
    _marco_vencido(orientacao, "defesa")
    config.definir_criticos(["qualificacao"])
    db.session.commit()
    r = painel.relogio(orientacao)
    assert r["marco_critico_vencido"] is False


def test_tela_salva_e_audita(client, admin):
    login(client, "admin@teste.br")
    assert client.get("/admin/risco").status_code == 200
    resposta = client.post(
        "/admin/risco",
        data={
            "limiar_medio": 60,
            "limiar_alto": 80,
            "tipos_criticos": ["defesa", "publicacao"],
        },
    )
    assert resposta.status_code == 302
    config = db.session.get(ConfiguracaoRisco, 1)
    assert config.limiar_medio == 60
    assert config.limiar_alto == 80
    # gravado na ordem canônica de TIPOS_MARCO
    assert config.criticos == ("publicacao", "defesa")
    assert config.atualizado_por == admin.id
    log = LogAuditoria.query.filter_by(acao="configuracao_risco").first()
    assert log is not None and "publicacao" in log.dados_json


def test_limiar_alto_deve_superar_o_medio(client, admin):
    login(client, "admin@teste.br")
    resposta = client.post(
        "/admin/risco",
        data={"limiar_medio": 80, "limiar_alto": 70, "tipos_criticos": []},
    )
    assert resposta.status_code == 200  # re-renderiza com erro, não grava
    assert "maior que o do risco médio".encode() in resposta.data
    assert db.session.get(ConfiguracaoRisco, 1) is None


def test_sem_tipos_criticos_o_risco_e_so_pelo_tempo(client, app, admin, orientacao):
    _prazo_80_por_cento(orientacao)
    _marco_vencido(orientacao, "defesa")
    login(client, "admin@teste.br")
    client.post(
        "/admin/risco",
        data={"limiar_medio": 75, "limiar_alto": 90},  # nenhum tipo marcado
    )
    config = db.session.get(ConfiguracaoRisco, 1)
    assert config.criticos == ()
    r = painel.relogio(orientacao)
    assert r["marco_critico_vencido"] is False
    assert r["risco"] == "medio"


def test_tela_restrita_ao_admin(client, orientador):
    login(client, "orientador@teste.br")
    assert client.get("/admin/risco").status_code == 403
