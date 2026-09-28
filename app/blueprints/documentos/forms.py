from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import (
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError


def exigir_arquivo_ou_comentario(form, field):
    """Uma versão precisa de arquivo OU comentário — nunca vazia. O arquivo
    deixou de ser obrigatório (retorno pode ser todo textual), mas os dois em
    branco não criam versão alguma. Validador do campo de arquivo, cruzando com
    `comentario`; reusado pelo anexo de marco."""
    anexos = getattr(form, "anexos", None)
    if not field.data and anexos is not None and anexos.data:
        raise ValidationError(
            "Os anexos acompanham um arquivo principal: envie-o também."
        )
    if not field.data and not (form.comentario.data or "").strip():
        raise ValidationError("Envie um arquivo ou escreva um comentário.")


def campo_anexos() -> MultipleFileField:
    """Arquivos que acompanham o principal (dados, figuras, carta). Campo à
    parte, e não um único campo múltiplo: a ordem em que o navegador entrega os
    arquivos não é controlável, e o principal — o texto que o parecer avalia —
    precisa ser escolha explícita de quem envia."""
    return MultipleFileField(
        "Anexos (opcional)",
        description="Arquivos que acompanham o principal: planilha, figuras, "
        "carta. Pode selecionar vários de uma vez.",
    )

# De quem é este arquivo, quando quem envia NÃO é a orientanda. O formulário só
# mostra o campo a gestores; a rota o ignora para a orientanda, cuja versão é
# sempre entrega dela. É um eixo binário — só decide se a versão pede parecer.
# "Devolução" NÃO está aqui: devolver é ato da tarefa (ver cronogramas), e a
# etiqueta de devolução nasce daquele ato, não de uma escolha no upload.
NATUREZA_CHOICES = [
    ("registro", "Registro meu (arquivo meu; não pede meu parecer)"),
    (
        "entrega",
        "Entrega da orientanda, que estou registrando por ela "
        "(entra na lista de pareceres, como se ela tivesse enviado)",
    ),
]


class NaturezaField(RadioField):
    """Escolha da natureza da versão, com a recusa dita em português (o WTForms
    responde "Not a valid choice." — inglês, num sistema todo em português)."""

    def pre_validate(self, form):
        # ValidationError, não ValueError: só a primeira o WTForms captura como
        # erro de campo — a outra sobe como erro 500
        if self.data not in [valor for valor, _ in self.choices]:
            raise ValidationError("Opção inválida para 'de quem é este arquivo'.")


def campo_natureza() -> NaturezaField:
    return NaturezaField(
        "De quem é este arquivo?", choices=NATUREZA_CHOICES, default="registro"
    )


def eh_entrega_da_orientanda(natureza: str) -> bool:
    """A escolha do formulário vira o flag `em_nome_do_orientando` da versão. O
    upload nunca marca `eh_devolucao` (isso é ato da tarefa)."""
    return natureza == "entrega"


class NovoDocumentoForm(FlaskForm):
    titulo = StringField(
        "Título",
        validators=[DataRequired("Informe o título do documento."), Length(max=255)],
    )
    marco_id = SelectField("Marco associado", coerce=int, validators=[Optional()])
    arquivo = FileField(
        "Arquivo principal", validators=[exigir_arquivo_ou_comentario]
    )
    anexos = campo_anexos()
    comentario = TextAreaField("Comentário", validators=[Optional()])
    natureza = campo_natureza()
    submit = SubmitField("Enviar")


class NovaVersaoForm(FlaskForm):
    arquivo = FileField(
        "Arquivo principal", validators=[exigir_arquivo_ou_comentario]
    )
    anexos = campo_anexos()
    comentario = TextAreaField("Comentário", validators=[Optional()])
    natureza = campo_natureza()
    submit = SubmitField("Enviar nova versão")


class ClassificarVersaoForm(FlaskForm):
    """Reclassifica uma versão já enviada (escotilha para registros antigos)."""

    natureza = SelectField("Natureza", choices=NATUREZA_CHOICES)
    submit = SubmitField("Aplicar")
