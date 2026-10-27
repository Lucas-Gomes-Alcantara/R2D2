# Como publicar no GitHub

[Voltar ao projeto](../README.md)

## Usando Git

Na pasta do projeto, confira os arquivos que serão incluídos:

```bash
git status --short
```

Esta cópia local já foi inicializada com a branch `main`. Se estiver usando uma
cópia extraída do ZIP, execute primeiro `git init -b main`.

Crie um repositório vazio no GitHub, sem adicionar README, licença ou `.gitignore`
nessa etapa. Depois, execute na pasta do projeto:

```bash
git add .
git diff --cached --stat
git commit -m "Organiza projeto R2D2 para publicacao"
git remote add origin https://github.com/SEU_USUARIO/R2D2.git
git push -u origin main
```

Substitua `SEU_USUARIO/R2D2` pelo proprietário e nome do repositório criado.
O envio exige autenticação na sua conta do GitHub. Se o Git pedir identificação
para o commit, configure `git config user.name "Seu nome"` e
`git config user.email "Seu email"` nesta pasta.

O `.gitignore` exclui o ambiente virtual, caches, credenciais, a agenda, gravações,
capturas de tela e os pacotes em `dist/`. Confira a lista antes de confirmar o
primeiro commit.

## Usando o navegador

Foi preparado um pacote em `dist/R2D2-github.zip` com os arquivos necessários
para esta versão do projeto.

1. Extraia o ZIP em uma pasta separada.
2. Abra o repositório no GitHub e use a opção de upload de arquivos.
3. Envie o **conteúdo da pasta `R2D2` extraída**, mantendo suas subpastas.
4. Inclua também `.gitignore` e `.gitattributes` e confirme o commit.

Envie os arquivos extraídos, não o ZIP como único arquivo do repositório. O
`.gitignore` é aplicado pelo Git local; ele não filtra arquivos selecionados
manualmente no navegador.

O pacote é uma cópia desta preparação. Se editar o projeto depois, use Git para
enviar a versão atual ou gere um novo pacote.

## Arquivos que ficam somente na máquina

| Caminho | Conteúdo |
|---|---|
| `.venv/` | Dependências instaladas localmente |
| `data/` | Agenda pessoal (`agenda.txt`) |
| `outputs/` | Capturas de tela e gravações de diagnóstico |
| `.env` e `.env.*` | Possíveis configurações privadas |
| `__pycache__/` | Cache do Python |
| `dist/` | ZIP preparado para distribuição |

Configure chaves de API por variáveis de ambiente, conforme o
[manual](manual.md#configurações-opcionais). O projeto não carrega `.env`
automaticamente.
