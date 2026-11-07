"""
Erros do app.

`ErroDeNegocio` é para mensagens que NÓS escrevemos para a pessoa ler ("O total de parcelas
deve estar entre 1 e 48."). É um `ValueError`, então código antigo que captura `ValueError`
continua funcionando. Qualquer OUTRO erro (falha do Google, bug, etc.) é técnico: a tela não
mostra o texto dele (ver `utils.widgets.mostrar_erro`).
"""


class ErroDeNegocio(ValueError):
    """Mensagem de validação pensada para o usuário final; pode ser exibida como está."""
