"""API JSON para sincronização offline-first com o aplicativo móvel."""

from datetime import UTC, date, datetime, time
from functools import wraps
from urllib.parse import urlparse

from flask import Response, current_app, g, jsonify, request
from flask_login import current_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from app.blueprints.api import bp
from app.blueprints.atas.forms import ESQUEMAS_LINK
from app.blueprints.auth.routes import _HASH_FALSO
from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    Documento,
    LogAuditoria,
    Marco,
    Orientacao,
    Parecer,
    Usuario,
    VersaoDocumento,
)
from app.models.ata import RESULTADOS_PARECER, TIPOS_PARECER
from app.models.cronograma import ENTREGAS_ESPERADAS, ETAPAS_MARCO, TIPOS_MARCO
from app.services import auditoria, exportacao, relatorio, tarefas
from app.services import cronogramas as servico_cronograma
from app.services import entregas as servico_entregas
from app.services.atas import (
    AtaImutavel,
    OperacaoInvalida,
    agendar_reuniao,
    atualizar_ata,
    cancelar_reuniao,
    finalizar_ata,
    reagendar_ata,
    registrar_presenca,
)
from app.services.pareceres import marco_aberto_da_versao
from app.services.rbac import manda_no_cronograma, orientacoes_do_usuario
from app.services.seguranca import excedeu_tentativas
from app.services.tempo import agora
from app.services.uploads import UploadInvalido
from app.services.usuarios import normalizar_email

_TOKEN_SALT = "ariadne-api-token-v1"
_DEFAULT_TOKEN_MAX_AGE = 30 * 24 * 3600


class _AcessoNegado(Exception):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_TOKEN_SALT)


def gerar_token(usuario: Usuario) -> str:
    """Emite token Bearer assinado ligado à identidade e ao trecho da senha."""
    return _serializer().dumps(
        {"uid": usuario.id, "sig": (usuario.senha_hash or "")[-16:]}
    )


def _autenticar_bearer():
    cabecalho = request.headers.get("Authorization", "")
    esquema, _, token = cabecalho.partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        return None, ({"erro": "Autenticação necessária."}, 401)
    max_age = int(current_app.config.get("API_TOKEN_MAX_AGE", _DEFAULT_TOKEN_MAX_AGE))
    try:
        dados = _serializer().loads(token.strip(), max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None, ({"erro": "Token inválido ou expirado."}, 401)
    if not isinstance(dados, dict) or not isinstance(dados.get("uid"), int):
        return None, ({"erro": "Token inválido."}, 401)
    usuario = db.session.get(Usuario, dados["uid"])
    if usuario is None or not usuario.ativo:
        return None, ({"erro": "Conta inexistente ou desativada."}, 401)
    if dados.get("sig") != (usuario.senha_hash or "")[-16:]:
        return None, ({"erro": "Sessão encerrada; autentique-se novamente."}, 401)
    if usuario.senha_provisoria:
        return None, (
            {
                "erro": "troca_senha_obrigatoria",
                "mensagem": "Troque a senha provisória na interface web antes de sincronizar.",
            },
            403,
        )
    return usuario, None


def api_auth_required(view):
    """Autentica via token Bearer e injeta `current_user` para os serviços."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        usuario, erro = _autenticar_bearer()
        if erro is not None:
            corpo, codigo = erro
            return jsonify(corpo), codigo
        g._login_user = usuario
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Serialização do estado autorizado


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _serializar_usuario(u: Usuario) -> dict:
    return {
        "id": u.id,
        "nome": u.nome,
        "email": u.email,
        "papel": u.papel,
    }


def _serializar_orientacao(o: Orientacao) -> dict:
    return {
        "id": o.id,
        "orientador_id": o.orientador_id,
        "orientador_nome": o.orientador.nome,
        "orientando_id": o.orientando_id,
        "orientando_nome": o.orientando.nome,
        "modalidade": o.modalidade,
        "titulo_projeto": o.titulo_projeto,
        "data_inicio": o.data_inicio.isoformat(),
        "data_fim_prevista": (
            o.data_fim_prevista.isoformat() if o.data_fim_prevista else None
        ),
        "status": o.status,
    }


def _serializar_marco(m: Marco) -> dict:
    return {
        "id": m.id,
        "orientacao_id": m.orientacao_id,
        "titulo": m.titulo,
        "descricao": m.descricao,
        "data_prevista": m.data_prevista.isoformat(),
        "data_conclusao": m.data_conclusao.isoformat() if m.data_conclusao else None,
        "status": m.status,
        "tipo": m.tipo,
        "etapa": m.etapa,
        "conclusao_sinalizada": bool(m.conclusao_sinalizada),
        "nota_conclusao": m.nota_conclusao,
        "devolvido_em": _iso(m.devolvido_em),
        "nota_devolucao": m.nota_devolucao,
        "grupo_id": m.grupo_id,
        "entrega_esperada": m.entrega_esperada,
        "documento_base_id": m.documento_base_id,
        "aguardando": m.aguardando,
        "criado_em": _iso(m.criado_em),
    }


def _serializar_ata(a: Ata) -> dict:
    participacoes = sorted(a.participacoes, key=lambda x: x.orientacao_id)
    return {
        "id": a.id,
        "tipo": a.tipo,
        "orientador_id": a.orientador_id,
        "data_reuniao": a.data_reuniao.isoformat(),
        "hora_reuniao": a.hora_reuniao.strftime("%H:%M") if a.hora_reuniao else None,
        "link_reuniao": a.link_reuniao,
        "pauta": a.pauta,
        "deliberacoes": a.deliberacoes,
        "status": a.status,
        "formato": a.formato_conteudo,
        "finalizada_em": _iso(a.finalizada_em),
        "cancelada_em": _iso(a.cancelada_em),
        "motivo_cancelamento": a.motivo_cancelamento,
        "criada_em": _iso(a.criada_em),
        "orientacao_ids": [p.orientacao_id for p in participacoes],
        "marco_ids": sorted(m.id for m in a.marcos),
        "participacoes": [
            {
                "orientacao_id": p.orientacao_id,
                "presenca": p.presenca,
                "presenca_registrada_em": _iso(p.presenca_registrada_em),
            }
            for p in participacoes
        ],
    }


def _serializar_versao_documento(v: VersaoDocumento) -> dict:
    marco_aberto = marco_aberto_da_versao(v)
    return {
        "id": v.id,
        "documento_id": v.documento_id,
        "numero_versao": v.numero_versao,
        "nome_original": v.nome_original,
        "tem_arquivo": bool(v.tem_arquivo),
        "enviado_por": v.enviado_por,
        "remetente_nome": v.remetente.nome if v.remetente else "",
        "enviado_em": _iso(v.enviado_em),
        "comentario": v.comentario,
        "natureza": v.natureza,
        "marco_aberto_id": marco_aberto.id if marco_aberto else None,
        "marco_aberto_titulo": marco_aberto.titulo if marco_aberto else None,
    }


def _serializar_documento(d: Documento) -> dict:
    versoes = d.versoes.all() if hasattr(d.versoes, "all") else list(d.versoes)
    return {
        "id": d.id,
        "orientacao_id": d.orientacao_id,
        "marco_id": d.marco_id,
        "marco_titulo": d.marco.titulo if d.marco else None,
        "titulo": d.titulo,
        "criado_em": _iso(d.criado_em),
        "versoes": [_serializar_versao_documento(v) for v in versoes],
    }


def _serializar_parecer(p: Parecer) -> dict:
    versao = p.versao_documento
    doc = versao.documento if versao else None
    marco = doc.marco if doc else None
    return {
        "id": p.id,
        "orientacao_id": p.orientacao_id,
        "versao_documento_id": p.versao_documento_id,
        "documento_id": doc.id if doc else None,
        "documento_titulo": doc.titulo if doc else None,
        "numero_versao": versao.numero_versao if versao else None,
        "nome_arquivo": versao.nome_original if versao else None,
        "marco_id": marco.id if marco else None,
        "marco_titulo": marco.titulo if marco else None,
        "tipo": p.tipo,
        "conteudo": p.conteudo,
        "resultado": p.resultado,
        "emitido_por": p.emitido_por,
        "emissor_nome": p.emissor.nome if p.emissor else None,
        "emitido_em": _iso(p.emitido_em),
        "formato": p.formato_conteudo,
    }


def _montar_estado_sync() -> dict:
    orientacoes = orientacoes_do_usuario().order_by(Orientacao.id).all()
    ids = [o.id for o in orientacoes]
    if ids:
        marcos = (
            Marco.query.filter(Marco.orientacao_id.in_(ids))
            .order_by(Marco.orientacao_id, Marco.etapa, Marco.data_prevista, Marco.id)
            .all()
        )
        documentos = (
            Documento.query.filter(Documento.orientacao_id.in_(ids))
            .order_by(Documento.criado_em.desc(), Documento.id.desc())
            .all()
        )
        atas = (
            Ata.query.join(AtaParticipacao, AtaParticipacao.ata_id == Ata.id)
            .filter(AtaParticipacao.orientacao_id.in_(ids))
            .distinct()
            .order_by(Ata.data_reuniao.desc(), Ata.id.desc())
            .all()
        )
        pareceres = (
            Parecer.query.filter(Parecer.orientacao_id.in_(ids))
            .order_by(Parecer.emitido_em.desc(), Parecer.id.desc())
            .all()
        )
    else:
        marcos, documentos, atas, pareceres = [], [], [], []

    return {
        "usuario": _serializar_usuario(current_user),
        "orientacoes": [_serializar_orientacao(o) for o in orientacoes],
        "marcos": [_serializar_marco(m) for m in marcos],
        "documentos": [_serializar_documento(d) for d in documentos],
        "atas": [_serializar_ata(a) for a in atas],
        "pareceres": [_serializar_parecer(p) for p in pareceres],
        "sincronizado_em": _iso(agora()),
    }


# ---------------------------------------------------------------------------
# Endpoints de autenticação e sincronização


@bp.route("/auth/token", methods=["POST"])
def emitir_token():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    email_bruto = str(payload.get("email") or "")
    senha = str(payload.get("senha") or "")

    if excedeu_tentativas():
        auditoria.registrar(
            "login_bloqueado", "usuario", dados={"email": email_bruto, "via": "api"}
        )
        db.session.commit()
        return (
            jsonify(
                {
                    "erro": "Muitas tentativas a partir deste endereço. "
                    "Aguarde alguns minutos e tente novamente."
                }
            ),
            429,
        )

    email = normalizar_email(email_bruto)
    usuario = Usuario.query.filter_by(email=email).first() if email else None
    senha_confere = (
        usuario.verificar_senha(senha)
        if usuario is not None
        else check_password_hash(_HASH_FALSO, senha)
    )
    if usuario is None or not senha_confere:
        auditoria.registrar(
            "login_falho", "usuario", dados={"email": email_bruto, "via": "api"}
        )
        db.session.commit()
        return jsonify({"erro": "Credenciais inválidas."}), 401

    if not usuario.ativo:
        auditoria.registrar(
            "login_falho",
            "usuario",
            usuario.id,
            {"email": email_bruto, "motivo": "conta_desativada", "via": "api"},
        )
        db.session.commit()
        return jsonify({"erro": "Conta desativada. Contate o administrador."}), 403

    if usuario.senha_provisoria:
        return (
            jsonify(
                {
                    "erro": "troca_senha_obrigatoria",
                    "mensagem": "Você entrou com uma senha temporária. Acesse o "
                    "sistema web para definir sua senha antes de sincronizar.",
                }
            ),
            403,
        )

    usuario.ultimo_acesso = datetime.now(UTC)
    auditoria.registrar("login", "usuario", usuario.id, {"via": "api"})
    db.session.commit()
    return (
        jsonify(
            {"token": gerar_token(usuario), "usuario": _serializar_usuario(usuario)}
        ),
        200,
    )


@bp.route("/sync", methods=["GET"])
@api_auth_required
def obter_sync():
    return jsonify(_montar_estado_sync()), 200


@bp.route("/orientacoes/<int:orientacao_id>/extrato.pdf", methods=["GET"])
@api_auth_required
def extrato_orientacao_pdf(orientacao_id: int):
    orientacao = orientacoes_do_usuario().filter(Orientacao.id == orientacao_id).first()
    if orientacao is None:
        return jsonify({"erro": "Vínculo não encontrado ou sem permissão."}), 404
    pdf = relatorio.gerar_pdf_relatorio(orientacao)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="relatorio-vinculo-{orientacao.id}.pdf"'
            )
        },
    )


@bp.route("/marcos/<int:marco_id>/entrega", methods=["POST"])
@api_auth_required
def enviar_entrega(marco_id: int):
    """Envio de documento pela tarefa (multipart), com a opção de sinalizar a
    conclusão no mesmo ato — a mesma regra da página da tarefa no site. Só
    online: arquivos não passam pela fila de sincronização. Idempotente por
    `op_id`, como as operações do `POST /sync`.

    Campos: `arquivo` (obrigatório), `destino` (id de documento da tarefa ou
    "novo"), `titulo` (para documento novo), `comentario`, `sinalizar` (0/1),
    `op_id`."""
    op_id = (request.form.get("op_id") or "").strip()
    if not op_id or len(op_id) > 128:
        return jsonify({"erro": "op_id inválido ou ausente."}), 400

    marco = db.session.get(Marco, marco_id)
    orientacao = (
        orientacoes_do_usuario().filter(Orientacao.id == marco.orientacao_id).first()
        if marco is not None
        else None
    )
    if orientacao is None:
        return jsonify({"erro": "Tarefa não encontrada ou sem permissão."}), 404

    if _op_ja_aplicada(op_id):
        return (
            jsonify({"status": "ja_aplicada", "estado": _montar_estado_sync()}),
            200,
        )
    if marco.status == "concluido":
        return jsonify({"erro": "A tarefa está concluída; não recebe novos envios."}), 409

    arquivo = request.files.get("arquivo")
    if arquivo is None or not arquivo.filename:
        return jsonify({"erro": "Envie o arquivo no campo 'arquivo'."}), 400

    destino = (request.form.get("destino") or "novo").strip()
    documento = None
    if destino != "novo":
        documento = next(
            (d for d in marco.documentos_da_tarefa if str(d.id) == destino), None
        )
        if documento is None:
            return jsonify({"erro": "Documento de destino não pertence à tarefa."}), 400
    titulo = (request.form.get("titulo") or "").strip()[:255]
    if documento is None and not titulo:
        titulo = marco.titulo[:255]
    comentario = (request.form.get("comentario") or "").strip()[:4000] or None
    sinalizar = (request.form.get("sinalizar") or "").strip().lower() in {
        "1", "true", "sim", "on",
    }

    try:
        resultado = servico_entregas.registrar_entrega(
            marco, current_user,
            documento=documento,
            titulo=titulo,
            arquivo=arquivo,
            comentario=comentario,
            sinalizar=sinalizar,
        )
        auditoria.registrar(
            "sync_operacao", "documento", resultado.documento.id,
            {"op_id": op_id, "acao": "enviar_entrega"},
        )
        db.session.commit()
    except (UploadInvalido, ValueError) as exc:
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 400

    return (
        jsonify(
            {
                "status": "ok",
                "documento_id": resultado.documento.id,
                "versao": resultado.versao.numero_versao,
                "sinalizou": resultado.sinalizou,
                "mensagem": resultado.mensagem(),
                "estado": _montar_estado_sync(),
            }
        ),
        200,
    )


@bp.route("/sync", methods=["POST"])
@api_auth_required
def aplicar_sync():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("operacoes"), list):
        return (
            jsonify({"erro": "Payload inválido; esperado objeto com lista 'operacoes'."}),
            400,
        )

    resultados = []
    aplicadas_no_lote: set[str] = set()
    for item in payload["operacoes"]:
        if not isinstance(item, dict):
            resultados.append(
                {"op_id": "", "acao": "", "status": "erro", "erro": "Operação inválida."}
            )
            continue

        op_id = item.get("op_id")
        acao = str(item.get("acao") or "")
        dados = item.get("dados")
        if not isinstance(op_id, str) or not op_id.strip() or len(op_id) > 128:
            resultados.append(
                {
                    "op_id": str(op_id or ""),
                    "acao": acao,
                    "status": "erro",
                    "erro": "op_id inválido ou ausente.",
                }
            )
            continue
        op_id = op_id.strip()
        if dados is None:
            dados = {}
        if not isinstance(dados, dict):
            resultados.append(
                {
                    "op_id": op_id,
                    "acao": acao,
                    "status": "erro",
                    "erro": "Campo 'dados' deve ser um objeto JSON.",
                }
            )
            continue

        if op_id in aplicadas_no_lote or _op_ja_aplicada(op_id):
            resultados.append({"op_id": op_id, "acao": acao, "status": "ja_aplicada"})
            continue

        handler = _HANDLERS.get(acao)
        if handler is None:
            resultados.append(
                {
                    "op_id": op_id,
                    "acao": acao,
                    "status": "erro",
                    "erro": f"Ação desconhecida: {acao}",
                }
            )
            continue

        try:
            with db.session.begin_nested():
                entidade, entidade_id, extras = handler(dados)
                db.session.flush()
                auditoria.registrar(
                    "sync_operacao",
                    entidade,
                    entidade_id,
                    {"op_id": op_id, "acao": acao},
                )
        except (_AcessoNegado, OperacaoInvalida, AtaImutavel, ValueError) as exc:
            resultados.append(
                {"op_id": op_id, "acao": acao, "status": "erro", "erro": str(exc)}
            )
            continue

        aplicadas_no_lote.add(op_id)
        resultado = {
            "op_id": op_id,
            "acao": acao,
            "status": "ok",
            "entidade": entidade,
            "entidade_id": entidade_id,
        }
        if extras:
            resultado.update(extras)
        resultados.append(resultado)

    db.session.commit()
    return jsonify({"resultados": resultados, "estado": _montar_estado_sync()}), 200


# ---------------------------------------------------------------------------
# Helpers de validação e idempotência


def _op_ja_aplicada(op_id: str) -> bool:
    candidatos = LogAuditoria.query.filter(
        LogAuditoria.usuario_id == current_user.id,
        LogAuditoria.acao == "sync_operacao",
        LogAuditoria.dados_json.contains(op_id),
    ).all()
    return any(
        isinstance(log.dados, dict) and log.dados.get("op_id") == op_id
        for log in candidatos
    )


def _int_obrigatorio(dados: dict, chave: str) -> int:
    valor = dados.get(chave)
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise OperacaoInvalida(f"Campo inteiro obrigatório inválido: {chave}.")
    return valor


def _lista_ints(dados: dict, chave: str) -> list[int]:
    bruto = dados.get(chave)
    if not isinstance(bruto, list):
        raise OperacaoInvalida(f"Campo '{chave}' deve ser uma lista de inteiros.")
    vistos: set[int] = set()
    saida: list[int] = []
    for item in bruto:
        if isinstance(item, bool) or not isinstance(item, int):
            raise OperacaoInvalida(f"Valor inválido em '{chave}'.")
        if item not in vistos:
            vistos.add(item)
            saida.append(item)
    return saida


def _texto_obrigatorio(dados: dict, chave: str, *, max_len: int | None = None) -> str:
    bruto = dados.get(chave)
    if not isinstance(bruto, str) or not bruto.strip():
        raise OperacaoInvalida(f"Informe o campo obrigatório: {chave}.")
    texto = bruto.strip()
    if max_len is not None and len(texto) > max_len:
        raise OperacaoInvalida(f"Campo '{chave}' excede {max_len} caracteres.")
    return texto


def _texto_opcional(dados: dict, chave: str, *, max_len: int | None = None) -> str | None:
    bruto = dados.get(chave)
    if bruto is None:
        return None
    if not isinstance(bruto, str):
        raise OperacaoInvalida(f"Campo '{chave}' deve ser texto.")
    texto = bruto.strip()
    if max_len is not None and len(texto) > max_len:
        raise OperacaoInvalida(f"Campo '{chave}' excede {max_len} caracteres.")
    return texto or None


def _parse_data(dados: dict, chave: str) -> date:
    bruto = dados.get(chave)
    if not isinstance(bruto, str) or not bruto.strip():
        raise OperacaoInvalida(f"Data obrigatória inválida: {chave}.")
    try:
        return date.fromisoformat(bruto.strip())
    except ValueError as exc:
        raise OperacaoInvalida(f"Data inválida para '{chave}'.") from exc


def _parse_hora(dados: dict, chave: str) -> time | None:
    bruto = dados.get(chave)
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return None
    if not isinstance(bruto, str):
        raise OperacaoInvalida(f"Hora inválida para '{chave}'.")
    try:
        return time.fromisoformat(bruto.strip())
    except ValueError as exc:
        raise OperacaoInvalida(f"Hora inválida para '{chave}'.") from exc


def _validar_link(valor) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise OperacaoInvalida("Link da reunião deve ser texto.")
    limpo = valor.strip()
    if not limpo:
        return None
    if len(limpo) > 500:
        raise OperacaoInvalida("Link da reunião excede 500 caracteres.")
    if not limpo.lower().startswith(ESQUEMAS_LINK):
        raise OperacaoInvalida(
            "Informe o endereço completo da sala, começando com https://"
        )
    partes = urlparse(limpo)
    if not partes.netloc or "." not in partes.netloc:
        raise OperacaoInvalida("Endereço da sala virtual inválido.")
    return limpo


def _carregar_marco(marco_id: int) -> Marco:
    marco = db.session.get(Marco, marco_id)
    if marco is None:
        raise OperacaoInvalida("Marco não encontrado.")
    return marco


def _carregar_ata(ata_id: int) -> Ata:
    ata = db.session.get(Ata, ata_id)
    if ata is None:
        raise OperacaoInvalida("Reunião/ata não encontrada.")
    return ata


def _pode_editar_ata(ata: Ata) -> bool:
    if current_user.papel == "admin" or current_user.id == ata.orientador_id:
        return True
    return bool(ata.participacoes) and all(
        p.orientacao.orienta(current_user) for p in ata.participacoes
    )


def _pode_gerir_ata(ata: Ata) -> bool:
    return current_user.id == ata.orientador_id or current_user.papel == "admin"


# ---------------------------------------------------------------------------
# Manipuladores de operações de sincronização


def _op_sinalizar_conclusao(dados: dict) -> tuple[str, int, dict | None]:
    marco = _carregar_marco(_int_obrigatorio(dados, "marco_id"))
    if not servico_cronograma.pode_sinalizar(marco, current_user):
        if current_user.id != marco.orientacao.orientando_id:
            raise _AcessoNegado("Apenas o orientando do vínculo pode sinalizar.")
        if marco.status == "concluido":
            raise OperacaoInvalida("A tarefa já está concluída.")
        raise OperacaoInvalida("A conclusão desta tarefa já foi sinalizada.")
    nota = _texto_opcional(dados, "nota", max_len=2000)
    servico_cronograma.sinalizar_conclusao(marco, nota)
    return "marco", marco.id, None


def _op_confirmar_conclusao(dados: dict) -> tuple[str, int, dict | None]:
    marco = _carregar_marco(_int_obrigatorio(dados, "marco_id"))
    if not manda_no_cronograma(marco.orientacao):
        raise _AcessoNegado("Sem permissão para confirmar conclusão neste cronograma.")
    servico_cronograma.confirmar_conclusao(marco)
    return "marco", marco.id, None


def _op_devolver_marco(dados: dict) -> tuple[str, int, dict | None]:
    marco = _carregar_marco(_int_obrigatorio(dados, "marco_id"))
    if not manda_no_cronograma(marco.orientacao):
        raise _AcessoNegado("Sem permissão para devolver neste cronograma.")
    if not servico_cronograma.pode_devolver(marco):
        raise OperacaoInvalida(servico_cronograma.recado_da_devolucao(marco)[0])
    nota = _texto_opcional(dados, "nota", max_len=2000)
    servico_cronograma.devolver_entrega(marco, nota)
    return "marco", marco.id, None


def _validar_campos_marco(dados: dict, *, padrao_tipo="outro", padrao_etapa=0):
    titulo = _texto_obrigatorio(dados, "titulo", max_len=255)
    tipo = str(dados.get("tipo") or padrao_tipo)
    if tipo not in TIPOS_MARCO:
        raise OperacaoInvalida("Tipo de marco inválido.")
    etapa_bruta = dados.get("etapa", padrao_etapa)
    if isinstance(etapa_bruta, bool) or not isinstance(etapa_bruta, int) or etapa_bruta not in ETAPAS_MARCO:
        raise OperacaoInvalida("Etapa de marco inválida.")
    entrega_bruta = dados.get("entrega_esperada")
    entrega_esperada = (entrega_bruta or "").strip() or None if isinstance(entrega_bruta, str) else entrega_bruta
    if entrega_esperada is not None and entrega_esperada not in ENTREGAS_ESPERADAS:
        raise OperacaoInvalida("Entrega esperada inválida.")
    descricao = _texto_opcional(dados, "descricao")
    data_prevista = _parse_data(dados, "data_prevista")
    return {
        "titulo": titulo,
        "tipo": tipo,
        "etapa": etapa_bruta,
        "entrega_esperada": entrega_esperada,
        "descricao": descricao,
        "data_prevista": data_prevista,
    }


def _op_criar_tarefa(dados: dict) -> tuple[str, int | None, dict | None]:
    if current_user.papel not in ("orientador", "admin"):
        raise _AcessoNegado("Apenas orientadores podem criar tarefas.")
    ids_solicitados = _lista_ints(dados, "orientacao_ids")
    if not ids_solicitados:
        raise OperacaoInvalida("Selecione ao menos um orientando.")
    vinculos = (
        Orientacao.query.filter(
            Orientacao.id.in_(ids_solicitados),
            Orientacao.status == "ativa",
        ).all()
    )
    por_id = {o.id: o for o in vinculos if manda_no_cronograma(o)}
    if len(por_id) != len(ids_solicitados):
        raise _AcessoNegado("Vínculo inexistente, inativo ou sem permissão de gestão.")
    selecionadas = [por_id[oid] for oid in ids_solicitados]

    ata = None
    ata_id = dados.get("ata_id")
    if ata_id is not None:
        if isinstance(ata_id, bool) or not isinstance(ata_id, int):
            raise OperacaoInvalida("ata_id inválido.")
        ata = _carregar_ata(ata_id)
        if not _pode_gerir_ata(ata):
            raise _AcessoNegado("Sem permissão para derivar tarefa desta reunião.")
        if ata.status == "cancelada":
            raise AtaImutavel("Reunião cancelada não deriva tarefas.")
        participantes = {p.orientacao_id for p in ata.participacoes}
        if not set(ids_solicitados).issubset(participantes):
            raise OperacaoInvalida("Vínculo selecionado não participa desta reunião.")

    campos = _validar_campos_marco(dados)
    criados = tarefas.criar_tarefa(
        selecionadas,
        titulo=campos["titulo"],
        tipo=campos["tipo"],
        descricao=campos["descricao"],
        data_prevista=campos["data_prevista"],
        etapa=campos["etapa"],
        ata=ata,
        entrega_esperada=campos["entrega_esperada"],
    )
    primeiro_id = criados[0].id if criados else None
    return "marco", primeiro_id, {"criados_ids": [m.id for m in criados]}


def _op_editar_marco(dados: dict) -> tuple[str, int, dict | None]:
    marco = _carregar_marco(_int_obrigatorio(dados, "marco_id"))
    if not manda_no_cronograma(marco.orientacao):
        raise _AcessoNegado("Sem permissão para editar este marco.")
    mesclado = {
        "titulo": dados.get("titulo", marco.titulo),
        "tipo": dados.get("tipo", marco.tipo),
        "etapa": dados.get("etapa", marco.etapa),
        "entrega_esperada": dados.get("entrega_esperada", marco.entrega_esperada),
        "descricao": dados.get("descricao", marco.descricao),
        "data_prevista": dados.get("data_prevista", marco.data_prevista.isoformat()),
    }
    campos = _validar_campos_marco(
        mesclado, padrao_tipo=marco.tipo, padrao_etapa=marco.etapa
    )
    marco.titulo = campos["titulo"]
    marco.tipo = campos["tipo"]
    marco.etapa = campos["etapa"]
    marco.entrega_esperada = campos["entrega_esperada"]
    marco.descricao = campos["descricao"]
    marco.data_prevista = campos["data_prevista"]
    if marco.entrega_esperada != "revisao":
        marco.documento_base_id = None
    auditoria.registrar("edicao_marco", "marco", marco.id)
    return "marco", marco.id, None


def _op_agendar_reuniao(dados: dict) -> tuple[str, int, dict | None]:
    if current_user.papel != "orientador":
        raise _AcessoNegado("Apenas orientadores podem agendar reuniões.")
    ids_solicitados = _lista_ints(dados, "orientacao_ids")
    if not ids_solicitados:
        raise OperacaoInvalida("Selecione ao menos um orientando.")
    vinculos = Orientacao.query.filter(
        Orientacao.id.in_(ids_solicitados),
        Orientacao.orientador_id == current_user.id,
        Orientacao.status == "ativa",
    ).all()
    por_id = {o.id: o for o in vinculos}
    if len(por_id) != len(ids_solicitados):
        raise _AcessoNegado("Vínculo inexistente, inativo ou de outro orientador.")
    selecionadas = [por_id[oid] for oid in ids_solicitados]

    data_reuniao = _parse_data(dados, "data_reuniao")
    hora_reuniao = _parse_hora(dados, "hora_reuniao")
    link_reuniao = _validar_link(dados.get("link_reuniao"))
    pauta = _texto_obrigatorio(dados, "pauta")
    ata = agendar_reuniao(
        current_user,
        vinculos=selecionadas,
        data=data_reuniao,
        hora=hora_reuniao,
        pauta=pauta,
        link=link_reuniao,
    )
    return "ata", ata.id, None


def _op_atualizar_ata(dados: dict) -> tuple[str, int, dict | None]:
    ata = _carregar_ata(_int_obrigatorio(dados, "ata_id"))
    if not _pode_editar_ata(ata):
        raise _AcessoNegado("Sem permissão para editar esta ata.")
    pauta = _texto_obrigatorio(dados, "pauta")
    deliberacoes_bruta = dados.get("deliberacoes", "")
    if not isinstance(deliberacoes_bruta, str):
        raise OperacaoInvalida("Campo 'deliberacoes' deve ser texto.")

    marcos = None
    if "marco_ids" in dados and dados["marco_ids"] is not None:
        marco_ids = _lista_ints(dados, "marco_ids")
        vinculo_ids = [p.orientacao_id for p in ata.participacoes]
        if marco_ids and vinculo_ids:
            marcos = Marco.query.filter(
                Marco.id.in_(marco_ids), Marco.orientacao_id.in_(vinculo_ids)
            ).all()
        else:
            marcos = []

    kwargs = {}
    if "link_reuniao" in dados:
        kwargs["link"] = _validar_link(dados.get("link_reuniao"))

    atualizar_ata(
        ata,
        pauta=pauta,
        deliberacoes=deliberacoes_bruta,
        marcos=marcos,
        **kwargs,
    )
    return "ata", ata.id, None


def _op_registrar_presenca(dados: dict) -> tuple[str, int, dict | None]:
    ata = _carregar_ata(_int_obrigatorio(dados, "ata_id"))
    orientacao_id = _int_obrigatorio(dados, "orientacao_id")
    participacao = ata.participacao_de(orientacao_id)
    if participacao is None:
        raise OperacaoInvalida("Vínculo não participa desta reunião.")
    if (
        current_user.papel != "admin"
        and current_user.id != ata.orientador_id
        and not participacao.orientacao.orienta(current_user)
    ):
        raise _AcessoNegado("Sem permissão para registrar presença neste vínculo.")
    presenca = str(dados.get("presenca") or "")
    registrar_presenca(participacao, presenca, current_user)
    return "ata", ata.id, None


def _op_reagendar_ata(dados: dict) -> tuple[str, int, dict | None]:
    ata = _carregar_ata(_int_obrigatorio(dados, "ata_id"))
    if not _pode_gerir_ata(ata):
        raise _AcessoNegado("Sem permissão para reagendar esta reunião.")
    data_nova = _parse_data(dados, "data_nova")
    hora_nova = _parse_hora(dados, "hora_nova")
    motivo = _texto_opcional(dados, "motivo")
    kwargs = {}
    if "link_reuniao" in dados:
        kwargs["link"] = _validar_link(dados.get("link_reuniao"))
    reagendar_ata(
        ata,
        current_user,
        data_nova=data_nova,
        hora_nova=hora_nova,
        motivo=motivo,
        **kwargs,
    )
    return "ata", ata.id, None


def _op_cancelar_reuniao(dados: dict) -> tuple[str, int, dict | None]:
    ata = _carregar_ata(_int_obrigatorio(dados, "ata_id"))
    if not _pode_gerir_ata(ata):
        raise _AcessoNegado("Sem permissão para cancelar esta reunião.")
    motivo = _texto_obrigatorio(dados, "motivo")
    cancelar_reuniao(ata, current_user, motivo)
    return "ata", ata.id, None


def _op_finalizar_ata(dados: dict) -> tuple[str, int, dict | None]:
    ata = _carregar_ata(_int_obrigatorio(dados, "ata_id"))
    if not _pode_gerir_ata(ata):
        raise _AcessoNegado("Sem permissão para finalizar esta ata.")
    finalizar_ata(ata)
    return "ata", ata.id, None


def _op_emitir_parecer(dados: dict) -> tuple[str, int, dict | None]:
    orientacao_id = _int_obrigatorio(dados, "orientacao_id")
    orientacao = db.session.get(Orientacao, orientacao_id)
    if orientacao is None:
        raise OperacaoInvalida("Orientação não encontrada.")
    if current_user.id != orientacao.orientador_id and current_user.papel != "admin":
        raise _AcessoNegado("Sem permissão para emitir parecer neste vínculo.")

    versao = None
    versao_id = dados.get("versao_documento_id")
    if versao_id is not None:
        if isinstance(versao_id, bool) or not isinstance(versao_id, int):
            raise OperacaoInvalida("versao_documento_id inválido.")
        versao = (
            db.session.query(VersaoDocumento)
            .join(Documento)
            .filter(
                VersaoDocumento.id == versao_id,
                Documento.orientacao_id == orientacao.id,
                VersaoDocumento.nome_fisico.isnot(None),
            )
            .first()
        )
        if versao is None:
            raise OperacaoInvalida("Versão de documento não encontrada neste vínculo.")

    tipo_bruto = str(dados.get("tipo") or "").strip()
    tipo = tipo_bruto or ("documento" if versao is not None else "")
    if tipo not in TIPOS_PARECER:
        raise OperacaoInvalida("Tipo de parecer inválido.")

    if versao is None and tipo == "documento":
        versao = (
            db.session.query(VersaoDocumento)
            .join(Documento)
            .filter(
                Documento.orientacao_id == orientacao.id,
                VersaoDocumento.nome_fisico.isnot(None),
            )
            .order_by(VersaoDocumento.enviado_em.desc(), VersaoDocumento.id.desc())
            .first()
        )

    resultado = str(dados.get("resultado") or "")
    if resultado not in RESULTADOS_PARECER:
        raise OperacaoInvalida("Resultado de parecer inválido.")
    conteudo = _texto_obrigatorio(dados, "conteudo")

    parecer = Parecer(
        orientacao_id=orientacao.id,
        versao_documento_id=versao.id if versao else None,
        tipo=tipo,
        conteudo=conteudo,
        resultado=resultado,
        emitido_por=current_user.id,
    )
    db.session.add(parecer)
    db.session.flush()
    exportacao.congelar_parecer(parecer)
    auditoria.registrar(
        "emissao_parecer",
        "parecer",
        parecer.id,
        {"tipo": parecer.tipo, "resultado": parecer.resultado},
    )

    concluir_marco = bool(dados.get("concluir_marco", False))
    marco = marco_aberto_da_versao(versao) if versao else None
    if marco is not None and marco.orientacao_id == orientacao.id:
        if concluir_marco and parecer.resultado in (
            "aprovado",
            "aprovado_com_ressalvas",
        ):
            servico_cronograma.confirmar_conclusao(marco)
        elif parecer.resultado == "reprovado" and servico_cronograma.pode_devolver(
            marco
        ):
            servico_cronograma.devolver_entrega(marco, parecer.conteudo)

    return "parecer", parecer.id, None


_HANDLERS = {
    "sinalizar_conclusao_marco": _op_sinalizar_conclusao,
    "confirmar_conclusao_marco": _op_confirmar_conclusao,
    "devolver_marco": _op_devolver_marco,
    "criar_tarefa": _op_criar_tarefa,
    "editar_marco": _op_editar_marco,
    "agendar_reuniao": _op_agendar_reuniao,
    "atualizar_ata": _op_atualizar_ata,
    "registrar_presenca": _op_registrar_presenca,
    "reagendar_ata": _op_reagendar_ata,
    "cancelar_reuniao": _op_cancelar_reuniao,
    "finalizar_ata": _op_finalizar_ata,
    "emitir_parecer": _op_emitir_parecer,
}
