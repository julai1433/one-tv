"""Cola de la tele: lo que se reproduce al terminar lo actual (videos de la biblioteca o de YouTube).

Cada entrada: {"kind": "item" | "yt", "id", "title", "thumb"}. Se guarda en la Mac para que
sobreviva a reinicios del servidor. items() puede agregar datos al momento (decorate): la app le pone la
duración a los videos de YouTube.
"""

import json
import threading
from pathlib import Path

MAX_ITEMS = 500   # cabe una lista larga entera (p. ej. «Ver más tarde»)


class PlayQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            self.entries = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.entries = []
        # función(copias de las entradas) -> las mismas con lo que se sepa al momento (p. ej. la duración de los videos
        # de YouTube); no se guarda en el archivo.
        self.decorate = None

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, ensure_ascii=False))
        tmp.replace(self.path)

    def items(self):
        with self.lock:
            out = [dict(e) for e in self.entries]
        return self.decorate(out) if self.decorate else out

    def add(self, entry, front=False):
        with self.lock:
            if front:
                self.entries.insert(0, entry)
            else:
                self.entries.append(entry)
            del self.entries[MAX_ITEMS:]
            self._save()
            return len(self.entries)

    def add_many(self, entries, front=False):
        """Varias de una vez y en su orden (al frente o al final). -> cuántas entraron (hay tope)."""
        with self.lock:
            room = max(MAX_ITEMS - len(self.entries), 0)
            entries = list(entries)[:room]
            if front:
                self.entries[0:0] = entries
            else:
                self.entries.extend(entries)
            self._save()
            return len(entries)

    def move(self, index, to):
        """Lleva la entrada `index` al lugar `to` (se acomoda dentro de la fila). -> el lugar donde quedó, o None."""
        with self.lock:
            if not 0 <= index < len(self.entries):
                return None
            to = min(max(to, 0), len(self.entries) - 1)
            if to != index:
                self.entries.insert(to, self.entries.pop(index))
                self._save()
            return to

    def remove(self, index):
        with self.lock:
            if not 0 <= index < len(self.entries):
                return None
            entry = self.entries.pop(index)
            self._save()
            return entry

    def pop(self):
        return self.remove(0)

    def clear(self):
        with self.lock:
            self.entries = []
            self._save()
