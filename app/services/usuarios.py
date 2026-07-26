"""Gestão de contas: criação e exclusão com salvaguardas de integridade.

Exclusão física é admitida apenas para contas sem qualquer vestígio no sistema
(vínculos, conteúdo ou ações auditadas); do contrário, a via correta é a
desativação, que preserva o histórico."""
from app.extensions import db
from app.models import (
    Ata,
    Documento,
    LogAuditoria,
    Orientacao,
    OrientacaoOrientador,
    Parecer,
    Reagendamento,
    Usuario,
    VersaoDocumento,
)
from app.models.ata import AtaParticipacao
from app.services import auditoria, senhas


class GestaoUsuarioInvalida(Exception):
    pass


def normalizar_email(email: str) -> str:
    """Forma canônica sob a qual todo e-mail é gravado E consultado
    (minúsculas, sem espaços). Ponto único: cada cópia inline desta regra é um
    lugar onde ela pode faltar — e quando falta, nasce conta que nunca
    autentica, porque login e recuperação consultam sempre a forma canônica."""
    return (email or "").strip().lower()


def orienta_vinculo_ativo(usuario: Usuario) -> bool:
    """A conta orienta algum vínculo ativo, como principal ou coorientador.
    Guarda comum à eliminação LGPD e à edição de conta: enquanto for verdade,
    a conta não muda de papel, não é desativada nem eliminada — orientando
    ativo não fica sem gestor."""
    como_principal = Orientacao.query.filter_by(
        orientador_id=usuario.id, status="ativa"
    )
    como_coorientador = OrientacaoOrientador.query.join(Orientacao).filter(
        OrientacaoOrientador.usuario_id == usuario.id,
        Orientacao.status == "ativa",
    )
    return bool(
        db.session.query(como_principal.exists()).scalar()
        or db.session.query(como_coorientador.exists()).scalar()
    )


def vinculo_sem_registros(orientacao: Orientacao) -> bool:
    """Vínculo que nada acumulou: nenhum marco, documento, ata, parecer, evento
    ou coorientador. Só um vínculo assim pode ser descartado com a conta."""
    return not (
        orientacao.marcos.first()
        or orientacao.documentos.first()
        or orientacao.atas.first()
        or orientacao.pareceres.first()
        or orientacao.eventos
        or orientacao.equipe
    )


def vinculos_descartaveis(usuario: Usuario) -> list[int]:
    """Vínculos em que a conta figura como orientando e que ainda não
    acumularam registro. Como o vínculo nasce junto com a conta (o orientador
    que cria o orientando torna-se seu orientador), exigir ausência de vínculo
    para excluir tornaria a exclusão impossível; o que se exige é ausência de
    histórico."""
    return [
        o.id
        for o in Orientacao.query.filter_by(orientando_id=usuario.id)
        if vinculo_sem_registros(o)
    ]


def motivo_bloqueio_exclusao(
    usuario: Usuario, descartaveis: list[int] | None = None
) -> str | None:
    """Retorna o motivo que impede a exclusão física, ou None se a conta é
    limpa. `descartaveis` lista vínculos vazios que serão removidos junto e
    que, portanto, não contam como vestígio."""
    descartaveis = descartaveis or []
    consulta_vinculos = Orientacao.query.filter(
        (Orientacao.orientador_id == usuario.id)
        | (Orientacao.orientando_id == usuario.id)
    )
    if descartaveis:
        consulta_vinculos = consulta_vinculos.filter(
            Orientacao.id.notin_(descartaveis)
        )
    verificacoes = [
        (consulta_vinculos, "participa de vínculo de orientação"),
        (LogAuditoria.query.filter_by(usuario_id=usuario.id), "possui ações auditadas"),
        (Documento.query.filter_by(criado_por=usuario.id), "criou documentos"),
        (VersaoDocumento.query.filter_by(enviado_por=usuario.id), "enviou versões"),
        (
            Ata.query.filter(
                (Ata.redigida_por == usuario.id) | (Ata.orientador_id == usuario.id)
            ),
            "figura em atas",
        ),
        (Parecer.query.filter_by(emitido_por=usuario.id), "emitiu pareceres"),
        (
            AtaParticipacao.query.filter_by(presenca_registrada_por=usuario.id),
            "registrou presenças",
        ),
        (
            Reagendamento.query.filter_by(registrado_por=usuario.id),
            "registrou reagendamentos",
        ),
        (
            OrientacaoOrientador.query.filter_by(usuario_id=usuario.id),
            "integra equipe de orientação (coorientação)",
        ),
        (Usuario.query.filter_by(criado_por=usuario.id), "criou outras contas"),
    ]
    for consulta, motivo in verificacoes:
        if db.session.query(consulta.exists()).scalar():
            return motivo
    return None


def criar_usuario(
    *, nome, email, papel, autor, ativo=True, telefone=None
) -> tuple[Usuario, str]:
    """Cria a conta com senha gerada e devolve `(usuario, senha)`.

    A senha nunca é escolhida por quem cria a conta: senha alheia digitada por
    terceiro tende a ser fraca, repetida entre contas e conhecida por quem a
    digitou por tempo indeterminado. Gerada e marcada como provisória, ela vale
    até o titular trocá-la, e não abre nada além da tela de troca.

    A senha é devolvida, e não guardada: quem chama a envia ao titular e, se o
    e-mail falhar, a exibe uma vez na tela. Depois disto só existe o hash."""
    if Usuario.query.filter_by(email=email).first():
        raise GestaoUsuarioInvalida("E-mail já cadastrado.")
    senha = senhas.gerar()
    usuario = Usuario(
        nome=nome, email=email, papel=papel, ativo=ativo, criado_por=autor.id,
        telefone=telefone or None,
    )
    usuario.set_senha(senha, provisoria=True)
    db.session.add(usuario)
    db.session.flush()
    auditoria.registrar(
        "criacao_usuario", "usuario", usuario.id, {"email": email, "papel": papel}
    )
    return usuario, senha


def repor_senha(usuario: Usuario, executor: Usuario) -> str:
    """Gera nova senha provisória e devolve-a para envio ao titular.

    Recusa a própria conta: além de o administrador ter a tela de troca à mão, a
    reposição invalida a sessão corrente (o hash entra em `get_id`), e ele se
    deslogaria sem entender por quê.

    Recusa conta desativada: a senha chegaria ao titular sem servir para nada,
    pois conta inativa não autentica. Reative primeiro."""
    if usuario.id == executor.id:
        raise GestaoUsuarioInvalida(
            "Para trocar a própria senha, use o menu Senha."
        )
    if not usuario.ativo:
        raise GestaoUsuarioInvalida(
            "A conta está desativada e não autentica. Reative-a antes de repor "
            "a senha."
        )
    senha = senhas.gerar()
    usuario.set_senha(senha, provisoria=True)
    # a senha jamais entra na trilha: a auditoria é legível pelo administrador,
    # e marcá-la como provisória serve justamente para encurtar quem a conhece
    auditoria.registrar(
        "reposicao_senha", "usuario", usuario.id, {"email": usuario.email}
    )
    return senha


def criar_orientando_com_vinculo(
    *,
    nome,
    email,
    orientador: Usuario,
    modalidade,
    titulo_projeto,
    data_inicio,
    data_fim_prevista=None,
    telefone=None,
) -> tuple[Orientacao, str]:
    """Cria a conta do orientando e, no mesmo ato, o vínculo de orientação com
    quem a criou. Dispensa a intermediação do administrador.

    Devolve `(orientacao, senha)`: a senha provisória segue para o e-mail de
    boas-vindas, pelo mesmo caminho da criação feita pelo administrador."""
    usuario, senha = criar_usuario(
        nome=nome,
        email=email,
        papel="orientando",
        autor=orientador,
        telefone=telefone,
    )
    orientacao = Orientacao(
        orientador_id=orientador.id,
        orientando_id=usuario.id,
        modalidade=modalidade,
        titulo_projeto=titulo_projeto,
        data_inicio=data_inicio,
        data_fim_prevista=data_fim_prevista,
    )
    db.session.add(orientacao)
    db.session.flush()
    auditoria.registrar(
        "criacao_orientacao",
        "orientacao",
        orientacao.id,
        {
            "orientador_id": orientador.id,
            "orientando_id": usuario.id,
            "modalidade": modalidade,
            "origem": "criacao_de_orientando",
        },
    )
    return orientacao, senha


def validar_remocao(
    usuario: Usuario, executor: Usuario, ato: str, verbo: str
) -> None:
    """Guardas comuns a qualquer remoção de conta (exclusão comum e eliminação
    LGPD): nem a própria conta do executor, nem o último administrador ativo.
    `ato`/`verbo` parametrizam a trilha e a mensagem ("exclusao"/"excluir",
    "eliminacao"/"eliminar")."""
    if usuario.id == executor.id:
        auditoria.registrar(f"auto{ato}_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(f"Não é possível {verbo} a própria conta.")
    if (
        usuario.papel == "admin"
        and usuario.ativo
        and Usuario.query.filter_by(papel="admin", ativo=True).count() <= 1
    ):
        auditoria.registrar(f"{ato}_ultimo_admin_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(
            "O sistema deve manter ao menos um administrador ativo."
        )


def validar_edicao(usuario: Usuario, *, papel: str, ativo: bool, email: str) -> None:
    """Guardas da edição de conta. As do último administrador ativo e da
    própria conta ficam na rota, pois dependem de quem executa; aqui ficam as
    que valem por qualquer caminho (rota, CLI ou API futura).

    - E-mail é único (mesma regra e mensagem de `criar_usuario`).
    - O papel não muda enquanto houver vínculo ativo pendurado no papel atual:
      orientador rebaixado perde acesso às próprias orientações enquanto os
      orientandos seguem apontando para ele.
    - Orientador com vínculo ativo tampouco é desativado — é o mesmo estado
      ingerível da mudança de papel, a um checkbox do caminho bloqueado."""
    if email != usuario.email and Usuario.query.filter(
        Usuario.email == email, Usuario.id != usuario.id
    ).first():
        raise GestaoUsuarioInvalida("E-mail já cadastrado.")
    if papel != usuario.papel:
        motivo = None
        if usuario.papel == "orientador" and orienta_vinculo_ativo(usuario):
            motivo = "orienta vínculo(s) ativo(s)"
        elif usuario.papel == "orientando" and db.session.query(
            Orientacao.query.filter_by(
                orientando_id=usuario.id, status="ativa"
            ).exists()
        ).scalar():
            motivo = "é orientando de vínculo ativo"
        if motivo:
            auditoria.registrar(
                "edicao_papel_recusada", "usuario", usuario.id, {"motivo": motivo}
            )
            raise GestaoUsuarioInvalida(
                f"Alteração de papel recusada: a conta {motivo}. Encerre ou "
                "reatribua os vínculos antes de mudar o papel."
            )
    if (
        usuario.papel == "orientador"
        and usuario.ativo
        and not ativo
        and orienta_vinculo_ativo(usuario)
    ):
        auditoria.registrar("desativacao_orientador_recusada", "usuario", usuario.id)
        raise GestaoUsuarioInvalida(
            "Desativação recusada: a conta orienta vínculo(s) ativo(s), e "
            "desativá-la deixaria os orientandos sem gestor. Encerre ou "
            "reatribua os vínculos antes."
        )


def excluir_usuario(
    usuario: Usuario, executor: Usuario, descartaveis: list[int] | None = None
) -> None:
    validar_remocao(usuario, executor, ato="exclusao", verbo="excluir")
    # revalida no serviço: só vínculos efetivamente vazios podem ser descartados
    descartaveis = [
        oid
        for oid in (descartaveis or [])
        if (o := db.session.get(Orientacao, oid)) is not None
        and o.orientando_id == usuario.id
        and vinculo_sem_registros(o)
    ]
    motivo = motivo_bloqueio_exclusao(usuario, descartaveis)
    if motivo:
        auditoria.registrar(
            "exclusao_recusada", "usuario", usuario.id, {"motivo": motivo}
        )
        raise GestaoUsuarioInvalida(
            f"Exclusão recusada: a conta {motivo}. Utilize a desativação, "
            "que preserva o histórico."
        )
    auditoria.registrar(
        "exclusao_usuario",
        "usuario",
        usuario.id,
        {
            "email": usuario.email,
            "papel": usuario.papel,
            "vinculos_removidos": descartaveis,
        },
    )
    for oid in descartaveis:
        db.session.delete(db.session.get(Orientacao, oid))
    db.session.delete(usuario)
