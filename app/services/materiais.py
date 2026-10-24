"""Materiais de consulta: publicar, compartilhar, listar e excluir.

Quem vê: o autor, o administrador e os participantes (orientando, orientador,
coorientadores) dos vínculos com que o material foi compartilhado — nenhum
outro. A tarefa ligada só decide onde mais o material aparece; compartilhar
com a tarefa compartilha com os vínculos dela.
"""
from app.extensions import db
from app.models import Marco, Material, Orientacao
from app.services import auditoria
from app.services.uploads import armazenar


def opcoes_de_tarefa(vinculos) -> list[tuple[str, str]]:
    """Tarefas em aberto dos vínculos, para ligar o material. A tarefa em grupo
    aparece uma vez só (`g:<grupo_id>`); a individual, como `m:<id>`."""
    ids = [o.id for o in vinculos]
    if not ids:
        return []
    marcos = (
        Marco.query.filter(Marco.orientacao_id.in_(ids), Marco.status != "concluido")
        .order_by(Marco.data_prevista)
        .all()
    )
    vistos, opcoes = set(), []
    for m in marcos:
        if m.grupo_id:
            if m.grupo_id in vistos:
                continue
            vistos.add(m.grupo_id)
            nomes = ", ".join(
                x.orientacao.orientando.nome.split()[0]
                for x in marcos
                if x.grupo_id == m.grupo_id
            )
            opcoes.append((f"g:{m.grupo_id}", f"{m.titulo} (grupo: {nomes})"))
        else:
            opcoes.append((f"m:{m.id}", f"{m.titulo} — {m.orientacao.orientando.nome}"))
    return opcoes


def marcos_da_opcao(valor: str, vinculos) -> list[Marco]:
    """Os marcos que a opção escolhida designa, restritos aos vínculos dados
    (o valor vem do formulário e não é confiável)."""
    ids = [o.id for o in vinculos]
    if not valor or not ids:
        return []
    tipo, _, chave = valor.partition(":")
    consulta = Marco.query.filter(Marco.orientacao_id.in_(ids))
    if tipo == "g":
        return consulta.filter(Marco.grupo_id == chave).all()
    if tipo == "m" and chave.isdigit():
        return consulta.filter(Marco.id == int(chave)).all()
    return []


def publicar(*, titulo, descricao, storage, vinculos, marcos, autor) -> Material:
    """Grava o arquivo e compartilha com os vínculos (mais os das tarefas
    ligadas). Não faz commit. `UploadInvalido` se o arquivo não passa."""
    colunas = armazenar(storage)
    alvo = {o.id: o for o in vinculos}
    for m in marcos:
        alvo.setdefault(m.orientacao_id, m.orientacao)
    material = Material(
        titulo=titulo.strip(),
        descricao=(descricao or "").strip() or None,
        enviado_por=autor.id,
        orientacoes=list(alvo.values()),
        marcos=list(marcos),
        **colunas,
    )
    db.session.add(material)
    db.session.flush()
    auditoria.registrar(
        "publicacao_material", "material", material.id,
        {"titulo": material.titulo, "orientacoes": sorted(alvo),
         "marcos": [m.id for m in marcos]},
    )
    return material


def pode_ver(material: Material, usuario) -> bool:
    if usuario.papel == "admin" or material.enviado_por == usuario.id:
        return True
    for o in material.orientacoes:
        if usuario.id in (o.orientando_id, o.orientador_id):
            return True
        if any(c.usuario_id == usuario.id for c in o.equipe):
            return True
    return False


def pode_excluir(material: Material, usuario) -> bool:
    return usuario.papel == "admin" or material.enviado_por == usuario.id


def da_orientacao(orientacao: Orientacao) -> list[Material]:
    return (
        Material.query.filter(Material.orientacoes.any(Orientacao.id == orientacao.id))
        .order_by(Material.enviado_em.desc())
        .all()
    )


def do_marco(marco: Marco) -> list[Material]:
    return (
        Material.query.filter(Material.marcos.any(Marco.id == marco.id))
        .order_by(Material.titulo)
        .all()
    )


def excluir(material: Material) -> str:
    """Remove o material e devolve o nome físico, a apagar do disco pelo
    chamador DEPOIS do commit. Não faz commit."""
    nome = material.nome_fisico
    auditoria.registrar(
        "exclusao_material", "material", material.id, {"titulo": material.titulo}
    )
    material.orientacoes = []
    material.marcos = []
    db.session.delete(material)
    return nome
