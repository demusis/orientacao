from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectMultipleField,
    SubmitField,
    TextAreaField,
    TimeField,
    widgets,
)
from wtforms.validators import DataRequired, Optional, ValidationError

from app.blueprints.cronogramas.forms import CamposMarco


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def _minimo_um(form, field):
    if len(field.data or []) < 1:
        raise ValidationError("Selecione ao menos um orientando.")


class AgendarReuniaoForm(FlaskForm):
    """Marcação de reunião futura. Sem deliberações: não há o que deliberar
    antes do encontro. A pauta é obrigatória porque é o que se comunica ao
    convidado, que precisa saber do que se trata para se preparar."""

    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    hora_reuniao = TimeField("Hora da reunião", validators=[Optional()])
    pauta = TextAreaField(
        "Pauta",
        validators=[DataRequired()],
        description="Vai no aviso enviado aos convidados. As deliberações são "
        "preenchidas depois da reunião.",
    )
    orientacoes = MultiCheckboxField(
        "Convidados (um ou mais)", coerce=int, validators=[_minimo_um]
    )
    submit = SubmitField("Agendar e avisar")


class ConvidadosForm(FlaskForm):
    orientacoes = MultiCheckboxField(
        "Convidados (um ou mais)", coerce=int, validators=[_minimo_um]
    )
    submit = SubmitField("Salvar e avisar")


class CancelarReuniaoForm(FlaskForm):
    motivo = TextAreaField(
        "Motivo do cancelamento",
        validators=[DataRequired()],
        description="Vai no aviso enviado aos convidados e fica no registro da "
        "reunião.",
    )
    submit = SubmitField("Cancelar reunião e avisar")


class AtaGrupoForm(FlaskForm):
    """Registro retroativo: a reunião já aconteceu e a ata é redigida de uma
    vez. Não dispara convite, pelo motivo evidente."""

    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    hora_reuniao = TimeField("Hora da reunião", validators=[Optional()])
    pauta = TextAreaField("Pauta", validators=[DataRequired()])
    deliberacoes = TextAreaField("Deliberações", validators=[DataRequired()])
    orientacoes = MultiCheckboxField(
        "Orientandos presentes (um ou mais)", coerce=int, validators=[_minimo_um]
    )
    submit = SubmitField("Salvar rascunho")


class MarcoGrupoForm(CamposMarco, FlaskForm):
    orientacoes = MultiCheckboxField(
        "Orientandos designados (um ou mais)", coerce=int, validators=[_minimo_um]
    )
    submit = SubmitField("Criar tarefa")
