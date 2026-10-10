"""Tradução de erros conhecidos do yt-dlp para mensagens acionáveis."""

# (trechos que precisam aparecer na mensagem, texto amigável)
# A ordem importa: o primeiro padrão que casar vence.
_KNOWN_ERRORS = (
    (("could not copy", "cookie database"),
     "O banco de cookies do navegador está bloqueado. Feche o navegador por "
     "completo (inclusive na bandeja do sistema) e tente de novo."),
    (("dpapi",),
     "Chrome/Edge/Brave no Windows protegem os cookies com App-Bound "
     "Encryption, e o yt-dlp não consegue lê-los do disco. Use o botão "
     "'Entrar no YouTube e exportar' (o próprio navegador entrega os "
     "cookies), o Firefox ou um cookies.txt."),
    (("app-bound",),
     "Chrome/Edge/Brave no Windows protegem os cookies com App-Bound "
     "Encryption, e o yt-dlp não consegue lê-los do disco. Use o botão "
     "'Entrar no YouTube e exportar' (o próprio navegador entrega os "
     "cookies), o Firefox ou um cookies.txt."),
    (("does not support profiles",),
     "Esse navegador não aceita perfil. Deixe o campo de perfil vazio."),
    (("could not find", "cookies database"),
     "Banco de cookies não encontrado. Confira se o navegador está "
     "instalado e se o nome do perfil está certo."),
    (("netscape",),
     "O cookies.txt precisa estar no formato Netscape (não JSON). Exporte "
     "com uma extensão como 'Get cookies.txt LOCALLY'."),
    (("sign in to confirm",),
     "O YouTube pediu verificação de que você não é um robô. Use cookies "
     "de uma conta logada."),
    (("signature solving failed",),
     "O desafio JavaScript do YouTube não foi resolvido. Confirme que o "
     "Deno e o yt-dlp-ejs estão instalados e atualize o yt-dlp."),
    (("n challenge solving failed",),
     "O desafio JavaScript do YouTube não foi resolvido. Confirme que o "
     "Deno e o yt-dlp-ejs estão instalados e atualize o yt-dlp."),
    (("page needs to be reloaded",),
     "O YouTube pediu para recarregar a página. Atualize o yt-dlp e tente "
     "de novo."),
    (("private video",),
     "Vídeo privado: só a conta dona (via cookies) pode baixar."),
    (("age-restricted",),
     "Vídeo com restrição de idade: use cookies de uma conta logada."),
    (("confirm your age",),
     "Vídeo com restrição de idade: use cookies de uma conta logada."),
    (("members-only",),
     "Conteúdo exclusivo para membros do canal."),
    (("video unavailable",),
     "Vídeo indisponível (removido ou bloqueado na sua região)."),
    (("http error 403",),
     "O YouTube recusou o download (HTTP 403). Atualize o yt-dlp ou use "
     "cookies."),
    (("http error 429",),
     "Muitas requisições (HTTP 429). Espere alguns minutos ou use cookies."),
    (("requested format is not available",),
     "O formato pedido não está disponível para este vídeo."),
    (("ffmpeg not found",),
     "FFmpeg não encontrado. Instale com: winget install Gyan.FFmpeg"),
    (("ffprobe and ffmpeg not found",),
     "FFmpeg não encontrado. Instale com: winget install Gyan.FFmpeg"),
)


def friendly_error(message):
    """Retorna a explicação amigável para o erro, ou None se desconhecido."""
    lower = str(message or "").lower()
    for needles, text in _KNOWN_ERRORS:
        if all(needle in lower for needle in needles):
            return text
    return None
