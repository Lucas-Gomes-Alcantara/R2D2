"""Grava uma frase inteira para comparar o audio com a transcricao do Google.

Execute com --listar para ver entradas ou --microfone INDICE para escolher uma.
Use: python -m scripts.diagnostico_voz
O arquivo fica em outputs/diagnostico_voz.wav; nao envia comandos ao Arduino.
"""

import argparse
from array import array
import math
from pathlib import Path
import sys

import pyaudio
import speech_recognition as sr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--microfone", type=int, default=None)
    args = parser.parse_args()
    if args.listar:
        audio_interface = pyaudio.PyAudio()
        try:
            for indice in range(audio_interface.get_device_count()):
                dispositivo = audio_interface.get_device_info_by_index(indice)
                if dispositivo["maxInputChannels"] > 0:
                    print(f"{indice}: {dispositivo['name']}")
        finally:
            audio_interface.terminate()
        return

    recognizer = sr.Recognizer()
    recognizer.operation_timeout = 10
    print('Vou gravar 6 segundos, sem cortar em pausas. Diga: "dedao listar comandos".')
    input("Pressione Enter quando estiver pronto. ")
    with sr.Microphone(device_index=args.microfone) as mic:
        print("FALE AGORA.", flush=True)
        audio = recognizer.record(mic, duration=6)
    caminho = Path(__file__).resolve().parents[1] / "outputs" / "diagnostico_voz.wav"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(audio.get_wav_data())
    amostras = array("h", audio.get_raw_data(convert_width=2))
    if sys.byteorder != "little":
        amostras.byteswap()
    if amostras:
        rms = math.sqrt(sum(valor * valor for valor in amostras) / len(amostras))
        pico = max(abs(valor) for valor in amostras)
        saturadas = sum(abs(valor) >= 32760 for valor in amostras) / len(amostras)
        print(f"Nivel medio: {20 * math.log10(max(rms, 1) / 32768):.1f} dBFS")
        print(f"Pico: {pico / 32768:.1%}; amostras saturadas: {saturadas:.2%}")
    print(f"Audio salvo em: {caminho}")
    print("Consulte a gravacao para verificar se a frase esta inteira e audivel.")
    try:
        texto = recognizer.recognize_google(audio, language="pt-BR")
        print(f"Google entendeu: {texto}")
    except sr.UnknownValueError:
        print("Google nao entendeu. A gravacao continua disponivel para comparar.")
    except (sr.RequestError, TimeoutError) as erro:
        print(f"Falha na consulta ao Google: {erro}")


if __name__ == "__main__":
    main()
