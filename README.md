# R.2.D.2 — Robotic Responsive Digital Dual Assistant

Assistente virtual por voz em português, ativado pela palavra **"dedão"**, com
agenda, calculadora, consultas a IA e integração opcional com Arduino Uno.

Projeto **CP4 — 2º semestre**, da disciplina de Programação Orientada a Objetos
em Python.

## Funcionalidades

- Reconhecimento e síntese de voz em português (Google STT e gTTS).
- Agenda local, data, hora e cálculos com números por extenso.
- IA via Ollama, com Groq como alternativa opcional.
- Clima, cotações, pesquisas, YouTube e capturas de tela.
- Detecção de rostos pela webcam.
- Servo e LEDs de estado no Arduino Uno, incluindo movimento durante o grito.

O Arduino é opcional. A câmera detecta rostos; a identificação de pessoas ainda
não está implementada.

## Estrutura do projeto

```text
R2D2/
├── checkpoint_alexa.py          # Aplicação principal e classes
├── requirements.txt            # Dependências Python
├── README.md
├── .gitignore                  # Exclusão de dados locais e credenciais
├── .gitattributes              # Tratamento de texto e arquivos binários
├── arduino/
│   └── r2d2_servo/
│       └── r2d2_servo.ino       # Firmware do servo e dos LEDs
├── assets/
│   └── audio/
│       └── r2d2_grito.mp3       # Áudio usado pela aplicação
├── docs/
│   ├── manual.md               # Instalação, montagem, comandos e diagnóstico
│   └── publicacao.md           # Como enviar o projeto ao GitHub
├── scripts/
│   ├── __init__.py
│   ├── diagnostico_arduino.py
│   └── diagnostico_voz.py
└── tests/
    └── test_comandos_voz.py     # Testes sem hardware ou rede
```

As pastas `data/` (agenda) e `outputs/` (capturas e gravações) são criadas conforme
o uso e ficam fora do Git. O ambiente `.venv/` e os pacotes em `dist/` também são
ignorados.

## Instalação e execução

Requisitos: **Python 3.10 ou superior**, microfone, saída de áudio e internet
para os serviços de voz. Use uma webcam para a detecção facial e, opcionalmente,
um Arduino Uno com servo e LEDs.

Baixe ou clone o repositório e abra um terminal na pasta do projeto.

**Windows — PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe checkpoint_alexa.py
```

**Linux / macOS:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python checkpoint_alexa.py
```

Para usar a IA local, instale o [Ollama](https://ollama.com), execute
`ollama pull llama3.2:3b` e mantenha o serviço em execução. As opções de Groq,
microfone e porta serial estão no [manual](docs/manual.md#configurações-opcionais).

Após a inicialização, diga **"dedão listar comandos"**. Para encerrar, diga
**"dedão sair"** ou pressione `Ctrl+C`.

## Diagnósticos e testes

Com as dependências instaladas e o ambiente virtual ativo, execute na raiz:

```bash
python -m scripts.diagnostico_voz --listar
python -m scripts.diagnostico_voz --microfone 1
python -m scripts.diagnostico_arduino --porta COM4
python -m unittest discover -s tests -v
```

Ajuste o índice do microfone e a porta à sua máquina. Feche o assistente e o
Monitor Serial antes de testar o Arduino.

Os testes automatizados usam a biblioteca padrão do Python e simulam áudio,
rede e comunicação serial. Eles não exigem instalar `requirements.txt` nem
conectar hardware; o funcionamento físico deve ser conferido separadamente.

## Documentação

- [Manual completo: instalação, montagem, comandos e solução de problemas](docs/manual.md)
- [Publicação no GitHub: Git ou upload pelo navegador](docs/publicacao.md)

## Integrantes

| Integrante | RM |
|---|---|
| Gabriel Gomes Catanzaro | RM93445 |
| Lucas Gomes Alcântara | RM98766 |
| Filipe Prado Menezes | RM98765 |
| Henrique Canali Cuzato | RM551326 |
| Cassio Eid Kobayashi Yonetsuka | RM99678 |
| Pedro Henrique Salvitti Habiro | RM88166 |
