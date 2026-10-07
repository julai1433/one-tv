# Servidor de prueba aislado: otro puerto, copia de los datos, sin Roku.
# Uso: CINE_PRUEBA=/carpeta CINE_PUERTO=8791 python3 pruebas/servidor_de_prueba.py
# No arranca las tareas automáticas del servicio: el organizador movería archivos de la biblioteca real
# y el actualizador tocaría el yt-dlp del servicio (de eso se encarga solo el servicio de verdad).
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
# Copia de los datos en una carpeta aparte (por omisión /tmp/cine-prueba): copia ahí «datos» antes de arrancar.
BASE = Path(os.environ.get("CINE_PRUEBA", "/tmp/cine-prueba"))
PORT = int(os.environ.get("CINE_PUERTO", "8790"))
cine.CACHE = BASE / "cache"; cine.DATA = BASE / "datos"
original = cine.load_config
def config():
    c = original(); c["puerto"] = PORT; return c
cine.load_config = config
cine.App.connect_roku = lambda self, force=False: False
cine.App.watch_roku = lambda self: None
cine.App.keep_library_fresh = lambda self: None
cine.App.watch_downloads = lambda self: None   # tampoco mira las Descargas reales
cine.App.keep_account_fresh = lambda self: None
cine.App.keep_avatars = lambda self: None
cine.App.keep_ytdlp_fresh = lambda self: None
cine.App.warm_up = lambda self: None
import intro; intro.IntroDetector.watch = lambda self, library: None   # la detección de entradas
import subsync; subsync.SubtitleAligner.watch = lambda self, library: None   # ni la de subtítulos
os.environ["CINE_NO_BROWSER"] = "1"
cine.run_server(background=True)
