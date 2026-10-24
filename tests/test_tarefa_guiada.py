"""Tarefa que diz o que espera e guia o próximo passo: tipo de entrega, envio
pela tarefa como nova versão (não documento paralelo), sinalizar no mesmo ato,
e o cartão "Próximo passo" conforme quem vê e o estado."""
from datetime import UTC, date, datetime, timedelta

from app.extensions import db
from app.models import Documento, LogAuditoria, Marco, VersaoDocumento
from tests.conftest import login, pdf_falso


def _marco(orientacao, titulo="Revisão da metodologia", data_prevista=None, **kw):
    m = Marco(orientacao_id=orientacao.id, titulo=titulo,
              data_prevista=data_prevista or date.today() + timedelta(days=20), **kw)
    db.session.add(m)
    db.session.commit()
    return m


def _doc(orientacao, autor_id, titulo="Projeto", marco=None, quando=None):
    d = Documento(orientacao_id=orientacao.id, titulo=titulo, criado_por=autor_id,
                  marco_id=marco.id if marco else None)
    db.session.add(d)
    db.session.flush()
    v = VersaoDocumento(documento_id=d.id, numero_versao=1, nome_original="p.pdf",
                        nome_fisico=f"{d.id:032x}.pdf", tamanho_bytes=10,
                        mimetype="application/pdf", enviado_por=autor_id,
                        enviado_em=quando or datetime.now(UTC))
    db.session.add(v)
    db.session.commit()
    return d


def _pagina(client, orientacao, marco):
    return client.get(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}").data.decode()


def _enviar(client, orientacao, marco, **dados):
    base = {"arquivo": pdf_falso("texto.pdf"), "comentario": ""}
    base.update(dados)
    return client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/anexar",
                       data=base, content_type="multipart/form-data",
                       follow_redirects=True)


# --- criação: o que a tarefa espera ---------------------------------------


def _criar(client, orientacao, **extra):
    dados = {"titulo": "T", "tipo": "outro", "descricao": "",
             "data_prevista": "2026-12-01", "etapa": 0}
    dados.update(extra)
    return client.post(f"/orientacoes/{orientacao.id}/cronograma/novo", data=dados,
                       follow_redirects=True)


def test_revisao_exige_o_texto_base(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    resp = _criar(client, orientacao, entrega_esperada="revisao", documento_base_id=0)
    assert "Escolha o texto a revisar" in resp.data.decode()
    assert Marco.query.count() == 0


def test_revisao_grava_o_texto_base(client, orientacao, orientador):
    doc = _doc(orientacao, orientacao.orientando_id)
    login(client, "orientador@teste.br")
    _criar(client, orientacao, entrega_esperada="revisao", documento_base_id=doc.id)
    marco = Marco.query.one()
    assert marco.entrega_esperada == "revisao"
    assert marco.documento_base_id == doc.id
    assert marco.criado_em is not None


def test_texto_base_so_vale_na_revisao(client, orientacao, orientador):
    doc = _doc(orientacao, orientacao.orientando_id)
    login(client, "orientador@teste.br")
    _criar(client, orientacao, entrega_esperada="documento", documento_base_id=doc.id)
    marco = Marco.query.one()
    assert marco.entrega_esperada == "documento"
    assert marco.documento_base_id is None


def test_nao_especificar_grava_nulo(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    _criar(client, orientacao, entrega_esperada="")
    assert Marco.query.one().entrega_esperada is None


def test_tarefa_em_grupo_leva_a_entrega_esperada(client, orientacao, orientacao2, orientador):
    login(client, "orientador@teste.br")
    client.post("/reunioes/tarefas/nova", data={
        "titulo": "Ler", "tipo": "outro", "descricao": "", "data_prevista": "2026-12-01",
        "etapa": 0, "entrega_esperada": "ato",
        "orientacoes": [str(orientacao.id), str(orientacao2.id)],
    })
    assert {m.entrega_esperada for m in Marco.query.all()} == {"ato"}


# --- envio pela tarefa ---------------------------------------------------


def test_envio_como_nova_versao_nao_cria_documento(client, orientacao, orientando):
    marco = _marco(orientacao, entrega_esperada="documento")
    doc = _doc(orientacao, orientacao.orientando_id, marco=marco)
    login(client, "orientando@teste.br")
    resp = _enviar(client, orientacao, marco, destino=str(doc.id))
    assert "Versão 2" in resp.data.decode()
    assert Documento.query.count() == 1
    assert doc.versao_atual.numero_versao == 2


def test_documento_novo_exige_titulo(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    resp = _enviar(client, orientacao, marco, destino="novo", titulo="")
    assert "Informe o título" in resp.data.decode()
    assert Documento.query.count() == 0


def test_documento_novo_fica_ligado_a_tarefa(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    _enviar(client, orientacao, marco, destino="novo", titulo="Capítulo 2")
    doc = Documento.query.one()
    assert doc.marco_id == marco.id and doc.titulo == "Capítulo 2"


def test_destino_fora_da_tarefa_e_recusado(client, orientacao, orientando):
    marco = _marco(orientacao)
    alheio = _doc(orientacao, orientacao.orientando_id, titulo="De outra tarefa",
                  marco=_marco(orientacao))
    login(client, "orientando@teste.br")
    resp = _enviar(client, orientacao, marco, destino=str(alheio.id))
    assert "Escolha uma das opções" in resp.data.decode()
    assert alheio.versoes.count() == 1


def test_enviar_e_avisar_o_orientador_no_mesmo_ato(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    resp = _enviar(client, orientacao, marco, destino="novo", titulo="Cap", sinalizar="y")
    assert "orientador foi avisado" in resp.data.decode()
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is True
    assert LogAuditoria.query.filter_by(acao="sinalizacao_conclusao_marco").count() == 1


def test_sem_marcar_o_aviso_nao_sinaliza(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    _enviar(client, orientacao, marco, destino="novo", titulo="Cap")
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is False


def test_tarefa_concluida_nao_recebe_envio(client, orientacao, orientando):
    marco = _marco(orientacao, status="concluido")
    login(client, "orientando@teste.br")
    resp = _enviar(client, orientacao, marco, destino="novo", titulo="Cap")
    assert "concluída" in resp.data.decode()
    assert Documento.query.count() == 0


# --- revisão de um texto existente ---------------------------------------


def test_revisao_envia_nova_versao_do_texto_base(client, orientacao, orientando):
    antigo = datetime.now(UTC) - timedelta(days=30)
    base = _doc(orientacao, orientacao.orientando_id, titulo="Projeto", quando=antigo,
                marco=_marco(orientacao))
    marco = _marco(orientacao, entrega_esperada="revisao", documento_base_id=base.id)
    # a versão antiga do texto-base não faz a revisão nascer "entregue"
    assert marco.tem_entrega_do_orientando is False
    login(client, "orientando@teste.br")
    pagina = _pagina(client, orientacao, marco)
    assert "Revisar e enviar" in pagina
    # já vem apontado o texto-base
    import re
    padrao = r'<input[^>]*name="destino"[^>]*value="' + str(base.id) + r'"[^>]*>'
    marcado = re.search(padrao, pagina)
    assert marcado and "checked" in marcado.group(0)
    _enviar(client, orientacao, marco, destino=str(base.id))
    assert base.versao_atual.numero_versao == 2
    db.session.expire(marco)
    assert marco.tem_entrega_do_orientando is True
    assert Documento.query.count() == 1  # revisão = nova versão, não documento paralelo


def test_texto_base_unico_nao_pode_ser_excluido(client, orientacao, orientador):
    base = _doc(orientacao, orientacao.orientador_id, titulo="Projeto")
    _marco(orientacao, entrega_esperada="revisao", documento_base_id=base.id)
    login(client, "orientador@teste.br")
    v = base.versao_atual
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{base.id}/versoes/{v.id}/excluir",
        follow_redirects=True)
    assert "texto a revisar" in resp.data.decode()
    assert Documento.query.count() == 1


# --- o cartão "Próximo passo" --------------------------------------------


def test_proximo_passo_da_orientanda_a_fazer(client, orientacao, orientando):
    marco = _marco(orientacao, entrega_esperada="documento")
    login(client, "orientando@teste.br")
    pagina = _pagina(client, orientacao, marco)
    assert "Próximo passo — Entregar" in pagina
    assert "avisar o orientador" in pagina
    assert "O que esta tarefa espera:" in pagina


def test_proximo_passo_tarefa_sem_arquivo(client, orientacao, orientando):
    marco = _marco(orientacao, entrega_esperada="ato")
    login(client, "orientando@teste.br")
    assert "Próximo passo — Concluir e avisar" in _pagina(client, orientacao, marco)


def test_proximo_passo_devolvida_traz_a_nota(client, orientacao, orientando):
    marco = _marco(orientacao, devolvido_em=datetime.now(UTC), status="em_andamento",
                   nota_devolucao="Reveja a seção 3")
    _doc(orientacao, orientacao.orientando_id, marco=marco)
    login(client, "orientando@teste.br")
    pagina = _pagina(client, orientacao, marco)
    assert "Próximo passo — Corrigir e reenviar" in pagina
    assert "Reveja a seção 3" in pagina


def test_proximo_passo_sinalizada(client, orientacao, orientando, orientador):
    marco = _marco(orientacao, conclusao_sinalizada=True, status="em_andamento")
    _doc(orientacao, orientacao.orientando_id, marco=marco)
    login(client, "orientando@teste.br")
    assert "Aguardar o orientador" in _pagina(client, orientacao, marco)
    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    pagina = _pagina(client, orientacao, marco)
    assert "Próximo passo — Conferir a entrega" in pagina
    assert "Confirmar conclusão" in pagina


def test_concluida_sem_formularios(client, orientacao, orientando):
    marco = _marco(orientacao, status="concluido", data_conclusao=date.today())
    login(client, "orientando@teste.br")
    pagina = _pagina(client, orientacao, marco)
    assert "Tarefa concluída" in pagina
    assert "/anexar" not in pagina


def test_texto_base_mostra_a_versao_atual(client, orientacao, orientador):
    doc = _doc(orientacao, orientacao.orientando_id, titulo="Defesa")
    login(client, "orientador@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/cronograma/novo").data.decode()
    assert "Defesa (hoje na v1)" in pagina
    assert doc.id


def test_emitir_parecer_so_na_entrega_da_orientanda(client, orientacao, orientador):
    meu = _doc(orientacao, orientacao.orientador_id, titulo="Anotado por mim")
    dela = _doc(orientacao, orientacao.orientando_id, titulo="Texto dela")
    login(client, "orientador@teste.br")
    pagina_meu = client.get(f"/orientacoes/{orientacao.id}/documentos/{meu.id}").data.decode()
    pagina_dela = client.get(f"/orientacoes/{orientacao.id}/documentos/{dela.id}").data.decode()
    assert "Emitir parecer" not in pagina_meu
    assert "Emitir parecer" in pagina_dela
