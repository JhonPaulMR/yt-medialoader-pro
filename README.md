# MediaLoader Pro

Baixe playlists e vídeos do YouTube em áudio de alta qualidade, mantenha sua biblioteca organizada e mande as músicas para o celular **pelo Wi-Fi, sem cabo**.

---

## Sumário
1. [Instalação](#1-instalação)
2. [Primeiros passos](#2-primeiros-passos)
3. [Telas do app](#3-telas-do-app)
4. [Cookies (conta do YouTube)](#4-cookies-conta-do-youtube)
5. [Celular sem cabo](#5-celular-sem-cabo)
6. [Problemas comuns](#6-problemas-comuns)
7. [Onde ficam os dados](#7-onde-ficam-os-dados)
8. [Para desenvolvedores](#8-para-desenvolvedores)

---

## 1. Instalação

### Opção A: instalador (recomendado)
1. Rode **`MediaLoader-Setup.exe`**. Ele não pede senha de administrador e instala só para o seu usuário.
2. Instale as duas ferramentas gratuitas que o app usa. Abra o **PowerShell** e rode:
   ```
   winget install Gyan.FFmpeg
   winget install DenoLand.Deno
   ```
   - **FFmpeg** converte o áudio e coloca a capa e os nomes nas músicas.
   - **Deno** resolve os desafios de segurança do YouTube. Sem ele, os downloads falham.
3. Abra o **MediaLoader Pro** pelo Menu Iniciar ou pelo atalho da Área de Trabalho.

Para **desinstalar**, use Configurações do Windows → Aplicativos → MediaLoader Pro. Suas músicas e configurações **não são apagadas**.

### Opção B: rodar pelo código (Python)
```
cd python
python -m pip install -r requirements.txt
python music.py
```
Funciona a partir de qualquer pasta. O app sempre usa a pasta onde o `music.py` está.

---

## 2. Primeiros passos
1. **Primeira execução do instalador**: o app pergunta qual é a **pasta da biblioteca**. Se você já usava o MediaLoader como script, escolha a pasta antiga (ex.: `...\python\Downloads_Playlist_HQ`). O histórico de downloads fica dentro dela, e assim nada é baixado de novo.
2. Na tela **Início**, cole a URL de uma playlist ou de um vídeo e pressione **Enter**.
3. Na tela **Seleção**, confira o que está marcado e clique em **Baixar selecionadas**.
4. Acompanhe na tela **Progresso**.

---

## 3. Telas do app

### Início
- O campo de URL guarda as **últimas 10 URLs** (seta à direita).
- Mostra a pasta de destino, o formato e os cookies em uso, com atalhos para alterar.
- **Biblioteca local** mostra quantos áudios há na pasta, quantos IDs estão no histórico (`.archive.txt`) e quantos estão ligados a um vídeo (`.library.json`).

### Seleção
Cada item da playlist recebe uma etiqueta:

| Etiqueta | Significado |
|---|---|
| **NOVO** | Ainda não está no PC. Vem marcado. |
| **NA PASTA** | Um arquivo com esse nome já existe na pasta (achado pelo título). |
| **BAIXADO** | Já foi baixado pelo app. |
| **REMOVIDO** | Foi baixado, mas o arquivo não está mais na pasta. |
| **INDISPONÍVEL** | Vídeo privado ou excluído. |

- **Buscar** (Ctrl+F) por título ou canal, e **filtros** por etiqueta.
- **Intervalo da playlist**: ex. "1 até 50", com a opção "Só novos".
- **Shift + clique** marca ou desmarca vários itens de uma vez. **Ctrl+A** marca todos do filtro.
- **☆ Salvar playlist** adiciona a playlist à tela Playlists.

### Playlists
- Lista as playlists salvas, com a data da última verificação e quantas músicas novas cada uma tem.
- **Verificar todas** consulta o YouTube, uma playlist por vez.
- **Sincronizar tudo** verifica e baixa, numa fila, as músicas novas de **todas** as playlists.

### Progresso
- Mostra a barra do item atual e a barra geral, e conta concluídas, puladas, falhas e o tempo.
- **Parar após a atual** termina a música em andamento e para. **Parar agora** interrompe na hora (o arquivo parcial é retomado no próximo download).
- No fim do lote:
  - **Tentar falhas de novo** e **Exportar falhas** (com a explicação de cada erro).
  - **Abrir pasta**.
- O log fica salvo em arquivo (veja a [seção 7](#7-onde-ficam-os-dados)).
- Se a janela estiver minimizada, o Windows avisa quando o lote termina.

### Celular
Envia músicas para o Android pelo Wi-Fi. Veja a [seção 5](#5-celular-sem-cabo).

### Renomeador
Limpa os nomes dos arquivos. Nenhuma mudança vale até você clicar em **Aplicar**, e **Desfazer última** reverte o último lote.

| Ação | O que faz | Exemplo |
|---|---|---|
| Apagar INÍCIO | tira o que vem antes do " - " | `Linkin Park - Numb.m4a` → `Numb.m4a` |
| Apagar FINAL | tira o que vem depois do " - " | `Numb - Ao Vivo.m4a` → `Numb.m4a` |
| Remover tags | tira "(Official Video)", "[HD]"… e mantém "(Ao Vivo)" e "(feat. X)" | `Numb (Official Video) [HD].m4a` → `Numb.m4a` |
| Usar metadado | usa o título gravado dentro do arquivo | `Linkin Park (14).m4a` → `Papercut - Linkin Park.m4a` |
| Manter Original | não mexe | |

- O filtro **Nomes genéricos** mostra arquivos cujo nome perdeu a música (ex.: `OFFICIAL VIDEO.m4a`, `Linkin Park (14).m4a`). Para eles, o app já sugere **Usar metadado**.
- A barra **Em massa** tem duas opções:
  - **Localizar → Substituir**: texto ou regex.
  - **Ação para todos os filtrados**.
- Verde = o nome vai mudar. Borda amarela = já existe um arquivo com esse nome.
- A capa solta (`.jpg`) é renomeada junto com o áudio.

### Diagnóstico
- **Playlist**: compara uma playlist com a pasta.
  - **Baixar faltantes** abre a Seleção só com o que falta.
  - **Registrar "na pasta" no histórico** grava no histórico as músicas que já estão na pasta, para nunca baixá-las de novo.
- **Biblioteca**:
  - **Duplicatas**: mesma música (pelo título do metadado) com duração parecida. O maior arquivo de cada grupo fica.
  - **Órfãos**: arquivos que não estão em nenhuma playlist salva.
  - **Nomes danificados**: abre o Renomeador já filtrado.
  - O botão **Mover para a Lixeira** sempre pede confirmação, e dá para recuperar pela Lixeira do Windows.
- **Ambiente**: mostra o estado do yt-dlp, FFmpeg, Deno e yt-dlp-ejs.
  - **Atualizar yt-dlp**: o YouTube muda com frequência, e o app avisa na barra lateral quando sai uma versão nova.

### Configurações
- **Pasta de destino** e **subpasta por playlist**.
- **Formato**: M4A (padrão, sem perda), MP3 320 kbps ou Opus.
- **Nome do arquivo**: `Título`, `NNN - Título` (posição na playlist) ou `Canal - Título`.
- **SponsorBlock**: corta intros e falas dos clipes, quando a comunidade marcou esses trechos.
- **Gerar .m3u8**: cria a playlist na ordem do YouTube, que abre em qualquer player.
- **Limite de velocidade** em MB/s, para não travar a internet de casa.
- **Cookies**: veja a próxima seção.
- **Enviar ao celular automaticamente** depois de cada download.

Tudo é salvo automaticamente.

---

## 4. Cookies (conta do YouTube)
Os cookies **não são necessários** para vídeos públicos. Use-os quando aparecer erro de vídeo privado, restrição de idade ou "Sign in to confirm you're not a bot".

**Com o Chrome, Edge ou Brave (recomendado):**
1. Em Configurações → Cookies, escolha **Ler do navegador** e depois o navegador.
2. Clique em **Entrar no YouTube e exportar**. Abre uma janela separada do navegador, com um perfil só do MediaLoader (seus perfis normais não são tocados).
3. Entre na sua conta do YouTube. O app percebe o login, exporta os cookies e fecha a janela.

Nas próximas vezes o login já estará salvo, e a exportação é imediata.

> Por que não ler o Chrome direto? Desde 2024, o Chrome, o Edge e o Brave criptografam os cookies no Windows (App-Bound Encryption). Só o próprio navegador consegue lê-los, por isso o app pede os cookies a ele.

**Com o Firefox:** escolha **Ler do navegador → Firefox**. Funciona mesmo com o Firefox aberto.

**Arquivo cookies.txt (manual):**
1. Abra uma **janela anônima**, entre no YouTube e acesse `youtube.com/robots.txt`.
2. Exporte com a extensão **Get cookies.txt LOCALLY**.
3. Feche a janela anônima.
4. No app, escolha **Arquivo cookies.txt**.

O app avisa quando o arquivo tem mais de 14 dias.

Use **Testar cookies** para ver quantos cookies foram lidos e se a conta está logada.

---

## 5. Celular sem cabo
O PC conversa com o celular pela rede Wi-Fi usando **FTP**. O celular vira um "servidor" e o MediaLoader envia só as músicas que faltam.

### 5.1 Preparar o celular (uma vez)
1. Instale o **Material Files**, gratuito e de código aberto (Play Store ou F-Droid). Qualquer app de "servidor FTP" serve, por exemplo o WiFi FTP Server.
2. Abra o Material Files → menu **☰** → **Servidor FTP** → **Iniciar**.
3. Anote o endereço que aparece, por exemplo `ftp://192.168.0.15:2121`. O IP é `192.168.0.15` e a porta é `2121`.
4. Nas opções do servidor, deixe o **acesso anônimo com permissão de escrita**, ou crie um usuário e uma senha.

### 5.2 Conectar no app
1. O **PC e o celular precisam estar na mesma rede Wi-Fi**. Redes "de convidados" costumam bloquear isso.
2. Na tela **Celular**, preencha o **IP**, a **porta** e, se tiver, o **usuário e a senha**.
3. Escolha a **pasta no celular**: normalmente `/Music`. Se ela não existir, o app cria.
4. Clique em **Testar conexão**. O app mostra quantas músicas já existem no celular.

### 5.3 Ver o que falta e enviar
1. Escolha a **origem**:
   - **Playlist atual**: a última carregada na tela Início.
   - **Playlist salva**: uma da tela Playlists.
   - **Pasta inteira do PC**.
2. Clique em **Comparar**. Cada música recebe uma etiqueta:
   - **NO CELULAR**: já está lá e não será enviada de novo.
   - **SÓ NO PC**: falta no celular. Vem marcada.
   - **FALTA NOS DOIS**: ainda não foi baixada.
3. Clique em **Enviar selecionadas**. Se marcar "Enviar também a playlist (.m3u8)", o player do celular mostra a playlist na ordem certa.

**Como o app sabe o que já está no celular** (mesmo nas músicas que você já tinha baixado por cabo):
- Pelo **nome do arquivo**, com a mesma comparação inteligente da tela Seleção: ignora maiúsculas, acentos, "(Official Video)" e o nome do artista no início.
- Depois do primeiro envio, por um registro exato (`.medialoader.json` na pasta do celular). Assim, mesmo que você renomeie o arquivo no celular, o app continua sabendo que ele já foi enviado.

### 5.4 Baixar direto para o celular (sem cabo)
- Na tela Celular, **Baixar faltantes e enviar** baixa no PC o que falta nos dois e envia logo em seguida.
- Para que **todo** download vá para o celular automaticamente, ligue em Configurações → Celular → **Enviar ao celular automaticamente depois de cada download**. Deixe o servidor FTP do celular ligado enquanto baixa.

O envio é seguro: cada música vai primeiro como `nome.part` e só é renomeada no fim. Se a conexão cair, não sobra arquivo quebrado no celular.

---

## 6. Problemas comuns

| Problema | Solução |
|---|---|
| **Celular:** "não respondeu" / "conexão recusada" | Confira se o servidor FTP está **ligado** no celular, se PC e celular estão no **mesmo Wi-Fi** e se o **IP mudou** (ele pode mudar ao reconectar). Na primeira vez, se o Windows perguntar sobre o Firewall, permita o MediaLoader. |
| **Celular:** usuário/senha recusados | Use o mesmo usuário e senha configurados no app do celular, ou ative o acesso anônimo. |
| **Cookies:** "App-Bound Encryption" | Use **Entrar no YouTube e exportar** ([seção 4](#4-cookies-conta-do-youtube)). |
| **Cookies:** "banco de cookies bloqueado" | Feche o navegador por completo (inclusive o ícone perto do relógio). |
| "Deno/EJS ausente" | `winget install DenoLand.Deno`, depois feche e abra o app. |
| "FFmpeg ausente" | `winget install Gyan.FFmpeg`, depois feche e abra o app. |
| HTTP 403 / "Signature solving failed" | Atualize o yt-dlp em **Diagnóstico → Ambiente**. |
| HTTP 429 / "not a bot" | Espere alguns minutos, use cookies e/ou ative o **limite de velocidade**. |
| Música aparece como **NA PASTA** sem estar | O nome do arquivo bate com o título. Marque-a manualmente na Seleção; o Diagnóstico mostra qual arquivo casou. |

---

## 7. Onde ficam os dados

| O quê | Instalador (.exe) | Script (Python) |
|---|---|---|
| Configurações, playlists salvas, cookies exportados | `%LOCALAPPDATA%\MediaLoader` | `python\data` |
| Logs dos downloads (30 dias) | `...\MediaLoader\logs` | `python\data\logs` |
| Histórico de renomeações (para desfazer) | `...\MediaLoader\rename_history.json` | `python\data\rename_history.json` |
| yt-dlp atualizado pelo app | `...\MediaLoader\lib` | via `pip` |
| Histórico de downloads (`.archive.txt`) e índice (`.library.json`) | dentro da pasta da biblioteca | dentro da pasta da biblioteca |

O arquivo de cookies dá acesso à sua conta do YouTube. **Não compartilhe** a pasta de dados.

---

## 8. Para desenvolvedores
```
python -m pip install -r requirements.txt
python -m pytest            # 100+ testes (inclui um servidor FTP local de teste)
```

Para gerar o instalador:
```
python -m pip install pyinstaller
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```
Saída: `dist\MediaLoader\MediaLoader.exe` (portátil) e `dist\MediaLoader-Setup.exe`.

Estrutura: `medialoader/` (núcleo) e `medialoader/ui/` (telas), com os testes em `tests/` e o build em `packaging/`. No executável, o yt-dlp fica como código-fonte em `_internal/vendor`, para poder ser atualizado pelo próprio app sem reinstalar.
