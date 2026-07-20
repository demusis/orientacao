from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from app.models.orientacao import MODALIDADE_LABEL, MODALIDADES


class OrientandoForm(FlaskForm):
    """Criação da conta e do vínculo de orientação em ato único: o orientador
    que cria o orientando torna-se seu orientador principal."""

    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=254)])
    senha = PasswordField(
        "Senha inicial", validators=[DataRequired(), Length(min=8, max=128)]
    )
    modalidade = SelectField(
        "Modalidade", choices=[(m, MODALIDADE_LABEL[m]) for m in MODALIDADES]
    )
    titulo_projeto = StringField(
        "Título do projeto", validators=[DataRequired(), Length(max=255)]
    )
    data_inicio = DateField("Início da orientação", validators=[DataRequired()])
    data_fim_prevista = DateField("Fim previsto", validators=[Optional()])
    submit = SubmitField("Criar orientando e vínculo")

    def validate_data_fim_prevista(self, field):
        if field.data and self.data_inicio.data and field.data <= self.data_inicio.data:
            raise ValidationError("O fim previsto deve ser posterior ao início.")
