from __future__ import annotations

import datetime
import sys
import time
from typing import Any

try:  # IPython é opcional (extra "notebook")
    from IPython import get_ipython
    from IPython.display import clear_output
except ImportError:  # pragma: no cover
    def get_ipython() -> Any:  # type: ignore[misc]
        return None

    def clear_output(wait: bool = False) -> None:  # type: ignore[misc]
        pass


def _clear_terminal() -> None:
    """Limpa o terminal com códigos ANSI (sem abrir um subprocesso)."""
    if sys.stdout.isatty():
        print('\033[2J\033[H', end='', flush=True)


class Progress:

    def __init__(self,
                 max: int,
                 if_clear: bool = False,
                 same_line: bool = False,
                 texto_inicial: str = '',
                 texto_final: str = '',
                 esperar_em_horario_comercial: bool = False,
                 tempo_pausa_fora_horario_comercial: float = 0,
                 tempo_pausa_horario_comercial: float = 2,
                 verbose: bool = False
                 ) -> None:
        if not isinstance(max, int) or isinstance(max, bool) or max <= 0:
            raise ValueError('O número de iterações deve ser um inteiro maior que zero.')
        self.max: int = max
        self.if_clear = if_clear
        self.same_line = same_line
        self.start_time = datetime.datetime.now()
        self.start_processing = datetime.datetime.now()
        self.curr_iter = 0
        self.curr_porcent = 0.0
        self.curr_time = self.start_time
        self.passed_time = datetime.timedelta(0)
        self.print_to_terminal = True
        self.last_rounded_porcent = 0
        self.retorno = ''
        self.texto_inicial = texto_inicial
        self.texto_final = texto_final
        self.esperar_em_horario_comercial = esperar_em_horario_comercial
        self.verbose = verbose
        self.tempo_pausa_fora_horario_comercial = tempo_pausa_fora_horario_comercial
        self.tempo_pausa_horario_comercial = tempo_pausa_horario_comercial

        temp_txt = f"Início em " \
                   f"{self.start_processing.strftime('%d/%m/%Y %H:%M:%S')}."
        self.texto = temp_txt
        print(temp_txt)

    def next(self, texto_inicial: str | None = None,
             texto_final: str | None = None) -> str | None:
        """
        Registra uma iteração. Devolve o texto impresso (quando a porcentagem
        avança) ou None. Chamadas além de ``max`` são ignoradas.
        """
        if self.curr_iter >= self.max:
            return None

        self.curr_iter += 1
        if self.esperar_em_horario_comercial:
            self.pausa_se_horario_comercial(
                tempo_pausa_fora_horario_comercial=self.tempo_pausa_fora_horario_comercial,
                tempo_pausa_horario_comercial=self.tempo_pausa_horario_comercial,
                verbose=self.verbose,
            )
        if self.verbose:
            print(f'Iteração {self.curr_iter} de {self.max}.')
        self.curr_porcent = self.curr_iter / self.max
        curr_rounded_porcent = int(100 * self.curr_porcent)
        if self.curr_iter == self.max:
            if self.verbose:
                print('Última iteração alcançada.')
            self.curr_time = datetime.datetime.now()
            self.passed_time = self.curr_time - self.start_time
            total_time = self.curr_time - self.start_processing
            temp_txt = f'Fim. Tempo para completar: {total_time}.'
            self.texto += temp_txt
            if self.same_line and not self.if_clear:
                print()  # encerra a linha reescrita com \r
            print(temp_txt)
            return temp_txt
        if self.last_rounded_porcent < curr_rounded_porcent or \
                (self.curr_iter == 10 and curr_rounded_porcent < 1):
            return self.imprime(texto_inicial, texto_final)
        return None

    # Compatibilidade: ``next(progress)`` e ``progress.__next__()``.
    __next__ = next

    @staticmethod
    def pausa_se_horario_comercial(tempo_pausa_fora_horario_comercial: float = 0,
                                   tempo_pausa_horario_comercial: float = 2,
                                   verbose: bool = False,
                                   ) -> None:
        """
        Pausa por ``tempo_pausa_horario_comercial`` segundos em dias úteis entre
        08:00 e 19:59; fora desse horário, por ``tempo_pausa_fora_horario_comercial``.

        Args:
            tempo_pausa_fora_horario_comercial: segundos de espera fora do horário comercial.
            tempo_pausa_horario_comercial: segundos de espera em horário comercial.
            verbose: se True, imprime mensagens sobre a pausa.
        """
        agora = datetime.datetime.now()

        # datetime.weekday() retorna 0 para segunda-feira e 6 para domingo.
        eh_dia_de_semana = 0 <= agora.weekday() <= 4

        # A hora deve estar entre 8 (inclusive) e 20 (exclusive).
        em_horario_comercial = 8 <= agora.hour < 20

        if eh_dia_de_semana and em_horario_comercial:
            pausa = tempo_pausa_horario_comercial
            condicao = 'Horário comercial'
        else:
            pausa = tempo_pausa_fora_horario_comercial
            condicao = 'Fora do horário comercial'
        if verbose:
            print(f"[{agora.strftime('%d/%m/%Y %H:%M:%S')}] {condicao}. "
                  f"Pausando por {pausa} segundos.")
        time.sleep(pausa)

    def imprime(self, texto_inicial: str | None = None,
                texto_final: str | None = None) -> str:
        if texto_inicial is None:
            texto_inicial = self.texto_inicial
        if texto_final is None:
            texto_final = self.texto_final

        curr_rounded_porcent = int(100 * self.curr_porcent)
        number_of_iter_to_complete = self.max - self.curr_iter
        self.curr_time = datetime.datetime.now()
        self.passed_time = self.curr_time - self.start_time
        elapsed = self.passed_time.total_seconds()
        time_for_each_iter = elapsed / self.curr_iter if self.curr_iter else 0.0
        time_to_complete = number_of_iter_to_complete * time_for_each_iter

        time_end = self.curr_time + datetime.timedelta(seconds=time_to_complete)

        texto_iter = ''
        if elapsed > 0 and self.curr_iter > 0:
            iter_time = self.curr_iter / elapsed
            if iter_time >= 1:
                texto_iter = f'Fazendo {iter_time:.2f} iter/s. '
            else:
                texto_iter = f'Fazendo {self.stringify(1 / iter_time)}/iter. '

        retorno = (texto_inicial +
                   f'{self.curr_iter}/{self.max}, {curr_rounded_porcent}%. ' +
                   f'Falta para acabar: {self.stringify(time_to_complete)}. ' +
                   f'Acabará às {time_end.strftime("%d/%m, %H:%M:%S")}. ' +
                   texto_iter +
                   texto_final)
        self.last_rounded_porcent = curr_rounded_porcent

        if self.if_clear:
            _clear_terminal()
            clear_output(wait=True)
        if self.print_to_terminal:
            self.texto += retorno
            if self.same_line and not self.if_clear:
                if get_ipython().__class__.__name__ == 'ZMQInteractiveShell':
                    clear_output(wait=True)
                    print(retorno)
                else:
                    print(f'\r{retorno}', end='', flush=True)
            else:
                print(retorno)
        self.retorno = retorno
        return retorno

    @staticmethod
    def stringify(time_in_seconds: float) -> str:
        """Formata segundos como ``1d 2h 3m 4.5s``."""
        time_in_seconds = max(0.0, time_in_seconds)
        if time_in_seconds >= 100:
            seconds: float = round(time_in_seconds % 60)
        elif time_in_seconds >= 10:
            seconds = round(time_in_seconds % 60, 1)
        else:
            seconds = round(time_in_seconds % 60, 2)
        text = f'{seconds}s'
        minutes = int(time_in_seconds % 3600 // 60)
        if minutes > 0:
            text = f'{minutes}m ' + text
        hours = int(time_in_seconds % 86400 // 3600)
        if hours > 0:
            text = f'{hours}h ' + text
        days = int(time_in_seconds // 86400)
        if days > 0:
            text = f'{days}d ' + text
        return text

    def start(self) -> None:
        # Reinicia o tempo. Útil se houver etapas iniciais que atrasam o processo.
        self.start_time = datetime.datetime.now()
        if self.verbose:
            print('Iniciando contagem de tempo...')
