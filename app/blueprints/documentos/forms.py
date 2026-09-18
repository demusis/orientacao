from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

# O que é esta versão, quando quem envia NÃO é a orientanda. O formulário só
# mostra o campo a gestores; a rota o ignora para a orientanda, cuja versão é
# sempre entrega dela. Um upload do orientador não pede parecer dele próprio —
# salvo quando ele declara estar registrando a entrega da orientanda.
NATUREZA_CHOICES = [
    ("registro", "Registro meu (não pede parecer nem altera a tarefa)"),
    (
        "devolucao",
        "Devolução minha, com correções (devolve a tarefa à orientanda para revisão)",
    ),
    (
        "entrega",
        "Entrega da orientanda, que estou registrando por ela "
        "(entra na minha lista de pareceres, como se ela tivesse enviado)",
    ),
]


def campo_natureza() -> RadioField:
    return RadioField(
        "O que é esta versão?", choices=NATUREZA_CHOICES, default="registro"
    )


def flags_da_natureza(natureza: str) -> tuple[bool, bool]:
    """(eh_devolucao, em_nome_do_orientando) a partir da escolha do formulário —
    o inverso de `VersaoDocumento.natureza`."""
    return natureza == "devolucao", natureza == "entrega"


class NovoDocumentoForm(FlaskForm):
    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    marco_id = SelectField("Marco associado", coerce=int, validators=[Optional()])
    arquivo = FileField("Arquivo", validators=[FileRequired()])
    comentario = TextAreaField("Comentário", validators=[Optional()])
    natureza = campo_natureza()
    submit = SubmitField("Enviar")


class NovaVersaoForm(FlaskForm):
    arquivo = FileField("Arquivo", validators=[FileRequired()])
    comentario = TextAreaField("Comentário", validators=[Optional()])
    natureza = campo_natureza()
    submit = SubmitField("Enviar nova versão")


class ClassificarVersaoForm(FlaskForm):
    """Reclassifica uma versão já enviada (escotilha para registros antigos)."""

    natureza = SelectField("Natureza", choices=NATUREZA_CHOICES)
    submit = SubmitField("Aplicar")
