from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
    widgets,
)

from app.models.cronograma import TIPOS_MARCO, TIPO_MARCO_LABEL
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def _minimo_dois(form, field):
    if len(field.data or []) < 2:
        raise ValidationError(
            "Selecione ao menos dois vínculos. Para reunião individual, "
            "utilize o módulo do próprio vínculo."
        )


class AtaGrupoForm(FlaskForm):
    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    hora_reuniao = TimeField("Hora da reunião", validators=[Optional()])
    pauta = TextAreaField("Pauta", validators=[DataRequired()])
    deliberacoes = TextAreaField("Deliberações", validators=[DataRequired()])
    orientacoes = MultiCheckboxField(
        "Orientandos presentes", coerce=int, validators=[_minimo_dois]
    )
    submit = SubmitField("Salvar rascunho")


class MarcoGrupoForm(FlaskForm):
    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    tipo = SelectField(
        "Tipo", choices=[(t, TIPO_MARCO_LABEL[t]) for t in TIPOS_MARCO], default="outro"
    )
    descricao = TextAreaField("Descrição", validators=[Optional()])
    data_prevista = DateField("Data prevista", validators=[DataRequired()])
    ordem = IntegerField("Ordem", default=0, validators=[Optional(), NumberRange(min=0)])
    orientacoes = MultiCheckboxField(
        "Orientandos designados", coerce=int, validators=[_minimo_dois]
    )
    submit = SubmitField("Criar tarefa em grupo")
