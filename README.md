# MediaLoader Pro Suite

Aplicativo Python com interface gráfica para baixar músicas de playlists do YouTube em lote, selecionar intervalos, acompanhar downloads, renomear arquivos e verificar itens faltantes.

## Requisitos

Windows 10/11 com:

- Python 3.10+ (Python 3.11 recomendado).
- `customtkinter`.
- `yt-dlp` + `yt-dlp-ejs`.
- Deno 2.3+ (runtime JavaScript usado pelo yt-dlp para o YouTube).
- FFmpeg + FFprobe.

O yt-dlp recomenda um runtime JavaScript suportado e os scripts EJS para downloads do YouTube. Deno é a opção recomendada. Veja a documentação oficial do EJS: https://github.com/yt-dlp/yt-dlp/wiki/EJS

## Estrutura do projeto

```text
meu-projeto/
├── music_improved.py
├── README.md
├── .venv/                  # opcional, recomendado
├── cookies.txt             # opcional; não compartilhar/publicar
└── Downloads_Playlist_HQ/ # criada automaticamente pelo programa
    └── .archive.txt       # histórico usado pelo yt-dlp
```

A pasta `Downloads_Playlist_HQ` fica no diretório de onde o script é executado.

## Instalação

### 1. Python

Confira:

```powershell
py --version
```

### 2. Ambiente virtual (recomendado)

Na pasta do projeto:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Bibliotecas Python

```powershell
python -m pip install -U pip
python -m pip install -U customtkinter "yt-dlp[default]"
```

O `yt-dlp[default]` inclui o `yt-dlp-ejs` no mesmo ambiente do yt-dlp.

Confira:

```powershell
python -m pip show customtkinter yt-dlp yt-dlp-ejs
```

### 4. Deno

No PowerShell:

```powershell
winget install DenoLand.Deno
```

Feche e abra o terminal novamente:

```powershell
deno --version
```

Instalação oficial: https://docs.deno.com/runtime/getting_started/installation/

### 5. FFmpeg

Uma opção simples no Windows:

```powershell
winget install -e --id Gyan.FFmpeg
```

Depois abra outro terminal e teste:

```powershell
ffmpeg -version
ffprobe -version
```

## Executar o programa

Com o ambiente virtual ativado:

```powershell
python .\music_improved.py
```

Ou diretamente:

```powershell
.\.venv\Scripts\python.exe .\music_improved.py
```

## Cookies e autenticação

Por padrão, o programa usa **Sem cookies**. Para playlists públicas, comece assim.

No Dashboard existem três opções:

### Sem cookies

Não acessa cookies do navegador.

### Usar navegador

Permite selecionar Chrome, Edge, Firefox ou Brave. A extração automática pode falhar no Windows por causa do DPAPI/proteção do banco de cookies.

### Usar cookies.txt

Clique em **Escolher cookies.txt** e selecione um arquivo exportado do navegador.

Não envie nem publique esse arquivo: ele pode conter uma sessão autenticada.

## Como usar

### 1. Dashboard

1. Cole a URL da playlist do YouTube.
2. Escolha a opção de cookies, se necessário.
3. Clique em **Load Playlist**.

O programa carrega a playlist e abre **Playlist Selection**.

### 2. Playlist Selection

A lista mostra até 50 itens por página.

**Filtros:**

- **Todos**: todos os itens da playlist.
- **Apenas Novos**: itens não registrados em `.archive.txt`.
- **Já Baixados**: itens registrados no histórico.

**Selecionar Todos / Desmarcar Todos** atuam sobre toda a lista filtrada.

### Selecionar um intervalo

Preencha:

```text
Início: 1
Fim: 213
```

Marque **Ignorar já baixadas** para excluir do intervalo os itens que já estão registrados no histórico e clique em **Selecionar Intervalo**.

O intervalo usa a posição **original da playlist**, então `1 até 213` significa as músicas 1–213 da playlist, independentemente da paginação ou dos filtros.

Depois clique em **Start Download**.

### Seleção com Shift

É possível marcar/desmarcar um intervalo visual segurando `Shift`. O recurso vale para os itens exibidos na página atual.

### 3. Active Processing

Durante o download a tela mostra:

- progresso geral do lote;
- música atual e posição na playlist;
- porcentagem;
- velocidade;
- ETA;
- logs do yt-dlp.

**Parar após a música atual** termina a música que já está sendo processada e encerra o lote.

### Arquivos gerados

Os downloads vão para:

```text
Downloads_Playlist_HQ/
```

O script tenta gerar áudio em **M4A** usando o FFmpeg e adicionar metadados e miniatura.

O arquivo:

```text
Downloads_Playlist_HQ/.archive.txt
```

é usado para registrar o histórico de itens processados.

### 4. Renamer

Abra **Renamer** e clique em **Ler Pasta Local**.

Formatos reconhecidos:

```text
.m4a  .mp3  .webm  .mp4  .mkv
```

O programa sugere uma ação:

- **Apagar INÍCIO**
- **Apagar FINAL**
- **Manter Original**

Você pode alterar o nome manualmente no campo **NOVO NOME (Editável)**.

Também é possível:

- filtrar pela ação sugerida;
- ordenar por nome ou data;
- marcar/desmarcar arquivos individualmente;
- usar Shift para selecionar um intervalo visual.

Clique em **Aplicar Correções** para executar as renomeações.

Se já existir um arquivo com o mesmo nome, o programa cria um nome alternativo, por exemplo:

```text
musica.m4a
musica (1).m4a
musica (2).m4a
```

As sugestões são heurísticas. Revise os nomes antes de aplicar.

### 5. Diagnostics

Abra **Diagnostics**, cole a URL da playlist e clique em **Verificar Falhas**.

A tela compara a playlist com o histórico `.archive.txt` e mostra os itens que não estão registrados.

Cada item mostra:

- posição;
- título;
- ID do vídeo;
- URL.

**Importante:** o diagnóstico atual usa o `.archive.txt` como referência principal. Ele não verifica de forma completa se cada arquivo físico ainda existe ou está íntegro na pasta.

## Fluxo recomendado para playlists grandes

Exemplo: playlist com 1.064 músicas.

```text
1. Dashboard
2. Colar URL
3. Load Playlist
4. Playlist Selection
5. Início = 1
6. Fim = 213
7. Ignorar já baixadas
8. Selecionar Intervalo
9. Start Download
10. Active Processing
```

Depois:

```text
Renamer      → limpar nomes
Diagnostics  → conferir itens não registrados
```

## Solução de problemas

### `The page needs to be reloaded` / `n challenge solving failed`

Verifique:

```powershell
deno --version
python -m pip show yt-dlp yt-dlp-ejs
```

Atualize:

```powershell
python -m pip install -U "yt-dlp[default]"
```

O erro normalmente indica problema no runtime JavaScript ou nos scripts EJS usados para resolver os desafios do YouTube.

### `Failed to decrypt with DPAPI`

Evite **Usar navegador** e tente:

```text
Dashboard
→ Autenticação / Cookies
→ Usar cookies.txt
```

### `FFmpeg Ausente`

Teste:

```powershell
ffmpeg -version
ffprobe -version
```

### O programa fecha ou apresenta erro no início

Execute pelo PowerShell:

```powershell
python .\music_improved.py
```

Assim a mensagem de erro permanece visível no terminal.

## Atualizar dependências

```powershell
python -m pip install -U customtkinter "yt-dlp[default]"
```

Depois confirme:

```powershell
python -m pip show yt-dlp yt-dlp-ejs
deno --version
ffmpeg -version
```

## Segurança

Não versione nem compartilhe:

```text
cookies.txt
Downloads_Playlist_HQ/
.venv/
```

Exemplo de `.gitignore`:

```gitignore
.venv/
cookies.txt
Downloads_Playlist_HQ/
```

## Links oficiais

- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Instalação do yt-dlp: https://github.com/yt-dlp/yt-dlp/wiki/Installation
- EJS / JavaScript runtime: https://github.com/yt-dlp/yt-dlp/wiki/EJS
- yt-dlp-ejs: https://github.com/yt-dlp/ejs
- Deno: https://docs.deno.com/runtime/getting_started/installation/
