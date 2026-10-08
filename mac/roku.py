"""Todo lo que habla con el Roku: encontrarlo en la red, instalarle la app
(modo desarrollador) y mandarle órdenes por ECP, el control remoto por red
que traen todos los Roku en el puerto 8060."""

import hashlib
import io
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

ECP_PORT = 8060


def discover(timeout=3):
    """Busca un Roku en la red local (SSDP). Devuelve su IP o None."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\n"
           'Man: "ssdp:discover"\r\nST: roku:ecp\r\nMX: 2\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    try:
        for _ in range(2):
            s.sendto(msg, ("239.255.255.250", 1900))
    except OSError:
        # «No route to host»: sin red, o macOS aún no le da a este Python el permiso de «Red local».
        s.close()
        return None
    try:
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = s.recvfrom(2048)
            except (socket.timeout, ConnectionResetError):   # (Windows avisa así de un paquete que no llegó)
                continue
            m = re.search(rb"(?i)LOCATION:\s*http://([\d.]+):8060", data)
            if m:
                return m.group(1).decode()
    finally:
        s.close()
    return None


def local_ip_towards(ip):
    """La IP de esta Mac en la red donde está el Roku."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, ECP_PORT))
        return s.getsockname()[0]
    finally:
        s.close()


class Roku:
    def __init__(self, ip, dev_password=""):
        self.ip = ip
        self.dev_password = dev_password

    def _ecp(self, method, path, timeout=5):
        req = urllib.request.Request(f"http://{self.ip}:{ECP_PORT}{path}", method=method,
                                     data=b"" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def device_name(self):
        xml = self._ecp("GET", "/query/device-info")
        m = re.search(r"<friendly-device-name>([^<]*)<", xml)
        return m.group(1) if m else "Roku"

    def active_app(self):
        return self._active()[0]

    def _active(self):
        """(id, tipo) de lo que se ve en la tele; tipo 'home' es la pantalla de inicio."""
        xml = self._ecp("GET", "/query/active-app")
        m = re.search(r'<app id="([^"]*)"(?: type="([^"]*)")?', xml)
        return (m.group(1), m.group(2) or "") if m else ("", "")

    def play(self, content_id, server_url, **options):
        """Abre la app y reproduce ese video (options: audio, sub, start).
        Si la app ya está abierta, se lo manda directo."""
        params = {"contentId": content_id, "mediaType": "movie", "server": server_url}
        params.update({k: v for k, v in options.items() if v is not None})
        q = urllib.parse.urlencode(params)
        if self.active_app() == "dev":
            self._ecp("POST", f"/input?{q}")
        else:
            self._ecp("POST", f"/launch/dev?{q}")

    def send(self, **params):
        """Orden para la app ya abierta (cambiar pistas, saltar a un punto...)."""
        self._ecp("POST", "/input?" + urllib.parse.urlencode(params))

    def show_code(self, code, server_url=""):
        """Muestra en la TV el código para cambiar la configuración desde otro aparato (mac/asistente.py). Si One TV no
        está abierta, la abre: quien lo pidió está frente a la TV esperándolo."""
        params = {"cmd": "codigo", "codigo": code}
        if self.active_app() == "dev":
            self._ecp("POST", "/input?" + urllib.parse.urlencode(params))
        else:
            if server_url:
                params["server"] = server_url
            self._ecp("POST", "/launch/dev?" + urllib.parse.urlencode(params))

    def player(self):
        """Estado del reproductor según el propio Roku: (estado, posición s, duración s)."""
        xml = self._ecp("GET", "/query/media-player", timeout=2)
        state = re.search(r'<player state="([^"]*)"', xml)
        pos = re.search(r"<position>(\d+) ms", xml)
        dur = re.search(r"<duration>(\d+) ms", xml)
        return (state.group(1) if state else "", int(pos.group(1)) / 1000 if pos else None,
                int(dur.group(1)) / 1000 if dur else None)

    def key(self, name):
        self._ecp("POST", f"/keypress/{urllib.parse.quote(name)}")

    # ---------- instalar la app ----------

    def install(self, zip_bytes):
        """Instala la app. Instalar la abre sola en la tele: después se vuelve a lo que se estaba viendo."""
        try:
            before = self._active()
        except OSError:
            before = ("", "")
        ok, msg = self._upload(zip_bytes)
        if ok and msg == "app instalada" and before[0] and before[0] != "dev":
            time.sleep(3)
            try:
                if before[1] == "home":
                    self.key("Home")
                else:
                    self._ecp("POST", f"/launch/{before[0]}")
            except OSError:
                pass
        return ok, msg

    def _digest_auth(self, method, url):
        """Cabecera Authorization (digest) armada de antemano con el reto de una petición vacía, para mandar
        el .zip una sola vez y ya autenticado. Sin esto el .zip viaja primero sin clave, el Roku contesta 401 y
        corta la conexión a la mitad: con una app de más de ~100 KB falla con «Broken pipe». None si no hace falta."""
        try:
            urllib.request.urlopen(url, timeout=10).close()
            return None
        except urllib.error.HTTPError as e:
            if e.code != 401:
                return None
            challenge = e.headers.get("WWW-Authenticate", "")
        except OSError:
            return None
        fields = dict(re.findall(r'(\w+)="?([^",]*)"?', challenge))
        realm, nonce = fields.get("realm", ""), fields.get("nonce", "")
        uri = urllib.parse.urlsplit(url).path
        ha1 = hashlib.md5(f"rokudev:{realm}:{self.dev_password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        head = f'Digest username="rokudev", realm="{realm}", nonce="{nonce}", uri="{uri}"'
        if "opaque" in fields:
            head += f', opaque="{fields["opaque"]}"'
        if "auth" in fields.get("qop", "").split(","):
            nc, cnonce = "00000001", uuid.uuid4().hex[:16]
            response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}".encode()).hexdigest()
            return head + f', response="{response}", qop=auth, nc={nc}, cnonce="{cnonce}"'
        return head + f', response="{hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()}"'

    def _upload(self, zip_bytes):
        """Sube el .zip de la app al instalador del modo desarrollador. Devuelve (ok, mensaje)."""
        boundary = uuid.uuid4().hex
        body = io.BytesIO()
        for name, value in (("mysubmit", "Install"),):
            body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="archive"; filename="cine.zip"\r\n'
                   "Content-Type: application/zip\r\n\r\n".encode())
        body.write(zip_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        url = f"http://{self.ip}/plugin_install"
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, "rokudev", self.dev_password)
        opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        auth = self._digest_auth("POST", url)
        if auth:
            headers["Authorization"] = auth
        req = urllib.request.Request(url, data=body.getvalue(), method="POST", headers=headers)
        try:
            with opener.open(req, timeout=60) as r:
                html = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "contraseña del modo desarrollador incorrecta (revisa config.json)"
            return False, f"el Roku respondió HTTP {e.code}"
        except OSError as e:
            return False, f"no se pudo conectar al instalador del Roku ({e}). ¿Está activo el modo desarrollador?"
        if "Identical to previous version" in html:
            return True, "la app ya estaba instalada y al día"
        if "Install Success" in html or "Application Received" in html:
            return True, "app instalada"
        m = re.search(r"Install Failure[^<\"]*", html)
        return False, m.group(0) if m else "respuesta inesperada del instalador"


def build_channel_zip(channel_dir, server_url):
    """Empaqueta la carpeta roku/ con la dirección del servidor escrita en el manifest."""
    channel_dir = Path(channel_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(channel_dir.rglob("*")):
            if f.is_dir() or f.name.startswith("."):
                continue
            rel = f.relative_to(channel_dir).as_posix()
            data = f.read_bytes()
            if rel == "manifest":
                text = re.sub(r"(?m)^server_url=.*$", f"server_url={server_url}", data.decode())
                data = text.encode()
            # Fecha fija: si nada cambió, el zip es idéntico y el Roku no reinstala.
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()
