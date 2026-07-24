"""P-5: relógio do programa — fração do prazo decorrida e sinal de risco que
combina tempo e marco crítico (qualificação/defesa vencida)."""
from datetime import timedelta

from app.extensions import db
from app.models import Marco
from app.services.painel import relogio
from app.services.tempo import agora


def _datas(orientacao, dias_desde_inicio, dias_ate_fim):
    hoje = agora().date()
    orientacao.data_inicio = hoje - timedelta(days=dias_desde_inicio)
    orientacao.data_fim_prevista = hoje + timedelta(days=dias_ate_fim)
    db.session.commit()


def test_risco_baixo_inicio_do_prazo(app, orientacao):
    _datas(orientacao, 100, 900)  # ~10% decorrido
    r = relogio(orientacao)
    assert r["risco"] == "baixo"
    assert r["sem_prazo"] is False


def test_risco_medio_acima_de_75(app, orientacao):
    _datas(orientacao, 800, 200)  # 80% decorrido
    assert relogio(orientacao)["risco"] == "medio"


def test_risco_alto_acima_de_90(app, orientacao):
    _datas(orientacao, 950, 50)  # 95% decorrido
    assert relogio(orientacao)["risco"] == "alto"


def test_sem_prazo_fica_baixo_mas_marcado(app, orientacao):
    # a fixture nasce sem data_fim_prevista
    r = relogio(orientacao)
    assert r["sem_prazo"] is True
    assert r["risco"] == "baixo"
    assert "prazo não definido" in r["rotulo"]


def test_marco_critico_vencido_forca_alto(app, orientacao):
    _datas(orientacao, 100, 900)  # tempo tranquilo (10%)
    hoje = agora().date()
    db.session.add(
        Marco(
            orientacao_id=orientacao.id,
            titulo="Exame de qualificação",
            tipo="qualificacao",
            etapa=40,
            data_prevista=hoje - timedelta(days=10),  # vencido
        )
    )
    db.session.commit()
    r = relogio(orientacao)
    assert r["marco_critico_vencido"] is True
    assert r["risco"] == "alto"
