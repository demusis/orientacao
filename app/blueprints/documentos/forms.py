from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class NovoDocumentoForm(FlaskForm):
    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    marco_id = SelectField("Marco associado", coerce=int, validators=[Optional()])
    arquivo = FileField("Arquivo", validators=[FileRequired()])
    comentario = TextAreaField("Comentário", validators=[Optional()])
    submit = SubmitField("Enviar")


class NovaVersaoForm(FlaskForm):
    arquivo = FileField("Arquivo", validators=[FileRequired()])
    comentario = TextAreaField("Comentário", validators=[Optional()])
    submit = SubmitField("Enviar nova versão")
