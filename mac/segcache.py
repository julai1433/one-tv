"""Trozos de YouTube y de los canales en vivo bajados de antemano, para que el mosaico arranque rápido.

ffmpeg abre las fuentes del mosaico una tras otra y, de cada una, baja dos trozos antes de pasar a la siguiente
(medido el 30 sep 2026: ~1 s por lista de YouTube y ~5 s con un canal en vivo, cuyos trozos de 6 s tardan ~2 s en
llegar). Antes de arrancar ffmpeg, la computadora pide a la vez los trozos que va a necesitar (mosaic.py) y quedan
aquí un rato: cuando ffmpeg los pide ya están, o vienen en camino y espera esa misma descarga sin repetirla.

Solo se guarda lo que se pidió de antemano (la petición lleva el encabezado X-Prefetch), y por poco tiempo: una
película o un video normal no llenan la memoria.
"""

import threading
import time

TTL = 90                         # segundos que se guarda un trozo pedido de antemano
MAX_BYTES = 96 * 1024 * 1024     # tope de memoria (unos 60 trozos de un canal en vivo)
WAIT = 30                        # lo más que se espera una descarga que ya viene en camino


class SegmentCache:
    def __init__(self, ttl=TTL, max_bytes=MAX_BYTES, clock=time.monotonic):
        self.ttl, self.max_bytes, self.clock = ttl, max_bytes, clock
        self.lock = threading.Lock()
        self.items = {}   # clave -> {"done": Event, "value", "size", "t"}

    def _expire(self, now):
        """Quita lo vencido y, si se pasa del tope, lo más viejo (con el candado tomado)."""
        for key in [k for k, e in self.items.items() if e["done"].is_set() and now - e["t"] > self.ttl]:
            del self.items[key]
        total = sum(e["size"] for e in self.items.values())
        for key in sorted((k for k, e in self.items.items() if e["done"].is_set()), key=lambda k: self.items[k]["t"]):
            if total <= self.max_bytes:
                break
            total -= self.items.pop(key)["size"]

    def get(self, key, produce, keep=False):
        """El trozo `key`: de la memoria, de la descarga que ya viene en camino o de produce() (que devuelve lo que
        se manda: bytes o una tupla cuyo primer elemento con bytes da el tamaño). keep: guardarlo (quien se
        adelanta). Si produce() falla, el error sale tal cual y no queda nada guardado."""
        now = self.clock()
        with self.lock:
            self._expire(now)
            entry = self.items.get(key)
            owner = entry is None and keep
            if owner:
                entry = self.items[key] = {"done": threading.Event(), "value": None, "size": 0, "t": now}
        if entry is None:
            return produce()
        if owner:
            try:
                value = produce()
            except BaseException:
                with self.lock:
                    if self.items.get(key) is entry:
                        del self.items[key]
                entry["done"].set()
                raise
            with self.lock:
                entry["value"], entry["size"], entry["t"] = value, _size(value), self.clock()
            entry["done"].set()
            return value
        entry["done"].wait(WAIT)
        if entry["value"] is not None:
            return entry["value"]
        return produce()   # la descarga de antemano falló o tardó demasiado: se pide de nuevo

    def __len__(self):
        with self.lock:
            return sum(1 for e in self.items.values() if e["value"] is not None)


def _size(value):
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(value, tuple):
        return sum(len(v) for v in value if isinstance(v, (bytes, bytearray)))
    return 0
