pub mod db;
pub mod models;
pub mod sync;

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};

use jni::objects::{JClass, JString};
use jni::sys::jstring;
use jni::JNIEnv;
use serde::Serialize;
use serde_json::Value;

use crate::db::RepositorioLocal;
use crate::models::{
    Ata, Documento, ItemFila, Marco, Orientacao, Parecer, PedidoEntrega, Usuario,
};
use crate::sync::ClienteAriadne;

#[derive(Debug, Clone, Serialize)]
pub struct SnapshotLocal {
    pub autenticado: bool,
    pub url_servidor: String,
    pub usuario: Option<Usuario>,
    pub ultima_sync: Option<String>,
    pub orientacoes: Vec<Orientacao>,
    pub marcos: Vec<Marco>,
    pub documentos: Vec<Documento>,
    pub atas: Vec<Ata>,
    pub pareceres: Vec<Parecer>,
    pub itens_fila: Vec<ItemFila>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RespostaPonte {
    pub ok: bool,
    pub mensagem: Option<String>,
    pub erro: Option<String>,
    pub estado: Option<SnapshotLocal>,
}

fn montar_snapshot(repo: &RepositorioLocal) -> Result<SnapshotLocal, String> {
    let url_servidor = repo
        .url_servidor()?
        .unwrap_or_else(|| "https://orientacao.pythonanywhere.com".to_string());
    let sessao = repo.carregar_sessao()?;
    let (autenticado, usuario) = match sessao {
        Some((_, _, u)) => (true, Some(u)),
        None => (false, None),
    };
    Ok(SnapshotLocal {
        autenticado,
        url_servidor,
        usuario,
        ultima_sync: repo.ultima_sync()?,
        orientacoes: repo.listar_orientacoes()?,
        marcos: repo.listar_marcos()?,
        documentos: repo.listar_documentos()?,
        atas: repo.listar_atas()?,
        pareceres: repo.listar_pareceres()?,
        itens_fila: repo.listar_itens_fila()?,
    })
}

fn json_ok(mensagem: Option<String>, erro: Option<String>, estado: SnapshotLocal) -> String {
    serde_json::to_string(&RespostaPonte {
        ok: true,
        mensagem,
        erro,
        estado: Some(estado),
    })
    .unwrap_or_else(|e| json_erro(&format!("Falha ao serializar resposta: {e}")))
}

fn json_erro(erro: &str) -> String {
    serde_json::to_string(&RespostaPonte {
        ok: false,
        mensagem: None,
        erro: Some(erro.to_string()),
        estado: None,
    })
    .unwrap_or_else(|_| r#"{"ok":false,"erro":"Erro interno de serialização"}"#.to_string())
}

fn executar_com_repo<F>(db_path: &Path, acao: F) -> String
where
    F: FnOnce(&mut RepositorioLocal) -> Result<(Option<String>, Option<String>), String>,
{
    let mut repo = match RepositorioLocal::abrir(db_path) {
        Ok(r) => r,
        Err(e) => return json_erro(&e),
    };
    match acao(&mut repo) {
        Ok((mensagem, erro)) => match montar_snapshot(&repo) {
            Ok(estado) => json_ok(mensagem, erro, estado),
            Err(e) => json_erro(&e),
        },
        Err(e) => json_erro(&e),
    }
}

pub fn estado_local_json(db_path: &Path) -> String {
    executar_com_repo(db_path, |_| Ok((None, None)))
}

pub fn login_e_sincronizar_json(db_path: &Path, url: &str, email: &str, senha: &str) -> String {
    if email.trim().is_empty() || senha.is_empty() {
        return json_erro("Informe e-mail e senha.");
    }
    executar_com_repo(db_path, |repo| {
        let _ = repo.salvar_url_servidor(url);
        let cliente = ClienteAriadne::novo()?;
        let resp = cliente.autenticar(url, email, senha)?;
        let estado = cliente.buscar_estado(url, &resp.token)?;
        repo.salvar_sessao(url, &resp.token, &resp.usuario)?;
        repo.aplicar_estado_remoto(&estado)?;
        Ok((Some("Conectado e sincronizado.".to_string()), None))
    })
}

pub fn sincronizar_json(db_path: &Path) -> String {
    executar_com_repo(db_path, |repo| {
        let cliente = ClienteAriadne::novo()?;
        let resumo = cliente.sincronizar_com_repositorio(repo)?;
        if resumo.falhas.is_empty() {
            let msg = if resumo.enviadas == 0 {
                "Dados atualizados com o servidor.".to_string()
            } else {
                format!(
                    "{} operação(ões) sincronizada(s) com sucesso.",
                    resumo.enviadas
                )
            };
            Ok((Some(msg), None))
        } else {
            let detalhes: Vec<String> = resumo
                .falhas
                .iter()
                .map(|f| {
                    format!(
                        "{}: {}",
                        f.acao,
                        f.erro.as_deref().unwrap_or("erro desconhecido")
                    )
                })
                .collect();
            Ok((
                Some(format!(
                    "Sincronizado com {} erro(s) mantido(s) na fila.",
                    resumo.falhas.len()
                )),
                Some(detalhes.join(" | ")),
            ))
        }
    })
}

pub fn enfileirar_operacao_json(db_path: &Path, acao: &str, dados_json: &str) -> String {
    let dados: Value = match serde_json::from_str(dados_json) {
        Ok(v) => v,
        Err(e) => return json_erro(&format!("JSON de dados inválido: {e}")),
    };
    executar_com_repo(db_path, |repo| {
        repo.enfileirar_operacao(acao, dados)?;
        Ok((Some("Alteração salva offline na fila de sincronização.".to_string()), None))
    })
}

pub fn descartar_operacao_json(db_path: &Path, op_id: &str) -> String {
    executar_com_repo(db_path, |repo| {
        let restaurado = repo.descartar_operacao(op_id)?;
        let msg = if restaurado {
            "Operação descartada; a tarefa voltou ao estado anterior."
        } else {
            "Operação removida da fila. Sincronize para atualizar a tela."
        };
        Ok((Some(msg.to_string()), None))
    })
}

/// Envia o documento de uma tarefa. Antes, despacha a fila pendente (a tarefa
/// e o estado local precisam estar alinhados com o servidor); depois, grava o
/// estado devolvido pelo servidor, que já inclui o documento novo.
pub fn enviar_entrega_json(db_path: &Path, pedido_json: &str) -> String {
    let pedido: PedidoEntrega = match serde_json::from_str(pedido_json) {
        Ok(p) => p,
        Err(e) => return json_erro(&format!("Pedido de envio inválido: {e}")),
    };
    if pedido.marco_id <= 0 {
        return json_erro("Sincronize a tarefa antes de enviar arquivos para ela.");
    }
    executar_com_repo(db_path, |repo| {
        let cliente = ClienteAriadne::novo()?;
        if repo.contar_fila()? > 0 {
            cliente.sincronizar_com_repositorio(repo)?;
        }
        let Some((url_base, token, _)) = repo.carregar_sessao()? else {
            return Err("Nenhuma sessão autenticada encontrada.".to_string());
        };
        let resposta = cliente.enviar_entrega(&url_base, &token, &pedido)?;
        repo.aplicar_estado_remoto(&resposta.estado)?;
        let msg = if resposta.status == "ja_aplicada" {
            "Este envio já havia sido recebido pelo servidor.".to_string()
        } else {
            resposta
                .mensagem
                .unwrap_or_else(|| "Documento enviado.".to_string())
        };
        Ok((Some(msg), None))
    })
}

pub fn encerrar_sessao_json(db_path: &Path) -> String {
    executar_com_repo(db_path, |repo| {
        repo.limpar_sessao()?;
        Ok((Some("Sessão encerrada.".to_string()), None))
    })
}

fn ler_jstring(env: &mut JNIEnv<'_>, s: &JString<'_>) -> Result<String, String> {
    env.get_string(s)
        .map(|java_str| java_str.into())
        .map_err(|e| format!("Falha ao ler string JNI: {e}"))
}

fn retornar_jstring(env: &mut JNIEnv<'_>, texto: String) -> jstring {
    match env.new_string(texto) {
        Ok(s) => s.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

fn executar_jni<F>(mut env: JNIEnv<'_>, db_path: JString<'_>, acao: F) -> jstring
where
    F: FnOnce(&mut JNIEnv<'_>, &Path) -> Result<String, String>,
{
    let resultado = catch_unwind(AssertUnwindSafe(|| {
        let caminho = ler_jstring(&mut env, &db_path)?;
        acao(&mut env, PathBuf::from(caminho).as_path())
    }));
    let resposta = match resultado {
        Ok(Ok(json)) => json,
        Ok(Err(e)) => json_erro(&e),
        Err(_) => json_erro("Erro inesperado no núcleo Rust."),
    };
    retornar_jstring(&mut env, resposta)
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_estadoLocal(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |_env, caminho| Ok(estado_local_json(caminho)))
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_loginESincronizar(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
    url: JString<'_>,
    email: JString<'_>,
    senha: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |env, caminho| {
        let url = ler_jstring(env, &url)?;
        let email = ler_jstring(env, &email)?;
        let senha = ler_jstring(env, &senha)?;
        Ok(login_e_sincronizar_json(caminho, &url, &email, &senha))
    })
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_sincronizar(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |_env, caminho| Ok(sincronizar_json(caminho)))
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_enfileirarOperacao(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
    acao: JString<'_>,
    dados_json: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |env, caminho| {
        let acao = ler_jstring(env, &acao)?;
        let dados_json = ler_jstring(env, &dados_json)?;
        Ok(enfileirar_operacao_json(caminho, &acao, &dados_json))
    })
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_descartarOperacao(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
    op_id: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |env, caminho| {
        let op_id = ler_jstring(env, &op_id)?;
        Ok(descartar_operacao_json(caminho, &op_id))
    })
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_enviarEntrega(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
    pedido_json: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |env, caminho| {
        let pedido_json = ler_jstring(env, &pedido_json)?;
        Ok(enviar_entrega_json(caminho, &pedido_json))
    })
}

#[no_mangle]
pub extern "system" fn Java_br_edu_ariadne_mobile_core_AriadneRustBridge_encerrarSessao(
    env: JNIEnv<'_>,
    _class: JClass<'_>,
    db_path: JString<'_>,
) -> jstring {
    executar_jni(env, db_path, |_env, caminho| Ok(encerrar_sessao_json(caminho)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn fachada_json_fluxo_offline_completo() {
        let dir = std::env::temp_dir().join(format!("ariadne-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let db_path = dir.join("ariadne.db");

        let inicial: Value = serde_json::from_str(&estado_local_json(&db_path)).unwrap();
        assert_eq!(inicial["ok"], true);
        assert_eq!(inicial["estado"]["autenticado"], false);

        let enfileirado: Value = serde_json::from_str(&enfileirar_operacao_json(
            &db_path,
            "criar_tarefa",
            &json!({
                "orientacao_ids": [1],
                "titulo": "Entregar capítulo 1",
                "tipo": "projeto",
                "data_prevista": "2026-12-10",
                "etapa": 20,
                "entrega_esperada": "documento"
            })
            .to_string(),
        ))
        .unwrap();
        assert_eq!(enfileirado["ok"], true);
        assert_eq!(enfileirado["estado"]["itens_fila"].as_array().unwrap().len(), 1);
        assert_eq!(enfileirado["estado"]["marcos"].as_array().unwrap().len(), 1);

        let op_id = enfileirado["estado"]["itens_fila"][0]["op_id"]
            .as_str()
            .unwrap()
            .to_string();
        let descartado: Value =
            serde_json::from_str(&descartar_operacao_json(&db_path, &op_id)).unwrap();
        assert_eq!(descartado["ok"], true);
        assert_eq!(descartado["estado"]["itens_fila"].as_array().unwrap().len(), 0);

        let encerrado: Value = serde_json::from_str(&encerrar_sessao_json(&db_path)).unwrap();
        assert_eq!(encerrado["ok"], true);
        assert_eq!(encerrado["estado"]["marcos"].as_array().unwrap().len(), 0);

        let _ = std::fs::remove_dir_all(&dir);
    }
}
