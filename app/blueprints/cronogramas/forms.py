from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DateField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.blueprints.documentos.forms import (
    campo_anexos,
    campo_natureza,
    exigir_arquivo_ou_comentario,
)
from app.models.cronograma import (
    ENTREGA_ESPERADA_LABEL,
    ENTREGAS_ESPERADAS,
    ETAPA_MARCO_LABEL,
    ETAPAS_MARCO,
    TIPO_MARCO_LABEL,
    TIPOS_MARCO,
)


class EscolhaField(RadioField):
    """RadioField com a recusa em português (o WTForms diz "Not a valid
    choice."). ValidationError, não ValueError: só a primeira vira erro de
    campo — a outra sobe como erro 500."""

    def pre_validate(self, form):
        # tarefa anterior ao campo chega com None: vale como "" (não
        # especificado), se essa opção existir
        valor = "" if self.data is None else self.data
        if valor not in [v for v, _ in self.choices]:
            raise ValidationError("Escolha uma das opções.")


class CamposMarco:
    """Campos comuns ao marco individual e à tarefa atribuída em grupo,
    mantidos em um único ponto para que os dois formulários não divirjam."""

    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    # a pergunta que a orientanda faz ao abrir a tarefa: o que entregar?
    entrega_esperada = EscolhaField(
        "O que esta tarefa espera?",
        choices=[(e, ENTREGA_ESPERADA_LABEL[e]) for e in ENTREGAS_ESPERADAS]
        + [("", "Não especificar")],
        default="documento",
    )
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


class MarcoIndividualForm(MarcoForm):
    """O marco de um só vínculo pode apontar o texto a revisar — na tarefa em
    grupo não, pois cada orientanda tem os seus documentos. As choices vêm da
    rota (os documentos do vínculo)."""

    documento_base_id = SelectField(
        "Texto a revisar (só para \"Revisar um texto\")",
        coerce=int,
        default=0,
        validators=[Optional()],
    )

    def validate_documento_base_id(self, field):
        if self.entrega_esperada.data == "revisao" and not field.data:
            raise ValidationError("Escolha o texto a revisar.")


class ConfirmacaoForm(FlaskForm):
    submit = SubmitField("Confirmar")


class SinalizarForm(FlaskForm):
    """Sinalização de conclusão pelo orientando, com uma nota opcional."""

    nota = TextAreaField("Nota (opcional)", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Sinalizar conclusão")


class DevolverForm(FlaskForm):
    """Devolução da entrega ao orientando — a porta única. Nota do que corrigir,
    e, opcionalmente, o arquivo corrigido anexado a um documento do marco, tudo
    num passo. As choices de `documento_id` são preenchidas na rota."""

    nota = TextAreaField(
        "O que precisa corrigir (opcional)", validators=[Optional(), Length(max=2000)]
    )
    documento_id = SelectField(
        "Anexar o arquivo corrigido a", coerce=int, validators=[Optional()]
    )
    arquivo = FileField("Arquivo corrigido (opcional)", validators=[Optional()])
    anexos = campo_anexos()
    submit = SubmitField("Devolver para revisão")


NOVO_DOCUMENTO = "novo"


class EntregaTarefaForm(FlaskForm):
    """Envio pela página da tarefa — a porta da entrega. Pergunta primeiro para
    onde vai o arquivo: **nova versão** de um documento da tarefa (a revisão de
    um texto é isso, não um documento paralelo) ou um **documento novo**. As
    choices de `destino` vêm da rota.

    `sinalizar` (só para a orientanda, com a tarefa aberta) junta os dois atos
    que antes eram separados: enviar e avisar o orientador."""

    destino = EscolhaField("Para onde vai este envio?")
    # sem Optional(): ele encerraria a cadeia antes de `validate_titulo`, que é
    # quem exige o título só quando o destino é documento novo
    titulo = StringField("Título do documento novo", validators=[Length(max=255)])
    arquivo = FileField(
        "Arquivo principal", validators=[exigir_arquivo_ou_comentario]
    )
    anexos = campo_anexos()
    comentario = TextAreaField("Comentário", validators=[Optional()])
    natureza = campo_natureza()
    sinalizar = BooleanField(
        "Esta é a entrega da tarefa — avisar o orientador para conferir",
        default=True,
    )
    submit = SubmitField("Enviar")

    def validate_titulo(self, field):
        if self.destino.data == NOVO_DOCUMENTO and not (field.data or "").strip():
            raise ValidationError("Informe o título do documento novo.")
