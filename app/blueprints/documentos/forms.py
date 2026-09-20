from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError

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


class NaturezaField(RadioField):
    """Escolha da natureza da versão, com a recusa dita em português.

    O WTForms responde "Not a valid choice." — inglês, num sistema todo em
    português, e sem dizer que campo falhou. A recusa aqui não é digitação
    errada: é o coorientador tentando uma opção que a tela não lhe oferece."""

    def pre_validate(self, form):
        # ValidationError, e não ValueError: só a primeira o WTForms captura e
        # transforma em erro de campo — a outra sobe como erro 500
        if self.data not in [valor for valor, _ in self.choices]:
            raise ValidationError(
                "Opção de natureza da versão inválida para o seu papel: "
                "devolver a tarefa cabe ao orientador principal."
            )


def campo_natureza() -> NaturezaField:
    """Campo montado com TODAS as opções; a rota restringe as escolhas de quem
    não pode devolver (ver `restringir_natureza`)."""
    return NaturezaField(
        "O que é esta versão?", choices=NATUREZA_CHOICES, default="registro"
    )


def restringir_natureza(campo, pode_devolver: bool) -> None:
    """Tira "devolução" das escolhas de quem não é o orientador principal.

    Devolver muda o estado do marco, e o cronograma é do orientador principal —
    a rota `/devolver` responde 403 ao coorientador. Sem isto, o mesmo ato
    passaria pelo upload. Mexer nas `choices` basta: o `RadioField` valida o
    valor recebido contra elas, então um POST forjado cai como formulário
    inválido, sem gravar nada."""
    if not pode_devolver:
        campo.choices = [c for c in NATUREZA_CHOICES if c[0] != "devolucao"]


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
