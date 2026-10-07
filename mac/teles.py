"""Las TV que la computadora maneja: el Roku (por su control remoto de red, mac/roku.py) y las TV con Android
(Google TV, Android TV y Fire TV, app en androidtv/).

Una TV con Android no tiene un control remoto de red como el Roku: mientras One TV está abierta en ella, la app deja
una consulta esperando en el servidor (GET /api/tv/ordenes, hasta ESPERA segundos). El servidor la contesta en cuanto
hay una orden para esa TV (o vacía al vencer) y la app vuelve a preguntar. Así el servidor sabe qué TV están
«conectadas» y les manda lo mismo que al Roku: ver algo, pausa, avanzar, pistas, canción anterior o siguiente, salir y
«actualiza».

¿A cuál TV va «Ver en la TV»? A la que se usó por última vez: la que empezó a reproducir algo más recientemente, la
que se acaba de abrir o la que se eligió en la web. Si solo hay una, a esa. Con solo un Roku todo sigue igual que antes.
"""

import collections
import itertools
import re
import threading
import time

ESPERA = 25          # segundos que la consulta de la TV se queda esperando antes de contestar vacía
GRACIA = 15          # sin consulta esperando, una TV sigue «conectada» este tiempo (lo que tarda en volver a preguntar)
VIDA_ORDEN = 30      # una orden que la TV no recogió en este tiempo ya no vale (se cerró la app o se apagó)
MAX_TELES = 12       # TV con Android recordadas a la vez (las más viejas desconectadas se olvidan)
MAX_ORDENES = 20     # órdenes en espera por TV
ROKU = "roku"        # el id del Roku en la lista de TV
NOMBRE_ANDROID = "TV con Android"
_ID = re.compile(r"[\w.:-]{1,80}")


def limpiar_nombre(nombre):
    """El nombre que la TV dice de sí misma, corto y sin saltos de línea."""
    nombre = " ".join(str(nombre or "").split())[:40]
    return nombre or NOMBRE_ANDROID


class SinTele(OSError):
    """La TV con Android ya no pregunta (se cerró One TV o se apagó): como cuando el Roku no responde."""


class AndroidTv:
    """Una TV con Android con One TV abierta. Recibe las mismas órdenes que el Roku (mac/roku.py: play, send y key),
    así el resto del servidor las manda igual a una o a otra."""

    def __init__(self, teles, device_id, nombre):
        self.teles = teles
        self.id = device_id
        self.nombre = nombre

    def play(self, content_id, server_url=None, **options):
        """Ver algo: el id de una película o episodio, «yt:<video>», «music:<sesión>» o «live:<canal>»
        (options: audio, sub, start). Como el Roku con la app abierta."""
        orden = {"cmd": "play", "contentId": content_id}
        orden.update({k: v for k, v in options.items() if v is not None})
        self.teles.mandar(self.id, orden)

    def send(self, **params):
        """Orden para lo que se ve: cmd = tracks (audio, sub), seek (t), song (dir) o refresh."""
        self.teles.mandar(self.id, {k: v for k, v in params.items() if v is not None})

    def key(self, name):
        """Una tecla del control con los nombres del Roku (Play, Back, Fwd, Rev…)."""
        self.teles.mandar(self.id, {"cmd": "key", "key": name})

    def active_app(self):
        return "dev"   # si está conectada, One TV está abierta (como el Roku con la app de One TV a la vista)

    def player(self):
        return None    # la posición la cuentan sus reportes (/api/progress)


class Teles:
    def __init__(self, reloj=time.monotonic):
        self._cond = threading.Condition()
        self._reloj = reloj
        # device_id -> {"nombre", "visto", "esperando", "turno", "ordenes": deque[(cuándo, orden)]}
        self._tv = collections.OrderedDict()
        self._usada = {}   # id (ROKU o el de una TV con Android) -> turno en que se usó, se abrió o se eligió por última vez
        # Un contador y no la hora: en Windows el reloj avanza a saltos de ~15 ms y dos elecciones seguidas empataban
        # (y ganaba el Roku).
        self._turno = itertools.count(1)
        self.vistas = False   # alguna vez se conectó una TV con Android (cambia el mensaje «No encontré el Roku»)

    # ---------- la TV con Android pregunta ----------

    def esperar(self, device_id, nombre="", espera=ESPERA):
        """La consulta de la TV: devuelve las órdenes que haya (o que lleguen antes de `espera` segundos) o []."""
        if not _ID.fullmatch(str(device_id or "")):
            return []
        fin = time.monotonic() + max(0.0, float(espera))
        with self._cond:
            t = self._registrar(device_id, nombre)
            t["turno"] += 1   # una consulta nueva de la misma TV suelta a la anterior (quizá quedó colgada)
            turno = t["turno"]
            t["esperando"] += 1
            self._cond.notify_all()
            try:
                while True:
                    self._vencer(t)
                    if t["turno"] != turno:
                        return []
                    if t["ordenes"]:
                        out = [o for _, o in t["ordenes"]]
                        t["ordenes"].clear()
                        return out
                    falta = fin - time.monotonic()
                    if falta <= 0:
                        return []
                    self._cond.wait(falta)
            finally:
                t["esperando"] -= 1
                if not t.get("adios"):   # se despidió mientras esperaba: ya no cuenta como conectada
                    t["visto"] = self._reloj()

    def devolver(self, device_id, ordenes):
        """No se pudo entregar la respuesta (se cortó la conexión): las órdenes vuelven al frente para la próxima."""
        with self._cond:
            t = self._tv.get(device_id)
            if not t:
                return
            for o in reversed(ordenes):
                t["ordenes"].appendleft((self._reloj(), o))
            self._cond.notify_all()

    def adios(self, device_id):
        """La app se cerró o se fue al fondo: esa TV deja de estar conectada ya (sin esperar a que venza)."""
        with self._cond:
            t = self._tv.get(device_id)
            if t:
                t["turno"] += 1
                t["visto"] = self._reloj() - GRACIA - 1
                t["adios"] = True
                self._cond.notify_all()

    def _registrar(self, device_id, nombre):
        t = self._tv.get(device_id)
        if t is None:
            t = {"nombre": NOMBRE_ANDROID, "visto": self._reloj(), "esperando": 0, "turno": 0,
                 "ordenes": collections.deque(maxlen=MAX_ORDENES)}
            self._tv[device_id] = t
            self._usada[device_id] = next(self._turno)   # recién abierta: es la que se está usando
            self._olvidar_viejas()
        elif t.pop("adios", False) or not self._conectada(t):
            self._usada[device_id] = next(self._turno)   # se volvió a abrir
            t["ordenes"].clear()
        if nombre:
            t["nombre"] = limpiar_nombre(nombre)
        self.vistas = True
        return t

    def _olvidar_viejas(self):
        while len(self._tv) > MAX_TELES:
            vieja = next((k for k, v in self._tv.items() if not self._conectada(v)), None)
            if vieja is None:
                break
            del self._tv[vieja]
            self._usada.pop(vieja, None)

    def _vencer(self, t):
        ahora = self._reloj()
        while t["ordenes"] and ahora - t["ordenes"][0][0] > VIDA_ORDEN:
            t["ordenes"].popleft()

    def _conectada(self, t):
        return t["esperando"] > 0 or self._reloj() - t["visto"] < GRACIA

    # ---------- mandar órdenes ----------

    def mandar(self, device_id, orden):
        with self._cond:
            t = self._tv.get(device_id)
            if not t or not self._conectada(t):
                raise SinTele("One TV no está abierta en esa TV")
            if orden.get("cmd") == "refresh" and any(o.get("cmd") == "refresh" for _, o in t["ordenes"]):
                return   # ya tiene un «actualiza» pendiente
            t["ordenes"].append((self._reloj(), dict(orden)))
            self._cond.notify_all()

    def a_todas(self, orden):
        """Una orden para todas las TV con Android conectadas (por ejemplo «actualiza»)."""
        for tv in self.android():
            try:
                self.mandar(tv.id, orden)
            except SinTele:
                pass

    # ---------- cuáles hay y a cuál se manda ----------

    def android(self):
        """Las TV con Android conectadas, en el orden en que aparecieron."""
        with self._cond:
            return [AndroidTv(self, k, v["nombre"]) for k, v in self._tv.items() if self._conectada(v)]

    def es_android(self, device_id):
        """¿Ese aparato (el device_id de un reporte) es una TV con Android?"""
        device_id = str(device_id or "")
        with self._cond:
            return device_id in self._tv or device_id.startswith("androidtv-")

    def de(self, device_id, roku):
        """La TV que mandó un reporte (la que está reproduciendo): la TV con Android de ese id o, si no, el Roku."""
        device_id = str(device_id or "")
        if self.es_android(device_id):
            with self._cond:
                t = self._tv.get(device_id)
                return AndroidTv(self, device_id, t["nombre"] if t else NOMBRE_ANDROID)
        return roku

    def usar(self, ident):
        """Esa TV empezó a reproducir algo: pasa a ser «la que se usó por última vez»."""
        with self._cond:
            self._usada[ident] = next(self._turno)

    def elegir(self, ident, roku):
        """La web eligió a qué TV mandar. -> False si esa TV ya no está."""
        if ident == ROKU and roku is not None or any(tv.id == ident for tv in self.android()):
            self.usar(ident)
            return True
        return False

    def candidatas(self, roku):
        """[(id, TV)] de las que se pueden usar: el Roku primero (si se encontró) y luego las de Android conectadas."""
        out = [(ROKU, roku)] if roku is not None else []
        return out + [(tv.id, tv) for tv in self.android()]

    def destino(self, roku):
        """La TV a la que va «Ver en la TV»: la que se usó por última vez. Sin datos, el Roku (como siempre). None si no
        hay ninguna."""
        todas = self.candidatas(roku)
        if not todas:
            return None
        with self._cond:
            usada = dict(self._usada)
        mejor = max(range(len(todas)), key=lambda i: (usada.get(todas[i][0], float("-inf")), -i))
        return todas[mejor][1]

    def lista(self, roku, roku_nombre=""):
        """Para la web: [{id, nombre, tipo, elegida}] de las TV que se pueden usar."""
        todas = self.candidatas(roku)
        elegida = self.destino(roku)
        out = []
        for ident, tv in todas:
            if ident == ROKU:
                out.append({"id": ROKU, "nombre": roku_nombre or "Roku", "tipo": "roku", "elegida": tv is elegida})
            else:
                out.append({"id": ident, "nombre": tv.nombre, "tipo": "android",
                            "elegida": isinstance(elegida, AndroidTv) and elegida.id == ident})
        return out
