"""Encuentra la entrada (la canción con los títulos) de cada episodio de una temporada.

No hay una base pública con esos tiempos, pero la entrada se repite igualita en todos los episodios de
una temporada, y casi nada más se repite. Así que se busca lo que suena igual en varios episodios:

1. De cada episodio se leen solo los primeros minutos (la entrada nunca está al final) y se resumen en
   las mismas «huellas» de 20 ms de mac/dubsync.py: la energía en 32 franjas de frecuencia.
2. Se comparan los episodios de dos en dos. Primero a grandes rasgos (5 huellas por segundo, todos
   contra todos): un tramo que suena igual en los dos aparece como una «diagonal» de puntos parecidos.
   Luego, en cada diagonal prometedora, cuadro por cuadro, para saber dónde empieza y dónde termina.
3. De cada par sale el tramo común (de 15 s a 2½ min, que empiece en los primeros 12 min: hay series
   con una escena antes de la entrada). Algunas entradas vienen recortadas en ciertos episodios: los
   trozos que siguen en orden se juntan.
4. Cada episodio se queda con el tramo en el que coinciden más compañeros (la mediana de sus inicios y
   finales). Si no hay suficientes que coincidan (el piloto sin entrada, una serie de antología), no se
   inventa nada: ese episodio queda sin marca.

Necesita numpy, así que corre aparte, con el Python del doblaje:
    python introsync.py detectar  RUTA IDX CANALES DURACION  [RUTA IDX CANALES DURACION …]
Escribe el resultado como JSON en la salida estándar (con --detalle, además, cada par en la de errores).
"""

import json
import sys
import time

import numpy as np

import dubsync
from dubsync import FPS

WINDOW = 900          # se leen hasta 15 min de cada episodio…
WINDOW_SHARE = 0.5    # …y nunca más de la primera mitad (en los episodios cortos, ahí ya van los créditos)
START_MAX = 720       # la entrada empieza en los primeros 12 min (Landman tiene escenas de 11 min antes)
MIN_LEN, MAX_LEN = 15, 150
COARSE = 10           # huellas de 20 ms por punto en la comparación gruesa (5 por segundo)
BLOCK = 25            # puntos gruesos por bloque de la diagonal (5 s)
COARSE_SIM = 0.5      # parecido mínimo de un punto grueso
BLOCK_HITS = 15       # puntos parecidos (de 25) para que un bloque de la diagonal cuente
MAX_LAGS = 8          # diagonales que se miran en detalle por par
FINE_SIM = 0.5        # parecido (promedio de 1 s) que un tramo tiene que alcanzar…
FINE_LOW = 0.2        # …y mientras no baje de este, sigue (lo que no tiene nada que ver da ±0,1)
MIN_RUN = 2.0         # s: trozos más cortos no se consideran
GAP = 1.5             # s: huecos que se perdonan dentro de un mismo tramo (un golpe, un silencio)
MAX_PARTNERS = 8      # en temporadas largas cada episodio se compara con sus 8 vecinos, no con todos


def _unit(f):
    """Cada huella con largo 1 (el parecido es el coseno); los silencios quedan en cero y no cuentan."""
    n = np.linalg.norm(f, axis=1, keepdims=True)
    u = f / np.maximum(n, 1e-6)
    u[n[:, 0] < 0.2 * np.sqrt(f.shape[1])] = 0
    return u.astype(np.float32)


def load(path, index, channels, duration):
    seconds = min(WINDOW, max(120.0, duration * WINDOW_SHARE)) if duration else WINDOW
    f = dubsync.features(path, index, channels, center=True, seconds=seconds)
    fine = _unit(f)
    m = len(f) // COARSE
    coarse = _unit(f[:m * COARSE].reshape(m, COARSE, -1).mean(axis=1))
    return {"fine": fine, "coarse": coarse, "seconds": len(f) / FPS}


def candidate_lags(a, b):
    """Desfases (en puntos gruesos, B = A + desfase) donde algún bloque de 5 s de A suena igual en B.
    Devuelve [(desfase, inicio del mejor bloque en A)], los más claros primero."""
    na, nb = len(a), len(b)
    best = np.zeros(na + nb - 1, dtype=np.int16)      # por desfase: cuántos puntos parecidos en su mejor bloque
    where = np.zeros(na + nb - 1, dtype=np.int32)
    padded = np.zeros((BLOCK, nb + 2 * BLOCK), dtype=np.int16)
    # Cada fila corrida un lugar más que la anterior: así cada columna es una diagonal (un desfase fijo).
    diag = np.lib.stride_tricks.as_strided(padded, (BLOCK, nb + BLOCK - 1),
                                           (padded.strides[0] + padded.strides[1], padded.strides[1]))
    for s in range(0, na - BLOCK + 1, BLOCK):
        padded[:, BLOCK - 1:BLOCK - 1 + nb] = a[s:s + BLOCK] @ b.T >= COARSE_SIM
        counts = diag.sum(axis=0, dtype=np.int16)
        lo = na - s - BLOCK                         # índice en best del desfase de la columna 0
        better = counts > best[lo:lo + len(counts)]
        best[lo:lo + len(counts)][better] = counts[better]
        where[lo:lo + len(counts)][better] = s
    out = []
    for k in np.argsort(best)[::-1]:
        if best[k] < BLOCK_HITS or len(out) >= MAX_LAGS:
            break
        if all(abs(k - o) > 3 for o, _ in out):
            out.append((int(k), int(where[k])))
    return [(k - (na - 1), s) for k, s in out]


def _runs(mask, gap):
    """Tramos [inicio, fin) donde mask es cierto, perdonando huecos cortos."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    runs = []
    for s, e in zip(edges[::2], edges[1::2]):
        if runs and s - runs[-1][1] <= gap:
            runs[-1][1] = e
        else:
            runs.append([s, e])
    return runs


def _diagonal(a, b, lag, lo=0, hi=None):
    """Parecido cuadro a cuadro de a[t] con b[t + lag], para t en [lo, hi). Devuelve (desde, parecidos)."""
    lo = max(lo, 0, -lag)
    hi = min(len(a) if hi is None else hi, len(a), len(b) - lag)
    if hi <= lo:
        return lo, np.zeros(0, dtype=np.float32)
    return lo, np.einsum("ij,ij->i", a[lo:hi], b[lo + lag:hi + lag])


def fine_runs(a, b, lag_coarse, block_start):
    """Mira cuadro por cuadro una diagonal: afina el desfase y dice dónde suena igual. [(a0, a1, desfase)] en s.
    Un tramo tiene que parecerse mucho en algún momento (FINE_SIM) y se extiende mientras se parezca
    algo (FINE_LOW): así entran las entradas con los créditos sobre escenas del episodio, donde a la
    canción se le suman ruidos y voces distintos en cada uno."""
    around = (block_start - 6 * BLOCK) * COARSE, (block_start + 7 * BLOCK) * COARSE   # ±30 s del bloque
    best = None
    for lag in range(lag_coarse * COARSE - COARSE, lag_coarse * COARSE + COARSE + 1):
        _, sim = _diagonal(a, b, lag, *around)
        if len(sim) and (best is None or sim.mean() > best[0]):
            best = (sim.mean(), lag)
    if best is None:
        return []
    lag = best[1]
    lo, sim = _diagonal(a, b, lag)
    smooth = np.convolve(sim, np.ones(int(FPS), dtype=np.float32) / int(FPS), mode="same")
    strong = smooth >= FINE_SIM
    out = []
    for s, e in _runs(smooth >= FINE_LOW, GAP * FPS):
        clear = np.flatnonzero(strong[s:e])
        if len(clear) >= MIN_RUN * FPS:
            # Las puntas, donde se parece clarito: lo tibio de las orillas suele ser el final de la escena
            # anterior con los primeros compases encima (saltarlo cortaría el remate de la escena).
            out.append(((s + clear[0] + lo) / FPS, (s + clear[-1] + 1 + lo) / FPS, lag / FPS))
    return out


def common_segments(ea, eb):
    """Tramos que suenan igual en los dos episodios: [(a0, a1, b0, b1)] en segundos."""
    runs = []
    for lag, block_start in candidate_lags(ea["coarse"], eb["coarse"]):
        runs += fine_runs(ea["fine"], eb["fine"], lag, block_start)
    runs.sort()
    groups = []
    for a0, a1, lag in runs:
        b0, b1 = a0 + lag, a1 + lag
        g = next((g for g in groups if _same_piece(g, (a0, a1, b0, b1))), None)
        if g:
            g[0], g[1], g[2], g[3] = min(g[0], a0), max(g[1], a1), min(g[2], b0), max(g[3], b1)
        else:
            groups.append([a0, a1, b0, b1])
    return [tuple(g) for g in groups]


def _same_piece(g, r):
    """¿El trozo r es parte del mismo tramo g? Sí si se enciman en los dos episodios, o si sigue en orden en
    los dos y en uno va pegado: la entrada corta de algunos episodios es la larga con un pedazo menos."""
    gap_a, gap_b = r[0] - g[1], r[2] - g[3]
    if gap_a <= GAP * 2 and r[1] >= g[0] - GAP * 2 and gap_b <= GAP * 2 and r[3] >= g[2] - GAP * 2:
        return True
    return min(gap_a, gap_b) >= -GAP * 2 and min(gap_a, gap_b) <= GAP * 2 and max(gap_a, gap_b) <= 60


def _ok(seg, sec_a, sec_b):
    a0, a1, b0, b1 = seg
    return (MIN_LEN <= a1 - a0 <= MAX_LEN and MIN_LEN <= b1 - b0 <= MAX_LEN
            and a0 < min(START_MAX, sec_a - MIN_LEN) and b0 < min(START_MAX, sec_b - MIN_LEN))


def consolidate(n, found, compared):
    """found[i] = [(inicio, fin, compañero)]: el tramo en el que más compañeros coinciden, o nada."""
    out = []
    for i in range(n):
        others = compared[i]
        if not others:
            out.append(None)
            continue
        need = 1 if others == 1 else max(2, int(np.ceil(0.25 * others)))
        clusters = []
        for s, e, j in sorted(found[i]):
            c = next((c for c in clusters
                      if min(e, c["end"]) - max(s, c["start"]) >= 0.5 * min(e - s, c["end"] - c["start"])), None)
            if c is None:
                c = {"segs": []}
                clusters.append(c)
            c["segs"].append((s, e, j))
            c["start"] = float(np.median([x[0] for x in c["segs"]]))
            c["end"] = float(np.median([x[1] for x in c["segs"]]))
        best = None
        for c in clusters:
            support = len({j for _, _, j in c["segs"]})
            key = (support, c["end"] - c["start"])
            if support >= need and (best is None or key > best[0]):
                best = (key, c)
        if not best:
            out.append(None)
            continue
        support, c = best[0][0], best[1]
        if not MIN_LEN <= c["end"] - c["start"] <= MAX_LEN:
            out.append(None)
            continue
        out.append({"start": round(c["start"], 2), "end": round(c["end"], 2),
                    "confidence": round(support / others, 2), "support": support, "compared": others})
    return out


def detect(episodes, detail=False):
    """Compara cada episodio con todos, o en temporadas largas con los 4 anteriores y los 4 siguientes
    (así en memoria hay a lo más 5 episodios, aunque la «temporada» sea una carpeta con 100 videos)."""
    n = len(episodes)
    reach = n - 1 if n - 1 <= MAX_PARTNERS else MAX_PARTNERS // 2
    feats, found, compared = {}, [[] for _ in range(n)], [0] * n
    read = compare = 0.0
    pairs = 0
    for j in range(n):
        t = time.time()
        try:
            feats[j] = load(*episodes[j])
        except (RuntimeError, OSError, ValueError) as e:   # un archivo dañado no arruina la temporada
            feats[j] = None
            if detail:
                print(f"{j + 1:>2}: no se pudo leer ({e})", file=sys.stderr)
        read += time.time() - t
        t = time.time()
        for i in range(max(0, j - reach), j):
            if feats[i] is None or feats[j] is None:
                continue
            pairs += 1
            compared[i] += 1
            compared[j] += 1
            segs = common_segments(feats[i], feats[j])
            good = [s for s in segs if _ok(s, feats[i]["seconds"], feats[j]["seconds"])]
            for a0, a1, b0, b1 in good:
                found[i].append((a0, a1, j))
                found[j].append((b0, b1, i))
            if detail:
                print(f"{i + 1:>2}–{j + 1:<2} " + ("  ".join(
                    f"{'✓' if s in good else '·'} {s[0]:6.1f}–{s[1]:6.1f} | {s[2]:6.1f}–{s[3]:6.1f}" for s in segs)
                    or "—"), file=sys.stderr)
        feats.pop(j - reach, None)   # ya no se compara con nadie más
        compare += time.time() - t
    return {"ok": True, "episodes": consolidate(n, found, compared), "pairs": pairs,
            "seconds": {"read": round(read, 1), "compare": round(compare, 1)}}


def main(argv):
    detail = "--detalle" in argv
    args = [a for a in argv[1:] if a != "--detalle"]
    if not args or args[0] != "detectar" or (len(args) - 1) % 4 or len(args) < 9:
        result = {"ok": False, "why": "uso: introsync.py detectar RUTA IDX CANALES DURACION (dos episodios o más)"}
    else:
        rest = args[1:]
        episodes = [(rest[k], int(rest[k + 1]), int(rest[k + 2]), float(rest[k + 3]))
                    for k in range(0, len(rest), 4)]
        result = detect(episodes, detail)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
