from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class TituloProjetoForm(FlaskForm):
    """Alteração do título pelo orientador. A fundamentação é exigida porque a
    mudança é registrada como evento formal do vínculo, preservando o título
    anterior — as datas do vínculo permanecem fora do alcance do orientador."""

    titulo_projeto = StringField(
        "Novo título do projeto", validators=[DataRequired(), Length(max=255)]
    )
    fundamentacao = TextAreaField("Fundamentação", validators=[DataRequired()])
    submit = SubmitField("Alterar título")
