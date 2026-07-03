"""
Garante que a raiz do projeto (onde ficam config.py, utils/, logica/ etc.)
esteja no sys.path ao rodar os testes, independentemente do diretório
a partir do qual `pytest` é chamado.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
