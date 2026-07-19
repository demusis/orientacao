from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class OrientandoForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=254)])
    senha = PasswordField(
        "Senha inicial", validators=[DataRequired(), Length(min=8, max=128)]
    )
    submit = SubmitField("Criar orientando")


class ExcluirForm(FlaskForm):
    submit = SubmitField("Excluir")
