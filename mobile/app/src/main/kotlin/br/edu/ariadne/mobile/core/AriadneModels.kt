package br.edu.ariadne.mobile.core

import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import org.json.JSONArray
import org.json.JSONObject

data class Usuario(
    val id: Long,
    val nome: String,
    val email: String,
    val papel: String,
)

data class Orientacao(
    val id: Long,
    val orientadorId: Long,
    val orientadorNome: String,
    val orientandoId: Long,
    val orientandoNome: String,
    val modalidade: String,
    val tituloProjeto: String,
    val dataInicio: String,
    val dataFimPrevista: String?,
    val status: String,
)

data class Marco(
    val id: Long,
    val orientacaoId: Long,
    val titulo: String,
    val descricao: String?,
    val dataPrevista: String,
    val dataConclusao: String?,
    val status: String,
    val tipo: String,
    val etapa: Int,
    val conclusaoSinalizada: Boolean,
    val notaConclusao: String?,
    val devolvidoEm: String?,
    val notaDevolucao: String?,
    val grupoId: String?,
    val entregaEsperada: String?,
    val aguardando: String?,
    val criadoEm: String?,
    val documentoBaseId: Long? = null,
)

/** Documentos que recebem entregas da tarefa: os ligados a ela e, na revisão,
 * o texto-base (que pode pertencer a outra tarefa). Mesma regra do servidor. */
fun Marco.documentosDaTarefa(documentos: List<Documento>): List<Documento> =
    documentos.filter { it.marcoId == id || (documentoBaseId != null && it.id == documentoBaseId) }

data class ParticipacaoAta(
    val orientacaoId: Long,
    val presenca: String,
    val presencaRegistradaEm: String?,
)

data class Ata(
    val id: Long,
    val tipo: String,
    val orientadorId: Long,
    val dataReuniao: String,
    val horaReuniao: String?,
    val linkReuniao: String?,
    val pauta: String,
    val deliberacoes: String,
    val status: String,
    val formato: String,
    val finalizadaEm: String?,
    val canceladaEm: String?,
    val motivoCancelamento: String?,
    val criadaEm: String?,
    val orientacaoIds: List<Long>,
    val marcoIds: List<Long>,
    val participacoes: List<ParticipacaoAta>,
)

data class VersaoDocumento(
    val id: Long,
    val documentoId: Long,
    val numeroVersao: Int,
    val nomeOriginal: String?,
    val temArquivo: Boolean,
    val enviadoPor: Long,
    val remetenteNome: String,
    val enviadoEm: String?,
    val comentario: String?,
    val natureza: String,
    val marcoAbertoId: Long?,
    val marcoAbertoTitulo: String?,
)

data class Documento(
    val id: Long,
    val orientacaoId: Long,
    val marcoId: Long?,
    val marcoTitulo: String?,
    val titulo: String,
    val criadoEm: String?,
    val versoes: List<VersaoDocumento>,
)

data class Parecer(
    val id: Long,
    val orientacaoId: Long,
    val versaoDocumentoId: Long?,
    val documentoId: Long? = null,
    val documentoTitulo: String? = null,
    val numeroVersao: Int? = null,
    val nomeArquivo: String? = null,
    val marcoId: Long? = null,
    val marcoTitulo: String? = null,
    val tipo: String,
    val conteudo: String,
    val resultado: String,
    val emitidoPor: Long,
    val emissorNome: String? = null,
    val emitidoEm: String,
    val formato: String,
)

data class ItemFila(
    val seq: Long,
    val opId: String,
    val acao: String,
    val dadosJson: String,
    val criadaEm: String,
)

data class EstadoApp(
    val autenticado: Boolean = false,
    val urlServidor: String = "https://orientacao.pythonanywhere.com",
    val usuario: Usuario? = null,
    val ultimaSync: String? = null,
    val orientacoes: List<Orientacao> = emptyList(),
    val marcos: List<Marco> = emptyList(),
    val documentos: List<Documento> = emptyList(),
    val atas: List<Ata> = emptyList(),
    val pareceres: List<Parecer> = emptyList(),
    val itensFila: List<ItemFila> = emptyList(),
)

data class RespostaPonte(
    val ok: Boolean,
    val mensagem: String?,
    val erro: String?,
    val estado: EstadoApp?,
)

object AriadneCatalogos {
    val tiposMarco = listOf(
        "outro" to "Outro",
        "projeto" to "Projeto de pesquisa",
        "comite_etica" to "Comitê de Ética",
        "qualificacao" to "Qualificação",
        "relatorio" to "Relatório (parcial, anual ou final)",
        "publicacao" to "Publicação",
        "defesa" to "Defesa",
    )

    val etapasMarco = listOf(
        0 to "Não classificada",
        10 to "Planejamento",
        20 to "Revisão de literatura",
        30 to "Coleta / Experimentos",
        40 to "Análise de resultados",
        50 to "Redação",
        60 to "Encerramento",
    )

    val entregasEsperadas = listOf(
        "documento" to "Entregar um documento",
        "revisao" to "Revisar um texto",
        "ato" to "Sem arquivo (só o ato)",
        "" to "Não especificar",
    )

    val tiposParecer = listOf(
        "andamento" to "Andamento",
        "documento" to "Documento",
        "marco" to "Marco",
    )

    val resultadosParecer = listOf(
        "aprovado" to "Aprovado",
        "aprovado_com_ressalvas" to "Aprovado com ressalvas",
        "reprovado" to "Reprovado",
    )

    val modalidades = mapOf(
        "ic" to "Iniciação Científica",
        "mestrado" to "Mestrado",
        "doutorado" to "Doutorado",
    )

    val papeis = mapOf(
        "orientador" to "Orientador",
        "orientando" to "Orientando",
        "admin" to "Administrador",
    )

    fun rotuloModalidade(modalidade: String): String =
        modalidades[modalidade] ?: modalidade

    fun rotuloPapel(papel: String): String =
        papeis[papel] ?: papel

    fun rotuloTipoMarco(tipo: String): String =
        tiposMarco.firstOrNull { it.first == tipo }?.second ?: tipo

    fun rotuloEntregaEsperada(entrega: String?): String? = when (entrega) {
        "documento" -> "Entregar um documento"
        "revisao" -> "Revisar um texto"
        "ato" -> "Sem arquivo (só o ato)"
        else -> null
    }

    fun rotuloEtapa(etapa: Int): String =
        etapasMarco.firstOrNull { it.first == etapa }?.second ?: "Etapa $etapa"

    fun rotuloAguardando(aguardando: String?): String = when (aguardando) {
        null -> "Concluída"
        "orientador" -> "Aguarda orientador"
        "orientando_revisao" -> "Devolvida para revisão"
        "orientando" -> "Com orientando"
        else -> "Em andamento"
    }

    fun rotuloResultadoParecer(resultado: String): String =
        resultadosParecer.firstOrNull { it.first == resultado }?.second ?: resultado

    private val acoesFila = mapOf(
        "sinalizar_conclusao_marco" to "Sinalizar conclusão",
        "confirmar_conclusao_marco" to "Confirmar conclusão",
        "devolver_marco" to "Devolver para revisão",
        "criar_tarefa" to "Criar tarefa",
        "editar_marco" to "Editar tarefa",
        "agendar_reuniao" to "Agendar reunião",
        "atualizar_ata" to "Atualizar ata",
        "registrar_presenca" to "Registrar presença",
        "reagendar_ata" to "Reagendar reunião",
        "cancelar_reuniao" to "Cancelar reunião",
        "finalizar_ata" to "Finalizar ata",
        "emitir_parecer" to "Emitir parecer",
    )

    fun rotuloAcaoFila(acao: String): String = acoesFila[acao] ?: acao
}

/** Descrição legível de uma operação da fila offline: a ação e, quando a
 * operação aponta para uma tarefa ou traz um título, o nome do alvo. */
fun ItemFila.descricao(marcos: List<Marco>): String {
    val rotulo = AriadneCatalogos.rotuloAcaoFila(acao)
    val dados = runCatching { JSONObject(dadosJson) }.getOrNull() ?: return rotulo
    val alvo = when {
        dados.has("marco_id") ->
            marcos.firstOrNull { it.id == dados.optLong("marco_id") }?.titulo
        dados.has("titulo") -> dados.optString("titulo").ifBlank { null }
        else -> null
    }
    return if (alvo != null) "$rotulo: «$alvo»" else rotulo
}

private val FORMATO_DATA_BR = DateTimeFormatter.ofPattern("dd/MM/yyyy")
private val FORMATO_DATA_HORA_BR = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm")

fun hojeIso(): String = LocalDate.now().toString()

fun formatarDataBr(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val trecho = iso.trim().take(10)
    return runCatching { LocalDate.parse(trecho).format(FORMATO_DATA_BR) }.getOrDefault(iso)
}

fun formatarDataHoraBr(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val limpo = iso.trim()
    return runCatching {
        val instant = Instant.parse(if (limpo.endsWith("Z")) limpo else "${limpo}Z")
        instant.atZone(ZoneOffset.UTC).format(FORMATO_DATA_HORA_BR)
    }.recoverCatching {
        LocalDateTime.parse(limpo.take(19).replace(' ', 'T')).format(FORMATO_DATA_HORA_BR)
    }.getOrElse {
        formatarDataBr(limpo)
    }
}

fun Marco.estaAtrasado(hoje: String = hojeIso()): Boolean =
    status != "concluido" && dataPrevista.isNotBlank() && dataPrevista < hoje

fun Ata.ehPassadaOuHoje(hoje: String = hojeIso()): Boolean =
    dataReuniao.isNotBlank() && dataReuniao <= hoje

private fun JSONObject.str(chave: String, padrao: String = ""): String =
    if (isNull(chave)) padrao else optString(chave, padrao)

private fun JSONObject.strOrNull(chave: String): String? =
    if (isNull(chave)) null else optString(chave, "").ifEmpty { null }

private fun JSONObject.longOrNull(chave: String): Long? =
    if (isNull(chave)) null else optLong(chave)

private fun JSONArray?.toLongList(): List<Long> {
    if (this == null) return emptyList()
    return List(length()) { i -> optLong(i) }
}

fun parseRespostaPonte(jsonTexto: String): RespostaPonte {
    val root = JSONObject(jsonTexto)
    val ok = root.optBoolean("ok", false)
    val mensagem = root.strOrNull("mensagem")
    val erro = root.strOrNull("erro")
    val estadoObj = if (root.isNull("estado")) null else root.optJSONObject("estado")
    val estado = estadoObj?.let(::parseEstado)
    return RespostaPonte(ok = ok, mensagem = mensagem, erro = erro, estado = estado)
}

private fun parseEstado(obj: JSONObject): EstadoApp {
    val usuarioObj = if (obj.isNull("usuario")) null else obj.optJSONObject("usuario")
    val usuario = usuarioObj?.let {
        Usuario(
            id = it.optLong("id"),
            nome = it.str("nome"),
            email = it.str("email"),
            papel = it.str("papel"),
        )
    }

    val orientacoesArr = obj.optJSONArray("orientacoes")
    val orientacoes = if (orientacoesArr == null) emptyList() else List(orientacoesArr.length()) { i ->
        val o = orientacoesArr.getJSONObject(i)
        Orientacao(
            id = o.optLong("id"),
            orientadorId = o.optLong("orientador_id"),
            orientadorNome = o.str("orientador_nome"),
            orientandoId = o.optLong("orientando_id"),
            orientandoNome = o.str("orientando_nome"),
            modalidade = o.str("modalidade"),
            tituloProjeto = o.str("titulo_projeto"),
            dataInicio = o.str("data_inicio"),
            dataFimPrevista = o.strOrNull("data_fim_prevista"),
            status = o.str("status"),
        )
    }

    val marcosArr = obj.optJSONArray("marcos")
    val marcos = if (marcosArr == null) emptyList() else List(marcosArr.length()) { i ->
        val m = marcosArr.getJSONObject(i)
        Marco(
            id = m.optLong("id"),
            orientacaoId = m.optLong("orientacao_id"),
            titulo = m.str("titulo"),
            descricao = m.strOrNull("descricao"),
            dataPrevista = m.str("data_prevista"),
            dataConclusao = m.strOrNull("data_conclusao"),
            status = m.str("status"),
            tipo = m.str("tipo"),
            etapa = m.optInt("etapa", 0),
            conclusaoSinalizada = m.optBoolean("conclusao_sinalizada", false),
            notaConclusao = m.strOrNull("nota_conclusao"),
            devolvidoEm = m.strOrNull("devolvido_em"),
            notaDevolucao = m.strOrNull("nota_devolucao"),
            grupoId = m.strOrNull("grupo_id"),
            entregaEsperada = m.strOrNull("entrega_esperada"),
            aguardando = m.strOrNull("aguardando"),
            criadoEm = m.strOrNull("criado_em"),
            documentoBaseId = m.longOrNull("documento_base_id"),
        )
    }

    val atasArr = obj.optJSONArray("atas")
    val atas = if (atasArr == null) emptyList() else List(atasArr.length()) { i ->
        val a = atasArr.getJSONObject(i)
        val partArr = a.optJSONArray("participacoes")
        val participacoes = if (partArr == null) emptyList() else List(partArr.length()) { j ->
            val p = partArr.getJSONObject(j)
            ParticipacaoAta(
                orientacaoId = p.optLong("orientacao_id"),
                presenca = p.str("presenca", "pendente"),
                presencaRegistradaEm = p.strOrNull("presenca_registrada_em"),
            )
        }
        Ata(
            id = a.optLong("id"),
            tipo = a.str("tipo"),
            orientadorId = a.optLong("orientador_id"),
            dataReuniao = a.str("data_reuniao"),
            horaReuniao = a.strOrNull("hora_reuniao"),
            linkReuniao = a.strOrNull("link_reuniao"),
            pauta = a.str("pauta"),
            deliberacoes = a.str("deliberacoes"),
            status = a.str("status"),
            formato = a.str("formato", "markdown"),
            finalizadaEm = a.strOrNull("finalizada_em"),
            canceladaEm = a.strOrNull("cancelada_em"),
            motivoCancelamento = a.strOrNull("motivo_cancelamento"),
            criadaEm = a.strOrNull("criada_em"),
            orientacaoIds = a.optJSONArray("orientacao_ids").toLongList(),
            marcoIds = a.optJSONArray("marco_ids").toLongList(),
            participacoes = participacoes,
        )
    }

    val documentosArr = obj.optJSONArray("documentos")
    val documentos = if (documentosArr == null) emptyList() else List(documentosArr.length()) { i ->
        val d = documentosArr.getJSONObject(i)
        val versoesArr = d.optJSONArray("versoes")
        val versoes = if (versoesArr == null) emptyList() else List(versoesArr.length()) { j ->
            val v = versoesArr.getJSONObject(j)
            VersaoDocumento(
                id = v.optLong("id"),
                documentoId = v.optLong("documento_id"),
                numeroVersao = v.optInt("numero_versao"),
                nomeOriginal = v.strOrNull("nome_original"),
                temArquivo = v.optBoolean("tem_arquivo", false),
                enviadoPor = v.optLong("enviado_por"),
                remetenteNome = v.str("remetente_nome"),
                enviadoEm = v.strOrNull("enviado_em"),
                comentario = v.strOrNull("comentario"),
                natureza = v.str("natureza"),
                marcoAbertoId = v.longOrNull("marco_aberto_id"),
                marcoAbertoTitulo = v.strOrNull("marco_aberto_titulo"),
            )
        }
        Documento(
            id = d.optLong("id"),
            orientacaoId = d.optLong("orientacao_id"),
            marcoId = d.longOrNull("marco_id"),
            marcoTitulo = d.strOrNull("marco_titulo"),
            titulo = d.str("titulo"),
            criadoEm = d.strOrNull("criado_em"),
            versoes = versoes,
        )
    }

    val pareceresArr = obj.optJSONArray("pareceres")
    val pareceres = if (pareceresArr == null) emptyList() else List(pareceresArr.length()) { i ->
        val p = pareceresArr.getJSONObject(i)
        Parecer(
            id = p.optLong("id"),
            orientacaoId = p.optLong("orientacao_id"),
            versaoDocumentoId = p.longOrNull("versao_documento_id"),
            documentoId = p.longOrNull("documento_id"),
            documentoTitulo = p.strOrNull("documento_titulo"),
            numeroVersao = if (p.isNull("numero_versao")) null else p.optInt("numero_versao"),
            nomeArquivo = p.strOrNull("nome_arquivo"),
            marcoId = p.longOrNull("marco_id"),
            marcoTitulo = p.strOrNull("marco_titulo"),
            tipo = p.str("tipo"),
            conteudo = p.str("conteudo"),
            resultado = p.str("resultado"),
            emitidoPor = p.optLong("emitido_por"),
            emissorNome = p.strOrNull("emissor_nome"),
            emitidoEm = p.str("emitido_em"),
            formato = p.str("formato", "markdown"),
        )
    }

    val filaArr = obj.optJSONArray("itens_fila")
    val itensFila = if (filaArr == null) emptyList() else List(filaArr.length()) { i ->
        val f = filaArr.getJSONObject(i)
        ItemFila(
            seq = f.optLong("seq"),
            opId = f.str("op_id"),
            acao = f.str("acao"),
            dadosJson = f.str("dados_json"),
            criadaEm = f.str("criada_em"),
        )
    }

    return EstadoApp(
        autenticado = obj.optBoolean("autenticado", false),
        urlServidor = obj.str("url_servidor", "https://orientacao.pythonanywhere.com"),
        usuario = usuario,
        ultimaSync = obj.strOrNull("ultima_sync"),
        orientacoes = orientacoes,
        marcos = marcos,
        documentos = documentos,
        atas = atas,
        pareceres = pareceres,
        itensFila = itensFila,
    )
}
