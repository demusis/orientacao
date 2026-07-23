from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from app.models.orientacao import MODALIDADE_LABEL, MODALIDADES


class OrientandoForm(FlaskForm):
    """Criação da conta e do vínculo de orientação em ato único: o orientador
    que cria o orientando torna-se seu orientador principal.

    Sem campo de senha: ela é gerada e enviada ao orientando, que é obrigado a
    trocá-la no primeiro acesso. O orientador não conhece a senha de ninguém."""

    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "E-mail", validators=[DataRequired(), Email(), Length(max=254)],
        description="É o nome de usuário no acesso, e o endereço para onde vão "
                    "a senha inicial e os avisos do sistema.",
    )
    telefone = StringField(
        "Telefone celular", validators=[Optional(), Length(max=32)]
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
