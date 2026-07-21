from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    BooleanField,
    DateField,
    DateTimeLocalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Optional,
    ValidationError,
)

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


class AjusteDatasForm(FlaskForm):
    """Alteração das datas do vínculo, privativa do administrador — inclusive a
    dilatação de prazo, que antes passava pelo evento de prorrogação. A
    fundamentação é obrigatória porque a trilha de auditoria já guarda as datas
    anterior e nova, mas não guardaria o motivo."""

    data_inicio = DateField("Data de início", validators=[DataRequired()])
    data_fim_prevista = DateField("Fim previsto", validators=[Optional()])
    fundamentacao = TextAreaField("Fundamentação", validators=[DataRequired()])
    submit = SubmitField("Aplicar datas")

    def validate_data_fim_prevista(self, field):
        if field.data and self.data_inicio.data and field.data <= self.data_inicio.data:
            raise ValidationError("O fim previsto deve ser posterior ao início.")


class EncerrarOrientacaoForm(FlaskForm):
    # "suspensa" existe em STATUS_ORIENTACAO mas nenhuma tela a apõe desde que o
    # registro de eventos saiu: o trancamento não alterava o comportamento do
    # sistema — marcos de vínculo suspenso continuavam contando como atrasados —,
    # de modo que era rótulo, não estado. O valor permanece no Enum apenas para
    # que registro legado continue legível (ver avaliacoes/DECISOES.md).
    status = SelectField(
        "Novo status",
        choices=[("concluida", "Concluída"), ("cancelada", "Cancelada")],
    )
    submit = SubmitField("Aplicar")


class CoorientadorForm(FlaskForm):
    usuario_id = SelectField("Coorientador", coerce=int)
    submit = SubmitField("Designar coorientador")


class RemoverForm(FlaskForm):
    submit = SubmitField("Remover")


class ExcluirForm(FlaskForm):
    """Exclusão de conta — privativa do administrador."""

    submit = SubmitField("Excluir")


class GerarBackupForm(FlaskForm):
    submit = SubmitField("Gerar e baixar backup")


class _ConfirmacaoEscrita(FlaskForm):
    """Operações irreversíveis exigem digitar a palavra, não apenas clicar: o
    clique acidental é comum, a digitação deliberada não. Cada formulário
    declara o campo `confirmacao` na posição que lhe convém — herdá-lo daqui o
    colocaria antes dos demais, invertendo a ordem de leitura."""

    PALAVRA = ""

    def validate_confirmacao(self, field):
        if field.data.strip().upper() != self.PALAVRA:
            raise ValidationError(
                f'Para prosseguir, digite exatamente "{self.PALAVRA}".'
            )


class RestaurarBackupForm(_ConfirmacaoEscrita):
    PALAVRA = "RESTAURAR"

    arquivo = FileField("Arquivo de backup (.zip)", validators=[FileRequired()])
    confirmacao = StringField(
        'Digite "RESTAURAR" para confirmar', validators=[DataRequired()]
    )
    submit = SubmitField("Restaurar backup")


class ExpurgarBaseForm(_ConfirmacaoEscrita):
    PALAVRA = "APAGAR"

    confirmacao = StringField(
        'Digite "APAGAR" para confirmar', validators=[DataRequired()]
    )
    submit = SubmitField("Apagar a base")


class FiltroAuditoriaForm(FlaskForm):
    """Filtro da trilha, submetido por GET para que o recorte seja endereçável.
    Os carimbos são gravados em UTC; os campos abaixo seguem a mesma referência."""

    class Meta:
        csrf = False  # consulta sem efeito colateral

    de = DateTimeLocalField(
        "De (UTC)", validators=[Optional()], format="%Y-%m-%dT%H:%M"
    )
    ate = DateTimeLocalField(
        "Até (UTC)", validators=[Optional()], format="%Y-%m-%dT%H:%M"
    )
    usuario_id = SelectField("Usuário", coerce=int, default=0, validators=[Optional()])
    acao = SelectField("Ação", default="", validators=[Optional()])
    submit = SubmitField("Filtrar")

    def validate_ate(self, field):
        if field.data and self.de.data and field.data < self.de.data:
            raise ValidationError("O fim do intervalo deve ser posterior ao início.")
