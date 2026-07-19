from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.cronograma import TIPOS_MARCO, TIPO_MARCO_LABEL


class MarcoForm(FlaskForm):
    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    tipo = SelectField(
        "Tipo", choices=[(t, TIPO_MARCO_LABEL[t]) for t in TIPOS_MARCO], default="outro"
    )
    descricao = TextAreaField("Descrição", validators=[Optional()])
    data_prevista = DateField("Data prevista", validators=[DataRequired()])
    ordem = IntegerField("Ordem", default=0, validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField("Salvar")


class ConfirmacaoForm(FlaskForm):
    submit = SubmitField("Confirmar")
