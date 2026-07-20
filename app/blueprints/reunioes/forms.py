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


class AtaGrupoForm(FlaskForm):
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
