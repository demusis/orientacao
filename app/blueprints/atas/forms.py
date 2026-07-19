from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.models.ata import RESULTADOS_PARECER, RESULTADO_LABEL, TIPOS_PARECER


class AtaForm(FlaskForm):
    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    pauta = TextAreaField("Pauta", validators=[DataRequired()])
    deliberacoes = TextAreaField("Deliberações", validators=[DataRequired()])
    submit = SubmitField("Salvar rascunho")


class FinalizarAtaForm(FlaskForm):
    submit = SubmitField("Finalizar ata")


class ParecerForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[(t, t.capitalize()) for t in TIPOS_PARECER])
    versao_documento_id = SelectField(
        "Versão de documento", coerce=int, validators=[Optional()]
    )
    conteudo = TextAreaField("Parecer", validators=[DataRequired()])
    resultado = SelectField(
        "Resultado", choices=[(r, RESULTADO_LABEL[r]) for r in RESULTADOS_PARECER]
    )
    submit = SubmitField("Emitir parecer")
