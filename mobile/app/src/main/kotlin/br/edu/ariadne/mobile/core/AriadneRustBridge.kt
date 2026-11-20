package br.edu.ariadne.mobile.core

object AriadneRustBridge {
    init {
        System.loadLibrary("ariadne_core")
    }

    external fun estadoLocal(dbPath: String): String

    external fun loginESincronizar(
        dbPath: String,
        url: String,
        email: String,
        senha: String,
    ): String

    external fun sincronizar(dbPath: String): String

    external fun enfileirarOperacao(
        dbPath: String,
        acao: String,
        dadosJson: String,
    ): String

    external fun descartarOperacao(dbPath: String, opId: String): String

    external fun encerrarSessao(dbPath: String): String

    /** Envio de documento pela tarefa (só online). `pedidoJson`: op_id,
     * marco_id, caminho_arquivo, nome_arquivo, mime, destino, titulo,
     * comentario, sinalizar. */
    external fun enviarEntrega(dbPath: String, pedidoJson: String): String
}
