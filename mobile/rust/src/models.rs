use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Usuario {
    pub id: i64,
    pub nome: String,
    pub email: String,
    pub papel: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Orientacao {
    pub id: i64,
    pub orientador_id: i64,
    pub orientador_nome: String,
    pub orientando_id: i64,
    pub orientando_nome: String,
    pub modalidade: String,
    pub titulo_projeto: String,
    pub data_inicio: String,
    pub data_fim_prevista: Option<String>,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Marco {
    pub id: i64,
    pub orientacao_id: i64,
    pub titulo: String,
    pub descricao: Option<String>,
    pub data_prevista: String,
    pub data_conclusao: Option<String>,
    pub status: String,
    pub tipo: String,
    pub etapa: i64,
    pub conclusao_sinalizada: bool,
    pub nota_conclusao: Option<String>,
    pub devolvido_em: Option<String>,
    pub nota_devolucao: Option<String>,
    pub grupo_id: Option<String>,
    pub entrega_esperada: Option<String>,
    pub aguardando: Option<String>,
    pub criado_em: Option<String>,
    #[serde(default)]
    pub documento_base_id: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ParticipacaoAta {
    pub orientacao_id: i64,
    pub presenca: String,
    pub presenca_registrada_em: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Ata {
    pub id: i64,
    pub tipo: String,
    pub orientador_id: i64,
    pub data_reuniao: String,
    pub hora_reuniao: Option<String>,
    pub link_reuniao: Option<String>,
    pub pauta: String,
    pub deliberacoes: String,
    pub status: String,
    pub formato: String,
    pub finalizada_em: Option<String>,
    pub cancelada_em: Option<String>,
    pub motivo_cancelamento: Option<String>,
    pub criada_em: Option<String>,
    pub orientacao_ids: Vec<i64>,
    pub marco_ids: Vec<i64>,
    pub participacoes: Vec<ParticipacaoAta>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct VersaoDocumento {
    pub id: i64,
    pub documento_id: i64,
    pub numero_versao: i64,
    #[serde(default)]
    pub nome_original: Option<String>,
    #[serde(default)]
    pub tem_arquivo: bool,
    #[serde(default)]
    pub enviado_por: i64,
    #[serde(default)]
    pub remetente_nome: String,
    #[serde(default)]
    pub enviado_em: Option<String>,
    #[serde(default)]
    pub comentario: Option<String>,
    #[serde(default)]
    pub natureza: String,
    #[serde(default)]
    pub marco_aberto_id: Option<i64>,
    #[serde(default)]
    pub marco_aberto_titulo: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Documento {
    pub id: i64,
    pub orientacao_id: i64,
    #[serde(default)]
    pub marco_id: Option<i64>,
    #[serde(default)]
    pub marco_titulo: Option<String>,
    pub titulo: String,
    #[serde(default)]
    pub criado_em: Option<String>,
    #[serde(default)]
    pub versoes: Vec<VersaoDocumento>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Parecer {
    pub id: i64,
    pub orientacao_id: i64,
    pub versao_documento_id: Option<i64>,
    #[serde(default)]
    pub documento_id: Option<i64>,
    #[serde(default)]
    pub documento_titulo: Option<String>,
    #[serde(default)]
    pub numero_versao: Option<i64>,
    #[serde(default)]
    pub nome_arquivo: Option<String>,
    #[serde(default)]
    pub marco_id: Option<i64>,
    #[serde(default)]
    pub marco_titulo: Option<String>,
    pub tipo: String,
    pub conteudo: String,
    pub resultado: String,
    pub emitido_por: i64,
    #[serde(default)]
    pub emissor_nome: Option<String>,
    pub emitido_em: String,
    pub formato: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EstadoSync {
    pub usuario: Usuario,
    pub orientacoes: Vec<Orientacao>,
    pub marcos: Vec<Marco>,
    #[serde(default)]
    pub documentos: Vec<Documento>,
    pub atas: Vec<Ata>,
    pub pareceres: Vec<Parecer>,
    pub sincronizado_em: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OperacaoSync {
    pub op_id: String,
    pub acao: String,
    pub dados: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResultadoOperacao {
    pub op_id: String,
    pub acao: String,
    pub status: String,
    pub entidade: Option<String>,
    pub entidade_id: Option<i64>,
    pub erro: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RespostaPostSync {
    pub resultados: Vec<ResultadoOperacao>,
    pub estado: EstadoSync,
}

/// Pedido de envio de documento pela tarefa, montado pelo app (JSON).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PedidoEntrega {
    pub op_id: String,
    pub marco_id: i64,
    pub caminho_arquivo: String,
    pub nome_arquivo: String,
    #[serde(default)]
    pub mime: Option<String>,
    /// Id do documento da tarefa que recebe nova versão, ou "novo".
    #[serde(default)]
    pub destino: Option<String>,
    #[serde(default)]
    pub titulo: Option<String>,
    #[serde(default)]
    pub comentario: Option<String>,
    #[serde(default)]
    pub sinalizar: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RespostaEntrega {
    pub status: String,
    #[serde(default)]
    pub mensagem: Option<String>,
    #[serde(default)]
    pub sinalizou: Option<bool>,
    pub estado: EstadoSync,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RespostaToken {
    pub token: String,
    pub usuario: Usuario,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErroApi {
    pub erro: String,
    pub mensagem: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ItemFila {
    pub seq: i64,
    pub op_id: String,
    pub acao: String,
    pub dados_json: String,
    pub criada_em: String,
}

pub const TIPOS_MARCO: &[(&str, &str)] = &[
    ("outro", "Outro"),
    ("projeto", "Projeto de pesquisa"),
    ("comite_etica", "Comitê de Ética"),
    ("qualificacao", "Qualificação"),
    ("relatorio", "Relatório (parcial, anual ou final)"),
    ("publicacao", "Publicação"),
    ("defesa", "Defesa"),
];

pub const ETAPAS_MARCO: &[(i64, &str)] = &[
    (0, "Não classificada"),
    (10, "Planejamento"),
    (20, "Revisão de literatura"),
    (30, "Coleta / Experimentos"),
    (40, "Análise de resultados"),
    (50, "Redação"),
    (60, "Encerramento"),
];

pub const ENTREGAS_ESPERADAS: &[(&str, &str)] = &[
    ("documento", "Entregar um documento"),
    ("revisao", "Revisar um texto"),
    ("ato", "Sem arquivo (só o ato)"),
    ("", "Não especificar"),
];

pub const TIPOS_PARECER: &[(&str, &str)] = &[
    ("andamento", "Andamento"),
    ("documento", "Documento"),
    ("marco", "Marco"),
];

pub const RESULTADOS_PARECER: &[(&str, &str)] = &[
    ("aprovado", "Aprovado"),
    ("aprovado_com_ressalvas", "Aprovado com ressalvas"),
    ("reprovado", "Reprovado"),
];

pub fn rotulo_etapa(etapa: i64) -> &'static str {
    ETAPAS_MARCO
        .iter()
        .find(|(codigo, _)| *codigo == etapa)
        .map(|(_, label)| *label)
        .unwrap_or("Etapa")
}

pub fn rotulo_resultado_parecer(resultado: &str) -> &'static str {
    RESULTADOS_PARECER
        .iter()
        .find(|(codigo, _)| *codigo == resultado)
        .map(|(_, label)| *label)
        .unwrap_or("Indefinido")
}

pub fn rotulo_aguardando(aguardando: Option<&str>) -> &'static str {
    match aguardando {
        None => "Concluída",
        Some("orientador") => "Aguarda orientador",
        Some("orientando_revisao") => "Devolvida para revisão",
        Some("orientando") => "Com orientando",
        Some(_) => "Em andamento",
    }
}
