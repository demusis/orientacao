from datetime import date, timedelta

from app.extensions import db
from app.models import Ata, LogAuditoria, Marco, Parecer, Usuario
from app.services.tempo import hoje_local


def _token_de(client, email, senha="senha-teste-123"):
    resp = client.post(
        "/api/v1/auth/token", json={"email": email, "senha": senha}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_api_auth_fluxos_e_bloqueios(client, app, orientador):
    # Credenciais inválidas
    r = client.post(
        "/api/v1/auth/token",
        json={"email": "orientador@teste.br", "senha": "errada"},
    )
    assert r.status_code == 401

    # E-mail inexistente
    r = client.post(
        "/api/v1/auth/token",
        json={"email": "naoexiste@teste.br", "senha": "errada"},
    )
    assert r.status_code == 401

    # Login válido
    r = client.post(
        "/api/v1/auth/token",
        json={"email": "orientador@teste.br", "senha": "senha-teste-123"},
    )
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["usuario"]["email"] == "orientador@teste.br"
    assert dados["usuario"]["papel"] == "orientador"
    token = dados["token"]

    # Token funciona em GET /sync
    assert client.get("/api/v1/sync", headers=_headers(token)).status_code == 200

    # Troca de senha invalida token anterior
    orientador.set_senha("nova-senha-forte-456")
    db.session.commit()
    assert client.get("/api/v1/sync", headers=_headers(token)).status_code == 401

    # Senha provisória bloqueia emissão e uso de token
    orientador.set_senha("temp-123", provisoria=True)
    db.session.commit()
    r_prov = client.post(
        "/api/v1/auth/token",
        json={"email": "orientador@teste.br", "senha": "temp-123"},
    )
    assert r_prov.status_code == 403
    assert r_prov.get_json()["erro"] == "troca_senha_obrigatoria"

    # Conta desativada
    orientador.set_senha("ativa-123", provisoria=False)
    orientador.ativo = False
    db.session.commit()
    r_inativo = client.post(
        "/api/v1/auth/token",
        json={"email": "orientador@teste.br", "senha": "ativa-123"},
    )
    assert r_inativo.status_code == 403


def test_api_auth_excesso_tentativas(client, app, orientador):
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    for _ in range(teto):
        r = client.post(
            "/api/v1/auth/token",
            json={"email": "orientador@teste.br", "senha": "errada"},
        )
        assert r.status_code == 401

    r_bloq = client.post(
        "/api/v1/auth/token",
        json={"email": "orientador@teste.br", "senha": "senha-teste-123"},
    )
    assert r_bloq.status_code == 429


def test_api_sync_sem_autenticacao(client):
    assert client.get("/api/v1/sync").status_code == 401
    assert (
        client.get("/api/v1/sync", headers={"Authorization": "Bearer invalido"}).status_code
        == 401
    )


def test_get_sync_isolamento_por_vinculo(
    client, orientador, orientando, orientando2, intruso, orientacao, orientacao2
):
    m1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Tarefa Orientando 1",
        data_prevista=date(2026, 6, 1),
        tipo="projeto",
        etapa=10,
    )
    m2 = Marco(
        orientacao_id=orientacao2.id,
        titulo="Tarefa Orientando 2",
        data_prevista=date(2026, 6, 2),
        tipo="relatorio",
        etapa=20,
    )
    db.session.add_all([m1, m2])
    db.session.commit()

    tok_orientador = _token_de(client, "orientador@teste.br")
    estado_or = client.get("/api/v1/sync", headers=_headers(tok_orientador)).get_json()
    assert {o["id"] for o in estado_or["orientacoes"]} == {orientacao.id, orientacao2.id}
    assert {m["titulo"] for m in estado_or["marcos"]} == {
        "Tarefa Orientando 1",
        "Tarefa Orientando 2",
    }

    tok_aluna = _token_de(client, "orientando@teste.br")
    estado_al = client.get("/api/v1/sync", headers=_headers(tok_aluna)).get_json()
    assert [o["id"] for o in estado_al["orientacoes"]] == [orientacao.id]
    assert [m["titulo"] for m in estado_al["marcos"]] == ["Tarefa Orientando 1"]

    tok_intruso = _token_de(client, "intruso@teste.br")
    estado_in = client.get("/api/v1/sync", headers=_headers(tok_intruso)).get_json()
    assert estado_in["orientacoes"] == []
    assert estado_in["marcos"] == []
    assert estado_in["atas"] == []
    assert estado_in["pareceres"] == []


def test_post_sync_fluxo_completo_e_idempotencia(
    client, orientador, orientando, orientacao, orientacao2
):
    tok_orientador = _token_de(client, "orientador@teste.br")
    tok_orientando = _token_de(client, "orientando@teste.br")
    hoje = hoje_local()
    amanha = hoje + timedelta(days=1)

    # 1. Orientador offline cria tarefa, agenda reunião de hoje e outra futura
    lote1 = {
        "operacoes": [
            {
                "op_id": "op-criar-tarefa-1",
                "acao": "criar_tarefa",
                "dados": {
                    "orientacao_ids": [orientacao.id, orientacao2.id],
                    "titulo": "Entregar revisão bibliográfica",
                    "tipo": "relatorio",
                    "descricao": "Incluir artigos de 2025",
                    "data_prevista": amanha.isoformat(),
                    "etapa": 20,
                    "entrega_esperada": "documento",
                },
            },
            {
                "op_id": "op-agendar-1",
                "acao": "agendar_reuniao",
                "dados": {
                    "orientacao_ids": [orientacao.id],
                    "data_reuniao": hoje.isoformat(),
                    "hora_reuniao": "10:00",
                    "link_reuniao": "https://meet.example.com/sala-1",
                    "pauta": "Alinhamento inicial",
                },
            },
            {
                "op_id": "op-agendar-2",
                "acao": "agendar_reuniao",
                "dados": {
                    "orientacao_ids": [orientacao2.id],
                    "data_reuniao": amanha.isoformat(),
                    "pauta": "Reunião futura para cancelar",
                },
            },
        ]
    }
    r1 = client.post("/api/v1/sync", json=lote1, headers=_headers(tok_orientador))
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert [x["status"] for x in d1["resultados"]] == ["ok", "ok", "ok"]
    assert len(d1["estado"]["marcos"]) == 2
    assert len(d1["estado"]["atas"]) == 2

    # Idempotência: reenviar o mesmo lote não duplica nada
    r1_dup = client.post("/api/v1/sync", json=lote1, headers=_headers(tok_orientador))
    assert r1_dup.status_code == 200
    assert [x["status"] for x in r1_dup.get_json()["resultados"]] == [
        "ja_aplicada",
        "ja_aplicada",
        "ja_aplicada",
    ]
    assert Marco.query.count() == 2
    assert Ata.query.count() == 2

    marco_o1 = next(
        m for m in d1["estado"]["marcos"] if m["orientacao_id"] == orientacao.id
    )
    ata_hoje = next(
        a for a in d1["estado"]["atas"] if orientacao.id in a["orientacao_ids"]
    )
    ata_futura = next(
        a for a in d1["estado"]["atas"] if orientacao2.id in a["orientacao_ids"]
    )

    # 2. Orientando sincroniza sinalização de conclusão (e tenta ação proibida no mesmo lote)
    lote_aluno = {
        "operacoes": [
            {
                "op_id": "op-aluno-sinalizar-1",
                "acao": "sinalizar_conclusao_marco",
                "dados": {
                    "marco_id": marco_o1["id"],
                    "nota": "Texto pronto para leitura.",
                },
            },
            {
                "op_id": "op-aluno-confirmar-proibido",
                "acao": "confirmar_conclusao_marco",
                "dados": {"marco_id": marco_o1["id"]},
            },
        ]
    }
    r_al = client.post("/api/v1/sync", json=lote_aluno, headers=_headers(tok_orientando))
    assert r_al.status_code == 200
    res_al = r_al.get_json()["resultados"]
    assert res_al[0]["status"] == "ok"
    assert res_al[1]["status"] == "erro"
    marco_sync = r_al.get_json()["estado"]["marcos"][0]
    assert marco_sync["conclusao_sinalizada"] is True
    assert marco_sync["aguardando"] == "orientador"

    # 3. Orientador devolve marco, depois edita marco, atualiza ata, marca presença,
    #    finaliza ata de hoje, cancela reunião futura e emite parecer
    lote2 = {
        "operacoes": [
            {
                "op_id": "op-devolver-1",
                "acao": "devolver_marco",
                "dados": {
                    "marco_id": marco_o1["id"],
                    "nota": "Ajustar referências ABNT.",
                },
            },
            {
                "op_id": "op-editar-marco-1",
                "acao": "editar_marco",
                "dados": {
                    "marco_id": marco_o1["id"],
                    "titulo": "Revisão bibliográfica ajustada",
                },
            },
            {
                "op_id": "op-presenca-1",
                "acao": "registrar_presenca",
                "dados": {
                    "ata_id": ata_hoje["id"],
                    "orientacao_id": orientacao.id,
                    "presenca": "presente",
                },
            },
            {
                "op_id": "op-atualizar-ata-1",
                "acao": "atualizar_ata",
                "dados": {
                    "ata_id": ata_hoje["id"],
                    "pauta": "Alinhamento inicial",
                    "deliberacoes": "Ficou definida a entrega da revisão.",
                    "marco_ids": [marco_o1["id"]],
                },
            },
            {
                "op_id": "op-finalizar-ata-1",
                "acao": "finalizar_ata",
                "dados": {"ata_id": ata_hoje["id"]},
            },
            {
                "op_id": "op-reagendar-ata-2",
                "acao": "reagendar_ata",
                "dados": {
                    "ata_id": ata_futura["id"],
                    "data_nova": (amanha + timedelta(days=2)).isoformat(),
                    "hora_nova": "15:30",
                    "motivo": "Ajuste de agenda",
                },
            },
            {
                "op_id": "op-cancelar-ata-2",
                "acao": "cancelar_reuniao",
                "dados": {
                    "ata_id": ata_futura["id"],
                    "motivo": "Orientando viajou",
                },
            },
            {
                "op_id": "op-parecer-1",
                "acao": "emitir_parecer",
                "dados": {
                    "orientacao_id": orientacao.id,
                    "tipo": "andamento",
                    "resultado": "aprovado_com_ressalvas",
                    "conteudo": "Bom progresso no semestre.",
                },
            },
        ]
    }
    r2 = client.post("/api/v1/sync", json=lote2, headers=_headers(tok_orientador))
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert all(x["status"] == "ok" for x in d2["resultados"]), d2["resultados"]

    m_atualizado = next(
        m for m in d2["estado"]["marcos"] if m["id"] == marco_o1["id"]
    )
    assert m_atualizado["titulo"] == "Revisão bibliográfica ajustada"
    assert m_atualizado["aguardando"] == "orientando_revisao"
    assert m_atualizado["nota_devolucao"] == "Ajustar referências ABNT."

    a1 = next(a for a in d2["estado"]["atas"] if a["id"] == ata_hoje["id"])
    assert a1["status"] == "finalizada"
    assert a1["marco_ids"] == [marco_o1["id"]]
    assert a1["participacoes"][0]["presenca"] == "presente"

    a2 = next(a for a in d2["estado"]["atas"] if a["id"] == ata_futura["id"])
    assert a2["status"] == "cancelada"
    assert a2["motivo_cancelamento"] == "Orientando viajou"

    assert len(d2["estado"]["pareceres"]) == 1
    assert Parecer.query.count() == 1
    assert Parecer.query.first().conteudo_congelado is not None

    # 4. Orientando re-sinaliza e orientador confirma conclusão
    r_al2 = client.post(
        "/api/v1/sync",
        json={
            "operacoes": [
                {
                    "op_id": "op-aluno-sinalizar-2",
                    "acao": "sinalizar_conclusao_marco",
                    "dados": {"marco_id": marco_o1["id"], "nota": "Corrigido."},
                }
            ]
        },
        headers=_headers(tok_orientando),
    )
    assert r_al2.get_json()["resultados"][0]["status"] == "ok"

    r_conf = client.post(
        "/api/v1/sync",
        json={
            "operacoes": [
                {
                    "op_id": "op-confirmar-1",
                    "acao": "confirmar_conclusao_marco",
                    "dados": {"marco_id": marco_o1["id"]},
                }
            ]
        },
        headers=_headers(tok_orientador),
    )
    assert r_conf.get_json()["resultados"][0]["status"] == "ok"
    m_final = next(
        m for m in r_conf.get_json()["estado"]["marcos"] if m["id"] == marco_o1["id"]
    )
    assert m_final["status"] == "concluido"
    assert m_final["aguardando"] is None

    # Confirma registro na trilha
    assert LogAuditoria.query.filter_by(acao="sync_operacao").count() >= 10
    assert Usuario.query.count() >= 2
