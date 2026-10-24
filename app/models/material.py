"""Material de consulta: arquivo que o orientador disponibiliza a um ou mais
orientandos (apostila, artigos, bases de dados).

Distinto de documento: não é trabalho do vínculo, não tem versões, não pede
parecer e não conta como entrega. Por isso mora fora de `documento`, e o
compartilhamento é explícito, vínculo a vínculo (`material_orientacao`) — quem
não está na lista não vê. A ligação a tarefas (`material_marco`) é opcional:
só faz o material aparecer também na página da tarefa onde é usado.
"""
from datetime import UTC, datetime

from app.extensions import db

material_orientacao = db.Table(
    "material_orientacao",
    db.Column("material_id", db.Integer, db.ForeignKey("material.id"), primary_key=True),
    db.Column("orientacao_id", db.Integer, db.ForeignKey("orientacao.id"), primary_key=True),
)

material_marco = db.Table(
    "material_marco",
    db.Column("material_id", db.Integer, db.ForeignKey("material.id"), primary_key=True),
    db.Column("marco_id", db.Integer, db.ForeignKey("marco.id"), primary_key=True),
)


class Material(db.Model):
    __tablename__ = "material"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    nome_original = db.Column(db.String(255), nullable=False)
    nome_fisico = db.Column(db.String(64), unique=True, nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    mimetype = db.Column(db.String(100), nullable=False)
    enviado_por = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    enviado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    autor = db.relationship("Usuario", foreign_keys=[enviado_por])
    orientacoes = db.relationship(
        "Orientacao", secondary=material_orientacao, order_by="Orientacao.id"
    )
    marcos = db.relationship("Marco", secondary=material_marco)

    def __repr__(self) -> str:
        return f"<Material {self.id} {self.titulo!r}>"
