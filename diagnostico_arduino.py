"""Testa LED verde, LED vermelho e cabeca pela serial, sem usar voz.

Use: python -m scripts.diagnostico_arduino --porta COM4
"""

import argparse
import time

from checkpoint_alexa import ArduinoController


def verificar(arduino, servo=False, verde=False, vermelho=False):
    esperado = {"servo": servo, "verde": verde, "vermelho": vermelho}
    recebido = arduino.consultar_estado()
    if recebido != esperado:
        raise RuntimeError(f"Estado incorreto: esperado {esperado}, recebido {recebido}")
    print(f"Uno confirmou: {recebido}", flush=True)


def desligar(arduino):
    arduino.parar_movimento()
    arduino.escutando(False)
    arduino.respondendo(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", default="", help="Ex.: COM4; padrao: deteccao automatica")
    parser.add_argument("--automatico", action="store_true", help="Executa sem aguardar Enter")
    args = parser.parse_args()
    arduino = ArduinoController(porta=args.porta)
    try:
        if not arduino.disponivel:
            raise RuntimeError("Nao foi possivel confirmar o firmware R2D2/1.")
        desligar(arduino)
        verificar(arduino)
        etapas = (
            ("LED VERDE aceso por 3 segundos", lambda: arduino.escutando(True), {"verde": True}),
            ("LED VERMELHO piscando por 3 segundos", lambda: arduino.respondendo(True), {"vermelho": True}),
            ("CABECA balancando por 3 segundos", arduino.iniciar_movimento, {"servo": True}),
        )
        for descricao, acao, estado in etapas:
            print(f"\nTESTE: {descricao}", flush=True)
            if not args.automatico:
                input("Observe o robo e pressione Enter para iniciar. ")
            acao()
            verificar(arduino, **estado)
            time.sleep(3)
            verificar(arduino, **estado)
            desligar(arduino)
            verificar(arduino)
        print("\nComunicacao e estados do firmware OK. Confirme visualmente luzes e movimento.")
    finally:
        arduino.fechar()


if __name__ == "__main__":
    main()
