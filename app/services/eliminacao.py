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

A raspagem do conteúdo congelado é guiada pelos **papéis e ids** do registro
(quem é o orientador da ata, que participação pertence a que vínculo), não pelo
nome atual do titular — assim ela alcança registros congelados antes de uma
renomeação da conta. Limite declarado: e-mails ANTIGOS digitados livremente em
tentativas de login não são rastreáveis depois que a conta muda de e-mail; os
lançamentos de gestão sobre a conta do titular têm os dados descartados por
inteiro justamente porque carregam nome/e-mail de épocas anteriores.

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

from sqlalchemy import delete, update

from app.extensions import db
from app.models import (
    Ata,
    ConfiguracaoEmail,
    Documento,
    EventoVinculo,
    LogAuditoria,
    ModeloDocumento,
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
from app.services.usuarios import GestaoUsuarioInvalida, validar_remocao

REMOVIDO = "[removido]"
_SENTINELA_EMAIL = "sentinela+removido@lgpd.invalid"


# ---------------------------------------------------------------------------
# Conta-sentinela: alvo neutro para os FKs NOT NULL que devem sobreviver


def eh_sentinela(usuario: Usuario) -> bool:
    """A conta-sentinela é infraestrutura, não um usuário: as rotas de gestão a
    recusam (editar, senha temporária, excluir, eliminar) para que ela nunca
    autentique nem seja apagada por engano — apagá-la órfã todos os registros já
    anonimizados que apontam para ela."""
    return usuario.email == _SENTINELA_EMAIL


def _conta_removido() -> Usuario:
    """Conta reservada "Usuário removido (LGPD)", criada sob demanda. Nunca
    autentica (inativa; `load_user` recusa conta inativa; as rotas de gestão a
    recusam via `eh_sentinela`) e não carrega dado pessoal — existe só para os
    FKs NOT NULL de registros preservados apontarem para algum lugar sem
    migração de esquema."""
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


def _anonimizar_congelado(registro, campos=(), orientacao_ids=frozenset()) -> None:
    """Raspa dado pessoal do `conteudo_congelado` de uma ata ou parecer, guiada
    pela estrutura, não pelo nome atual do titular: `campos` diz que papéis do
    registro (orientador, redator, emissor) eram dele, e `orientacao_ids` marca
    as participações (por id do vínculo, presente no congelado) cujos orientando
    e projeto devem sumir. Imune a renomeações da conta. Muda o hash, de
    propósito (ver docstring do módulo). Nada faz se ainda não foi congelado."""
    if not registro.conteudo_congelado:
        return
    dados = json.loads(registro.conteudo_congelado)
    for campo in campos:
        if campo in dados:
            dados[campo] = REMOVIDO
    for participacao in dados.get("participacoes", []):
        if participacao.get("orientacao_id") in orientacao_ids:
            participacao["orientando"] = REMOVIDO
            participacao["projeto"] = REMOVIDO
    registro.conteudo_congelado = _canonico(dados)


# ---------------------------------------------------------------------------
# Apagar os vínculos do titular como orientando (dados privados)


def _apagar_vinculo_do_titular(
    orientacao: Orientacao, ids_titular: frozenset, arquivos: list
) -> None:
    """Apaga uma orientação em que o titular é o orientando, com toda a subárvore
    privada, na ordem que as chaves estrangeiras exigem. Ata com participação de
    OUTRO orientando sobrevive: some só a participação do titular, e os dados
    dele são raspados do congelado. `ids_titular` traz TODOS os vínculos do
    titular, para que uma ata de grupo que só envolva vínculos dele (ex.: IC
    encerrada + mestrado) não escape como se fosse de terceiros."""
    participacoes = AtaParticipacao.query.filter_by(orientacao_id=orientacao.id).all()
    for participacao in participacoes:
        ata = participacao.ata
        if any(p.orientacao_id not in ids_titular for p in ata.participacoes):
            # há terceiros na ata: preserva para eles, anonimiza o titular
            _anonimizar_congelado(ata, orientacao_ids=ids_titular)
            db.session.delete(participacao)
        else:
            # ata só do titular (individual ou de grupo entre vínculos dele):
            # some inteira; os cascades removem participações e linhas ata_marco
            for reagendamento in list(ata.reagendamentos):
                db.session.delete(reagendamento)
            db.session.delete(ata)

    # pareceres (referenciam versões) antes das versões
    for parecer in list(orientacao.pareceres):
        db.session.delete(parecer)
    # documentos e suas versões (coleta os arquivos físicos)
    for documento in list(orientacao.documentos):
        for versao in list(documento.versoes):
            arquivos.append(versao.nome_fisico)
            db.session.delete(versao)
        db.session.delete(documento)
    # marcos: limpa antes a associação com atas de grupo que sobrevivem
    for marco in list(orientacao.marcos):
        db.session.execute(delete(ata_marco).where(ata_marco.c.marco_id == marco.id))
        db.session.delete(marco)
    for evento in list(orientacao.eventos):
        db.session.delete(evento)
    db.session.delete(orientacao)  # cascade remove a equipe de coorientadores


# ---------------------------------------------------------------------------
# Re-atribuição e anonimização dos registros que sobrevivem


def _reatribuir_autorias(usuario: Usuario, sentinela: Usuario) -> int:
    """Re-aponta à sentinela os FKs de autoria do titular em registros que
    sobrevivem (de terceiros), e raspa a identidade dele do congelado de
    atas/pareceres. Devolve quantos registros foram tocados."""
    tocados = 0

    # atas e pareceres precisam do laço (raspagem do congelado, papel a papel)
    for ata in Ata.query.filter(
        (Ata.orientador_id == usuario.id)
        | (Ata.redigida_por == usuario.id)
        | (Ata.cancelada_por == usuario.id)
    ):
        campos = []
        if ata.orientador_id == usuario.id:
            ata.orientador_id = sentinela.id
            campos.append("orientador")
        if ata.redigida_por == usuario.id:
            ata.redigida_por = sentinela.id
            campos.append("redator")
        if ata.cancelada_por == usuario.id:
            ata.cancelada_por = sentinela.id
        _anonimizar_congelado(ata, campos=campos)
        tocados += 1
    for parecer in Parecer.query.filter_by(emitido_por=usuario.id):
        parecer.emitido_por = sentinela.id
        _anonimizar_congelado(parecer, campos=("emissor",))
        tocados += 1

    # colunas puramente FK: UPDATE em massa, sem carregar objeto a objeto
    for modelo, coluna in (
        (Orientacao, Orientacao.orientador_id),  # vínculos não-ativos que ele
        (Documento, Documento.criado_por),  # orientava (ativos são barrados)
        (VersaoDocumento, VersaoDocumento.enviado_por),
        (AtaParticipacao, AtaParticipacao.presenca_registrada_por),
        (Reagendamento, Reagendamento.registrado_por),
        (EventoVinculo, EventoVinculo.registrado_por),
    ):
        tocados += db.session.execute(
            update(modelo).where(coluna == usuario.id).values({coluna: sentinela.id})
        ).rowcount
    # coorientação do titular em vínculos que sobrevivem: some a linha
    tocados += db.session.execute(
        delete(OrientacaoOrientador).where(
            OrientacaoOrientador.usuario_id == usuario.id
        )
    ).rowcount
    # campos anuláveis: some a identidade sem sentinela
    for modelo, coluna in (
        (Usuario, Usuario.criado_por),
        (ModeloDocumento, ModeloDocumento.enviado_por),
        (ConfiguracaoEmail, ConfiguracaoEmail.atualizado_por),
    ):
        db.session.execute(
            update(modelo).where(coluna == usuario.id).values({coluna: None})
        )
    return tocados


def _raspar_valor(valor, email: str):
    """Troca por [removido] todo valor string IGUAL ao e-mail (sem diferenciar
    caixa), percorrendo a estrutura do JSON. Igualdade de valor, não substring:
    o e-mail de um terceiro que contenha o do titular (ana@… em mariana@…) fica
    intacto."""
    if isinstance(valor, str):
        return REMOVIDO if valor.lower() == email else valor
    if isinstance(valor, dict):
        return {chave: _raspar_valor(v, email) for chave, v in valor.items()}
    if isinstance(valor, list):
        return [_raspar_valor(v, email) for v in valor]
    return valor


def _anonimizar_trilha(usuario: Usuario) -> None:
    """Preserva a trilha append-only sem identificar o titular: autor nulo,
    e-mail raspado dos dados de qualquer lançamento, e dados descartados dos
    lançamentos de gestão SOBRE a conta dele (que carregam nome/e-mail de épocas
    anteriores, irrecuperáveis por comparação com os valores atuais)."""
    for log in LogAuditoria.query.filter_by(usuario_id=usuario.id):
        log.usuario_id = None
    for log in LogAuditoria.query.filter_by(
        entidade="usuario", entidade_id=usuario.id
    ):
        log.dados_json = None
    email = (usuario.email or "").lower()
    if email:
        # o LIKE (case-insensitive no SQLite) só pré-filtra; a troca real é por
        # igualdade de valor no JSON, campo a campo
        for log in LogAuditoria.query.filter(
            LogAuditoria.dados_json.like(f"%{email}%")
        ):
            dados = json.loads(log.dados_json)
            raspado = _raspar_valor(dados, email)
            if raspado != dados:
                log.dados_json = json.dumps(raspado, ensure_ascii=False)


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
    if eh_sentinela(usuario):
        auditoria.registrar("eliminacao_sentinela_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(
            "A conta-sentinela de remoção é infraestrutura do sistema e não "
            "pode ser eliminada: os registros já anonimizados apontam para ela."
        )
    validar_remocao(usuario, executor, ato="eliminacao", verbo="eliminar")
    if _orienta_vinculo_ativo(usuario):
        auditoria.registrar("eliminacao_recusada", "usuario", usuario.id,
                            {"motivo": "orienta vínculo ativo"})
        raise GestaoUsuarioInvalida(
            "A conta orienta vínculo(s) ativo(s). Encerre ou reatribua esses "
            "vínculos antes de eliminar os dados do titular, para não deixar "
            "orientando ativo sem orientador."
        )

    papel = usuario.papel
    sentinela = _conta_removido()
    arquivos: list[str] = []

    # 1. apaga os vínculos em que o titular é o orientando (dados privados)
    vinculos = list(Orientacao.query.filter_by(orientando_id=usuario.id))
    ids_titular = frozenset(o.id for o in vinculos)
    for orientacao in vinculos:
        _apagar_vinculo_do_titular(orientacao, ids_titular, arquivos)

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
