---
plugin: grill
version: 1.2.3
date: 2026-10-10
target: python/music.py
style: Quick review + plano de melhorias (implementado)
addons: []
agents: []
---

# MediaLoader Pro: análise e melhorias

## Escopo

Este relatório cobre `python/music.py` (2.584 linhas, uma classe só) e o estado real da pasta `Downloads_Playlist_HQ`. Todos os achados abaixo foram corrigidos na versão 2.0. O código antigo está preservado em `music_legacy.py`.

## Achados

| # | Sev. | Onde (versão antiga) | Problema | Situação |
|---|---|---|---|---|
| B1 | ALTA | `music.py:21,192` | A pasta de downloads era relativa ao diretório atual (CWD). Abrir por atalho criava uma pasta vazia e tudo aparecia como NOVO. | Corrigido: `config.APP_DIR`. Validado abrindo o app a partir de `C:\`. |
| B2 | ALTA | pasta | O archive tem 813 IDs e a pasta tem 1.483 áudios. O status e o Diagnóstico só olhavam o archive. | Corrigido: `library.py` combina archive, `.library.json` (id→arquivo) e o casamento de títulos com o disco. |
| B3 | ALTA | 1166 / 1850 | Os cookies do navegador eram relidos a cada música, os erros do Chrome/Edge (DPAPI, banco travado) só apareciam no meio do lote e não havia como testar. | Corrigido: `cookies.py` com "Testar", "Exportar → cookies.txt" (só domínios do YouTube/Google), perfil e mensagens traduzidas. Uma instância do YoutubeDL por lote. |
| B4 | ALTA | 1721 | Não havia como voltar à tela de Progresso. | Corrigido: item na sidebar com mini barra de progresso. |
| B5 | MÉDIA | — | Fechar a janela matava o download no meio. | Corrigido: confirmação, "parar agora" e espera de até 10 s. |
| B6 | MÉDIA | 1804/1853/1830 | Itens pulados eram contados como sucesso e o contador mostrava um item a mais. | Corrigido: status sucesso/pulado/falha por item. |
| B7 | MÉDIA | 1736 | Só existia "parar após a atual". | Corrigido: "Parar agora" via `DownloadCancelled` (testado: 3,3 s). |
| B8 | MÉDIA | pasta | 7 capas `.jpg/.webp` órfãs. O Renomeador não levava a capa junto. | Corrigido: conversão `before_dl`, limpeza de capas órfãs e renomeação da capa junto com o áudio. |
| B9 | MÉDIA | 1336 vs 2458 | Análise e Diagnóstico tinham fluxos e numeração diferentes. | Corrigido: `playlist.fetch_entries` único. |
| B10 | MÉDIA | 1326 | Vídeo avulso era rejeitado. | Corrigido. |
| B11 | BAIXA | 83 vs 117 | A heurística aceitava o travessão "–", mas a regex não. | Corrigido. |
| B12 | BAIXA | 2236 | Editar o nome de uma linha desmarcada não tinha efeito. | Corrigido: editar marca a linha. |
| B13 | BAIXA | 1700 | `deno --version` rodava na thread da UI. | Corrigido: verificação em thread, com cache. |
| B14 | BAIXA | `render_*` | Paginação destruía e recriava cerca de 50 widgets. | Corrigido: `RowPool`. Troca de página em cerca de 0,22 s. |
| B15 | BAIXA | `python/cookies.txt` | Arquivo de sessão solto ao lado do script. | Sinalizado na tela Configurações, com o botão "Mover para data/". |
| B16 | MÉDIA | `guess_rename_action` | "Música - Official Video" virava `Official Video.m4a` e "03 - Música" virava `03.m4a`. Há **6 arquivos** na pasta com nome destruído assim (`OFFICIAL VIDEO.m4a`, `Lyric Video.m4a`…). | Heurística corrigida. Os 6 arquivos precisam ser renomeados à mão (o título original está nos metadados do m4a). |

## O que foi entregue

- **Arquitetura**: pacote `medialoader/` com `config`, `theme`, `utils`, `rename_rules`, `errors`, `library`, `cookies`, `playlist`, `downloader` e `ui/` (uma tela por módulo).
- **Funcionalidades**:
  - Seletor de pasta.
  - Formato m4a, mp3 ou opus.
  - Template de nome (Título / NNN - Título / Canal - Título).
  - SponsorBlock (`music_offtopic`).
  - M3U em ordem.
  - Subpasta por playlist.
  - Busca e filtros por status.
  - "Baixar faltantes".
  - "Registrar 'na pasta' no histórico".
  - Tentar falhas de novo e exportar falhas.
  - Desfazer renomeação.
  - Atualizar o yt-dlp.
  - Histórico de URLs.
  - Configurações persistentes.
- **Interface**: tokens de tema dark + vermelho, sidebar com item ativo, cards, badges de status, toasts, log colorido e textos todos em PT-BR.
- **Testes**: 68 testes pytest (utils, rename_rules, library, cookies, config, downloader com YoutubeDL simulado).

## Verificação feita

- `python -m pytest tests -q`: 68 passed.
- App aberto a partir de `C:\` com navegação por todas as telas: 0 exceções.
- Download real de "Me at the zoo" em pasta temporária:
  - Saiu `001 - Me at the zoo.m4a` na subpasta.
  - AAC com capa e tags embutidas.
  - Item repetido marcado como "pulado".
  - M3U gerado.
- "Parar agora" testado com um vídeo de 3,5 min.
- Playlist pública de 182 vídeos lida em 1,6 s. O casamento de títulos foi ajustado depois de falsos positivos reais ("Stronger" × "Stronger Version").

## Não verificado / riscos restantes

- Os fluxos de cookies com navegador real (Firefox/Chrome) e a confirmação ao fechar foram verificados só por teste unitário e revisão de código. Falta testar no app.
- O casamento parcial de títulos ainda pode errar com títulos de uma palavra (ex.: "home"). Esses itens aparecem como **NA PASTA**, desmarcados, e o Diagnóstico mostra qual arquivo casou.
- Fora do escopo: thumbnails na lista, downloads paralelos e tema claro.

## Fixing Plan (pendências)

### Fase 4: limpeza oportunista
- **Achado B16**: renomear os 6 arquivos com nome genérico. É possível ler o título original com `ffprobe -show_entries format_tags=title`.
- **Achado B15**: mover `python/cookies.txt` para `python/data/` pelo botão em Configurações.
- **Legado**: apagar `music_legacy.py` depois de validar a nova versão.

---

# Fase 2 (2026-10-10): sincronização com o celular, playlists, manutenção e instalador

## Achados novos (com evidência)

| # | Sev. | Problema | Situação |
|---|---|---|---|
| F1 | ALTA | **55 arquivos com nome danificado** pela heurística antiga: o nome virou só a tag ou o artista (`OFFICIAL VIDEO.m4a`, `Linkin Park (14).m4a`, `Fruto Sagrado (Oficial) (2).m4a`…). | O título real está no metadado. A ação **Usar metadado** e o filtro **Nomes genéricos** do Renomeador recuperam todos (ex.: `Linkin Park (14).m4a` → `Papercut - Linkin Park.m4a`). |
| F2 | MÉDIA | Comparar só pelo nome agruparia versões diferentes como duplicatas (cover × original, `Linkin Park (N)` com durações parecidas). | As duplicatas usam o **título do metadado** e a duração ±2 s. Na biblioteca real, só 1 grupo legítimo (2 versões de vídeo de "Love Me to Death"). |
| F3 | MÉDIA | Chrome/Edge/Brave (App-Bound Encryption) bloqueiam a leitura de cookies pelo yt-dlp. | Exportação assistida via DevTools num perfil exclusivo (já validada pelo usuário). |
| F4 | BAIXA | O yt-dlp desatualiza rápido, e o .exe não tem pip. | O app checa o PyPI ao abrir. No .exe, atualiza baixando o wheel e conferindo o sha256 em `%LOCALAPPDATA%\MediaLoader\lib`, que tem prioridade sobre a versão embutida. |

## Entregue
- **Celular (Android, Wi-Fi/FTP)**: `phone.py` e a tela Celular.
  - Testar conexão e comparar (playlist atual, playlist salva ou pasta inteira).
  - Envio via `.part` → renomear, com cancelamento.
  - Manifesto `.medialoader.json` no celular e `.m3u8` da playlist.
  - "Baixar faltantes e enviar" e envio automático após cada download.
- **Playlists salvas**: `playlists.py` e a tela Playlists. "Verificar todas" e "Sincronizar tudo" usam uma fila de lotes (uma playlist por vez).
- **Renomeador**: ações "Remover tags" e "Usar metadado", filtro "Nomes genéricos", localizar/substituir (texto ou regex), ação em massa e prévia em verde.
- **Diagnóstico → Biblioteca**: duplicatas, órfãos (contra as playlists salvas), "Mover para a Lixeira" (recuperável, `SHFileOperationW` + `FOF_ALLOWUNDO`) e atalho para os nomes danificados.
- **Qualidade de vida**:
  - Notificação do Windows ao fim do lote (se a janela estiver sem foco) e log em arquivo com rotação de 30 dias.
  - Limite de velocidade e aviso de nova versão do yt-dlp.
  - Botão "Ajuda / manual".
- **Executável e instalador**: `packaging/` (`make_icon.py`, `medialoader.spec`, `installer.iss`, `build.ps1`) e o modo `--self-test`.
- **README.md** completo em PT-BR (instalação, telas, cookies, celular sem cabo, problemas comuns).
- **Refatoração**: `matching.py` (`TitleMatcher`), compartilhado entre PC e celular.

## Verificação feita
- `python -m pytest`: **100 testes passando**, incluindo um servidor FTP real local (pyftpdlib) com nomes Unicode e m4a reais gerados com ffmpeg.
- UI: smoke test sem exceções. Fluxo do Celular dentro do app contra o FTP local: conectou, comparou 1.488 arquivos e enviou 2 músicas com manifesto.
- **Executável**:
  - `MediaLoader.exe --self-test`: yt-dlp carregado de `_internal\vendor`, download real OK.
  - Após atualização por wheel, carregado de `lib\` e download OK.
  - Primeira execução pede a pasta da biblioteca.
- **Instalador** (17 MB): instalação silenciosa criou os arquivos e os atalhos; a desinstalação removeu tudo e preservou os dados.

## Não verificado
- Envio para um **celular Android de verdade**: foi testado com um servidor FTP local que simula o celular. Precisa de teste com o Material Files no aparelho.
- Notificação toast do Windows (é feita em melhor esforço; a barra de tarefas piscando é a garantia).

## Pendências
- Aplicar os 55 renomeios sugeridos (filtro "Nomes genéricos" → revisar → Aplicar).
- Testar a sincronização com o celular real ([README, seção 5](README.md#5-celular-sem-cabo)).
