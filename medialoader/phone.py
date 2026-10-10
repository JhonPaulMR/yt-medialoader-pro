"""
Sincronização com o celular (Android) pelo Wi-Fi, via FTP.

O celular roda um servidor FTP (ex.: Material Files → "Servidor FTP").
O app lista a pasta de músicas do celular, descobre o que já está lá
(manifesto .medialoader.json + nome do arquivo) e envia só o que falta.
"""

import ftplib
import io
import json
import os
import posixpath
import socket
from dataclasses import dataclass
from datetime import datetime

from .config import SUPPORTED_MEDIA_EXTS
from .matching import TitleMatcher

MANIFEST_NAME = ".medialoader.json"
ON_PHONE = "on_phone"
ONLY_PC = "only_pc"
MISSING = "missing"

STATUS_LABELS = {ON_PHONE: "NO CELULAR", ONLY_PC: "SÓ NO PC", MISSING: "FALTA NOS DOIS"}


class UploadCancelled(Exception):
    pass


@dataclass
class PhoneConfig:
    host: str = ""
    port: int = 2121
    user: str = ""
    password: str = ""
    folder: str = "/Music"

    @classmethod
    def from_settings(cls, settings):
        try:
            port = int(str(settings.phone_port).strip() or 2121)
        except ValueError:
            port = 2121
        return cls(settings.phone_host.strip(), port, settings.phone_user.strip(),
                   settings.phone_password, settings.phone_folder.strip() or "/Music")

    def validate(self):
        if not self.host:
            raise ValueError("Informe o endereço IP do celular (aparece no app de servidor FTP).")
        if not 1 <= self.port <= 65535:
            raise ValueError("Porta inválida.")


def _friendly_ftp_error(exc, config):
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (f"O celular não respondeu em {config.host}:{config.port}. Confira se o servidor FTP está "
                "ligado, se o PC e o celular estão no mesmo Wi-Fi e se o IP não mudou.")
    if isinstance(exc, ConnectionRefusedError):
        return f"Conexão recusada em {config.host}:{config.port}: o servidor FTP do celular está desligado ou a porta está errada."
    if isinstance(exc, socket.gaierror):
        return f"Endereço inválido: {config.host}."
    if isinstance(exc, ftplib.error_perm) and str(exc).startswith("530"):
        return "Usuário ou senha recusados pelo servidor FTP do celular."
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10060, 10065, 10051):
        return (f"Não foi possível alcançar {config.host}. PC e celular precisam estar na mesma rede Wi-Fi "
                "(redes de convidados costumam isolar os aparelhos).")
    return str(exc)


class PhoneClient:
    def __init__(self, config, timeout=15):
        self.config = config
        self.timeout = timeout
        self.ftp = None
        self.root = None

    # ---------------- conexão ----------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def connect(self):
        self.config.validate()
        ftp = ftplib.FTP()
        ftp.encoding = "utf-8"
        try:
            ftp.connect(self.config.host, self.config.port, timeout=self.timeout)
            ftp.login(self.config.user or "anonymous", self.config.password or "")
        except Exception as exc:
            raise ConnectionError(_friendly_ftp_error(exc, self.config)) from exc
        try:
            ftp.sendcmd("OPTS UTF8 ON")
        except ftplib.all_errors:
            pass
        self.ftp = ftp
        self.root = self._ensure_dir(self.config.folder)

    def close(self):
        if self.ftp is not None:
            try:
                self.ftp.quit()
            except ftplib.all_errors:
                self.ftp.close()
            self.ftp = None

    def _ensure_dir(self, path):
        """Entra na pasta, criando os níveis que faltarem. Retorna o caminho absoluto."""
        path = "/" + path.strip("/") if path.strip("/") else "/"
        self.ftp.cwd("/")
        for part in [p for p in path.split("/") if p]:
            try:
                self.ftp.cwd(part)
            except ftplib.error_perm:
                self.ftp.mkd(part)
                self.ftp.cwd(part)
        return self.ftp.pwd()

    def _remote(self, rel):
        return posixpath.join(self.root, rel)

    # ---------------- leitura ----------------
    def list_audio(self, max_depth=3):
        """Arquivos de áudio da pasta (caminhos relativos, com subpastas)."""
        found = []

        def walk(directory, rel_prefix, depth):
            try:
                entries = list(self.ftp.mlsd(directory, facts=["type"]))
                for name, facts in entries:
                    if name in (".", ".."):
                        continue
                    rel = f"{rel_prefix}{name}"
                    if facts.get("type") == "dir":
                        if depth < max_depth and not name.startswith("."):
                            walk(posixpath.join(directory, name), rel + "/", depth + 1)
                    elif name.lower().endswith(SUPPORTED_MEDIA_EXTS):
                        found.append(rel)
            except ftplib.error_perm:
                # Servidor sem MLSD: lista só o nível atual.
                for name in self.ftp.nlst(directory):
                    name = posixpath.basename(name)
                    if name.lower().endswith(SUPPORTED_MEDIA_EXTS):
                        found.append(f"{rel_prefix}{name}")

        walk(self.root, "", 0)
        return sorted(found, key=str.lower)

    def read_manifest(self):
        buffer = io.BytesIO()
        try:
            self.ftp.retrbinary(f"RETR {self._remote(MANIFEST_NAME)}", buffer.write)
            data = json.loads(buffer.getvalue().decode("utf-8"))
        except (ftplib.error_perm, ValueError):
            return {"ids": {}, "files": {}}
        return {"ids": dict(data.get("ids") or {}), "files": dict(data.get("files") or {})}

    def write_manifest(self, manifest):
        manifest = dict(manifest, updated=datetime.now().isoformat(timespec="seconds"))
        payload = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
        self.ftp.storbinary(f"STOR {self._remote(MANIFEST_NAME)}", io.BytesIO(payload))

    # ---------------- escrita ----------------
    def upload(self, local_path, remote_rel, progress=None, cancel=None):
        """Envia para <nome>.part e renomeia no fim: nada fica pela metade no celular."""
        remote_dir = posixpath.dirname(remote_rel)
        if remote_dir:
            self._ensure_dir(posixpath.join(self.config.folder, remote_dir))
            self.ftp.cwd(self.root)
        final = self._remote(remote_rel)
        partial = final + ".part"
        total = os.path.getsize(local_path) or 1
        sent = [0]

        def on_block(block):
            if cancel is not None and cancel.is_set():
                raise UploadCancelled()
            sent[0] += len(block)
            if progress:
                progress(sent[0] / total)

        with open(local_path, "rb") as file:
            try:
                self.ftp.storbinary(f"STOR {partial}", file, blocksize=65536, callback=on_block)
            except UploadCancelled:
                try:
                    self.ftp.abort()
                except ftplib.all_errors:
                    pass
                self._safe_delete(partial)
                raise
        try:
            self.ftp.delete(final)  # alguns servidores não sobrescrevem no RNTO
        except ftplib.error_perm:
            pass
        self.ftp.rename(partial, final)

    def upload_bytes(self, data, remote_rel):
        self.ftp.storbinary(f"STOR {self._remote(remote_rel)}", io.BytesIO(data))

    def _safe_delete(self, remote):
        try:
            self.ftp.delete(remote)
        except ftplib.all_errors:
            pass


# ================================================================
# COMPARAÇÃO
# ================================================================
def compare_entries(entries, phone_files, manifest, library):
    """Itens de uma playlist × celular. Usa o manifesto (exato) e depois o título."""
    phone_set = set(phone_files)
    matcher = TitleMatcher(phone_files)
    ids = manifest.get("ids", {})
    items = []
    for entry in entries:
        remote = ids.get(entry.get("id"))
        if remote not in phone_set:
            remote = matcher.match(entry.get("title"))
        local = library.path_for(entry)
        if local and not library.file_exists(local):
            local = None
        if remote:
            status = ON_PHONE
        elif local:
            status = ONLY_PC
        else:
            status = MISSING
        items.append({"entry": entry, "status": status, "remote": remote, "local": local,
                      "title": entry.get("title") or "", "position": entry.get("position")})
    return items


def compare_files(local_files, phone_files, manifest):
    """Pasta inteira do PC × celular (pelo nome do arquivo)."""
    phone_set = set(phone_files)
    matcher = TitleMatcher(phone_files)
    known = manifest.get("files", {})
    items = []
    for rel in local_files:
        remote = known.get(rel)
        if remote not in phone_set:
            remote = matcher.match_file(rel)
        items.append({"entry": None, "status": ON_PHONE if remote else ONLY_PC, "remote": remote,
                      "local": rel, "title": os.path.splitext(os.path.basename(rel))[0], "position": None})
    return items


def m3u_for_phone(entries, remote_for):
    """Conteúdo .m3u8 (ordem da playlist) apontando para os arquivos do celular."""
    lines = ["#EXTM3U"]
    for entry in sorted(entries, key=lambda e: e.get("position") or 0):
        remote = remote_for(entry)
        if remote:
            lines.append(f"#EXTINF:{int(entry.get('duration') or -1)},{entry.get('title') or ''}")
            lines.append(remote)
    return ("\n".join(lines) + "\n") if len(lines) > 1 else None
