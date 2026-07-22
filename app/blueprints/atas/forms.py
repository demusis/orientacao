from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectField,
    SelectMultipleField,
    SubmitField,
    TextAreaField,
    TimeField,
    widgets,
)
from wtforms.validators import DataRequired, Optional

from app.models.ata import RESULTADO_LABEL, RESULTADOS_PARECER, TIPOS_PARECER

# Nota exibida sob os campos longos, que aceitam marcação. O texto é curto de
# propósito: o repertório completo está na Ajuda.
AJUDA_MARCACAO = (
    "Aceita formatação: **negrito**, *itálico*, # título, - lista, "
    "> citação e tabelas. Ver Ajuda para o repertório completo."
)

AJUDA_MARCOS = (
    "Marcos do cronograma tratados nesta reunião. Ao finalizar a ata, esta "
    "associação congela junto com o registro."
)


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class AtaForm(FlaskForm):
    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    hora_reuniao = TimeField("Hora da reunião", validators=[Optional()])
    pauta = TextAreaField("Pauta", validators=[DataRequired()], description=AJUDA_MARCACAO)
    deliberacoes = TextAreaField(
        "Deliberações", validators=[DataRequired()], description=AJUDA_MARCACAO
    )
    marcos = MultiCheckboxField(
        "Marcos discutidos", coerce=int, validators=[Optional()], description=AJUDA_MARCOS
    )
    submit = SubmitField("Salvar rascunho")


class AtaEdicaoForm(FlaskForm):
    """Edição de rascunho: data/hora mudam apenas pelo fluxo de reagendamento."""

    pauta = TextAreaField("Pauta", validators=[DataRequired()], description=AJUDA_MARCACAO)
    deliberacoes = TextAreaField(
        "Deliberações", validators=[DataRequired()], description=AJUDA_MARCACAO
    )
    marcos = MultiCheckboxField(
        "Marcos discutidos", coerce=int, validators=[Optional()], description=AJUDA_MARCOS
    )
    submit = SubmitField("Salvar alterações")


class ReagendarForm(FlaskForm):
    data_reuniao = DateField("Nova data", validators=[DataRequired()])
    hora_reuniao = TimeField("Nova hora", validators=[Optional()])
    motivo = TextAreaField("Motivo (opcional)", validators=[Optional()])
    submit = SubmitField("Reagendar reunião")


class AcaoForm(FlaskForm):
    """Confirmação simples (CSRF) para ações de botão."""

    submit = SubmitField("Confirmar")


class FinalizarAtaForm(FlaskForm):
    submit = SubmitField("Finalizar ata")


class ParecerForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[(t, t.capitalize()) for t in TIPOS_PARECER])
    versao_documento_id = SelectField(
        "Versão de documento", coerce=int, validators=[Optional()]
    )
    conteudo = TextAreaField(
        "Parecer", validators=[DataRequired()], description=AJUDA_MARCACAO
    )
    resultado = SelectField(
        "Resultado", choices=[(r, RESULTADO_LABEL[r]) for r in RESULTADOS_PARECER]
    )
    submit = SubmitField("Emitir parecer")
