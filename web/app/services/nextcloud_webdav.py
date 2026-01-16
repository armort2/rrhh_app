from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class NextcloudConfig:
    webdav_url: str      # ej: https://cloud.tld/remote.php/dav/files/usuario
    username: str
    password: str        # ideal: App Password


class NextcloudWebDAV:
    """
    Cliente WebDAV minimalista para Nextcloud:
    - exists(path): PROPFIND Depth:0
    - ensure_dir(path): crea directorios faltantes con MKCOL (cascada)
    - upload_file(local_path, remote_dir, remote_filename)
    """

    def __init__(self, cfg: NextcloudConfig, timeout: int = 30):
        if not cfg.webdav_url or not cfg.username or not cfg.password:
            raise ValueError("NextcloudWebDAV: faltan credenciales o URL WebDAV (revisar config/env).")

        self.cfg = cfg
        self.timeout = timeout

        self.session = requests.Session()
        self.session.auth = (cfg.username, cfg.password)
        self.session.headers.update({"User-Agent": "GrupoCS-RRHH/1.0"})

    def _url_for(self, remote_path: str) -> str:
        """
        Construye URL final. remote_path es relativo a la raíz webdav (sin slash inicial obligatorio).
        Se encodea por segmentos para respetar espacios y caracteres especiales.
        """
        base = self.cfg.webdav_url.rstrip("/")
        cleaned = remote_path.strip("/")

        # Encode por segmento para permitir '/' como separador real
        segments = [quote(seg, safe="") for seg in cleaned.split("/") if seg]
        if segments:
            return f"{base}/" + "/".join(segments)
        return base

    def exists(self, remote_path: str) -> bool:
        url = self._url_for(remote_path)
        headers = {"Depth": "0"}

        resp = self.session.request("PROPFIND", url, headers=headers, timeout=self.timeout)
        if resp.status_code in (200, 207):
            return True
        if resp.status_code == 404:
            return False

        raise RuntimeError(f"Nextcloud exists() inesperado {resp.status_code}: {resp.text[:300]}")

    def mkdir(self, remote_dir: str) -> None:
        """
        Crea un directorio (MKCOL). Si ya existe, no falla.
        """
        url = self._url_for(remote_dir)
        resp = self.session.request("MKCOL", url, timeout=self.timeout)

        if resp.status_code in (201, 200, 204):  # creado / ok
            return
        if resp.status_code == 405:
            # 405 Method Not Allowed: suele significar "ya existe"
            return
        if resp.status_code == 409:
            raise RuntimeError(
                "No se pudo crear carpeta (409 Conflict). "
                "Generalmente falta una carpeta padre. Use ensure_dir()."
            )

        raise RuntimeError(f"Nextcloud mkdir() error {resp.status_code}: {resp.text[:300]}")

    def ensure_dir(self, remote_dir: str) -> None:
        """
        Crea directorios faltantes en cascada.
        Ej: 'A/B/C' crea A, luego A/B, luego A/B/C si no existen.
        """
        cleaned = remote_dir.strip("/")
        if not cleaned:
            return

        parts = cleaned.split("/")
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            if not self.exists(cur):
                self.mkdir(cur)

    def upload_file(self, local_path: Path, remote_dir: str, remote_filename: Optional[str] = None) -> str:
        """
        Sube un archivo local a remote_dir/remote_filename (PUT).
        Retorna la ruta remota (relativa) final.
        """
        if not local_path.exists():
            raise FileNotFoundError(f"Archivo local no existe: {local_path}")

        remote_filename = remote_filename or local_path.name
        remote_dir_clean = remote_dir.strip("/")
        remote_path = f"{remote_dir_clean}/{remote_filename}" if remote_dir_clean else remote_filename

        # Aseguramos carpeta
        if remote_dir_clean:
            self.ensure_dir(remote_dir_clean)

        url = self._url_for(remote_path)

        with open(local_path, "rb") as f:
            resp = self.session.put(url, data=f, timeout=self.timeout)

        if resp.status_code in (200, 201, 204):
            return remote_path

        raise RuntimeError(f"Nextcloud upload_file() error {resp.status_code}: {resp.text[:300]}")
