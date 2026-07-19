from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class MarcoForm(FlaskForm):
    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    descricao = TextAreaField("Descrição", validators=[Optional()])
    data_prevista = DateField("Data prevista", validators=[DataRequired()])
    ordem = IntegerField("Ordem", default=0, validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField("Salvar")


class ConfirmacaoForm(FlaskForm):
    submit = SubmitField("Confirmar")
