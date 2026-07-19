from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class LoginForm(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(), Email()])
    senha = PasswordField("Senha", validators=[DataRequired()])
    lembrar = BooleanField("Manter sessão")
    submit = SubmitField("Entrar")


class TrocaSenhaForm(FlaskForm):
    senha_atual = PasswordField("Senha atual", validators=[DataRequired()])
    nova_senha = PasswordField(
        "Nova senha", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirmacao = PasswordField(
        "Confirmação",
        validators=[DataRequired(), EqualTo("nova_senha", message="Senhas não conferem.")],
    )
    submit = SubmitField("Alterar senha")
