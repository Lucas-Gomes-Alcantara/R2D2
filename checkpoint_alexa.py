"""
============================================================
  CP4 - Assistente Virtual R.2.D.2
  Robotic Responsive Digital Dual Assistant
  Checkpoint 4 - 2 Semestre
  Programacao Orientada a Objetos em Python
============================================================

Comandos disponiveis (fale "dedao" para ativar):
  - "dedao cadastrar evento na agenda"
  - "dedao ler agenda"
  - "dedao limpar agenda"
  - "dedao que horas sao"
  - "dedao que dia e hoje"
  - "dedao calcular <expressao>"
  - "dedao reconhecer face" / "dedao quem sou eu"
  - "dedao perguntar <pergunta>"   -> IA via Ollama (llama3.2:3b)
  - "dedao previsao do tempo"
  - "dedao valor do dolar"
  - "dedao bitcoin"
  - "dedao tirar screenshot"
  - "dedao pesquisar <termo>"
  - "dedao abrir youtube"
  - "dedao sair"
============================================================
"""

import os
import io
import re
import ast
import time
import operator
import unicodedata
import logging
import datetime
import webbrowser
from pathlib import Path
import requests
import speech_recognition as sr
import cv2
from gtts import gTTS
from pygame import mixer


# Caminhos relativos ao projeto, independentemente do diretorio do terminal.
PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_DADOS = PASTA_PROJETO / "data"
PASTA_SAIDAS = PASTA_PROJETO / "outputs"
AUDIO_GRITO = PASTA_PROJETO / "assets" / "audio" / "r2d2_grito.mp3"

# Suprime logs de retry/debug do gTTS no console
logging.getLogger("gtts").setLevel(logging.ERROR)


def remover_acentos(texto: str) -> str:
    """Remove acentos de um texto (ex.: 'três' -> 'tres')."""
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# ============================================================
#  CLASSE 1 - SpeechManager
#  Gerencia reconhecimento e sintese de voz
# ============================================================
class SpeechManager:
    """
    Responsavel por ouvir o usuario (microfone -> texto)
    e falar para o usuario (texto -> voz).

    Sintese de voz: gTTS (Google Text-to-Speech) + pygame mixer.
    Reconhecimento: SpeechRecognition + Google STT.
    """

    VELOCIDADE_WPM = 175

    def __init__(self, idioma: str = "pt-BR", arduino: "ArduinoController" = None):
        """
        Args:
            idioma:  idioma do reconhecimento de voz
            arduino: ArduinoController (opcional) para acender os LEDs de
                     estado: verde = escutando, vermelho = respondendo
        """
        self.idioma     = idioma
        self.arduino    = arduino
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 1.2
        self.recognizer.non_speaking_duration = 0.6
        self.recognizer.operation_timeout = 10
        # A calibracao inicial define o limiar. Nao o aumente durante a fala,
        # pois trechos mais baixos podem acabar tratados como silencio.
        self.recognizer.dynamic_energy_threshold = False
        self._microfone_calibrado = False
        indice = os.getenv("R2D2_MIC_INDEX", "").strip()
        self.microfone_index = int(indice) if indice else None

        # Mixer para reproducao de audio (fala + som R2D2)
        if not mixer.get_init():
            mixer.pre_init(frequency=24000, size=-16, channels=1, buffer=512)
            mixer.init()

        print("[R.2.D.2]: Sistema de audio iniciado (gTTS + pygame).")
        print(f"[R.2.D.2]: Microfone: {self.microfone_index if self.microfone_index is not None else 'padrao do Windows'}.")

    def _led_escuta(self, ligado: bool):
        """Acende/apaga o LED verde (escutando), se houver Arduino."""
        if self.arduino:
            self.arduino.escutando(ligado)

    def _led_resposta(self, ligado: bool):
        """Liga/desliga o pisca do LED vermelho (respondendo), se houver Arduino."""
        if self.arduino:
            self.arduino.respondendo(ligado)

    def falar(self, texto: str):
        """
        Fala o texto e mantem o LED vermelho piscando enquanto responde
        (da geracao da voz ate o fim da reproducao). O LED e sempre
        apagado no final, mesmo se ocorrer algum erro.
        """
        self._led_resposta(True)
        try:
            self._falar_audio(texto)
        finally:
            self._led_resposta(False)

    def _falar_audio(self, texto: str):
        """
        Converte texto em voz com gTTS e toca via pygame.
        Gera o MP3 em memoria (sem arquivo em disco), toca e aguarda
        o fim antes de retornar — garante que o microfone so abre depois.
        """
        print(f"\n[R.2.D.2]: {texto}")
        try:
            tts = gTTS(text=texto, lang="pt", slow=False, timeout=(3, 10))
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)

            mixer.music.stop()
            mixer.music.load(buf)
            mixer.music.set_volume(1.0)
            mixer.music.play()

            while mixer.music.get_busy():
                time.sleep(0.05)

            mixer.music.unload()
            time.sleep(0.3)
        except Exception as erro:
            print(f"[R.2.D.2]: Erro de audio: {erro}")

    # Variacoes do nome "r2" que o STT costuma devolver (ja sem acentos).
    # Sao aplicadas com limite de palavra (\b) e NUNCA incluem sequencias
    # puramente numericas (ex.: "32", "112"), para nao corromper calculos.
    VARIACOES_R2 = [
        "erre dois d dois", "erre 2 d 2", "r dois d dois", "r dois d 2",
        "r 2 d dois", "r 2 d 2", "are too d 2", "are 2 d 2", "our 2 d 2",
        "s 2 d 2", "r2d 2", "r 2d2", "r 2d 2", "r2 d2", "r2 z2", "r2 e2",
        "r2 b2", "r2z2", "r2b2", "r2e2", "s2 d2", "2 d 2", "2 d2", "r2d2",
        "erre2", "erre dois", "s2",
    ]

    def _normalizar_texto(self, texto: str) -> str:
        """
        Normaliza o texto reconhecido pelo Google STT:
        - Converte para minusculas
        - Remove acentos (para comparacao robusta de comandos)
        - Padroniza variacoes do nome 'r2'
        - Preserva palavras como 'entao' e 'dedo', que nao sao ativadores

        Returns:
            Texto normalizado em minusculas sem acentos
        """
        texto = remover_acentos(texto.lower().strip())

        # Variacoes do mais longo para o mais curto (evita substituicao parcial)
        for variacao in sorted(self.VARIACOES_R2, key=len, reverse=True):
            texto = re.sub(rf"\b{re.escape(variacao)}\b", "r2", texto)

        return texto

    def ouvir(self, timeout: int = 8, duracao: int = 10) -> str:
        """
        Captura audio do microfone e retorna o texto reconhecido.

        Args:
            timeout:  segundos esperando o usuario comecar a falar (padrao 8)
            duracao:  duracao maxima da fala em segundos (padrao 10)

        Returns:
            Texto reconhecido ou string vazia
        """
        audio = None

        # Passo 1: captura o audio e fecha o microfone imediatamente
        try:
            with sr.Microphone(device_index=self.microfone_index) as mic:
                if not self._microfone_calibrado:
                    print("[R.2.D.2]: Calibrando microfone: mantenha silencio por 1 segundo.")
                    self.recognizer.adjust_for_ambient_noise(mic, duration=1)
                    self._microfone_calibrado = True
                    print(f"[R.2.D.2]: Limiar de voz: {self.recognizer.energy_threshold:.0f}.")
                print("[R.2.D.2]: Ouvindo...")
                self._led_escuta(True)   # LED verde: escutando
                try:
                    audio = self.recognizer.listen(mic, timeout=timeout, phrase_time_limit=duracao)
                finally:
                    self._led_escuta(False)
            # Microfone fechado aqui — driver de audio liberado para pygame

        except sr.WaitTimeoutError:
            print("[R.2.D.2]: Tempo esgotado.")
            return ""
        except Exception as erro:
            print(f"[R.2.D.2]: Erro ao capturar audio: {erro}")
            return ""

        # Passo 2: envia para o Google STT (microfone ja fechado)
        try:
            texto = self.recognizer.recognize_google(audio, language=self.idioma)
            texto = self._normalizar_texto(texto)
            print(f"[Voce disse]: {texto}")
            return texto

        except sr.UnknownValueError:
            print("[R.2.D.2]: Nao entendi o que voce disse.")
            return ""
        except (sr.RequestError, TimeoutError) as erro:
            print(f"[R.2.D.2]: Erro na API de reconhecimento: {erro}")
            return ""

    def ouvir_resposta(self, pergunta: str) -> str:
        """
        Fala uma pergunta e aguarda a resposta do usuario.

        Args:
            pergunta: texto que o R.2.D.2 vai falar antes de ouvir

        Returns:
            Resposta do usuario em texto
        """
        self.falar(pergunta)
        return self.ouvir(timeout=7)


# ============================================================
#  CLASSE 2 - AgendaManager
#  Gerencia eventos: cadastrar, ler e limpar agenda
# ============================================================
class AgendaManager:
    """
    Responsavel por salvar, ler e limpar eventos na agenda.
    Os eventos sao gravados em um arquivo texto (data/agenda.txt).
    """

    def __init__(self, caminho_arquivo: str | Path = PASTA_DADOS / "agenda.txt"):
        """
        Inicializa o gerenciador de agenda.

        Args:
            caminho_arquivo: caminho do arquivo onde os eventos sao salvos
        """
        self.caminho = Path(caminho_arquivo)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        # Cria o arquivo se nao existir
        if not os.path.exists(self.caminho):
            open(self.caminho, "w", encoding="utf-8").close()

    def cadastrar_evento(self, evento: str) -> str:
        """
        Grava um evento na agenda com data e hora atuais.

        Args:
            evento: descricao do evento a ser cadastrado

        Returns:
            Mensagem de confirmacao
        """
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        linha = f"[{agora}] {evento}\n"

        with open(self.caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(linha)

        return f"Evento cadastrado com sucesso: {evento}"

    def ler_agenda(self) -> str:
        """
        Le todos os eventos salvos na agenda.

        Returns:
            String com todos os eventos ou mensagem de agenda vazia
        """
        with open(self.caminho, "r", encoding="utf-8") as arquivo:
            conteudo = arquivo.read().strip()

        if not conteudo:
            return "Sua agenda está vazia."

        linhas = conteudo.split("\n")
        resultado = f"Você tem {len(linhas)} evento(s) na agenda: "
        for i, linha in enumerate(linhas, 1):
            resultado += f" Evento {i}: {linha}."
        return resultado

    def limpar_agenda(self) -> str:
        """
        Apaga todos os eventos sem excluir o arquivo.

        Returns:
            Mensagem de confirmacao
        """
        with open(self.caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write("")  # Sobrescreve com conteudo vazio

        return "Agenda limpa com sucesso."


# ============================================================
#  CLASSE 3 - Calculator
#  Calcula operacoes matematicas faladas pelo usuario
# ============================================================
class Calculator:
    """
    Interpreta expressoes matematicas ditas por voz
    e retorna o resultado das operacoes basicas.

    Suporta numeros compostos por extenso ("vinte e cinco",
    "cento e dois", "mil e quinhentos"), simbolos (+, -, *, /, x)
    e palavras em portugues (mais, menos, vezes, dividido por...).
    A conta e avaliada por um avaliador seguro (sem eval).
    """

    # Frases de operador (tratadas ANTES das palavras soltas)
    FRASES_OPERADORES = [
        (r"\bmultiplicado\s+por\b", "*"),
        (r"\bdividido\s+por\b", "/"),
        (r"\bdividido\s+entre\b", "/"),
        (r"\belevado\s+(?:a|ao)\b", "**"),
        (r"\bsubtraido\s+de\b", "-"),
        (r"\badicionado\s+(?:a|com)\b", "+"),
        (r"\bsomado\s+(?:a|com)\b", "+"),
    ]

    # Palavras soltas -> operadores
    PALAVRAS_OPERADORES = {
        "mais": "+", "soma": "+", "somar": "+",
        "menos": "-", "subtraido": "-",
        "vezes": "*", "multiplicar": "*",
        "dividir": "/", "sobre": "/", "por": "/",
        "elevado": "**",
    }

    # Numeros por extenso (sem acento) -> valor
    UNIDADES = {
        "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3,
        "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
        "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14,
        "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
        "dezoito": 18, "dezenove": 19,
    }
    DEZENAS = {
        "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
        "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90,
    }
    CENTENAS = {
        "cem": 100, "cento": 100, "duzentos": 200, "trezentos": 300,
        "quatrocentos": 400, "quinhentos": 500, "seiscentos": 600,
        "setecentos": 700, "oitocentos": 800, "novecentos": 900,
    }
    MULTIPLICADORES = {"mil": 1_000, "milhao": 1_000_000, "milhoes": 1_000_000}

    # Limites de seguranca
    MAX_EXPOENTE = 100
    MAX_TAMANHO_EXPRESSAO = 120

    # Operadores permitidos no avaliador seguro
    _OPS_BINARIOS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }

    # ----------------------------------------------------------
    #  Numeros por extenso -> algarismos
    # ----------------------------------------------------------
    def _valor_palavra(self, palavra: str):
        """Retorna o valor (<1000) de uma palavra numerica, ou None."""
        for tabela in (self.UNIDADES, self.DEZENAS, self.CENTENAS):
            if palavra in tabela:
                return tabela[palavra]
        return None

    @staticmethod
    def _pode_somar(grupo: int, valor: int) -> bool:
        """
        Diz se 'valor' continua o mesmo numero que 'grupo'.
        Ex.: 20 + 5 sim ("vinte e cinco"), 100 + 20 sim, 5 + 3 nao.
        """
        if grupo == 0:
            return True
        if grupo % 100 == 0 and valor < 100:      # centena + resto
            return True
        if grupo % 100 in range(20, 100, 10) and valor < 10:  # dezena + unidade
            return True
        return False

    def _converter_extenso(self, texto: str) -> str:
        """Troca numeros por extenso (inclusive compostos) por algarismos."""
        tokens = texto.split()
        saida = []
        total, grupo, ativo = 0, 0, False

        def fechar():
            nonlocal total, grupo, ativo
            if ativo:
                saida.append(str(total + grupo))
            total, grupo, ativo = 0, 0, False

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            valor = self._valor_palavra(tok)

            if valor is not None:
                if ativo and not self._pode_somar(grupo, valor):
                    fechar()
                grupo += valor
                ativo = True
            elif tok in self.MULTIPLICADORES:
                total += (grupo or 1) * self.MULTIPLICADORES[tok]
                grupo, ativo = 0, True
            elif tok == "e" and ativo and i + 1 < len(tokens) and (
                self._valor_palavra(tokens[i + 1]) is not None
                or tokens[i + 1] in self.MULTIPLICADORES
            ):
                pass  # "e" ligando partes do mesmo numero
            else:
                fechar()
                saida.append(tok)
            i += 1

        fechar()
        return " ".join(saida)

    # ----------------------------------------------------------
    #  Avaliador seguro (substitui eval)
    # ----------------------------------------------------------
    def _avaliar_no(self, no):
        """Avalia recursivamente a AST permitindo apenas + - * / ** e numeros."""
        if isinstance(no, ast.Expression):
            return self._avaliar_no(no.body)
        if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
            return no.value
        if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.UAdd, ast.USub)):
            valor = self._avaliar_no(no.operand)
            return -valor if isinstance(no.op, ast.USub) else valor
        if isinstance(no, ast.BinOp) and type(no.op) in self._OPS_BINARIOS:
            esquerda = self._avaliar_no(no.left)
            direita = self._avaliar_no(no.right)
            if isinstance(no.op, ast.Pow) and abs(direita) > self.MAX_EXPOENTE:
                raise OverflowError("expoente muito grande")
            return self._OPS_BINARIOS[type(no.op)](esquerda, direita)
        raise ValueError("expressao nao permitida")

    # ----------------------------------------------------------
    #  Interface publica
    # ----------------------------------------------------------
    def calcular(self, expressao: str) -> str:
        """
        Interpreta e calcula uma expressao matematica.

        Args:
            expressao: texto com a expressao (ex: "vinte e cinco mais tres")

        Returns:
            String com o resultado ou mensagem de erro
        """
        expressao = remover_acentos(expressao.lower())

        # Remove palavras de ativacao/comando
        for palavra in ["dedao", "calcular", "quanto e", "quanto vale", "r2"]:
            expressao = re.sub(rf"\b{re.escape(palavra)}\b", " ", expressao)

        # "x" como multiplicacao apenas quando e uma palavra isolada (10 x 2)
        expressao = re.sub(r"\bx\b", " * ", expressao)

        # Numeros no formato brasileiro: 1.000 -> 1000 ; 2,5 -> 2.5
        expressao = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", expressao)
        expressao = re.sub(r"(?<=\d),(?=\d)", ".", expressao)

        # Frases de operador primeiro ("multiplicado por", "dividido por"...)
        for padrao, simbolo in self.FRASES_OPERADORES:
            expressao = re.sub(padrao, f" {simbolo} ", expressao)

        # Numeros por extenso -> algarismos (antes das palavras soltas)
        expressao = self._converter_extenso(expressao)

        # Palavras soltas de operador -> simbolos
        for palavra, simbolo in self.PALAVRAS_OPERADORES.items():
            expressao = re.sub(rf"\b{palavra}\b", f" {simbolo} ", expressao)

        # Mantem apenas numeros e operadores
        expressao_limpa = re.sub(r"[^\d\+\-\*\/\.\(\)\s]", " ", expressao)
        expressao_limpa = re.sub(r"\s+", " ", expressao_limpa).strip()

        if not expressao_limpa or len(expressao_limpa) > self.MAX_TAMANHO_EXPRESSAO:
            return "Não consegui entender a expressão matemática."

        try:
            arvore = ast.parse(expressao_limpa, mode="eval")
            resultado = self._avaliar_no(arvore)

            if isinstance(resultado, float):
                resultado = round(resultado, 4)
                if resultado.is_integer():
                    resultado = int(resultado)

            # Virgula decimal para a fala em portugues
            return f"O resultado é {str(resultado).replace('.', ',')}"
        except ZeroDivisionError:
            return "Erro: divisão por zero não é permitida."
        except OverflowError:
            return "Esse número é grande demais para eu calcular."
        except Exception:
            return "Não consegui calcular essa expressão."


# ============================================================
#  CLASSE 4 - FaceRecognizer
#  Reconhecimento facial com OpenCV (Haar Cascade)
# ============================================================
class FaceRecognizer:
    """
    Detecta e exibe faces usando a webcam com OpenCV.
    Usa o classificador Haar Cascade pre-treinado do proprio OpenCV.

    STAND BY: por enquanto apenas DETECTA rostos. O reconhecimento de
    quem e a pessoa (modelo LBPH .yml + "desconhecido") sera implementado depois.
    """

    def __init__(self):
        """Inicializa o detector de faces com o modelo Haar Cascade."""
        caminho_modelo = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(caminho_modelo)

    def reconhecer(self) -> str:
        """
        Abre a webcam e detecta faces em tempo real.
        Pressione 'Q' para fechar a janela.

        Returns:
            Mensagem sobre o resultado do reconhecimento
        """
        cap = cv2.VideoCapture(0)  # Webcam padrao

        if not cap.isOpened():
            return "Não consegui acessar a webcam. Verifique se ela está conectada."

        print("[R.2.D.2]: Pressione Q para fechar a c\u00e2mera.")
        faces_detectadas = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Converte para escala de cinza (exigido pelo detector Haar)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detecta faces no frame
            faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            faces_detectadas = len(faces)

            # Desenha retangulo e label em cada face detectada
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    frame, "Pessoa detectada",
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
                )

            # Contador de faces no canto superior esquerdo
            cv2.putText(
                frame, f"Faces: {faces_detectadas}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2
            )

            cv2.imshow("R.2.D.2 - Reconhecimento Facial (Q para sair)", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

        if faces_detectadas == 0:
            return "Nenhuma face foi detectada."
        elif faces_detectadas == 1:
            return "Detectei uma pessoa na câmera."
        else:
            return f"Detectei {faces_detectadas} pessoas na câmera."


# ============================================================
#  CLASSE 5 - AIIntegration
#  Integracao com IA generativa via Ollama (local)
# ============================================================
class AIIntegration:
    """
    Integra o R.2.D.2 com modelos de linguagem generativos.
    Usa Ollama local (llama3.2:3b) como principal.
    Usa Groq (nuvem) como fallback se Ollama estiver offline.
    A chave do Groq vem da variavel de ambiente GROQ_API_KEY.
    """

    # Endereco local do Ollama
    OLLAMA_URL = "http://localhost:11434/api/generate"

    # Valor sentinela devolvido quando o Ollama nao esta acessivel.
    # Usado em perguntar() para decidir o fallback (evita comparar textos soltos).
    OLLAMA_OFFLINE = "ollama offline"

    # Modelo do Groq. O antigo "llama3-8b-8192" foi desligado em 08/2025 e o
    # "llama-3.1-8b-instant" tem desligamento em 16/08/2026 (ver
    # console.groq.com/docs/deprecations). Pode ser trocado pela variavel
    # de ambiente GROQ_MODEL sem mexer no codigo.
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    # Instrucao de sistema para o modelo
    SYSTEM_PROMPT = (
        "Voce e R.2.D.2, uma assistente virtual inteligente e amigavel. "
        "Responda sempre em portugues do Brasil, de forma clara e objetiva. "
        "Seja conciso nas respostas para que possam ser lidas em voz alta."
    )

    def __init__(self, modelo: str = "llama3.2:3b", groq_api_key: str = ""):
        """
        Inicializa a integracao com IA.

        Args:
            modelo: nome do modelo Ollama
            groq_api_key: chave da API Groq (opcional, alternativa na nuvem)
        """
        self.modelo = modelo
        self.groq_api_key = groq_api_key

    def perguntar_ollama(self, pergunta: str) -> str:
        """
        Envia uma pergunta ao modelo local via Ollama.

        Args:
            pergunta: texto da pergunta do usuario

        Returns:
            Resposta do modelo ou mensagem de erro
        """
        prompt_completo = f"{self.SYSTEM_PROMPT}\n\nUsuario: {pergunta}\nR.2.D.2:"

        try:
            resposta = requests.post(
                self.OLLAMA_URL,
                json={
                    "model": self.modelo,
                    "prompt": prompt_completo,
                    "stream": False  # Recebe a resposta completa de uma vez
                },
                timeout=30
            )
            dados = resposta.json()
            return dados.get("response", "Não recebi resposta do modelo.").strip()

        except requests.exceptions.ConnectionError:
            return self.OLLAMA_OFFLINE
        except requests.exceptions.Timeout:
            return "O modelo demorou muito para responder. Tente novamente."
        except Exception as erro:
            return f"Erro ao consultar a IA: {erro}"

    def perguntar_groq(self, pergunta: str) -> str:
        """
        Envia uma pergunta para a API Groq na nuvem (fallback).

        Args:
            pergunta: texto da pergunta do usuario

        Returns:
            Resposta do modelo ou mensagem de erro
        """
        if not self.groq_api_key:
            return "Chave da API Groq nao configurada."

        try:
            from groq import Groq
            cliente = Groq(api_key=self.groq_api_key)
            resposta = cliente.chat.completions.create(
                model=self.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": pergunta}
                ]
            )
            return resposta.choices[0].message.content.strip()
        except Exception as erro:
            return f"Erro ao consultar o Groq: {erro}"

    def perguntar(self, pergunta: str) -> str:
        """
        Tenta Ollama primeiro; se offline, usa Groq como backup.

        Args:
            pergunta: texto da pergunta do usuario

        Returns:
            Resposta da IA
        """
        resposta = self.perguntar_ollama(pergunta)

        # Fallback para Groq se Ollama nao estiver rodando
        if resposta == self.OLLAMA_OFFLINE:
            if self.groq_api_key:
                print("[R.2.D.2]: Ollama offline, usando Groq como backup...")
                resposta = self.perguntar_groq(pergunta)
            else:
                resposta = (
                    "A inteligência artificial local não está disponível. "
                    "Inicie o Ollama com: ollama serve"
                )

        return resposta


# ============================================================
#  CLASSE 5.5 - ArduinoController
#  Controla servo e LEDs de estado (via Arduino Uno) pela porta serial
# ============================================================
class ArduinoController:
    """
    Comunica com o Arduino Uno (sketch r2d2_servo.ino) pela serial.

    Protocolo (1 caractere por comando, 9600 baud):
        b"a" -> comeca a balancar o servo      b"b" -> para o servo
        b"c" -> LED verde aceso (escutando)    b"d" -> LED verde apagado
        b"e" -> LED vermelho piscando          b"f" -> LED vermelho apagado
                (respondendo)

    Se o Arduino nao estiver conectado (ou o pyserial nao estiver instalado),
    a classe apenas avisa no console e o R.2.D.2 continua funcionando
    normalmente, so que sem servo e sem LEDs.

    A porta pode ser definida pela variavel de ambiente ARDUINO_PORT
    (ex.: COM3 no Windows, /dev/ttyACM0 no Linux). Se nao for definida,
    tenta detectar automaticamente e, por ultimo, usa COM3.
    """

    BAUDRATE       = 9600
    PORTA_PADRAO   = "COM3"
    PROTOCOLO      = b"R2D2/1"
    CMD_PING       = b"?"
    CMD_ESTADO     = b"s"
    CMD_SERVO_ON   = b"a"
    CMD_SERVO_OFF  = b"b"
    CMD_VERDE_ON   = b"c"
    CMD_VERDE_OFF  = b"d"
    CMD_VERM_ON    = b"e"
    CMD_VERM_OFF   = b"f"
    ESPERA_RESET_S = 2  # o Uno reinicia ao abrir a serial

    def __init__(self, porta: str = ""):
        """
        Args:
            porta: porta serial (opcional; vazio = ARDUINO_PORT ou autodeteccao)
        """
        self.porta = porta or os.getenv("ARDUINO_PORT", "")
        self.conexao = None
        self._conectar()

    @property
    def disponivel(self) -> bool:
        """True se ha uma conexao serial aberta com o Arduino."""
        return self.conexao is not None and self.conexao.is_open

    def _detectar_porta(self) -> str:
        """Procura uma porta com cara de Arduino; devolve a padrao se nao achar."""
        try:
            from serial.tools import list_ports
            for info in list_ports.comports():
                descricao = f"{info.description} {info.manufacturer}".lower()
                if any(chave in descricao for chave in ("arduino", "ch340", "usb serial")):
                    return info.device
        except Exception:
            pass
        return self.PORTA_PADRAO

    def _conectar(self):
        """Abre a serial (uma vez, na inicializacao) e aguarda o reset do Uno."""
        try:
            import serial
        except ImportError:
            print("[R.2.D.2]: pyserial nao instalado (pip install pyserial). Arduino desativado.")
            return

        porta = self.porta or self._detectar_porta()
        try:
            self.conexao = serial.Serial(porta, self.BAUDRATE, timeout=0.5, write_timeout=1)
            time.sleep(self.ESPERA_RESET_S)
            self.conexao.reset_input_buffer()
            if self._enviar(self.CMD_PING) == self.PROTOCOLO:
                self.porta = porta
                print(f"[R.2.D.2]: Arduino confirmado em {porta} (R2D2/1).")
            else:
                print("[R.2.D.2]: Firmware nao confirmado. Confira a conexao USB e se o Uno esta executando r2d2_servo.ino.")
        except Exception as erro:
            self._desconectar()
            print(f"[R.2.D.2]: Arduino nao encontrado em {porta} ({erro}). Arduino desativado.")

    def _desconectar(self):
        """Libera a serial mesmo quando uma operacao falha."""
        if self.conexao is not None:
            try:
                self.conexao.close()
            except Exception:
                pass
            self.conexao = None

    def _enviar(self, comando: bytes) -> bytes:
        """Envia um comando e exige resposta do firmware; falhas fecham a serial."""
        if not self.disponivel:
            return b""
        try:
            if self.conexao.write(comando) != len(comando):
                raise OSError("comando enviado parcialmente")
            self.conexao.flush()
            resposta = self.conexao.readline().strip()
            if comando == self.CMD_PING:
                valida = resposta == self.PROTOCOLO
            elif comando == self.CMD_ESTADO:
                valida = re.fullmatch(rb"STATE [01] [01] [01]", resposta) is not None
            else:
                valida = resposta == b"OK " + comando
            if not valida:
                raise OSError(f"sem confirmacao para {comando!r}: {resposta!r}")
            return resposta
        except Exception as erro:
            print(f"[R.2.D.2]: Falha na comunicacao com o Arduino: {erro}")
            self._desconectar()
            return b""

    def consultar_estado(self):
        """Le os estados logicos do Uno; nao comprova movimento ou fiacao."""
        resposta = self._enviar(self.CMD_ESTADO)
        if not resposta:
            return None
        valores = resposta.split()[1:]
        return dict(zip(("servo", "verde", "vermelho"), (valor == b"1" for valor in valores)))

    # ---------------- Servo ----------------
    def iniciar_movimento(self):
        """Manda o servo comecar a balancar."""
        self._enviar(self.CMD_SERVO_ON)

    def parar_movimento(self):
        """Manda o servo parar e voltar ao centro."""
        self._enviar(self.CMD_SERVO_OFF)

    # ---------------- LEDs ----------------
    def escutando(self, ligado: bool):
        """LED verde: aceso enquanto o R.2.D.2 esta escutando."""
        self._enviar(self.CMD_VERDE_ON if ligado else self.CMD_VERDE_OFF)

    def respondendo(self, ligado: bool):
        """LED vermelho: pisca enquanto o R.2.D.2 esta respondendo."""
        self._enviar(self.CMD_VERM_ON if ligado else self.CMD_VERM_OFF)

    def fechar(self):
        """Desliga servo e LEDs e fecha a porta serial."""
        self.parar_movimento()
        self.escutando(False)
        self.respondendo(False)
        self._desconectar()


# ============================================================
#  CLASSE 6 - ExtraCommands
#  Comandos extras: clima, dolar, bitcoin, screenshot, busca
# ============================================================
class ExtraCommands:
    """
    Comandos extras que enriquecem a experiencia do R.2.D.2:
    - Previsao do tempo (wttr.in, sem chave)
    - Cotacao do dolar (AwesomeAPI, sem chave)
    - Valor do Bitcoin (CoinGecko, sem chave)
    - Screenshot da tela (Pillow)
    - Pesquisa no Google
    - Abrir YouTube
    - Abrir portal da FIAP
    """

    # URLs de APIs publicas e gratuitas
    URL_DOLAR   = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
    URL_BITCOIN = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl,usd"
    URL_CLIMA   = "https://wttr.in/{cidade}?format=j1"
    TEMPO_MIN_MOVIMENTO_S = 4.0

    def __init__(self, arduino: "ArduinoController" = None):
        """
        Args:
            arduino: ArduinoController usado para mexer o servo e piscar o
                     LED vermelho durante o grito (opcional; sem ele o
                     grito toca apenas o som)
        """
        self.arduino = arduino

    def obter_dolar(self) -> str:
        """
        Consulta a cotacao atual do dolar em reais.

        Returns:
            String com a cotacao ou mensagem de erro
        """
        try:
            resposta = requests.get(self.URL_DOLAR, timeout=5)
            dados = resposta.json()
            cotacao = float(dados["USDBRL"]["bid"])
            return f"O dólar está cotado a {cotacao:.2f} reais."
        except Exception:
            return "Não consegui obter a cotação do dólar agora."

    def obter_bitcoin(self) -> str:
        """
        Consulta o valor atual do Bitcoin em reais e dolares.

        Returns:
            String com o valor ou mensagem de erro
        """
        try:
            resposta = requests.get(self.URL_BITCOIN, timeout=5)
            dados = resposta.json()
            valor_brl = dados["bitcoin"]["brl"]
            valor_usd = dados["bitcoin"]["usd"]
            return (
                f"O Bitcoin está valendo {valor_brl:,.0f} reais "
                f"ou {valor_usd:,.0f} dólares."
            )
        except Exception:
            return "Não consegui obter o valor do Bitcoin agora."

    def obter_clima(self, cidade: str = "S\u00e3o Paulo") -> str:
        """
        Consulta a previsao do tempo para uma cidade.

        Args:
            cidade: nome da cidade (padrao S\u00e3o Paulo)

        Returns:
            String com a previsao ou mensagem de erro
        """
        try:
            url = self.URL_CLIMA.format(cidade=cidade.replace(" ", "+"))
            resposta = requests.get(url, timeout=5)
            dados = resposta.json()

            atual     = dados["current_condition"][0]
            temp_c    = atual["temp_C"]
            descricao = atual["weatherDesc"][0]["value"]
            umidade   = atual["humidity"]

            return (
                f"Em {cidade}, a temperatura é de {temp_c} graus Celsius, "
                f"{descricao}, com {umidade} porcento de umidade."
            )
        except Exception:
            return f"Não consegui obter a previsão do tempo para {cidade}."

    def tirar_screenshot(self) -> str:
        """
        Captura a tela e salva como arquivo PNG com timestamp.

        Returns:
            Mensagem com o nome do arquivo salvo ou erro
        """
        try:
            from PIL import ImageGrab
            agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo = f"screenshot_{agora}.png"
            PASTA_SAIDAS.mkdir(parents=True, exist_ok=True)
            imagem = ImageGrab.grab()
            imagem.save(PASTA_SAIDAS / nome_arquivo)
            return f"Screenshot salvo em outputs/{nome_arquivo}."
        except ImportError:
            return "Instale o Pillow para tirar screenshots: pip install Pillow"
        except Exception as erro:
            return f"Erro ao tirar screenshot: {erro}"

    def pesquisar_google(self, termo: str) -> str:
        """
        Abre o Google com uma pesquisa no navegador padrao.

        Args:
            termo: o que pesquisar

        Returns:
            Confirmacao da acao
        """
        url = f"https://www.google.com/search?q={termo.replace(' ', '+')}"
        webbrowser.open(url)
        return f"Pesquisando por {termo} no Google."

    def abrir_youtube(self, busca: str = "") -> str:
        """
        Abre o YouTube, com busca opcional.

        Args:
            busca: termo de busca (opcional)

        Returns:
            Confirmacao da acao
        """
        if busca:
            url = f"https://www.youtube.com/results?search_query={busca.replace(' ', '+')}"
            webbrowser.open(url)
            return f"Abrindo YouTube com a busca: {busca}."
        else:
            webbrowser.open("https://www.youtube.com")
            return "Abrindo YouTube."

    def abrir_portal_fiap(self) -> str:
        """
        Abre o portal da FIAP no navegador.

        Returns:
            Confirmacao da acao
        """
        webbrowser.open("https://on.fiap.com.br")
        return "Abrindo o portal da FIAP."

    def grita(self) -> str:
        """
        Toca o som caracteristico do R2D2 e, ao mesmo tempo, balanca o
        servo motor e pisca o LED vermelho (Arduino). Com a placa conectada,
        mantem a animacao por pelo menos 4 segundos, mesmo se o audio acabar
        antes, para dar tempo de a cabeca completar o movimento.

        Servo e LED sao sempre desligados no final (bloco finally), mesmo
        se ocorrer algum erro na reproducao.

        Returns:
            String vazia (a resposta e o proprio som) ou mensagem de erro
        """
        try:
            mixer.music.stop()
            mixer.music.unload()
            mixer.music.load(str(AUDIO_GRITO))
            mixer.music.set_volume(1.0)
            mover_cabeca = self.arduino is not None and self.arduino.disponivel
            try:
                # Inicia o movimento antes do som para nao perder parte do
                # audio curto esperando pelas confirmacoes da serial.
                if mover_cabeca:
                    self.arduino.iniciar_movimento()
                    self.arduino.respondendo(True)
                inicio = time.monotonic()
                mixer.music.play()

                while mixer.music.get_busy() or (
                    mover_cabeca and time.monotonic() - inicio < self.TEMPO_MIN_MOVIMENTO_S
                ):
                    time.sleep(0.05)
            finally:
                # Falhas na reproducao interrompem a animacao imediatamente.
                if mover_cabeca:
                    self.arduino.parar_movimento()
                    self.arduino.respondendo(False)
                mixer.music.stop()
                mixer.music.unload()
            if self.arduino is not None and not self.arduino.disponivel:
                return (
                    "O som tocou, mas perdi a comunicação com o Arduino. "
                    "Não consegui confirmar o comando da cabeça. Confira a conexão USB."
                )
            return ""
        except Exception as erro:
            return f"N\u00e3o consegui tocar o som: {erro}"


# ============================================================
#  CLASSE 7 - R2D2 (Orquestradora Principal)
#  Integra todos os modulos e processa os comandos de voz
# ============================================================
class R2D2:
    """
    Classe principal que orquestra todas as funcionalidades do R.2.D.2.
    Processa comandos de voz e delega para os modulos corretos.

    O assistente so executa acoes quando ouve "dedao" no inicio da fala.
    Caso contrario, apenas imprime o texto reconhecido sem agir.
    """

    # Palavra de ativacao - usuario precisa dizer isso primeiro
    # "dedao" é a versao normalizada (sem acento) de "dedão"
    NOME = "dedao"

    def __init__(self, groq_api_key: str = ""):
        """
        Inicializa o R.2.D.2 e todos os seus modulos.

        Args:
            groq_api_key: chave opcional para usar o Groq como IA de backup
        """
        print("=" * 52)
        print("  R.2.D.2 - Robotic Responsive Digital Dual Assistant")
        print("  Inicializando sistemas...")
        print("=" * 52)

        # Composicao de objetos: cada modulo tem responsabilidade unica
        # Arduino primeiro: o SpeechManager usa os LEDs de estado
        self.arduino = ArduinoController()
        self.speech = SpeechManager(arduino=self.arduino)
        self.agenda = AgendaManager()
        self.calc   = Calculator()
        self.face   = FaceRecognizer()
        self.ai     = AIIntegration(modelo="llama3.2:3b", groq_api_key=groq_api_key)
        self.extras = ExtraCommands(arduino=self.arduino)

    def _dizer_hora(self) -> str:
        """Retorna a hora atual formatada para fala."""
        agora = datetime.datetime.now()
        return f"São {agora.hour} horas e {agora.minute} minutos."

    def _dizer_data(self) -> str:
        """Retorna a data atual formatada para fala."""
        agora      = datetime.datetime.now()
        dias       = ["segunda-feira", "terça-feira", "quarta-feira",
                      "quinta-feira", "sexta-feira", "sábado", "domingo"]
        meses      = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                      "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        dia_semana = dias[agora.weekday()]
        return (
            f"Hoje é {dia_semana}, {agora.day} de "
            f"{meses[agora.month - 1]} de {agora.year}."
        )

    def processar_comando(self, comando: str) -> bool:
        """
        Valida a ativacao no inicio da fala e aciona o modulo correto.

        Args:
            comando: fala completa, incluindo a palavra de ativacao

        Returns:
            False para encerrar o programa, True para continuar
        """

        comando = remover_acentos(comando.lower().strip())
        comando = re.sub(r"\s+", " ", comando)
        ativacao = re.match(rf"{re.escape(self.NOME)}\b[\s,.:;!?-]*", comando)
        if not ativacao:
            print(f"[Reconhecido, sem acao]: {comando}")
            return True

        # Retira apenas a ativacao inicial; o assunto pode mencionar "dedao".
        comando = comando[ativacao.end():].strip()

        # Cada intencao deve estar no inicio, nunca dentro de um assunto.
        # -- Sair: somente um pedido completo de encerramento -------
        if re.fullmatch(r"(?:sair|encerrar|tchau)[.!?]*", comando):
            self.speech.falar("Até logo! Sistemas desligando. Bip bup.")
            return False

        # -- Agenda: cadastrar -------------------------------------
        elif re.match(r"(?:cadastrar evento|adicionar evento)\b", comando):
            evento = self.speech.ouvir_resposta("Ok, qual evento devo cadastrar?")
            if evento:
                resultado = self.agenda.cadastrar_evento(evento)
                self.speech.falar(resultado)
            else:
                self.speech.falar("Não consegui ouvir o evento.")

        # -- Agenda: ler -------------------------------------------
        elif re.match(r"(?:ler agenda|minha agenda)\b", comando):
            resultado = self.agenda.ler_agenda()
            self.speech.falar(resultado)

        # -- Agenda: limpar ----------------------------------------
        elif re.match(r"(?:limpar agenda|apagar agenda)\b", comando):
            confirmacao = self.speech.ouvir_resposta(
                "Tem certeza que deseja limpar toda a agenda? Diga sim ou não."
            )
            if "sim" in confirmacao:
                resultado = self.agenda.limpar_agenda()
                self.speech.falar(resultado)
            else:
                self.speech.falar("Ok, agenda mantida.")

        # -- Horas -------------------------------------------------
        elif re.match(r"(?:que horas|horas sao)\b", comando):
            self.speech.falar(self._dizer_hora())

        # -- Data --------------------------------------------------
        elif re.match(r"(?:que dia|dia e hoje|data de hoje)\b", comando):
            self.speech.falar(self._dizer_data())

        # -- Calculo -----------------------------------------------
        elif re.match(r"(?:calcular|quanto e|quanto vale)\b", comando):
            resultado = self.calc.calcular(comando)
            self.speech.falar(resultado)

        # -- Reconhecimento facial ---------------------------------
        elif re.match(r"(?:reconhecer face|quem sou eu|reconhecer rosto)\b", comando):
            self.speech.falar("Abrindo a câmera para reconhecimento facial.")
            resultado = self.face.reconhecer()
            self.speech.falar(resultado)

        # -- IA generativa -----------------------------------------
        elif pedido_ia := re.match(r"(perguntar|me fale sobre|o que e)\b[\s,:-]*", comando):
            pergunta = comando[pedido_ia.end():].strip()
            if pedido_ia.group(1) == "o que e" and pergunta:
                pergunta = f"o que e {pergunta}"
            if not pergunta:
                pergunta = self.speech.ouvir_resposta("O que você quer saber?")

            if pergunta:
                self.speech.falar("Consultando a inteligência artificial, aguarde.")
                resposta = self.ai.perguntar(pergunta)
                self.speech.falar(resposta)

        # -- Previsao do tempo -------------------------------------
        elif re.match(r"(?:previsao do tempo|tempo em|como esta o tempo)\b", comando):
            cidade = "S\u00e3o Paulo"
            if "em " in comando:
                partes = comando.split("em ")
                if len(partes) > 1:
                    cidade = partes[-1].strip()
            resultado = self.extras.obter_clima(cidade)
            self.speech.falar(resultado)

        # -- Dolar -------------------------------------------------
        elif re.match(r"(?:(?:valor|cotacao) do )?(?:dolar|cambio)\b", comando):
            resultado = self.extras.obter_dolar()
            self.speech.falar(resultado)

        # -- Bitcoin -----------------------------------------------
        elif re.match(r"(?:(?:valor|cotacao) do )?(?:bitcoin|cripto)\b", comando):
            resultado = self.extras.obter_bitcoin()
            self.speech.falar(resultado)

        # -- Screenshot --------------------------------------------
        elif re.match(r"(?:tirar screenshot|screenshot|print da tela|capturar tela)\b", comando):
            resultado = self.extras.tirar_screenshot()
            self.speech.falar(resultado)

        # -- YouTube -----------------------------------------------
        elif pedido_youtube := re.match(
            r"(?:abrir (?:o )?)?youtube\b(?:\s+(?:sobre|video de)\b[\s,:-]*(.*))?",
            comando,
        ):
            busca = (pedido_youtube.group(1) or "").strip()
            resultado = self.extras.abrir_youtube(busca)
            self.speech.falar(resultado)

        # -- Pesquisa no Google ------------------------------------
        elif pedido_google := re.match(
            r"(?:pesquisar|buscar|pesquisa)\b(?:\s+no google\b)?[\s,:-]*", comando
        ):
            termo = comando[pedido_google.end():].strip()
            if not termo:
                termo = self.speech.ouvir_resposta("O que você quer pesquisar?")
            if termo:
                resultado = self.extras.pesquisar_google(termo)
                self.speech.falar(resultado)

        # -- Portal da FIAP ----------------------------------------
        elif re.match(r"(?:abrir (?:o |a )?)?(?:portal|fiap|faculdade)\b", comando):
            resultado = self.extras.abrir_portal_fiap()
            self.speech.falar(resultado)

        # -- Grita / som do R2D2 -----------------------------------
        elif re.match(r"(?:grita|grite|som)\b", comando):
            print("[R.2.D.2]: *beep boop*")
            resultado = self.extras.grita()
            if resultado:  # So fala se houver mensagem de erro
                self.speech.falar(resultado)

        # -- Listar comandos ---------------------------------------
        elif re.match(r"(?:listar comandos|listar|comandos?)\b", comando):
            self.speech.falar(
                "Aqui estão os comandos disponíveis. "
                "Cadastrar evento. "
                "Ler agenda. "
                "Limpar agenda. "
                "Que horas são. "
                "Que dia é hoje. "
                "Calcular. "
                "Reconhecer face. "
                "Perguntar. "
                "Previsão do tempo. "
                "Valor do dólar. "
                "Bitcoin. "
                "Tirar screenshot. "
                "Pesquisar. "
                "Abrir YouTube. "
                "Abrir portal. "
                "Grita. "
                "Sair. "
                "Para usar qualquer comando, diga dedão seguido do comando."
            )

        # -- Comando nao reconhecido -------------------------------
        else:
            self.speech.falar(
                "Comando não reconhecido. "
                "Para ver todos os comandos, diga: dedão listar comandos."
            )

        return True  # Continua rodando

    def iniciar(self):
        """
        Loop principal do R.2.D.2.
        Ouve continuamente e so age quando a fala comeca com 'dedao'.
        Qualquer outra fala e impressa sem executar nenhuma acao.
        """
        self.speech.falar(
            "Sistemas online. Eu sou R 2 Dedão, sua assistente virtual. "
            "Diga dedão seguido do comando para interagir comigo. "
            "Para sair, diga dedão sair."
        )

        print("\n[R.2.D.2]: Aguardando comandos... (diga 'dedão <comando>')")
        print("[R.2.D.2]: Para sair, diga 'dedão sair' ou pressione Ctrl+C\n")

        try:
            while True:
                try:
                    comando = self.speech.ouvir(timeout=10, duracao=10)

                    if not comando:
                        continue

                    continuar = self.processar_comando(comando)
                    if not continuar:
                        break

                except KeyboardInterrupt:
                    print("\n[R.2.D.2]: Encerrando por interrupcao do usuario.")
                    self.speech.falar("Até logo! Bip bup.")
                    break
        finally:
            # Garante que servo e LEDs desligam e a porta serial e liberada
            self.arduino.fechar()


# ============================================================
#  PONTO DE ENTRADA
# ============================================================
if __name__ == "__main__":
    # Chave do Groq (opcional) - backup se Ollama estiver offline.
    # Defina na variavel de ambiente GROQ_API_KEY (NUNCA escreva a chave aqui,
    # para nao vazar no GitHub). Windows (PowerShell): $env:GROQ_API_KEY="gsk_..."
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    assistente = R2D2(groq_api_key=GROQ_API_KEY)
    assistente.iniciar()
