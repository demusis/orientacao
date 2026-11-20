use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::models::{
    Ata, Documento, EstadoSync, ItemFila, Marco, OperacaoSync, Orientacao, Parecer,
    ParticipacaoAta, ResultadoOperacao, Usuario,
};

const CHAVE_ESTADO_REMOTO: &str = "ultimo_estado_remoto";

pub struct RepositorioLocal {
    conn: Connection,
}

impl RepositorioLocal {
    pub fn abrir(caminho: &Path) -> Result<Self, String> {
        if let Some(parent) = caminho.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| format!("Falha ao criar pasta local: {e}"))?;
            }
        }
        let conn = Connection::open(caminho)
            .map_err(|e| format!("Falha ao abrir banco SQLite local: {e}"))?;
        let repo = Self { conn };
        repo.init_esquema()?;
        Ok(repo)
    }

    pub fn em_memoria() -> Result<Self, String> {
        let conn = Connection::open_in_memory()
            .map_err(|e| format!("Falha ao abrir SQLite em memória: {e}"))?;
        let repo = Self { conn };
        repo.init_esquema()?;
        Ok(repo)
    }

    fn init_esquema(&self) -> Result<(), String> {
        self.conn
            .execute_batch(
                "
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = OFF;

                CREATE TABLE IF NOT EXISTS config (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orientacoes (
                    id INTEGER PRIMARY KEY,
                    orientador_id INTEGER NOT NULL,
                    orientador_nome TEXT NOT NULL,
                    orientando_id INTEGER NOT NULL,
                    orientando_nome TEXT NOT NULL,
                    modalidade TEXT NOT NULL,
                    titulo_projeto TEXT NOT NULL,
                    data_inicio TEXT NOT NULL,
                    data_fim_prevista TEXT,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS marcos (
                    id INTEGER PRIMARY KEY,
                    orientacao_id INTEGER NOT NULL,
                    titulo TEXT NOT NULL,
                    descricao TEXT,
                    data_prevista TEXT NOT NULL,
                    data_conclusao TEXT,
                    status TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    etapa INTEGER NOT NULL,
                    conclusao_sinalizada INTEGER NOT NULL,
                    nota_conclusao TEXT,
                    devolvido_em TEXT,
                    nota_devolucao TEXT,
                    grupo_id TEXT,
                    entrega_esperada TEXT,
                    aguardando TEXT,
                    criado_em TEXT
                );

                CREATE TABLE IF NOT EXISTS atas (
                    id INTEGER PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    orientador_id INTEGER NOT NULL,
                    data_reuniao TEXT NOT NULL,
                    hora_reuniao TEXT,
                    link_reuniao TEXT,
                    pauta TEXT NOT NULL,
                    deliberacoes TEXT NOT NULL,
                    status TEXT NOT NULL,
                    formato TEXT NOT NULL,
                    finalizada_em TEXT,
                    cancelada_em TEXT,
                    motivo_cancelamento TEXT,
                    criada_em TEXT,
                    orientacao_ids_json TEXT NOT NULL,
                    marco_ids_json TEXT NOT NULL,
                    participacoes_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documentos (
                    id INTEGER PRIMARY KEY,
                    orientacao_id INTEGER NOT NULL,
                    dados_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pareceres (
                    id INTEGER PRIMARY KEY,
                    orientacao_id INTEGER NOT NULL,
                    versao_documento_id INTEGER,
                    documento_id INTEGER,
                    documento_titulo TEXT,
                    numero_versao INTEGER,
                    nome_arquivo TEXT,
                    marco_id INTEGER,
                    marco_titulo TEXT,
                    tipo TEXT NOT NULL,
                    conteudo TEXT NOT NULL,
                    resultado TEXT NOT NULL,
                    emitido_por INTEGER NOT NULL,
                    emissor_nome TEXT,
                    emitido_em TEXT NOT NULL,
                    formato TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fila_operacoes (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    op_id TEXT UNIQUE NOT NULL,
                    acao TEXT NOT NULL,
                    dados_json TEXT NOT NULL,
                    criada_em TEXT NOT NULL
                );
                ",
            )
            .map_err(|e| format!("Falha ao inicializar esquema local: {e}"))?;
        for col in [
            "documento_id INTEGER",
            "documento_titulo TEXT",
            "numero_versao INTEGER",
            "nome_arquivo TEXT",
            "marco_id INTEGER",
            "marco_titulo TEXT",
            "emissor_nome TEXT",
        ] {
            let _ = self
                .conn
                .execute(&format!("ALTER TABLE pareceres ADD COLUMN {col}"), []);
        }
        let _ = self
            .conn
            .execute("ALTER TABLE marcos ADD COLUMN documento_base_id INTEGER", []);
        Ok(())
    }

    fn get_config(&self, chave: &str) -> Result<Option<String>, String> {
        self.conn
            .query_row(
                "SELECT valor FROM config WHERE chave = ?1",
                params![chave],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| format!("Erro ao ler configuração '{chave}': {e}"))
    }

    fn set_config(conn: &Connection, chave: &str, valor: &str) -> Result<(), String> {
        conn.execute(
            "INSERT INTO config (chave, valor) VALUES (?1, ?2)
             ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            params![chave, valor],
        )
        .map_err(|e| format!("Erro ao gravar configuração '{chave}': {e}"))?;
        Ok(())
    }

    pub fn url_servidor(&self) -> Result<Option<String>, String> {
        self.get_config("url_servidor")
    }

    pub fn salvar_url_servidor(&self, url: &str) -> Result<(), String> {
        Self::set_config(&self.conn, "url_servidor", url.trim())
    }

    pub fn ultima_sync(&self) -> Result<Option<String>, String> {
        self.get_config("ultima_sync")
    }

    pub fn salvar_sessao(
        &self,
        url_servidor: &str,
        token: &str,
        usuario: &Usuario,
    ) -> Result<(), String> {
        let usuario_json = serde_json::to_string(usuario)
            .map_err(|e| format!("Erro ao serializar usuário: {e}"))?;
        Self::set_config(&self.conn, "url_servidor", url_servidor.trim())?;
        Self::set_config(&self.conn, "token", token)?;
        Self::set_config(&self.conn, "usuario_json", &usuario_json)?;
        Ok(())
    }

    pub fn carregar_sessao(&self) -> Result<Option<(String, String, Usuario)>, String> {
        let Some(url) = self.get_config("url_servidor")? else {
            return Ok(None);
        };
        let Some(token) = self.get_config("token")? else {
            return Ok(None);
        };
        let Some(usuario_json) = self.get_config("usuario_json")? else {
            return Ok(None);
        };
        let usuario: Usuario = serde_json::from_str(&usuario_json)
            .map_err(|e| format!("Sessão local corrompida: {e}"))?;
        Ok(Some((url, token, usuario)))
    }

    pub fn limpar_sessao(&mut self) -> Result<(), String> {
        let tx = self
            .conn
            .transaction()
            .map_err(|e| format!("Erro ao iniciar transação: {e}"))?;
        tx.execute(
            "DELETE FROM config WHERE chave IN ('token', 'usuario_json', 'ultima_sync', 'ultimo_estado_remoto')",
            [],
        )
        .map_err(|e| format!("Erro ao limpar sessão: {e}"))?;
        tx.execute("DELETE FROM orientacoes", [])
            .map_err(|e| format!("Erro ao limpar orientações: {e}"))?;
        tx.execute("DELETE FROM marcos", [])
            .map_err(|e| format!("Erro ao limpar marcos: {e}"))?;
        tx.execute("DELETE FROM documentos", [])
            .map_err(|e| format!("Erro ao limpar documentos: {e}"))?;
        tx.execute("DELETE FROM atas", [])
            .map_err(|e| format!("Erro ao limpar atas: {e}"))?;
        tx.execute("DELETE FROM pareceres", [])
            .map_err(|e| format!("Erro ao limpar pareceres: {e}"))?;
        tx.execute("DELETE FROM fila_operacoes", [])
            .map_err(|e| format!("Erro ao limpar fila: {e}"))?;
        tx.commit()
            .map_err(|e| format!("Erro ao confirmar limpeza: {e}"))?;
        Ok(())
    }

    pub fn aplicar_estado_remoto(&mut self, estado: &EstadoSync) -> Result<(), String> {
        let tx = self
            .conn
            .transaction()
            .map_err(|e| format!("Erro ao iniciar transação: {e}"))?;
        Self::gravar_estado_na_transacao(&tx, estado)?;
        Self::reaplicar_fila(&tx)?;
        tx.commit()
            .map_err(|e| format!("Erro ao confirmar estado remoto: {e}"))?;
        Ok(())
    }

    pub fn concluir_sincronizacao(
        &mut self,
        resultados: &[ResultadoOperacao],
        estado: &EstadoSync,
    ) -> Result<Vec<ResultadoOperacao>, String> {
        let tx = self
            .conn
            .transaction()
            .map_err(|e| format!("Erro ao iniciar transação: {e}"))?;

        let mut falhas = Vec::new();
        for res in resultados {
            if res.status == "ok" || res.status == "ja_aplicada" {
                tx.execute(
                    "DELETE FROM fila_operacoes WHERE op_id = ?1",
                    params![res.op_id],
                )
                .map_err(|e| format!("Erro ao remover operação confirmada: {e}"))?;
            } else {
                falhas.push(res.clone());
            }
        }

        Self::gravar_estado_na_transacao(&tx, estado)?;
        Self::reaplicar_fila(&tx)?;
        tx.commit()
            .map_err(|e| format!("Erro ao concluir sincronização: {e}"))?;
        Ok(falhas)
    }

    fn gravar_estado_na_transacao(conn: &Connection, estado: &EstadoSync) -> Result<(), String> {
        let usuario_json = serde_json::to_string(&estado.usuario)
            .map_err(|e| format!("Erro ao serializar usuário: {e}"))?;
        Self::set_config(conn, "usuario_json", &usuario_json)?;
        Self::set_config(conn, "ultima_sync", &estado.sincronizado_em)?;
        // Último estado confirmado pelo servidor: base para desfazer o efeito
        // otimista de uma operação descartada da fila sem precisar de rede.
        let snapshot = serde_json::to_string(estado)
            .map_err(|e| format!("Erro ao serializar estado remoto: {e}"))?;
        Self::set_config(conn, CHAVE_ESTADO_REMOTO, &snapshot)?;

        conn.execute("DELETE FROM orientacoes", [])
            .map_err(|e| format!("Erro ao atualizar orientações: {e}"))?;
        conn.execute("DELETE FROM marcos", [])
            .map_err(|e| format!("Erro ao atualizar marcos: {e}"))?;
        conn.execute("DELETE FROM documentos", [])
            .map_err(|e| format!("Erro ao atualizar documentos: {e}"))?;
        conn.execute("DELETE FROM atas", [])
            .map_err(|e| format!("Erro ao atualizar atas: {e}"))?;
        conn.execute("DELETE FROM pareceres", [])
            .map_err(|e| format!("Erro ao atualizar pareceres: {e}"))?;

        for o in &estado.orientacoes {
            conn.execute(
                "INSERT INTO orientacoes (
                    id, orientador_id, orientador_nome, orientando_id, orientando_nome,
                    modalidade, titulo_projeto, data_inicio, data_fim_prevista, status
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
                params![
                    o.id,
                    o.orientador_id,
                    o.orientador_nome,
                    o.orientando_id,
                    o.orientando_nome,
                    o.modalidade,
                    o.titulo_projeto,
                    o.data_inicio,
                    o.data_fim_prevista,
                    o.status
                ],
            )
            .map_err(|e| format!("Erro ao gravar orientação #{}: {e}", o.id))?;
        }

        for m in &estado.marcos {
            conn.execute(
                "INSERT INTO marcos (
                    id, orientacao_id, titulo, descricao, data_prevista, data_conclusao,
                    status, tipo, etapa, conclusao_sinalizada, nota_conclusao,
                    devolvido_em, nota_devolucao, grupo_id, entrega_esperada, aguardando, criado_em,
                    documento_base_id
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)",
                params![
                    m.id,
                    m.orientacao_id,
                    m.titulo,
                    m.descricao,
                    m.data_prevista,
                    m.data_conclusao,
                    m.status,
                    m.tipo,
                    m.etapa,
                    m.conclusao_sinalizada,
                    m.nota_conclusao,
                    m.devolvido_em,
                    m.nota_devolucao,
                    m.grupo_id,
                    m.entrega_esperada,
                    m.aguardando,
                    m.criado_em,
                    m.documento_base_id
                ],
            )
            .map_err(|e| format!("Erro ao gravar marco #{}: {e}", m.id))?;
        }

        for a in &estado.atas {
            let orientacao_ids_json = serde_json::to_string(&a.orientacao_ids)
                .map_err(|e| format!("Erro ao serializar orientacao_ids: {e}"))?;
            let marco_ids_json = serde_json::to_string(&a.marco_ids)
                .map_err(|e| format!("Erro ao serializar marco_ids: {e}"))?;
            let participacoes_json = serde_json::to_string(&a.participacoes)
                .map_err(|e| format!("Erro ao serializar participacoes: {e}"))?;
            conn.execute(
                "INSERT INTO atas (
                    id, tipo, orientador_id, data_reuniao, hora_reuniao, link_reuniao,
                    pauta, deliberacoes, status, formato, finalizada_em, cancelada_em,
                    motivo_cancelamento, criada_em, orientacao_ids_json, marco_ids_json, participacoes_json
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)",
                params![
                    a.id,
                    a.tipo,
                    a.orientador_id,
                    a.data_reuniao,
                    a.hora_reuniao,
                    a.link_reuniao,
                    a.pauta,
                    a.deliberacoes,
                    a.status,
                    a.formato,
                    a.finalizada_em,
                    a.cancelada_em,
                    a.motivo_cancelamento,
                    a.criada_em,
                    orientacao_ids_json,
                    marco_ids_json,
                    participacoes_json
                ],
            )
            .map_err(|e| format!("Erro ao gravar ata #{}: {e}", a.id))?;
        }

        for d in &estado.documentos {
            let dados_json = serde_json::to_string(d)
                .map_err(|e| format!("Erro ao serializar documento #{}: {e}", d.id))?;
            conn.execute(
                "INSERT INTO documentos (id, orientacao_id, dados_json) VALUES (?1, ?2, ?3)",
                params![d.id, d.orientacao_id, dados_json],
            )
            .map_err(|e| format!("Erro ao gravar documento #{}: {e}", d.id))?;
        }

        for p in &estado.pareceres {
            conn.execute(
                "INSERT INTO pareceres (
                    id, orientacao_id, versao_documento_id, documento_id, documento_titulo,
                    numero_versao, nome_arquivo, marco_id, marco_titulo, tipo, conteudo,
                    resultado, emitido_por, emissor_nome, emitido_em, formato
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
                params![
                    p.id,
                    p.orientacao_id,
                    p.versao_documento_id,
                    p.documento_id,
                    p.documento_titulo,
                    p.numero_versao,
                    p.nome_arquivo,
                    p.marco_id,
                    p.marco_titulo,
                    p.tipo,
                    p.conteudo,
                    p.resultado,
                    p.emitido_por,
                    p.emissor_nome,
                    p.emitido_em,
                    p.formato
                ],
            )
            .map_err(|e| format!("Erro ao gravar parecer #{}: {e}", p.id))?;
        }

        Ok(())
    }

    pub fn enfileirar_operacao(&mut self, acao: &str, dados: Value) -> Result<String, String> {
        let op_id = Uuid::new_v4().to_string();
        let dados_json = serde_json::to_string(&dados)
            .map_err(|e| format!("Erro ao serializar operação: {e}"))?;

        let tx = self
            .conn
            .transaction()
            .map_err(|e| format!("Erro ao iniciar transação: {e}"))?;
        tx.execute(
            "INSERT INTO fila_operacoes (op_id, acao, dados_json, criada_em)
             VALUES (?1, ?2, ?3, datetime('now'))",
            params![op_id, acao, dados_json],
        )
        .map_err(|e| format!("Erro ao enfileirar operação: {e}"))?;

        Self::aplicar_otimista(&tx, acao, &dados)?;
        tx.commit()
            .map_err(|e| format!("Erro ao confirmar operação offline: {e}"))?;
        Ok(op_id)
    }

    fn proximo_id_temporario(conn: &Connection, tabela: &str) -> Result<i64, String> {
        let sql = format!("SELECT COALESCE(MIN(id), 0) FROM {tabela}");
        let min_id: i64 = conn
            .query_row(&sql, [], |r| r.get(0))
            .map_err(|e| format!("Erro ao gerar ID temporário em {tabela}: {e}"))?;
        Ok(if min_id <= 0 { min_id - 1 } else { -1 })
    }

    fn aplicar_otimista(conn: &Connection, acao: &str, dados: &Value) -> Result<(), String> {
        match acao {
            "sinalizar_conclusao_marco" => {
                if let Some(marco_id) = dados.get("marco_id").and_then(Value::as_i64) {
                    let nota = dados
                        .get("nota")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    conn.execute(
                        "UPDATE marcos
                         SET conclusao_sinalizada = 1,
                             status = 'em_andamento',
                             nota_conclusao = COALESCE(?2, nota_conclusao),
                             aguardando = 'orientador'
                         WHERE id = ?1",
                        params![marco_id, nota],
                    )
                    .map_err(|e| format!("Erro ao atualizar marco local: {e}"))?;
                }
            }
            "confirmar_conclusao_marco" => {
                if let Some(marco_id) = dados.get("marco_id").and_then(Value::as_i64) {
                    conn.execute(
                        "UPDATE marcos
                         SET status = 'concluido',
                             data_conclusao = COALESCE(data_conclusao, date('now', 'localtime')),
                             aguardando = NULL
                         WHERE id = ?1",
                        params![marco_id],
                    )
                    .map_err(|e| format!("Erro ao confirmar marco local: {e}"))?;
                }
            }
            "devolver_marco" => {
                if let Some(marco_id) = dados.get("marco_id").and_then(Value::as_i64) {
                    let nota = dados
                        .get("nota")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    conn.execute(
                        "UPDATE marcos
                         SET conclusao_sinalizada = 0,
                             status = 'em_andamento',
                             devolvido_em = datetime('now'),
                             nota_devolucao = ?2,
                             aguardando = 'orientando_revisao'
                         WHERE id = ?1",
                        params![marco_id, nota],
                    )
                    .map_err(|e| format!("Erro ao devolver marco local: {e}"))?;
                }
            }
            "criar_tarefa" => {
                let ids: Vec<i64> = dados
                    .get("orientacao_ids")
                    .and_then(Value::as_array)
                    .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
                    .unwrap_or_default();
                let titulo = dados
                    .get("titulo")
                    .and_then(Value::as_str)
                    .unwrap_or("Nova tarefa");
                let tipo = dados
                    .get("tipo")
                    .and_then(Value::as_str)
                    .unwrap_or("outro");
                let descricao = dados
                    .get("descricao")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|s| !s.is_empty());
                let data_prevista = dados
                    .get("data_prevista")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let etapa = dados.get("etapa").and_then(Value::as_i64).unwrap_or(0);
                let entrega = dados
                    .get("entrega_esperada")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|s| !s.is_empty());
                let grupo_id = if ids.len() > 1 {
                    Some(Uuid::new_v4().simple().to_string())
                } else {
                    None
                };
                for oid in ids {
                    let temp_id = Self::proximo_id_temporario(conn, "marcos")?;
                    conn.execute(
                        "INSERT INTO marcos (
                            id, orientacao_id, titulo, descricao, data_prevista, data_conclusao,
                            status, tipo, etapa, conclusao_sinalizada, nota_conclusao,
                            devolvido_em, nota_devolucao, grupo_id, entrega_esperada, aguardando, criado_em
                         ) VALUES (?1, ?2, ?3, ?4, ?5, NULL, 'pendente', ?6, ?7, 0, NULL, NULL, NULL, ?8, ?9, 'orientando', datetime('now'))",
                        params![
                            temp_id,
                            oid,
                            titulo,
                            descricao,
                            data_prevista,
                            tipo,
                            etapa,
                            grupo_id,
                            entrega
                        ],
                    )
                    .map_err(|e| format!("Erro ao inserir marco local: {e}"))?;
                }
            }
            "editar_marco" => {
                if let Some(marco_id) = dados.get("marco_id").and_then(Value::as_i64) {
                    let titulo = dados.get("titulo").and_then(Value::as_str);
                    let tipo = dados.get("tipo").and_then(Value::as_str);
                    let descricao = dados
                        .get("descricao")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    let data_prevista = dados.get("data_prevista").and_then(Value::as_str);
                    let etapa = dados.get("etapa").and_then(Value::as_i64);
                    let entrega = dados
                        .get("entrega_esperada")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    conn.execute(
                        "UPDATE marcos
                         SET titulo = COALESCE(?2, titulo),
                             tipo = COALESCE(?3, tipo),
                             descricao = ?4,
                             data_prevista = COALESCE(?5, data_prevista),
                             etapa = COALESCE(?6, etapa),
                             entrega_esperada = ?7
                         WHERE id = ?1",
                        params![
                            marco_id,
                            titulo,
                            tipo,
                            descricao,
                            data_prevista,
                            etapa,
                            entrega
                        ],
                    )
                    .map_err(|e| format!("Erro ao editar marco local: {e}"))?;
                }
            }
            "agendar_reuniao" => {
                let ids: Vec<i64> = dados
                    .get("orientacao_ids")
                    .and_then(Value::as_array)
                    .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
                    .unwrap_or_default();
                let temp_id = Self::proximo_id_temporario(conn, "atas")?;
                let tipo = if ids.len() > 1 { "grupo" } else { "individual" };
                let data_reuniao = dados
                    .get("data_reuniao")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let hora_reuniao = dados
                    .get("hora_reuniao")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|s| !s.is_empty());
                let link_reuniao = dados
                    .get("link_reuniao")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|s| !s.is_empty());
                let pauta = dados.get("pauta").and_then(Value::as_str).unwrap_or("");
                let participacoes: Vec<ParticipacaoAta> = ids
                    .iter()
                    .map(|&oid| ParticipacaoAta {
                        orientacao_id: oid,
                        presenca: "pendente".to_string(),
                        presenca_registrada_em: None,
                    })
                    .collect();
                let oid_json = serde_json::to_string(&ids).unwrap_or_else(|_| "[]".to_string());
                let part_json =
                    serde_json::to_string(&participacoes).unwrap_or_else(|_| "[]".to_string());
                conn.execute(
                    "INSERT INTO atas (
                        id, tipo, orientador_id, data_reuniao, hora_reuniao, link_reuniao,
                        pauta, deliberacoes, status, formato, finalizada_em, cancelada_em,
                        motivo_cancelamento, criada_em, orientacao_ids_json, marco_ids_json, participacoes_json
                     ) VALUES (?1, ?2, 0, ?3, ?4, ?5, ?6, '', 'rascunho', 'markdown', NULL, NULL, NULL, datetime('now'), ?7, '[]', ?8)",
                    params![
                        temp_id,
                        tipo,
                        data_reuniao,
                        hora_reuniao,
                        link_reuniao,
                        pauta,
                        oid_json,
                        part_json
                    ],
                )
                .map_err(|e| format!("Erro ao inserir reunião local: {e}"))?;
            }
            "atualizar_ata" => {
                if let Some(ata_id) = dados.get("ata_id").and_then(Value::as_i64) {
                    let pauta = dados.get("pauta").and_then(Value::as_str);
                    let deliberacoes = dados.get("deliberacoes").and_then(Value::as_str);
                    let link_informado = dados.get("link_reuniao").is_some();
                    let link = dados
                        .get("link_reuniao")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    if link_informado {
                        conn.execute(
                            "UPDATE atas
                             SET pauta = COALESCE(?2, pauta),
                                 deliberacoes = COALESCE(?3, deliberacoes),
                                 link_reuniao = ?4
                             WHERE id = ?1",
                            params![ata_id, pauta, deliberacoes, link],
                        )
                        .map_err(|e| format!("Erro ao atualizar ata local: {e}"))?;
                    } else {
                        conn.execute(
                            "UPDATE atas
                             SET pauta = COALESCE(?2, pauta),
                                 deliberacoes = COALESCE(?3, deliberacoes)
                             WHERE id = ?1",
                            params![ata_id, pauta, deliberacoes],
                        )
                        .map_err(|e| format!("Erro ao atualizar ata local: {e}"))?;
                    }
                    if let Some(marco_ids) = dados.get("marco_ids").and_then(Value::as_array) {
                        let m_json = serde_json::to_string(marco_ids)
                            .unwrap_or_else(|_| "[]".to_string());
                        conn.execute(
                            "UPDATE atas SET marco_ids_json = ?2 WHERE id = ?1",
                            params![ata_id, m_json],
                        )
                        .map_err(|e| format!("Erro ao atualizar marcos da ata: {e}"))?;
                    }
                }
            }
            "registrar_presenca" => {
                if let (Some(ata_id), Some(oid), Some(presenca)) = (
                    dados.get("ata_id").and_then(Value::as_i64),
                    dados.get("orientacao_id").and_then(Value::as_i64),
                    dados.get("presenca").and_then(Value::as_str),
                ) {
                    let atual_json: Option<String> = conn
                        .query_row(
                            "SELECT participacoes_json FROM atas WHERE id = ?1",
                            params![ata_id],
                            |r| r.get(0),
                        )
                        .optional()
                        .map_err(|e| format!("Erro ao ler participações: {e}"))?;
                    if let Some(txt) = atual_json {
                        if let Ok(mut lista) = serde_json::from_str::<Vec<ParticipacaoAta>>(&txt) {
                            for p in &mut lista {
                                if p.orientacao_id == oid {
                                    p.presenca = presenca.to_string();
                                }
                            }
                            if let Ok(novo_json) = serde_json::to_string(&lista) {
                                conn.execute(
                                    "UPDATE atas SET participacoes_json = ?2 WHERE id = ?1",
                                    params![ata_id, novo_json],
                                )
                                .map_err(|e| format!("Erro ao gravar presença local: {e}"))?;
                            }
                        }
                    }
                }
            }
            "reagendar_ata" => {
                if let Some(ata_id) = dados.get("ata_id").and_then(Value::as_i64) {
                    let data_nova = dados.get("data_nova").and_then(Value::as_str);
                    let hora_nova = dados
                        .get("hora_nova")
                        .and_then(Value::as_str)
                        .map(str::trim)
                        .filter(|s| !s.is_empty());
                    conn.execute(
                        "UPDATE atas
                         SET data_reuniao = COALESCE(?2, data_reuniao),
                             hora_reuniao = ?3
                         WHERE id = ?1",
                        params![ata_id, data_nova, hora_nova],
                    )
                    .map_err(|e| format!("Erro ao reagendar ata local: {e}"))?;
                }
            }
            "cancelar_reuniao" => {
                if let Some(ata_id) = dados.get("ata_id").and_then(Value::as_i64) {
                    let motivo = dados.get("motivo").and_then(Value::as_str).unwrap_or("");
                    conn.execute(
                        "UPDATE atas
                         SET status = 'cancelada',
                             cancelada_em = datetime('now'),
                             motivo_cancelamento = ?2
                         WHERE id = ?1",
                        params![ata_id, motivo],
                    )
                    .map_err(|e| format!("Erro ao cancelar reunião local: {e}"))?;
                }
            }
            "finalizar_ata" => {
                if let Some(ata_id) = dados.get("ata_id").and_then(Value::as_i64) {
                    conn.execute(
                        "UPDATE atas
                         SET status = 'finalizada',
                             finalizada_em = datetime('now')
                         WHERE id = ?1",
                        params![ata_id],
                    )
                    .map_err(|e| format!("Erro ao finalizar ata local: {e}"))?;
                }
            }
            "emitir_parecer" => {
                let temp_id = Self::proximo_id_temporario(conn, "pareceres")?;
                let oid = dados
                    .get("orientacao_id")
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
                let versao_id = dados
                    .get("versao_documento_id")
                    .and_then(Value::as_i64)
                    .filter(|&id| id > 0);
                let doc_info = versao_id.and_then(|vid| Self::buscar_versao_local(conn, oid, vid));
                let mut tipo = dados
                    .get("tipo")
                    .and_then(Value::as_str)
                    .unwrap_or(if versao_id.is_some() { "documento" } else { "andamento" });
                if tipo.trim().is_empty() {
                    tipo = if versao_id.is_some() { "documento" } else { "andamento" };
                }
                let resultado = dados
                    .get("resultado")
                    .and_then(Value::as_str)
                    .unwrap_or("aprovado");
                let conteudo = dados.get("conteudo").and_then(Value::as_str).unwrap_or("");
                let (emitido_por, emissor_nome) = Self::usuario_local(conn);

                let (doc_id, doc_titulo, num_versao, nome_arq, marco_id, marco_titulo) =
                    if let Some((ref doc, ref versao)) = doc_info {
                        (
                            Some(doc.id),
                            Some(doc.titulo.clone()),
                            Some(versao.numero_versao),
                            versao.nome_original.clone(),
                            doc.marco_id.or(versao.marco_aberto_id),
                            doc.marco_titulo.clone().or_else(|| versao.marco_aberto_titulo.clone()),
                        )
                    } else {
                        (None, None, None, None, None, None)
                    };

                conn.execute(
                    "INSERT INTO pareceres (
                        id, orientacao_id, versao_documento_id, documento_id, documento_titulo,
                        numero_versao, nome_arquivo, marco_id, marco_titulo, tipo, conteudo,
                        resultado, emitido_por, emissor_nome, emitido_em, formato
                     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, datetime('now'), 'markdown')",
                    params![
                        temp_id,
                        oid,
                        versao_id,
                        doc_id,
                        doc_titulo,
                        num_versao,
                        nome_arq,
                        marco_id,
                        marco_titulo,
                        tipo,
                        conteudo,
                        resultado,
                        emitido_por,
                        emissor_nome
                    ],
                )
                .map_err(|e| format!("Erro ao inserir parecer local: {e}"))?;

                let concluir_marco = dados
                    .get("concluir_marco")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                if let Some(mid) = marco_id {
                    if concluir_marco && (resultado == "aprovado" || resultado == "aprovado_com_ressalvas") {
                        conn.execute(
                            "UPDATE marcos
                             SET status = 'concluido',
                                 data_conclusao = COALESCE(data_conclusao, date('now', 'localtime')),
                                 aguardando = NULL
                             WHERE id = ?1",
                            params![mid],
                        )
                        .map_err(|e| format!("Erro ao concluir marco pelo parecer local: {e}"))?;
                    } else if resultado == "reprovado" {
                        conn.execute(
                            "UPDATE marcos
                             SET conclusao_sinalizada = 0,
                                 status = 'em_andamento',
                                 devolvido_em = datetime('now'),
                                 nota_devolucao = ?2,
                                 aguardando = 'orientando_revisao'
                             WHERE id = ?1 AND status != 'concluido'",
                            params![mid, conteudo],
                        )
                        .map_err(|e| format!("Erro ao devolver marco pelo parecer local: {e}"))?;
                    }
                }
            }
            _ => {}
        }
        Ok(())
    }

    fn buscar_versao_local(
        conn: &Connection,
        orientacao_id: i64,
        versao_id: i64,
    ) -> Option<(Documento, crate::models::VersaoDocumento)> {
        let mut stmt = conn
            .prepare("SELECT dados_json FROM documentos WHERE orientacao_id = ?1")
            .ok()?;
        let rows = stmt
            .query_map(params![orientacao_id], |row| row.get::<_, String>(0))
            .ok()?;
        for raw in rows.flatten() {
            if let Ok(doc) = serde_json::from_str::<Documento>(&raw) {
                if let Some(v) = doc.versoes.iter().find(|v| v.id == versao_id).cloned() {
                    return Some((doc, v));
                }
            }
        }
        None
    }

    fn usuario_local(conn: &Connection) -> (i64, Option<String>) {
        let json_opt: Option<String> = conn
            .query_row(
                "SELECT valor FROM config WHERE chave = 'usuario_json'",
                [],
                |row| row.get(0),
            )
            .optional()
            .ok()
            .flatten();
        if let Some(txt) = json_opt {
            if let Ok(u) = serde_json::from_str::<Usuario>(&txt) {
                return (u.id, Some(u.nome));
            }
        }
        (0, None)
    }

    pub fn listar_operacoes(&self) -> Result<Vec<OperacaoSync>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT op_id, acao, dados_json FROM fila_operacoes ORDER BY seq ASC")
            .map_err(|e| format!("Erro ao preparar consulta da fila: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                let op_id: String = row.get(0)?;
                let acao: String = row.get(1)?;
                let dados_json: String = row.get(2)?;
                let dados: Value = serde_json::from_str(&dados_json).unwrap_or_else(|_| json!({}));
                Ok(OperacaoSync { op_id, acao, dados })
            })
            .map_err(|e| format!("Erro ao ler fila: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar fila: {e}"))
    }

    pub fn listar_itens_fila(&self) -> Result<Vec<ItemFila>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT seq, op_id, acao, dados_json, criada_em
                 FROM fila_operacoes ORDER BY seq ASC",
            )
            .map_err(|e| format!("Erro ao consultar itens da fila: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                Ok(ItemFila {
                    seq: row.get(0)?,
                    op_id: row.get(1)?,
                    acao: row.get(2)?,
                    dados_json: row.get(3)?,
                    criada_em: row.get(4)?,
                })
            })
            .map_err(|e| format!("Erro ao ler itens da fila: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar itens da fila: {e}"))
    }

    pub fn contar_fila(&self) -> Result<usize, String> {
        let count: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM fila_operacoes", [], |r| r.get(0))
            .map_err(|e| format!("Erro ao contar fila: {e}"))?;
        Ok(count.max(0) as usize)
    }

    /// Remove a operação da fila e desfaz o seu efeito local: o estado volta ao
    /// último retrato confirmado pelo servidor e as operações que continuam na
    /// fila são reaplicadas, na ordem. Retorna `false` quando não há retrato
    /// guardado (instalação anterior a esta versão) — aí só a fila é alterada e
    /// a próxima sincronização corrige a tela.
    pub fn descartar_operacao(&mut self, op_id: &str) -> Result<bool, String> {
        let tx = self
            .conn
            .transaction()
            .map_err(|e| format!("Erro ao iniciar transação: {e}"))?;
        tx.execute("DELETE FROM fila_operacoes WHERE op_id = ?1", params![op_id])
            .map_err(|e| format!("Erro ao descartar operação: {e}"))?;
        let snapshot: Option<String> = tx
            .query_row(
                "SELECT valor FROM config WHERE chave = ?1",
                params![CHAVE_ESTADO_REMOTO],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| format!("Erro ao ler estado remoto guardado: {e}"))?;
        let estado: Option<EstadoSync> =
            snapshot.and_then(|s| serde_json::from_str(&s).ok());
        let restaurado = if let Some(estado) = estado {
            Self::gravar_estado_na_transacao(&tx, &estado)?;
            Self::reaplicar_fila(&tx)?;
            true
        } else {
            false
        };
        tx.commit()
            .map_err(|e| format!("Erro ao confirmar descarte: {e}"))?;
        Ok(restaurado)
    }

    /// Reaplica, na ordem, o efeito otimista das operações ainda na fila sobre
    /// o estado recém-gravado — a tela continua refletindo o que o usuário fez
    /// e ainda não foi enviado.
    fn reaplicar_fila(conn: &Connection) -> Result<(), String> {
        let mut stmt = conn
            .prepare("SELECT acao, dados_json FROM fila_operacoes ORDER BY seq ASC")
            .map_err(|e| format!("Erro ao preparar consulta da fila: {e}"))?;
        let ops = stmt
            .query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)))
            .map_err(|e| format!("Erro ao ler fila: {e}"))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar fila: {e}"))?;
        for (acao, dados_json) in ops {
            let dados: Value = serde_json::from_str(&dados_json).unwrap_or_else(|_| json!({}));
            Self::aplicar_otimista(conn, &acao, &dados)?;
        }
        Ok(())
    }

    pub fn listar_orientacoes(&self) -> Result<Vec<Orientacao>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT id, orientador_id, orientador_nome, orientando_id, orientando_nome,
                        modalidade, titulo_projeto, data_inicio, data_fim_prevista, status
                 FROM orientacoes ORDER BY titulo_projeto ASC, id ASC",
            )
            .map_err(|e| format!("Erro ao consultar orientações: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                Ok(Orientacao {
                    id: row.get(0)?,
                    orientador_id: row.get(1)?,
                    orientador_nome: row.get(2)?,
                    orientando_id: row.get(3)?,
                    orientando_nome: row.get(4)?,
                    modalidade: row.get(5)?,
                    titulo_projeto: row.get(6)?,
                    data_inicio: row.get(7)?,
                    data_fim_prevista: row.get(8)?,
                    status: row.get(9)?,
                })
            })
            .map_err(|e| format!("Erro ao ler orientações: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar orientações: {e}"))
    }

    pub fn listar_marcos(&self) -> Result<Vec<Marco>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT id, orientacao_id, titulo, descricao, data_prevista, data_conclusao,
                        status, tipo, etapa, conclusao_sinalizada, nota_conclusao,
                        devolvido_em, nota_devolucao, grupo_id, entrega_esperada, aguardando, criado_em,
                        documento_base_id
                 FROM marcos ORDER BY data_prevista ASC, etapa ASC, id ASC",
            )
            .map_err(|e| format!("Erro ao consultar marcos: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                Ok(Marco {
                    id: row.get(0)?,
                    orientacao_id: row.get(1)?,
                    titulo: row.get(2)?,
                    descricao: row.get(3)?,
                    data_prevista: row.get(4)?,
                    data_conclusao: row.get(5)?,
                    status: row.get(6)?,
                    tipo: row.get(7)?,
                    etapa: row.get(8)?,
                    conclusao_sinalizada: row.get(9)?,
                    nota_conclusao: row.get(10)?,
                    devolvido_em: row.get(11)?,
                    nota_devolucao: row.get(12)?,
                    grupo_id: row.get(13)?,
                    entrega_esperada: row.get(14)?,
                    aguardando: row.get(15)?,
                    criado_em: row.get(16)?,
                    documento_base_id: row.get(17)?,
                })
            })
            .map_err(|e| format!("Erro ao ler marcos: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar marcos: {e}"))
    }

    pub fn listar_atas(&self) -> Result<Vec<Ata>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT id, tipo, orientador_id, data_reuniao, hora_reuniao, link_reuniao,
                        pauta, deliberacoes, status, formato, finalizada_em, cancelada_em,
                        motivo_cancelamento, criada_em, orientacao_ids_json, marco_ids_json, participacoes_json
                 FROM atas ORDER BY data_reuniao DESC, id DESC",
            )
            .map_err(|e| format!("Erro ao consultar atas: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                let oid_json: String = row.get(14)?;
                let mid_json: String = row.get(15)?;
                let part_json: String = row.get(16)?;
                Ok(Ata {
                    id: row.get(0)?,
                    tipo: row.get(1)?,
                    orientador_id: row.get(2)?,
                    data_reuniao: row.get(3)?,
                    hora_reuniao: row.get(4)?,
                    link_reuniao: row.get(5)?,
                    pauta: row.get(6)?,
                    deliberacoes: row.get(7)?,
                    status: row.get(8)?,
                    formato: row.get(9)?,
                    finalizada_em: row.get(10)?,
                    cancelada_em: row.get(11)?,
                    motivo_cancelamento: row.get(12)?,
                    criada_em: row.get(13)?,
                    orientacao_ids: serde_json::from_str(&oid_json).unwrap_or_default(),
                    marco_ids: serde_json::from_str(&mid_json).unwrap_or_default(),
                    participacoes: serde_json::from_str(&part_json).unwrap_or_default(),
                })
            })
            .map_err(|e| format!("Erro ao ler atas: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar atas: {e}"))
    }

    pub fn listar_documentos(&self) -> Result<Vec<Documento>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT dados_json FROM documentos ORDER BY id DESC")
            .map_err(|e| format!("Erro ao consultar documentos: {e}"))?;
        let rows = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(|e| format!("Erro ao ler documentos: {e}"))?;
        let mut docs = Vec::new();
        for raw in rows {
            let txt = raw.map_err(|e| format!("Erro ao iterar documentos: {e}"))?;
            if let Ok(doc) = serde_json::from_str::<Documento>(&txt) {
                docs.push(doc);
            }
        }
        Ok(docs)
    }

    pub fn listar_pareceres(&self) -> Result<Vec<Parecer>, String> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT id, orientacao_id, versao_documento_id, documento_id, documento_titulo,
                        numero_versao, nome_arquivo, marco_id, marco_titulo, tipo, conteudo,
                        resultado, emitido_por, emissor_nome, emitido_em, formato
                 FROM pareceres ORDER BY emitido_em DESC, id DESC",
            )
            .map_err(|e| format!("Erro ao consultar pareceres: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                Ok(Parecer {
                    id: row.get(0)?,
                    orientacao_id: row.get(1)?,
                    versao_documento_id: row.get(2)?,
                    documento_id: row.get(3)?,
                    documento_titulo: row.get(4)?,
                    numero_versao: row.get(5)?,
                    nome_arquivo: row.get(6)?,
                    marco_id: row.get(7)?,
                    marco_titulo: row.get(8)?,
                    tipo: row.get(9)?,
                    conteudo: row.get(10)?,
                    resultado: row.get(11)?,
                    emitido_por: row.get(12)?,
                    emissor_nome: row.get(13)?,
                    emitido_em: row.get(14)?,
                    formato: row.get(15)?,
                })
            })
            .map_err(|e| format!("Erro ao ler pareceres: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("Erro ao iterar pareceres: {e}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn estado_exemplo() -> EstadoSync {
        EstadoSync {
            usuario: Usuario {
                id: 1,
                nome: "Orientador Teste".to_string(),
                email: "orientador@teste.br".to_string(),
                papel: "orientador".to_string(),
            },
            orientacoes: vec![Orientacao {
                id: 10,
                orientador_id: 1,
                orientador_nome: "Orientador Teste".to_string(),
                orientando_id: 2,
                orientando_nome: "Maria Aluna".to_string(),
                modalidade: "mestrado".to_string(),
                titulo_projeto: "Dissertação Exemplo".to_string(),
                data_inicio: "2026-01-10".to_string(),
                data_fim_prevista: Some("2028-01-10".to_string()),
                status: "ativa".to_string(),
            }],
            marcos: vec![Marco {
                id: 100,
                orientacao_id: 10,
                titulo: "Qualificação".to_string(),
                descricao: Some("Texto preliminar".to_string()),
                data_prevista: "2026-12-01".to_string(),
                data_conclusao: None,
                status: "pendente".to_string(),
                tipo: "qualificacao".to_string(),
                etapa: 40,
                conclusao_sinalizada: false,
                nota_conclusao: None,
                devolvido_em: None,
                nota_devolucao: None,
                grupo_id: None,
                entrega_esperada: Some("documento".to_string()),
                aguardando: Some("orientando".to_string()),
                criado_em: Some("2026-01-10T10:00:00".to_string()),
                documento_base_id: None,
            }],
            documentos: vec![Documento {
                id: 300,
                orientacao_id: 10,
                marco_id: Some(100),
                marco_titulo: Some("Qualificação".to_string()),
                titulo: "Texto de Qualificação".to_string(),
                criado_em: Some("2026-11-10T10:00:00".to_string()),
                versoes: vec![crate::models::VersaoDocumento {
                    id: 301,
                    documento_id: 300,
                    numero_versao: 1,
                    nome_original: Some("qualificacao-v1.pdf".to_string()),
                    tem_arquivo: true,
                    enviado_por: 2,
                    remetente_nome: "Maria Aluna".to_string(),
                    enviado_em: Some("2026-11-10T10:05:00".to_string()),
                    comentario: Some("Primeira versão".to_string()),
                    natureza: "entrega".to_string(),
                    marco_aberto_id: Some(100),
                    marco_aberto_titulo: Some("Qualificação".to_string()),
                }],
            }],
            atas: vec![Ata {
                id: 200,
                tipo: "individual".to_string(),
                orientador_id: 1,
                data_reuniao: "2026-11-16".to_string(),
                hora_reuniao: Some("14:00".to_string()),
                link_reuniao: None,
                pauta: "Revisão do cronograma".to_string(),
                deliberacoes: "".to_string(),
                status: "rascunho".to_string(),
                formato: "markdown".to_string(),
                finalizada_em: None,
                cancelada_em: None,
                motivo_cancelamento: None,
                criada_em: Some("2026-11-10T12:00:00".to_string()),
                orientacao_ids: vec![10],
                marco_ids: vec![100],
                participacoes: vec![ParticipacaoAta {
                    orientacao_id: 10,
                    presenca: "pendente".to_string(),
                    presenca_registrada_em: None,
                }],
            }],
            pareceres: vec![],
            sincronizado_em: "2026-11-16T18:00:00".to_string(),
        }
    }

    #[test]
    fn sessao_e_estado_remoto_funcionam() {
        let mut repo = RepositorioLocal::em_memoria().unwrap();
        let estado = estado_exemplo();
        repo.salvar_sessao("https://exemplo.pythonanywhere.com", "tok123", &estado.usuario)
            .unwrap();
        let (url, token, usr) = repo.carregar_sessao().unwrap().unwrap();
        assert_eq!(url, "https://exemplo.pythonanywhere.com");
        assert_eq!(token, "tok123");
        assert_eq!(usr.id, 1);

        repo.aplicar_estado_remoto(&estado).unwrap();
        assert_eq!(repo.listar_orientacoes().unwrap().len(), 1);
        assert_eq!(repo.listar_marcos().unwrap().len(), 1);
        assert_eq!(repo.listar_documentos().unwrap().len(), 1);
        assert_eq!(repo.listar_atas().unwrap().len(), 1);
    }

    #[test]
    fn emitir_parecer_otimista_associa_documento_e_conclui_marco() {
        let mut repo = RepositorioLocal::em_memoria().unwrap();
        let estado = estado_exemplo();
        repo.salvar_sessao("https://exemplo.pythonanywhere.com", "tok123", &estado.usuario)
            .unwrap();
        repo.aplicar_estado_remoto(&estado).unwrap();

        repo.enfileirar_operacao(
            "emitir_parecer",
            json!({
                "orientacao_id": 10,
                "versao_documento_id": 301,
                "resultado": "aprovado",
                "conteudo": "Aprovado para defesa de qualificação.",
                "concluir_marco": true
            }),
        )
        .unwrap();

        let pareceres = repo.listar_pareceres().unwrap();
        assert_eq!(pareceres.len(), 1);
        assert_eq!(pareceres[0].tipo, "documento");
        assert_eq!(pareceres[0].versao_documento_id, Some(301));
        assert_eq!(pareceres[0].documento_titulo.as_deref(), Some("Texto de Qualificação"));
        assert_eq!(pareceres[0].numero_versao, Some(1));
        assert_eq!(pareceres[0].marco_titulo.as_deref(), Some("Qualificação"));
        assert_eq!(pareceres[0].emissor_nome.as_deref(), Some("Orientador Teste"));

        let marcos = repo.listar_marcos().unwrap();
        assert_eq!(marcos[0].status, "concluido");
    }

    #[test]
    fn fila_offline_aplica_otimista_e_limpa_apos_sync() {
        let mut repo = RepositorioLocal::em_memoria().unwrap();
        let estado = estado_exemplo();
        repo.aplicar_estado_remoto(&estado).unwrap();

        let op1 = repo
            .enfileirar_operacao(
                "sinalizar_conclusao_marco",
                json!({"marco_id": 100, "nota": "Enviado"}),
            )
            .unwrap();
        let op2 = repo
            .enfileirar_operacao(
                "criar_tarefa",
                json!({
                    "orientacao_ids": [10],
                    "titulo": "Nova tarefa offline",
                    "tipo": "outro",
                    "data_prevista": "2026-12-20",
                    "etapa": 10,
                    "entrega_esperada": "ato"
                }),
            )
            .unwrap();

        assert_eq!(repo.contar_fila().unwrap(), 2);
        let marcos = repo.listar_marcos().unwrap();
        assert_eq!(marcos.len(), 2);
        let m100 = marcos.iter().find(|m| m.id == 100).unwrap();
        assert!(m100.conclusao_sinalizada);
        assert_eq!(m100.aguardando.as_deref(), Some("orientador"));

        let resultados = vec![
            ResultadoOperacao {
                op_id: op1,
                acao: "sinalizar_conclusao_marco".to_string(),
                status: "ok".to_string(),
                entidade: Some("marco".to_string()),
                entidade_id: Some(100),
                erro: None,
            },
            ResultadoOperacao {
                op_id: op2,
                acao: "criar_tarefa".to_string(),
                status: "erro".to_string(),
                entidade: None,
                entidade_id: None,
                erro: Some("Sem permissão".to_string()),
            },
        ];
        let falhas = repo.concluir_sincronizacao(&resultados, &estado).unwrap();
        assert_eq!(falhas.len(), 1);
        assert_eq!(repo.contar_fila().unwrap(), 1);
    }

    #[test]
    fn descartar_operacao_desfaz_efeito_otimista_e_preserva_as_demais() {
        let mut repo = RepositorioLocal::em_memoria().unwrap();
        let estado = estado_exemplo();
        repo.aplicar_estado_remoto(&estado).unwrap();

        let op_sinalizar = repo
            .enfileirar_operacao(
                "sinalizar_conclusao_marco",
                json!({"marco_id": 100, "nota": "sem querer"}),
            )
            .unwrap();
        repo.enfileirar_operacao(
            "criar_tarefa",
            json!({
                "orientacao_ids": [10],
                "titulo": "Tarefa que fica",
                "tipo": "outro",
                "data_prevista": "2026-12-20",
                "etapa": 10,
                "entrega_esperada": "ato"
            }),
        )
        .unwrap();
        let m100 = repo.listar_marcos().unwrap().into_iter().find(|m| m.id == 100).unwrap();
        assert!(m100.conclusao_sinalizada);

        assert!(repo.descartar_operacao(&op_sinalizar).unwrap());

        let marcos = repo.listar_marcos().unwrap();
        let m100 = marcos.iter().find(|m| m.id == 100).unwrap();
        assert!(!m100.conclusao_sinalizada);
        assert_eq!(m100.aguardando.as_deref(), Some("orientando"));
        assert_eq!(m100.status, "pendente");
        assert_eq!(m100.nota_conclusao, None);
        // a outra operação continua na fila e com efeito na tela
        assert_eq!(repo.contar_fila().unwrap(), 1);
        assert!(marcos.iter().any(|m| m.titulo == "Tarefa que fica" && m.id < 0));
    }

    #[test]
    fn descartar_sem_retrato_remoto_so_altera_a_fila() {
        let mut repo = RepositorioLocal::em_memoria().unwrap();
        let op = repo
            .enfileirar_operacao("sinalizar_conclusao_marco", json!({"marco_id": 1}))
            .unwrap();
        assert!(!repo.descartar_operacao(&op).unwrap());
        assert_eq!(repo.contar_fila().unwrap(), 0);
    }
}
