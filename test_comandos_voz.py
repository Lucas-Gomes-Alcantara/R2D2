"""Regressoes de ativacao e roteamento, sem audio, rede ou Arduino."""

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, call, patch


CAMINHO = Path(__file__).resolve().parents[1] / "checkpoint_alexa.py"
spec = importlib.util.spec_from_file_location("r2d2_em_teste", CAMINHO)
app = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    nome: Mock() for nome in ("requests", "speech_recognition", "cv2", "gtts", "pygame")
}):
    spec.loader.exec_module(app)


class ComandosVozTest(unittest.TestCase):
    def setUp(self):
        self.assistente = app.R2D2.__new__(app.R2D2)
        self.acoes = Mock()
        for nome in ("speech", "agenda", "calc", "face", "ai", "extras", "arduino"):
            setattr(self.assistente, nome, getattr(self.acoes, nome))
        self.voz = app.SpeechManager.__new__(app.SpeechManager)
        self.console = contextlib.redirect_stdout(io.StringIO())
        self.console.__enter__()
        self.addCleanup(self.console.__exit__, None, None, None)

    def executar(self, fala):
        return self.assistente.processar_comando(self.voz._normalizar_texto(fala))

    def test_falas_sem_ativacao_exata_no_inicio_nao_executam_acoes(self):
        for fala in (
            "que horas são", "então sair", "dedo sair", "sair dedão",
            "você sabe dedão que horas são", "meu dedão sair",
            "dedãozinho sair", "dedão2 sair", "superdedão sair", "",
        ):
            with self.subTest(fala=fala):
                self.assertTrue(self.executar(fala))
                self.assertEqual(self.acoes.mock_calls, [])

    def test_ativacao_aceita_acentos_caixa_espacos_e_pontuacao(self):
        for fala in ("dedão sair", "  DEDÃO, sair!  ", "dedao: sair", "dedão   sair"):
            with self.subTest(fala=fala):
                self.acoes.reset_mock()
                self.assertFalse(self.executar(fala))
                self.assistente.speech.falar.assert_called_once()

    def test_aliases_de_saida_funcionam_como_comando_completo(self):
        for comando in ("sair", "encerrar", "tchau"):
            with self.subTest(comando=comando):
                self.acoes.reset_mock()
                self.assertFalse(self.executar(f"dedão {comando}"))
                self.assistente.speech.falar.assert_called_once()
        self.assertTrue(self.executar("dedão sair do windows"))

    def test_pesquisa_preserva_termo_e_nao_dispara_outros_comandos(self):
        for termo in (
            "como sair do windows", "como encerrar um programa", "como dizer tchau",
            "como cadastrar evento e limpar agenda", "que horas sao em toquio",
            "como calcular dois mais tres", "como reconhecer face",
            "o que e bitcoin", "previsao do tempo em santos", "valor do dolar",
            "tirar screenshot no youtube", "portal fiap", "grita e listar comandos",
            "como pesquisar e perguntar sobre o dedao", "entao e dedo",
        ):
            with self.subTest(termo=termo):
                self.acoes.reset_mock()
                self.assistente.extras.pesquisar_google.return_value = "Pesquisa aberta."
                self.assertTrue(self.executar(f"dedão pesquisar {termo}"))
                self.assertEqual(self.acoes.mock_calls, [
                    call.extras.pesquisar_google(termo),
                    call.speech.falar("Pesquisa aberta."),
                ])

    def test_perguntas_nao_acionam_comandos_mencionados(self):
        for prefixo in ("perguntar", "me fale sobre"):
            with self.subTest(prefixo=prefixo):
                self.acoes.reset_mock()
                pergunta = "como sair e calcular depois de perguntar ao dedao"
                self.assertTrue(self.executar(f"dedão {prefixo} {pergunta}"))
                self.assistente.ai.perguntar.assert_called_once_with(pergunta)
                self.assistente.calc.calcular.assert_not_called()
                self.assistente.extras.pesquisar_google.assert_not_called()

    def test_youtube_preserva_busca_com_palavras_de_outros_comandos(self):
        for prefixo in ("youtube sobre", "abrir youtube sobre", "youtube video de"):
            with self.subTest(prefixo=prefixo):
                self.acoes.reset_mock()
                busca = "como sair e calcular falando sobre bitcoin"
                self.assistente.extras.abrir_youtube.return_value = "YouTube aberto."
                self.assertTrue(self.executar(f"dedão {prefixo} {busca}"))
                self.assertEqual(self.acoes.mock_calls, [
                    call.extras.abrir_youtube(busca), call.speech.falar("YouTube aberto."),
                ])

    def test_pesquisa_sem_termo_pede_resposta_sem_palavra_de_ativacao(self):
        self.assistente.speech.ouvir_resposta.return_value = "como sair do windows"
        self.assertTrue(self.executar("dedão pesquisar"))
        self.assistente.speech.ouvir_resposta.assert_called_once()
        self.assistente.extras.pesquisar_google.assert_called_once_with("como sair do windows")

    def test_comandos_documentados_continuam_acessiveis(self):
        casos = (
            ("calcular cinquenta mais vinte e cinco", "calc.calcular"),
            ("cadastrar evento", "agenda.cadastrar_evento"),
            ("ler agenda", "agenda.ler_agenda"),
            ("limpar agenda", "agenda.limpar_agenda"),
            ("reconhecer face", "face.reconhecer"),
            ("previsão do tempo em santos", "extras.obter_clima"),
            ("valor do dólar", "extras.obter_dolar"),
            ("bitcoin", "extras.obter_bitcoin"),
            ("tirar screenshot", "extras.tirar_screenshot"),
            ("abrir youtube", "extras.abrir_youtube"),
            ("abrir portal", "extras.abrir_portal_fiap"),
            ("grita", "extras.grita"),
        )
        for comando, destino in casos:
            with self.subTest(comando=comando):
                self.acoes.reset_mock()
                self.assistente.speech.ouvir_resposta.return_value = "sim"
                self.assertTrue(self.executar(f"dedão {comando}"))
                modulo, metodo = destino.split(".")
                getattr(getattr(self.assistente, modulo), metodo).assert_called_once()

    def test_loop_ignora_falas_sem_ativacao_e_fecha_arduino_ao_sair(self):
        self.assistente.speech.ouvir.side_effect = [
            self.voz._normalizar_texto(fala)
            for fala in ("então sair", "você sabe dedão sair", "dedão pesquisar como sair do windows", "dedão sair")
        ]
        self.assistente.iniciar()
        self.assertEqual(self.assistente.speech.ouvir.call_count, 4)
        self.assistente.extras.pesquisar_google.assert_called_once_with("como sair do windows")
        self.assistente.arduino.fechar.assert_called_once()


class GritoTest(unittest.TestCase):
    def setUp(self):
        self.agora = 0.0
        self.fim_audio = 0.1
        self.eventos = []
        self.arduino = Mock(disponivel=True)
        self.arduino.iniciar_movimento.side_effect = lambda: self.eventos.append(("movimento", self.agora))
        self.arduino.parar_movimento.side_effect = lambda: self.eventos.append(("parada", self.agora))
        self.music = Mock()
        self.music.get_busy.side_effect = lambda: self.agora < self.fim_audio
        self.music.play.side_effect = lambda: self.eventos.append(("audio", self.agora))
        self.contexto = contextlib.ExitStack()
        self.addCleanup(self.contexto.close)
        self.contexto.enter_context(patch.object(app.mixer, "music", self.music))
        self.contexto.enter_context(patch.object(app.time, "monotonic", side_effect=lambda: self.agora))
        self.contexto.enter_context(patch.object(app.time, "sleep", side_effect=self.avancar))
        self.extras = app.ExtraCommands(arduino=self.arduino)

    def avancar(self, segundos):
        self.agora += segundos

    def test_audio_curto_nao_interrompe_movimento_antes_de_quatro_segundos(self):
        self.assertEqual(self.extras.grita(), "")
        self.assertEqual([evento for evento, _ in self.eventos], ["movimento", "audio", "parada"])
        self.assertGreaterEqual(self.eventos[-1][1], 4.0)
        self.arduino.respondendo.assert_has_calls([call(True), call(False)])

    def test_audio_longo_mantem_movimento_ate_terminar(self):
        self.fim_audio = 6.0
        self.assertEqual(self.extras.grita(), "")
        self.assertGreaterEqual(self.eventos[-1][1], 6.0)

    def test_sem_arduino_nao_adiciona_espera_ao_som(self):
        self.extras.arduino = None
        self.assertEqual(self.extras.grita(), "")
        self.assertLess(self.agora, 0.2)

    def test_arduino_desconectado_nao_tenta_mover_nem_adiciona_espera(self):
        self.arduino.disponivel = False
        self.assertIn("comunicação com o Arduino", self.extras.grita())
        self.arduino.iniciar_movimento.assert_not_called()
        self.assertLess(self.agora, 0.2)

    def test_perda_da_conexao_durante_grito_nao_e_reportada_como_sucesso(self):
        self.music.play.side_effect = lambda: setattr(self.arduino, "disponivel", False)
        self.assertIn("comunicação com o Arduino", self.extras.grita())
        self.arduino.parar_movimento.assert_called_once()
        self.arduino.respondendo.assert_called_with(False)

    def test_falha_no_player_desliga_servo_led_e_audio_imediatamente(self):
        self.music.play.side_effect = RuntimeError("falha no player")
        self.assertIn("falha no player", self.extras.grita())
        self.arduino.parar_movimento.assert_called_once()
        self.arduino.respondendo.assert_called_with(False)
        self.music.stop.assert_called()
        self.music.unload.assert_called()
        self.assertEqual(self.agora, 0.0)


class ComunicacaoArduinoTest(unittest.TestCase):
    def setUp(self):
        self.porta = Mock(is_open=True)
        self.porta.write.side_effect = lambda comando: len(comando)
        self.porta.readline.return_value = b"R2D2/1\r\n"
        self.serial = Mock()
        self.serial.Serial.return_value = self.porta
        self.contexto = contextlib.ExitStack()
        self.addCleanup(self.contexto.close)
        self.contexto.enter_context(patch.dict(sys.modules, {"serial": self.serial}))
        self.contexto.enter_context(patch.object(app.time, "sleep"))
        self.contexto.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_porta_aberta_so_e_aceita_apos_identificacao_do_firmware(self):
        arduino = app.ArduinoController(porta="COM4")
        self.assertTrue(arduino.disponivel)
        self.porta.write.assert_called_once_with(b"?")
        self.assertEqual(arduino.porta, "COM4")

    def test_firmware_sem_resposta_libera_porta_e_desativa_controle(self):
        self.porta.readline.return_value = b""
        arduino = app.ArduinoController(porta="COM4")
        self.assertFalse(arduino.disponivel)
        self.porta.close.assert_called_once()

    def test_confirmacao_de_outro_comando_nao_e_aceita(self):
        arduino = app.ArduinoController(porta="COM4")
        self.porta.readline.return_value = b"OK b\r\n"
        arduino.iniciar_movimento()
        self.assertFalse(arduino.disponivel)
        self.porta.close.assert_called_once()

    def test_falha_de_escrita_libera_porta(self):
        arduino = app.ArduinoController(porta="COM4")
        self.porta.write.side_effect = OSError("USB desconectado")
        arduino.escutando(True)
        self.assertFalse(arduino.disponivel)
        self.porta.close.assert_called_once()

    def test_estado_informado_pelo_firmware(self):
        arduino = app.ArduinoController(porta="COM4")
        self.porta.readline.return_value = b"STATE 1 0 1\r\n"
        self.assertEqual(arduino.consultar_estado(), {
            "servo": True, "verde": False, "vermelho": True,
        })

    def test_encerramento_confirma_desligamento_das_tres_saidas(self):
        arduino = app.ArduinoController(porta="COM4")
        self.porta.reset_mock()
        self.porta.readline.side_effect = [b"OK b\n", b"OK d\n", b"OK f\n"]
        arduino.fechar()
        self.assertEqual(self.porta.write.call_args_list, [call(b"b"), call(b"d"), call(b"f")])
        self.porta.close.assert_called_once()
        self.assertFalse(arduino.disponivel)


class CapturaVozTest(unittest.TestCase):
    def setUp(self):
        self.recognizer = Mock(energy_threshold=300)
        self.recognizer.recognize_google.return_value = "dedão listar comandos"
        self.microfone = MagicMock()
        self.sr = Mock()
        self.sr.Recognizer.return_value = self.recognizer
        self.sr.Microphone = self.microfone
        self.sr.WaitTimeoutError = type("WaitTimeoutError", (Exception,), {})
        self.sr.UnknownValueError = type("UnknownValueError", (Exception,), {})
        self.sr.RequestError = type("RequestError", (Exception,), {})
        self.contexto = contextlib.ExitStack()
        self.addCleanup(self.contexto.close)
        self.contexto.enter_context(patch.object(app, "sr", self.sr))
        self.contexto.enter_context(patch.dict(app.os.environ, {"R2D2_MIC_INDEX": "1"}))
        self.contexto.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.arduino = Mock()
        self.voz = app.SpeechManager(arduino=self.arduino)

    def test_segunda_fala_nao_e_consumida_por_nova_calibracao(self):
        self.recognizer.listen.side_effect = ["primeiro audio", "segundo audio"]
        self.assertEqual(self.voz.ouvir(), "dedao listar comandos")
        self.assertEqual(self.voz.ouvir(), "dedao listar comandos")
        self.assertEqual(self.recognizer.adjust_for_ambient_noise.call_count, 1)
        self.microfone.assert_called_with(device_index=1)
        self.assertEqual(self.recognizer.recognize_google.call_args_list, [
            call("primeiro audio", language="pt-BR"),
            call("segundo audio", language="pt-BR"),
        ])

    def test_falha_na_calibracao_permite_nova_tentativa(self):
        self.recognizer.adjust_for_ambient_noise.side_effect = [OSError("microfone ocupado"), None]
        self.assertEqual(self.voz.ouvir(), "")
        self.assertEqual(self.voz.ouvir(), "dedao listar comandos")
        self.assertEqual(self.recognizer.adjust_for_ambient_noise.call_count, 2)

    def test_timeout_de_escuta_desliga_led(self):
        self.recognizer.listen.side_effect = self.sr.WaitTimeoutError()
        self.assertEqual(self.voz.ouvir(), "")
        self.assertEqual(self.arduino.escutando.call_args_list, [call(True), call(False)])

    def test_timeout_da_rede_nao_derruba_assistente(self):
        self.recognizer.recognize_google.side_effect = TimeoutError("sem resposta")
        self.assertEqual(self.voz.ouvir(), "")
        self.arduino.escutando.assert_called_with(False)


if __name__ == "__main__":
    unittest.main()
