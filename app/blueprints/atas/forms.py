from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    TimeField,
    widgets,
)
from wtforms.validators import (
    URL,
    DataRequired,
    Length,
    Optional,
    ValidationError,
)

from app.models.ata import RESULTADO_LABEL, RESULTADOS_PARECER, TIPOS_PARECER

# Nota exibida sob os campos longos, que aceitam marcação. O texto é curto de
# propósito: o repertório completo está na Ajuda.
AJUDA_MARCACAO = (
    "Aceita formatação: **negrito**, *itálico*, # título, - lista, "
    "> citação e tabelas. Ver Ajuda para o repertório completo."
)

AJUDA_MARCOS = (
    "Marcos do cronograma tratados nesta reunião. Ao finalizar a ata, esta "
    "associação congela junto com o registro."
)

AJUDA_LINK = (
    "Opcional. Endereço da sala virtual (Meet, Zoom, Teams), que vai no aviso "
    "enviado aos convidados. Deixe em branco se a reunião é presencial."
)

# Esquemas admitidos no endereço da sala virtual. A restrição não é formalismo:
# o valor é renderizado como `href` na tela e no e-mail em HTML, e um esquema
# arbitrário abriria a porta para `javascript:` e afins. A política de conteúdo
# do sistema já barra script, mas o e-mail sai do nosso alcance e é lido no
# cliente do destinatário, onde política alguma nossa vale.
ESQUEMAS_LINK = ("http://", "https://")


def validar_link_reuniao(form, field):
    if not field.data:
        return
    if not field.data.strip().lower().startswith(ESQUEMAS_LINK):
        raise ValidationError(
            "Informe o endereço completo da sala, começando com https://"
        )


def _aparar(valor):
    """Apara o espaço em volta antes de qualquer validação. Sem isto, um
    endereço colado com um espaço ao final seria recusado pelo validador de URL,
    coisa que quem cola de um convite não entenderia."""
    return valor.strip() if isinstance(valor, str) else valor


def campo_link_reuniao():
    """Campo do endereço da sala virtual, declarado num ponto só para que o
    agendamento e a edição do rascunho não divirjam em rótulo nem em validação."""
    return StringField(
        "Link da reunião online",
        filters=[_aparar],
        validators=[
            Optional(),
            Length(max=500),
            URL(require_tld=True, message="Endereço inválido."),
            validar_link_reuniao,
        ],
        description=AJUDA_LINK,
    )


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class AtaForm(FlaskForm):
    data_reuniao = DateField("Data da reunião", validators=[DataRequired()])
    hora_reuniao = TimeField("Hora da reunião", validators=[Optional()])
    link_reuniao = campo_link_reuniao()
    pauta = TextAreaField("Pauta", validators=[DataRequired()], description=AJUDA_MARCACAO)
    deliberacoes = TextAreaField(
        "Deliberações", validators=[DataRequired()], description=AJUDA_MARCACAO
    )
    marcos = MultiCheckboxField(
        "Marcos discutidos", coerce=int, validators=[Optional()], description=AJUDA_MARCOS
    )
    submit = SubmitField("Salvar rascunho")


class AtaEdicaoForm(FlaskForm):
    """Edição de rascunho: data/hora mudam apenas pelo fluxo de reagendamento.

    As deliberações são opcionais aqui, e não por descuido: a reunião agendada
    ainda não aconteceu, e exigi-las impediria de corrigir a pauta antes do
    encontro. A obrigatoriedade vale no momento certo, o da finalização, imposta
    por `services.atas.finalizar_ata`."""

    link_reuniao = campo_link_reuniao()
    pauta = TextAreaField("Pauta", validators=[DataRequired()], description=AJUDA_MARCACAO)
    deliberacoes = TextAreaField(
        "Deliberações", validators=[Optional()], description=AJUDA_MARCACAO
    )
    marcos = MultiCheckboxField(
        "Marcos discutidos", coerce=int, validators=[Optional()], description=AJUDA_MARCOS
    )
    submit = SubmitField("Salvar alterações")


class ReagendarForm(FlaskForm):
    data_reuniao = DateField("Nova data", validators=[DataRequired()])
    hora_reuniao = TimeField("Nova hora", validators=[Optional()])
    motivo = TextAreaField("Motivo (opcional)", validators=[Optional()])
    submit = SubmitField("Reagendar reunião")


class AcaoForm(FlaskForm):
    """Confirmação simples (CSRF) para ações de botão."""

    submit = SubmitField("Confirmar")


class FinalizarAtaForm(FlaskForm):
    submit = SubmitField("Finalizar ata")


class ParecerForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[(t, t.capitalize()) for t in TIPOS_PARECER])
    versao_documento_id = SelectField(
        "Versão de documento", coerce=int, validators=[Optional()]
    )
    conteudo = TextAreaField(
        "Parecer", validators=[DataRequired()], description=AJUDA_MARCACAO
    )
    resultado = SelectField(
        "Resultado", choices=[(r, RESULTADO_LABEL[r]) for r in RESULTADOS_PARECER]
    )
    submit = SubmitField("Emitir parecer")
