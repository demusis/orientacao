from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.blueprints.reunioes.forms import MultiCheckboxField


class TarefaField(SelectField):
    """Recusa em português valor fora da lista (o WTForms diz "Not a valid
    choice."). A lista só traz tarefas dos vínculos do próprio orientador: é
    ela que barra valor forjado."""

    def pre_validate(self, form):
        if self.data not in [valor for valor, _ in self.choices]:
            raise ValidationError("Tarefa inválida para o material.")


class MaterialForm(FlaskForm):
    """Publicação de material de consulta. As choices de `orientacoes` e
    `tarefa` vêm da rota (os vínculos ativos do orientador)."""

    titulo = StringField(
        "Título", validators=[DataRequired("Informe o título."), Length(max=255)]
    )
    descricao = TextAreaField(
        "Descrição (opcional)", validators=[Optional(), Length(max=2000)]
    )
    arquivo = FileField("Arquivo", validators=[FileRequired("Escolha o arquivo.")])
    orientacoes = MultiCheckboxField("Compartilhar com", coerce=int)
    tarefa = TarefaField(
        "Mostrar também na tarefa (opcional)",
        description="Escolhendo uma tarefa, o material aparece na página dela e é "
        "compartilhado com os orientandos dela.",
        validators=[Optional()],
    )
    submit = SubmitField("Publicar")

    def validate_orientacoes(self, field):
        if not field.data and not self.tarefa.data:
            raise ValidationError(
                "Escolha ao menos um orientando (ou uma tarefa) para compartilhar."
            )


class ExcluirMaterialForm(FlaskForm):
    submit = SubmitField("Excluir")
