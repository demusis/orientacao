"""Pendências do painel: entregas a confirmar, tarefas em aberto, atas em
rascunho e versões sem parecer."""
from datetime import date, timedelta

from app.extensions import db
from app.models import Ata, Marco
from tests.conftest import login, pdf_falso


def _marco(orientacao, titulo, *, dias=10, sinalizado=False, concluido=False):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo=titulo,
        data_prevista=date.today() + timedelta(days=dias),
        conclusao_sinalizada=sinalizado,
        status="concluido" if concluido else ("em_andamento" if sinalizado else "pendente"),
    )
    db.session.add(m)
    db.session.commit()
    return m


def test_entrega_sinalizada_aparece_para_orientador_e_orientando(
    client, orientacao, orientador, orientando
):
    _marco(orientacao, "Capítulo entregue", sinalizado=True)
    _marco(orientacao, "Ainda por fazer")

    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "aguardando sua confirmação" in pagina
    assert "Capítulo entregue" in pagina
    assert "Tarefas em aberto" in pagina
    assert "Ainda por fazer" in pagina

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "aguardando avaliação" in pagina
    assert "Capítulo entregue" in pagina


def test_marco_concluido_nao_e_pendencia(client, orientacao, orientador):
    _marco(orientacao, "Já concluído", concluido=True)
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "Já concluído" not in pagina
    assert "Nenhuma pendência em aberto" in pagina


def test_marco_atrasado_recebe_selo(client, orientacao, orientador):
    _marco(orientacao, "Vencido", dias=-5)
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "Vencido" in pagina
    assert "atrasado" in pagina


def test_ata_em_rascunho_aparece_e_some_ao_finalizar(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/atas/nova",
        data={"data_reuniao": "2026-07-20", "pauta": "Pauta pendente", "deliberacoes": "D"},
    )
    ata = Ata.query.one()
    assert "Atas em rascunho" in client.get("/dashboard").data.decode()

    client.post(f"/orientacoes/{orientacao.id}/atas/{ata.id}/finalizar")
    assert "Atas em rascunho" not in client.get("/dashboard").data.decode()


def test_versao_sem_parecer_aparece_e_some_apos_parecer(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={
            "titulo": "Projeto de pesquisa",
            "marco_id": 0,
            "arquivo": pdf_falso("projeto.pdf"),
            "comentario": "",
        },
        content_type="multipart/form-data",
    )
    from app.models import VersaoDocumento

    versao = VersaoDocumento.query.one()
    pagina = client.get("/dashboard").data.decode()
    assert "aguardando parecer" in pagina
    assert "Projeto de pesquisa" in pagina

    client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo",
        data={
            "tipo": "documento",
            "versao_documento_id": versao.id,
            "conteudo": "Adequado.",
            "resultado": "aprovado",
        },
    )
    assert "aguardando parecer" not in client.get("/dashboard").data.decode()


def test_apenas_a_versao_corrente_conta_como_pendencia(client, orientacao, orientador):
    """Versão superada por outra não é pendência, ainda que sem parecer."""
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={
            "titulo": "Projeto",
            "marco_id": 0,
            "arquivo": pdf_falso("v1.pdf"),
            "comentario": "",
        },
        content_type="multipart/form-data",
    )
    from app.models import Documento

    doc = Documento.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "comentario": ""},
        content_type="multipart/form-data",
    )

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # duas versões, uma única pendência (a corrente). O orientador vê "Emitir
    # parecer" no lugar de "Abrir documento" desde que o Painel passou a levar
    # direto ao parecer; o que se afere aqui é a contagem, não o rótulo.
    assert doc.versoes.count() == 2
    assert resp.data.decode().count("Emitir parecer") == 1


def test_pendencia_de_vinculo_alheio_nao_vaza(client, orientacao, orientador, intruso):
    _marco(orientacao, "Sigiloso", sinalizado=True)
    login(client, "intruso@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "Sigiloso" not in pagina


def test_barra_de_modulos_marca_a_aba_ativa(client, orientacao, orientando):
    """A barra de abas acompanha as telas do vínculo e destaca a atual."""
    login(client, "orientando@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/").data.decode()
    assert 'class="modulos-nav"' in pagina
    assert 'class="ativo">Cronograma' in pagina
    # e oferece o salto lateral aos demais módulos
    assert f"/orientacoes/{orientacao.id}/documentos/" in pagina
    assert f"/orientacoes/{orientacao.id}/atas" in pagina


def test_hub_do_orientando_leva_aos_modulos(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert 'class="hub-painel"' in pagina
    assert f"/orientacoes/{orientacao.id}/cronograma/" in pagina
    assert f"/orientacoes/{orientacao.id}/documentos/" in pagina
    assert f"/orientacoes/{orientacao.id}/pareceres" in pagina


def test_tabela_do_orientador_tem_atalhos_por_vinculo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert f"/orientacoes/{orientacao.id}/cronograma/" in pagina
    assert f"/orientacoes/{orientacao.id}/documentos/" in pagina
    assert f"/orientacoes/{orientacao.id}/atas" in pagina


def test_hub_do_painel_por_papel(client, admin, orientador, orientando):
    """A central de comando do Painel lista os atalhos do papel."""
    login(client, "admin@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert 'class="hub-painel"' in pagina
    for area in ("Modelos", "Backup", "Auditoria", "Usuários"):
        assert area in pagina

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "Reuniões" in pagina and "Orientandos" in pagina

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    # orientando não tem grade de acesso rápido
    assert 'class="hub-painel"' not in client.get("/dashboard").data.decode()


def test_logout_pelo_menu_de_conta_funciona(client, orientador):
    """O Sair migrou para o menu de conta, mas continua sendo um POST comum."""
    login(client, "orientador@teste.br")
    assert client.get("/dashboard").status_code == 200
    client.post("/auth/logout")
    # sem sessão, o dashboard redireciona ao login
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_atalhos_de_criacao_so_para_orientador(client, orientador, orientando, admin):
    """As ações de criação no Painel apontam para rotas exclusivas do orientador;
    orientando e administrador não devem vê-las (o admin receberia 403)."""
    login(client, "orientador@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "+ Nova tarefa" in pagina
    assert "+ Nova ata de reunião" in pagina

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "+ Nova tarefa" not in pagina

    client.post("/auth/logout")
    login(client, "admin@teste.br")
    pagina = client.get("/dashboard").data.decode()
    assert "+ Nova tarefa" not in pagina
