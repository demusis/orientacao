from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

from app.models.cronograma import (
    ETAPA_MARCO_LABEL,
    ETAPAS_MARCO,
    TIPO_MARCO_LABEL,
    TIPOS_MARCO,
)


class CamposMarco:
    """Campos comuns ao marco individual e à tarefa atribuída em grupo,
    mantidos em um único ponto para que os dois formulários não divirjam."""

    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    tipo = SelectField(
        "Tipo", choices=[(t, TIPO_MARCO_LABEL[t]) for t in TIPOS_MARCO], default="outro"
    )
    descricao = TextAreaField("Descrição", validators=[Optional()])
    data_prevista = DateField("Data prevista", validators=[DataRequired()])
    # coerce=int já recusa valor fora de choices; dispensa NumberRange
    etapa = SelectField(
        "Etapa do projeto",
        coerce=int,
        default=0,
        choices=[(c, ETAPA_MARCO_LABEL[c]) for c in ETAPAS_MARCO],
    )


class MarcoForm(CamposMarco, FlaskForm):
    submit = SubmitField("Salvar")


class ConfirmacaoForm(FlaskForm):
    submit = SubmitField("Confirmar")
