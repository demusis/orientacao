from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Optional

from app.models.orientacao import MODALIDADES, MODALIDADE_LABEL
from app.models.user import PAPEIS


class UsuarioForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=254)])
    papel = SelectField("Papel", choices=[(p, p.capitalize()) for p in PAPEIS])
    senha = PasswordField("Senha inicial", validators=[Optional(), Length(min=8, max=128)])
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")


class OrientacaoForm(FlaskForm):
    orientador_id = SelectField("Orientador", coerce=int)
    orientando_id = SelectField("Orientando", coerce=int)
    modalidade = SelectField(
        "Modalidade", choices=[(m, MODALIDADE_LABEL[m]) for m in MODALIDADES]
    )
    titulo_projeto = StringField(
        "Título do projeto", validators=[DataRequired(), Length(max=255)]
    )
    data_inicio = DateField("Data de início", validators=[DataRequired()])
    data_fim_prevista = DateField("Fim previsto", validators=[Optional()])
    submit = SubmitField("Salvar")


class EventoVinculoForm(FlaskForm):
    tipo = SelectField(
        "Tipo do evento",
        choices=[
            ("prorrogacao", "Prorrogação de prazo"),
            ("trancamento", "Trancamento"),
            ("destrancamento", "Destrancamento"),
            ("mudanca_titulo", "Mudança de título"),
        ],
    )
    fundamentacao = TextAreaField("Fundamentação", validators=[DataRequired()])
    data_nova = DateField("Novo fim previsto (prorrogação)", validators=[Optional()])
    texto_novo = StringField(
        "Novo título (mudança de título)", validators=[Optional(), Length(max=255)]
    )
    submit = SubmitField("Registrar evento")


class EncerrarOrientacaoForm(FlaskForm):
    status = SelectField(
        "Novo status",
        choices=[("concluida", "Concluída"), ("suspensa", "Suspensa"), ("cancelada", "Cancelada")],
    )
    submit = SubmitField("Aplicar")


class CoorientadorForm(FlaskForm):
    usuario_id = SelectField("Coorientador", coerce=int)
    submit = SubmitField("Designar coorientador")


class RemoverForm(FlaskForm):
    submit = SubmitField("Remover")
