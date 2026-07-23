"""Geração de senha provisória.

A senha que o sistema gera trafega em texto claro por e-mail e é digitada uma
única vez, no primeiro acesso, antes da troca obrigatória. Isso define as duas
exigências, que puxam em sentidos opostos:

- **imprevisível**, porque o e-mail pode ser lido por terceiros e a senha vale
  até ser trocada. Daí `secrets`, e não `random`, cujo gerador é determinístico
  e reconstituível a partir de poucas saídas;
- **transcritível sem erro**, porque quem recebe costuma copiar à mão de um
  celular. Daí a exclusão dos caracteres que se confundem entre si em fonte de
  leitura corrente.

Fora do alfabeto: `0` e `O`, `1`, `l` e `I`, `5` e `S`, `2` e `Z`. Sobram 48
símbolos; com 12 posições, são cerca de 67 bits de entropia, folga suficiente
para uma senha que pode ficar parada numa caixa de e-mail até alguém usá-la.
"""
import secrets

ALFABETO = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXY346789"
COMPRIMENTO = 12


def gerar(comprimento: int = COMPRIMENTO) -> str:
    """Senha provisória, formatada em blocos de quatro para facilitar a leitura
    em voz alta e a conferência visual (ex.: `htkp-9fnq-wme4`).

    Os hifens contam como conteúdo para quem digita, mas não como entropia: ela
    vem apenas das posições sorteadas."""
    bruta = "".join(secrets.choice(ALFABETO) for _ in range(comprimento))
    return "-".join(bruta[i : i + 4] for i in range(0, len(bruta), 4))
