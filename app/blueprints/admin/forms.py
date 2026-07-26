from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    BooleanField,
    DateField,
    DateTimeLocalField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from app.models.cronograma import TIPO_MARCO_LABEL, TIPOS_MARCO
from app.models.orientacao import MODALIDADE_LABEL, MODALIDADES
from app.models.user import PAPEIS


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class UsuarioForm(FlaskForm):
    """Cadastro da conta, sem campo de senha.

    O administrador não digita senha alheia: a da criação é gerada e enviada ao
    titular, e a reposição tem botão próprio. Senha escolhida por terceiro tende
    a ser fraca, repetida entre contas e conhecida por quem a digitou por tempo
    indeterminado."""

    nome = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "E-mail", validators=[DataRequired(), Email(), Length(max=254)],
        description="É o nome de usuário no acesso, e o endereço para onde vão "
                    "a senha inicial e os avisos do sistema.",
    )
    telefone = StringField(
        "Telefone celular", validators=[Optional(), Length(max=32)]
    )
    papel = SelectField("Papel", choices=[(p, p.capitalize()) for p in PAPEIS])
    ativo = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")


class SenhaTemporariaForm(FlaskForm):
    """Reposição de acesso: gera senha aleatória e a envia ao titular."""

    submit = SubmitField("Gerar senha temporária e enviar")


class ModeloForm(FlaskForm):
    """Envio de um arquivo-modelo pelo administrador."""

    titulo = StringField("Título", validators=[DataRequired(), Length(max=255)])
    descricao = TextAreaField("Descrição", validators=[Optional(), Length(max=1000)])
    arquivo = FileField("Arquivo do modelo", validators=[FileRequired()])
    submit = SubmitField("Enviar modelo")


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

    def validate_data_fim_prevista(self, field):
        # mesma regra do AjusteDatasForm: fim antes do início passava aqui e o
        # relógio de risco do painel ficava mudo justamente para esse vínculo
        if field.data and self.data_inicio.data and field.data <= self.data_inicio.data:
            raise ValidationError("O fim previsto deve ser posterior ao início.")


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


class EliminarUsuarioForm(FlaskForm):
    """Eliminação LGPD dos dados de um usuário — irreversível. A confirmação é o
    próprio e-mail do titular (não uma palavra fixa): força o administrador a
    identificar exatamente quem está sendo eliminado, e o e-mail certo é validado
    na rota, contra o alvo."""

    confirmacao = StringField(
        "Digite o e-mail do titular para confirmar", validators=[DataRequired()]
    )
    submit = SubmitField("Eliminar dados do usuário")


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


class ConfiguracaoEmailForm(FlaskForm):
    """A senha nunca é devolvida à tela: o campo chega sempre em branco e só
    substitui a guardada quando algo é digitado. Assim ela não trafega de volta
    ao navegador nem fica no HTML da página a cada visita."""

    ativo = BooleanField("Envio de e-mail habilitado")
    servidor = StringField(
        "Servidor SMTP", validators=[DataRequired(), Length(max=255)],
        description="O plano gratuito do PythonAnywhere alcança smtp.gmail.com; "
                    "smtp.office365.com é bloqueado.",
    )
    porta = IntegerField(
        "Porta", validators=[DataRequired(), NumberRange(min=1, max=65535)],
        description="587 para STARTTLS, 465 para SSL.",
    )
    usuario = StringField(
        "Conta de envio", validators=[DataRequired(), Email(), Length(max=254)],
        description="Convém uma conta dedicada ao sistema, não a pessoal: assim "
                    "um vazamento não alcança sua correspondência.",
    )
    senha = PasswordField(
        "Senha de app", validators=[Optional(), Length(max=255)],
        description="16 caracteres, gerada em myaccount.google.com com a "
                    "verificação em duas etapas ativa. Deixe em branco para "
                    "manter a senha já guardada.",
    )
    remetente_nome = StringField(
        "Nome do remetente", validators=[DataRequired(), Length(max=120)]
    )
    submit = SubmitField("Salvar configuração")


class ConfiguracaoRiscoForm(FlaskForm):
    """Parâmetros do selo de risco da coluna Prazo. Os limiares são percentuais
    do prazo decorrido do vínculo; os tipos marcados tornam o atraso do marco
    um alerta vermelho por si só."""

    limiar_medio = IntegerField(
        "Limiar do risco médio (%)",
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        description="Decorrido mais que este percentual do prazo do vínculo, o "
                    "selo fica amarelo.",
    )
    limiar_alto = IntegerField(
        "Limiar do risco alto (%)",
        validators=[DataRequired(), NumberRange(min=1, max=100)],
        description="Decorrido mais que este percentual, vermelho. Deve ser "
                    "maior que o limiar do risco médio.",
    )
    tipos_criticos = MultiCheckboxField(
        "Tipos de marco críticos",
        choices=[(t, TIPO_MARCO_LABEL[t]) for t in TIPOS_MARCO],
        validators=[Optional()],
        description="Marco de tipo crítico vencido e não concluído põe o vínculo "
                    "em risco alto (vermelho), qualquer que seja o percentual do "
                    "prazo. Desmarcar todos deixa o risco a cargo apenas do tempo.",
    )
    submit = SubmitField("Salvar parâmetros")

    def validate_limiar_alto(self, field):
        if self.limiar_medio.data and field.data and field.data <= self.limiar_medio.data:
            raise ValidationError(
                "O limiar do risco alto deve ser maior que o do risco médio."
            )


class TesteEmailForm(FlaskForm):
    destinatario = StringField(
        "Enviar teste para", validators=[DataRequired(), Email(), Length(max=254)]
    )
    submit = SubmitField("Enviar e-mail de teste")


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
