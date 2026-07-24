"""Eliminação de dados de um usuário (LGPD, art. 18).

Vai além da exclusão comum (services/usuarios.py), que recusa contas com
histórico: aqui a conta é apagada mesmo em uso. A estratégia é **anonimizar o que
precisa sobreviver e apagar o resto**:

- Apaga os dados privados do titular (a conta, e o que ele acumulou como
  orientando: vínculo, marcos, documentos e seus arquivos, atas individuais,
  pareceres).
- Preserva de forma ANÔNIMA o que pertence a terceiros ou à integridade do
  sistema: a trilha de auditoria (append-only) fica com o autor nulo e o e-mail
  raspado; registros que o titular autorou em dados de outros (atas de grupo,
  pareceres sobre outros orientandos, presenças que registrou) são re-atribuídos
  a uma conta-sentinela e têm o nome do titular trocado por "[removido]".

**Consequência assumida.** Trocar o nome no `conteudo_congelado` de uma ata ou
parecer altera o SHA-256 daquele registro: um PDF assinado antes da eliminação
passará a divergir na rota de verificação. É o preço de eliminar dado pessoal de
um registro imutável, e está declarado na tela de confirmação.

Não faz commit: a transação é do chamador, para que a eliminação seja atômica. A
remoção dos arquivos físicos fica a cargo do chamador, **após** o commit (o
serviço devolve a lista), para não apagar arquivo de um registro que a falha do
commit faria voltar.
"""
import json

from sqlalchemy import delete

from app.extensions import db
from app.models import (
    Ata,
    Documento,
    EventoVinculo,
    LogAuditoria,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Reagendamento,
    Usuario,
    VersaoDocumento,
)
from app.models.ata import AtaParticipacao, ata_marco
from app.services import auditoria, senhas
from app.services.exportacao import _canonico
from app.services.usuarios import GestaoUsuarioInvalida

REMOVIDO = "[removido]"
_SENTINELA_EMAIL = "sentinela+removido@lgpd.invalid"


# ---------------------------------------------------------------------------
# Conta-sentinela: alvo neutro para os FKs NOT NULL que devem sobreviver


def _conta_removido() -> Usuario:
    """Conta reservada "Usuário removido (LGPD)", criada sob demanda. Nunca
    autentica (inativa; `load_user` recusa conta inativa) e não carrega dado
    pessoal — existe só para os FKs NOT NULL de registros preservados apontarem
    para algum lugar sem migração de esquema."""
    sentinela = Usuario.query.filter_by(email=_SENTINELA_EMAIL).first()
    if sentinela is None:
        sentinela = Usuario(
            nome="Usuário removido (LGPD)",
            email=_SENTINELA_EMAIL,
            papel="orientador",
            ativo=False,
        )
        sentinela.set_senha(senhas.gerar())  # senha inutilizável; a conta é inativa
        db.session.add(sentinela)
        db.session.flush()
    return sentinela


# ---------------------------------------------------------------------------
# Anonimização do conteúdo congelado (assinado)


def _anonimizar_congelado(registro, nome: str) -> None:
    """Troca `nome` por [removido] nos campos de nome do `conteudo_congelado` de
    uma ata ou parecer. Casa por igualdade de nome — homônimo exato no mesmo
    registro é o limite conhecido. Muda o hash, de propósito (ver docstring do
    módulo). Nada faz se o registro ainda não foi congelado."""
    if not registro.conteudo_congelado:
        return
    dados = json.loads(registro.conteudo_congelado)
    for campo in ("orientador", "redator", "emissor", "orientando"):
        if dados.get(campo) == nome:
            dados[campo] = REMOVIDO
    for participacao in dados.get("participacoes", []):
        if participacao.get("orientando") == nome:
            participacao["orientando"] = REMOVIDO
    registro.conteudo_congelado = _canonico(dados)


# ---------------------------------------------------------------------------
# Apagar o vínculo do titular como orientando (dados privados)


def _apagar_vinculo_do_titular(orientacao: Orientacao, nome: str, arquivos: list) -> None:
    """Apaga uma orientação em que o titular é o orientando, com toda a subárvore
    privada, na ordem que as chaves estrangeiras exigem. Ata de grupo (com outros
    participantes) sobrevive: some só a participação do titular, e o nome dele é
    raspado do congelado."""
    # atas ligadas ao vínculo, via participação
    participacoes = AtaParticipacao.query.filter_by(orientacao_id=orientacao.id).all()
    for participacao in participacoes:
        ata = participacao.ata
        outros = [p for p in ata.participacoes if p.orientacao_id != orientacao.id]
        if outros:
            # ata de grupo: preserva para os demais, anonimiza o titular
            _anonimizar_congelado(ata, nome)
            db.session.delete(participacao)
        else:
            # ata individual do titular: some inteira
            db.session.execute(delete(ata_marco).where(ata_marco.c.ata_id == ata.id))
            for reagendamento in list(ata.reagendamentos):
                db.session.delete(reagendamento)
            db.session.delete(ata)  # cascade remove a participação restante

    # pareceres (referenciam versões) antes das versões
    for parecer in list(orientacao.pareceres):
        db.session.delete(parecer)
    # documentos e suas versões (coleta os arquivos físicos)
    for documento in list(orientacao.documentos):
        for versao in list(documento.versoes):
            arquivos.append(versao.nome_fisico)
            db.session.delete(versao)
        db.session.delete(documento)
    # marcos (limpa a associação ata_marco antes)
    for marco in list(orientacao.marcos):
        db.session.execute(delete(ata_marco).where(ata_marco.c.marco_id == marco.id))
        db.session.delete(marco)
    for evento in list(orientacao.eventos):
        db.session.delete(evento)
    for membro in list(orientacao.equipe):
        db.session.delete(membro)
    db.session.delete(orientacao)


# ---------------------------------------------------------------------------
# Re-atribuição e anonimização dos registros que sobrevivem


def _reatribuir_autorias(usuario: Usuario, sentinela: Usuario) -> int:
    """Re-aponta à sentinela os FKs de autoria do titular em registros que
    sobrevivem (de terceiros), e raspa o nome dele do congelado de atas/pareceres.
    Devolve quantos registros foram tocados."""
    nome = usuario.nome
    tocados = 0

    # vínculos que o titular ORIENTA e que sobrevivem (não-ativos; os ativos são
    # barrados antes): re-aponta à sentinela para não órfa-los nem violar o NOT
    # NULL de orientador_id ao apagar a conta.
    for o in Orientacao.query.filter_by(orientador_id=usuario.id):
        o.orientador_id = sentinela.id
        tocados += 1
    for doc in Documento.query.filter_by(criado_por=usuario.id):
        doc.criado_por = sentinela.id
        tocados += 1
    for versao in VersaoDocumento.query.filter_by(enviado_por=usuario.id):
        versao.enviado_por = sentinela.id
        tocados += 1
    for ata in Ata.query.filter(
        (Ata.orientador_id == usuario.id)
        | (Ata.redigida_por == usuario.id)
        | (Ata.cancelada_por == usuario.id)
    ):
        if ata.orientador_id == usuario.id:
            ata.orientador_id = sentinela.id
        if ata.redigida_por == usuario.id:
            ata.redigida_por = sentinela.id
        if ata.cancelada_por == usuario.id:
            ata.cancelada_por = sentinela.id
        _anonimizar_congelado(ata, nome)
        tocados += 1
    for parecer in Parecer.query.filter_by(emitido_por=usuario.id):
        parecer.emitido_por = sentinela.id
        _anonimizar_congelado(parecer, nome)
        tocados += 1
    for p in AtaParticipacao.query.filter_by(presenca_registrada_por=usuario.id):
        p.presenca_registrada_por = sentinela.id
        tocados += 1
    for r in Reagendamento.query.filter_by(registrado_por=usuario.id):
        r.registrado_por = sentinela.id
        tocados += 1
    for e in EventoVinculo.query.filter_by(registrado_por=usuario.id):
        e.registrado_por = sentinela.id
        tocados += 1
    # coorientação do titular em vínculos que sobrevivem: some a linha
    for membro in OrientacaoOrientador.query.filter_by(usuario_id=usuario.id):
        db.session.delete(membro)
        tocados += 1
    # campos anuláveis: some a identidade sem sentinela
    for conta in Usuario.query.filter_by(criado_por=usuario.id):
        conta.criado_por = None
    return tocados


def _anonimizar_trilha(usuario: Usuario) -> None:
    """Preserva a trilha append-only sem identificar o titular: autor nulo e
    e-mail raspado dos dados de qualquer lançamento."""
    for log in LogAuditoria.query.filter_by(usuario_id=usuario.id):
        log.usuario_id = None
    email = usuario.email
    if email:
        for log in LogAuditoria.query.filter(
            LogAuditoria.dados_json.like(f"%{email}%")
        ):
            log.dados_json = log.dados_json.replace(email, REMOVIDO)


# ---------------------------------------------------------------------------
# Orquestração


def _orienta_vinculo_ativo(usuario: Usuario) -> bool:
    como_principal = Orientacao.query.filter_by(
        orientador_id=usuario.id, status="ativa"
    )
    como_coorientador = (
        OrientacaoOrientador.query.join(Orientacao)
        .filter(
            OrientacaoOrientador.usuario_id == usuario.id,
            Orientacao.status == "ativa",
        )
    )
    return bool(
        db.session.query(como_principal.exists()).scalar()
        or db.session.query(como_coorientador.exists()).scalar()
    )


def eliminar_usuario(usuario: Usuario, executor: Usuario) -> dict:
    """Elimina os dados do titular. Não faz commit; devolve um resumo, incluindo
    `arquivos` (nomes físicos a remover do disco pelo chamador, após o commit)."""
    if usuario.id == executor.id:
        auditoria.registrar("autoeliminacao_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida("Não é possível eliminar a própria conta.")
    if (
        usuario.papel == "admin"
        and usuario.ativo
        and Usuario.query.filter_by(papel="admin", ativo=True).count() <= 1
    ):
        auditoria.registrar("eliminacao_ultimo_admin_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(
            "O sistema deve manter ao menos um administrador ativo."
        )
    if _orienta_vinculo_ativo(usuario):
        auditoria.registrar("eliminacao_recusada", "usuario", usuario.id,
                            {"motivo": "orienta vínculo ativo"})
        raise GestaoUsuarioInvalida(
            "A conta orienta vínculo(s) ativo(s). Encerre ou reatribua esses "
            "vínculos antes de eliminar os dados do titular, para não deixar "
            "orientando ativo sem orientador."
        )

    nome = usuario.nome
    papel = usuario.papel
    sentinela = _conta_removido()
    arquivos: list[str] = []

    # 1. apaga os vínculos em que o titular é o orientando (dados privados)
    vinculos = list(Orientacao.query.filter_by(orientando_id=usuario.id))
    for orientacao in vinculos:
        _apagar_vinculo_do_titular(orientacao, nome, arquivos)

    # 2. preserva anonimizando o que ele autorou em dados de terceiros
    reatribuidos = _reatribuir_autorias(usuario, sentinela)

    # 3. anonimiza a trilha de auditoria
    _anonimizar_trilha(usuario)

    # 4. registra o ato (sem dado pessoal) e apaga a conta
    auditoria.registrar(
        "eliminacao_lgpd", "usuario", usuario.id,
        {"papel": papel, "executor": executor.id},
    )
    db.session.delete(usuario)

    return {
        "vinculos_apagados": len(vinculos),
        "registros_reatribuidos": reatribuidos,
        "arquivos": arquivos,
    }
