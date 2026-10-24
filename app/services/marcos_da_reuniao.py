"""Opções do campo "Marcos discutidos" da ata: enxutas e legíveis.

A lista antiga somava os cronogramas inteiros dos participantes — concluídos
incluídos, e cada tarefa em grupo repetida uma vez por orientando. Aqui:

- **tarefa em grupo é uma opção só** (`g:<grupo_id>`), que ao salvar liga os
  marcos daquele grupo de todos os participantes; a individual é `m:<id>`;
- **relevantes à vista**: em aberto com prazo até `JANELA_DIAS` depois da
  reunião (atrasados incluídos) e, sempre, os já ligados à ata — omiti-los
  faria o salvamento apagá-los (`atualizar_ata` substitui a seleção);
- **o resto recolhido** (concluídos e prazo distante), ainda marcável.

Ids numéricos puros continuam aceitos ao salvar, por compatibilidade.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

JANELA_DIAS = 60

SITUACAO_CURTA = {
    None: "concluída",
    "orientador": "aguarda orientador",
    "orientando_revisao": "devolvida",
    "orientando": "",
}


@dataclass
class Opcao:
    valor: str
    rotulo: str
    detalhe: str  # prazo e situação, em texto curto


@dataclass
class Bloco:
    titulo: str
    opcoes: list = field(default_factory=list)


@dataclass
class Opcoes:
    visiveis: list  # [Bloco]
    recolhidas: list  # [Bloco]

    @property
    def todas(self) -> list[Opcao]:
        return [o for b in self.visiveis + self.recolhidas for o in b.opcoes]

    @property
    def total_recolhidas(self) -> int:
        return sum(len(b.opcoes) for b in self.recolhidas)


def _marcos(vinculos):
    return [m for o in vinculos for m in o.marcos]


def _detalhe(marcos) -> str:
    m = min(marcos, key=lambda x: x.data_prevista)
    partes = [f"prazo {m.data_prevista:%d/%m/%Y}"]
    if any(x.atrasado for x in marcos):
        partes.append("atrasada")
    situacoes = {SITUACAO_CURTA[x.aguardando] for x in marcos} - {""}
    if len(situacoes) == 1:
        partes.append(situacoes.pop())
    return " · ".join(partes)


def valor_de(marco) -> str:
    return f"g:{marco.grupo_id}" if marco.grupo_id else f"m:{marco.id}"


def opcoes(vinculos, data_reuniao: date | None, marcados=()) -> Opcoes:
    """As opções agrupadas: tarefas em grupo primeiro, depois por orientando;
    cada grupo dividido entre à vista e recolhido."""
    referencia = data_reuniao or date.today()
    limite = referencia + timedelta(days=JANELA_DIAS)
    ids_marcados = {m.id for m in marcados}
    vinculos = list(vinculos)
    marcos = _marcos(vinculos)

    # tarefa em grupo: só vira opção única quando o grupo tem marco em mais de
    # um participante desta reunião; senão, é individual para efeito da lista
    por_grupo: dict[str, list] = {}
    for m in marcos:
        if m.grupo_id:
            por_grupo.setdefault(m.grupo_id, []).append(m)
    unidades = []  # (valor, marcos, rótulo, nome do bloco)
    vistos = set()
    for m in marcos:
        if m.grupo_id and len(por_grupo[m.grupo_id]) > 1:
            if m.grupo_id in vistos:
                continue
            vistos.add(m.grupo_id)
            grupo = por_grupo[m.grupo_id]
            nomes = ", ".join(x.orientacao.orientando.nome.split()[0] for x in grupo)
            unidades.append((f"g:{m.grupo_id}", grupo, f"{m.titulo} — grupo: {nomes}",
                             "Tarefas em grupo"))
        else:
            unidades.append((f"m:{m.id}", [m], m.titulo, m.orientacao.orientando.nome))

    def relevante(ms) -> bool:
        if any(x.id in ids_marcados for x in ms):
            return True
        return any(x.status != "concluido" and x.data_prevista <= limite for x in ms)

    visiveis: dict[str, Bloco] = {}
    recolhidas: dict[str, Bloco] = {}
    for valor, ms, rotulo, bloco in sorted(
        unidades, key=lambda u: (u[3] != "Tarefas em grupo", u[3],
                                 min(x.data_prevista for x in u[1]))
    ):
        destino = visiveis if relevante(ms) else recolhidas
        destino.setdefault(bloco, Bloco(bloco)).opcoes.append(
            Opcao(valor, rotulo, _detalhe(ms))
        )
    return Opcoes(list(visiveis.values()), list(recolhidas.values()))


def valores_marcados(marcados, vinculos) -> list[str]:
    """Os valores do formulário que representam os marcos já ligados."""
    oferecidos = {o.valor for o in opcoes(vinculos, None, marcados).todas}
    valores = []
    for m in marcados:
        v = valor_de(m)
        if v not in oferecidos:  # grupo com um só participante na reunião
            v = f"m:{m.id}"
        if v not in valores:
            valores.append(v)
    return valores


def expandir(valores, vinculos) -> list:
    """Os marcos designados pelos valores enviados, restritos aos vínculos da
    ata — valor forjado (marco ou grupo alheio) é descartado em silêncio."""
    marcos = _marcos(vinculos)
    por_id = {m.id: m for m in marcos}
    escolhidos = []
    for valor in valores or []:
        valor = str(valor)
        tipo, _, chave = valor.partition(":")
        if not chave and valor.isdigit():  # id numérico puro (compatibilidade)
            tipo, chave = "m", valor
        if tipo == "g":
            alvo = [m for m in marcos if m.grupo_id == chave]
        elif tipo == "m" and chave.isdigit() and int(chave) in por_id:
            alvo = [por_id[int(chave)]]
        else:
            alvo = []
        for m in alvo:
            if m not in escolhidos:
                escolhidos.append(m)
    return escolhidos
