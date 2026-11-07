"""
Limite de tentativas de login COMPARTILHADO entre todas as sessões do app.

O contador antigo vivia no `st.session_state` (cada aba nova começava do zero, e um F5
também). Aqui as falhas ficam num objeto único no servidor, então abrir várias abas em
paralelo não ajuda a adivinhar a senha.

Regras:
  • por nome digitado (qualquer nome, existente ou não — assim não dá para descobrir quais
    usuários existem): `max_falhas` falhas dentro de `janela_s` bloqueiam esse nome por
    `bloqueio_s`;
  • global: `max_falhas_global` falhas somando todos os nomes bloqueiam TODOS os logins por
    `bloqueio_s` (cobre quem testa uma senha comum em muitos nomes diferentes);
  • durante o bloqueio nem a senha certa entra (a senha nem chega a ser conferida);
  • login com sucesso zera as falhas daquele nome.

Puro (sem Streamlit) e com relógio injetável, para testar. O estado some quando o app
reinicia, o que é aceitável: o atacante não consegue reiniciar o servidor.
"""

import math
import threading
import time
from collections import deque

_GLOBAL = "*global*"
_OUTROS = "*outros*"


class LimiteLogin:
    def __init__(self, max_falhas: int = 5, janela_s: float = 900, bloqueio_s: float = 900,
                 max_falhas_global: int = 30, max_chaves: int = 500, relogio=time.monotonic):
        self.max_falhas = max_falhas
        self.janela_s = janela_s
        self.bloqueio_s = bloqueio_s
        self.max_falhas_global = max_falhas_global
        self.max_chaves = max_chaves
        self._relogio = relogio
        self._falhas = {}      # chave -> deque de instantes de falha
        self._bloqueio = {}    # chave -> instante em que o bloqueio termina
        self._trava = threading.Lock()

    # ── utilidades internas (chamar sempre com a trava) ────────────────────────
    @staticmethod
    def normalizar(nome) -> str:
        return str(nome or "").strip().lower()[:64]

    def _chave(self, nome) -> str:
        """Nome normalizado; passado de `max_chaves` nomes distintos, os novos dividem uma chave só."""
        n = self.normalizar(nome)
        if n in self._falhas or n in self._bloqueio or len(self._falhas) < self.max_chaves:
            return n
        return _OUTROS

    def _podar(self, agora: float):
        for chave in list(self._falhas):
            fila = self._falhas[chave]
            while fila and agora - fila[0] > self.janela_s:
                fila.popleft()
            if not fila:
                del self._falhas[chave]
        for chave in list(self._bloqueio):
            if self._bloqueio[chave] <= agora:
                del self._bloqueio[chave]

    def _registrar(self, chave: str, limite: int, agora: float):
        fila = self._falhas.setdefault(chave, deque())
        fila.append(agora)
        while fila and agora - fila[0] > self.janela_s:
            fila.popleft()
        if len(fila) >= limite:
            self._bloqueio[chave] = agora + self.bloqueio_s
            del self._falhas[chave]          # recomeça do zero quando o bloqueio acabar

    def _restante(self, chave: str, agora: float) -> float:
        return max(self._bloqueio.get(chave, 0.0) - agora, 0.0)

    # ── API ────────────────────────────────────────────────────────────────────
    def segundos_bloqueado(self, nome="") -> int:
        """Segundos que faltam para esse nome poder tentar de novo (0 = liberado)."""
        with self._trava:
            agora = self._relogio()
            self._podar(agora)
            faltam = max(self._restante(self._chave(nome), agora), self._restante(_GLOBAL, agora))
            return int(math.ceil(faltam)) if faltam > 0 else 0

    def bloqueio_global(self) -> int:
        """Segundos que faltam para o bloqueio geral acabar (0 = não há)."""
        with self._trava:
            agora = self._relogio()
            self._podar(agora)
            faltam = self._restante(_GLOBAL, agora)
            return int(math.ceil(faltam)) if faltam > 0 else 0

    def falhas_restantes(self, nome="") -> int:
        """Quantas tentativas erradas esse nome ainda pode fazer antes de ser bloqueado."""
        with self._trava:
            agora = self._relogio()
            self._podar(agora)
            usadas = len(self._falhas.get(self._chave(nome), ()))
            return max(self.max_falhas - usadas, 0)

    def registrar_falha(self, nome="") -> None:
        with self._trava:
            agora = self._relogio()
            self._podar(agora)
            self._registrar(self._chave(nome), self.max_falhas, agora)
            self._registrar(_GLOBAL, self.max_falhas_global, agora)

    def registrar_sucesso(self, nome="") -> None:
        """Zera as falhas desse nome (o contador global continua)."""
        with self._trava:
            chave = self._chave(nome)
            self._falhas.pop(chave, None)


def texto_espera(segundos: int) -> str:
    """'menos de 1 minuto', '1 minuto', '15 minutos' (arredonda para cima)."""
    if segundos <= 0:
        return "agora"
    if segundos < 60:
        return "menos de 1 minuto"
    minutos = int(math.ceil(segundos / 60))
    return f"{minutos} minuto" + ("" if minutos == 1 else "s")
