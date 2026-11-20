use std::time::Duration;

use reqwest::blocking::Client;
use serde_json::json;

use crate::db::RepositorioLocal;
use crate::models::{
    ErroApi, EstadoSync, OperacaoSync, PedidoEntrega, RespostaEntrega, RespostaPostSync,
    RespostaToken, ResultadoOperacao,
};

#[derive(Debug, Clone)]
pub struct ResumoSync {
    pub enviadas: usize,
    pub falhas: Vec<ResultadoOperacao>,
    pub sincronizado_em: String,
}

pub struct ClienteAriadne {
    http: Client,
}

impl ClienteAriadne {
    pub fn novo() -> Result<Self, String> {
        let http = Client::builder()
            .timeout(Duration::from_secs(25))
            .build()
            .map_err(|e| format!("Falha ao inicializar cliente HTTP: {e}"))?;
        Ok(Self { http })
    }

    fn normalizar_url(url_base: &str) -> Result<String, String> {
        let limpa = url_base.trim().trim_end_matches('/');
        if !(limpa.starts_with("https://") || limpa.starts_with("http://")) {
            return Err("Informe o endereço completo do servidor (https://...).".to_string());
        }
        Ok(limpa.to_string())
    }

    fn extrair_erro(status: reqwest::StatusCode, corpo: &str) -> String {
        if let Ok(err) = serde_json::from_str::<ErroApi>(corpo) {
            if let Some(msg) = err.mensagem {
                if !msg.is_empty() {
                    return msg;
                }
            }
            if !err.erro.is_empty() {
                return err.erro;
            }
        }
        format!("Erro HTTP {}", status.as_u16())
    }

    pub fn autenticar(
        &self,
        url_base: &str,
        email: &str,
        senha: &str,
    ) -> Result<RespostaToken, String> {
        let base = Self::normalizar_url(url_base)?;
        let endpoint = format!("{base}/api/v1/auth/token");
        let resp = self
            .http
            .post(&endpoint)
            .json(&json!({ "email": email.trim(), "senha": senha }))
            .send()
            .map_err(|e| format!("Sem conexão com {base}: {e}"))?;

        let status = resp.status();
        let corpo = resp
            .text()
            .map_err(|e| format!("Falha ao ler resposta do servidor: {e}"))?;
        if !status.is_success() {
            return Err(Self::extrair_erro(status, &corpo));
        }
        serde_json::from_str::<RespostaToken>(&corpo)
            .map_err(|e| format!("Resposta de login inválida: {e}"))
    }

    pub fn buscar_estado(&self, url_base: &str, token: &str) -> Result<EstadoSync, String> {
        let base = Self::normalizar_url(url_base)?;
        let endpoint = format!("{base}/api/v1/sync");
        let resp = self
            .http
            .get(&endpoint)
            .bearer_auth(token)
            .send()
            .map_err(|e| format!("Falha ao sincronizar com {base}: {e}"))?;

        let status = resp.status();
        let corpo = resp
            .text()
            .map_err(|e| format!("Falha ao ler dados de sincronização: {e}"))?;
        if !status.is_success() {
            return Err(Self::extrair_erro(status, &corpo));
        }
        serde_json::from_str::<EstadoSync>(&corpo)
            .map_err(|e| format!("Payload de sincronização inválido: {e}"))
    }

    pub fn enviar_e_sincronizar(
        &self,
        url_base: &str,
        token: &str,
        operacoes: &[OperacaoSync],
    ) -> Result<RespostaPostSync, String> {
        let base = Self::normalizar_url(url_base)?;
        let endpoint = format!("{base}/api/v1/sync");
        let resp = self
            .http
            .post(&endpoint)
            .bearer_auth(token)
            .json(&json!({ "operacoes": operacoes }))
            .send()
            .map_err(|e| format!("Falha ao enviar alterações para {base}: {e}"))?;

        let status = resp.status();
        let corpo = resp
            .text()
            .map_err(|e| format!("Falha ao ler resposta do envio: {e}"))?;
        if !status.is_success() {
            return Err(Self::extrair_erro(status, &corpo));
        }
        serde_json::from_str::<RespostaPostSync>(&corpo)
            .map_err(|e| format!("Resposta de sincronização inválida: {e}"))
    }

    /// Envia um arquivo pela tarefa (multipart). Só online: arquivos não
    /// passam pela fila. Timeout maior que o da sincronização, pois o arquivo
    /// pode ter até 20 MB numa rede móvel.
    pub fn enviar_entrega(
        &self,
        url_base: &str,
        token: &str,
        pedido: &PedidoEntrega,
    ) -> Result<RespostaEntrega, String> {
        use reqwest::blocking::multipart::{Form, Part};

        let base = Self::normalizar_url(url_base)?;
        let endpoint = format!("{base}/api/v1/marcos/{}/entrega", pedido.marco_id);
        let mut parte = Part::file(&pedido.caminho_arquivo)
            .map_err(|e| format!("Não foi possível ler o arquivo escolhido: {e}"))?
            .file_name(pedido.nome_arquivo.clone());
        if let Some(mime) = pedido.mime.as_deref().filter(|m| !m.is_empty()) {
            parte = parte
                .mime_str(mime)
                .map_err(|e| format!("Tipo de arquivo inválido: {e}"))?;
        }
        let mut form = Form::new()
            .text("op_id", pedido.op_id.clone())
            .text(
                "destino",
                pedido.destino.clone().unwrap_or_else(|| "novo".to_string()),
            )
            .text("sinalizar", if pedido.sinalizar { "1" } else { "0" })
            .part("arquivo", parte);
        if let Some(titulo) = pedido.titulo.as_deref().filter(|t| !t.trim().is_empty()) {
            form = form.text("titulo", titulo.trim().to_string());
        }
        if let Some(c) = pedido.comentario.as_deref().filter(|c| !c.trim().is_empty()) {
            form = form.text("comentario", c.trim().to_string());
        }

        let http = Client::builder()
            .timeout(Duration::from_secs(180))
            .build()
            .map_err(|e| format!("Falha ao inicializar cliente HTTP: {e}"))?;
        let resp = http
            .post(&endpoint)
            .bearer_auth(token)
            .multipart(form)
            .send()
            .map_err(|e| {
                format!(
                    "Envio de arquivo requer conexão; tente novamente quando estiver online. ({e})"
                )
            })?;

        let status = resp.status();
        let corpo = resp
            .text()
            .map_err(|e| format!("Falha ao ler resposta do servidor: {e}"))?;
        if status.as_u16() == 413 {
            return Err("Arquivo grande demais: o limite é de 20 MB.".to_string());
        }
        if !status.is_success() {
            return Err(Self::extrair_erro(status, &corpo));
        }
        serde_json::from_str::<RespostaEntrega>(&corpo)
            .map_err(|e| format!("Resposta de envio inválida: {e}"))
    }

    pub fn sincronizar_com_repositorio(
        &self,
        repo: &mut RepositorioLocal,
    ) -> Result<ResumoSync, String> {
        let Some((url_base, token, _)) = repo.carregar_sessao()? else {
            return Err("Nenhuma sessão autenticada encontrada.".to_string());
        };
        let pendentes = repo.listar_operacoes()?;
        if pendentes.is_empty() {
            let estado = self.buscar_estado(&url_base, &token)?;
            let sincronizado_em = estado.sincronizado_em.clone();
            repo.aplicar_estado_remoto(&estado)?;
            return Ok(ResumoSync {
                enviadas: 0,
                falhas: Vec::new(),
                sincronizado_em,
            });
        }

        let resposta = self.enviar_e_sincronizar(&url_base, &token, &pendentes)?;
        let sincronizado_em = resposta.estado.sincronizado_em.clone();
        let falhas = repo.concluir_sincronizacao(&resposta.resultados, &resposta.estado)?;
        Ok(ResumoSync {
            enviadas: pendentes.len(),
            falhas,
            sincronizado_em,
        })
    }
}
