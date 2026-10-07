"""Cómo se corresponde un subtítulo con la voz de un video (la parte de mac/subsync.py que necesita numpy).

1. La voz: el audio se lee a 16 kHz (en 5.1, solo el canal central: ahí van los diálogos) y cada 10 ms se
   mide la energía entre 300 y 3400 Hz, donde está la voz. Cuenta lo que sobresale del fondo de esa escena
   (comparado con los 20 s de alrededor) y lo que sube y baja rápido, como las sílabas (la música y los
   ruidos de fondo son más parejos). Queda un «hay voz» de 0 a 1 cada 10 ms. Se guarda en la caché, así un
   segundo subtítulo del mismo video no vuelve a leer el audio.
2. El subtítulo: 1 mientras hay una línea en pantalla, 0 si no.
3. Primero, todo junto: para cada velocidad posible (23,976 / 24 / 25 cuadros por segundo entre sí) se
   comparan las dos señales con desfases de hasta ±15 min (o un cuarto del video, si es corto). El mejor
   desfase tiene que sobresalir mucho del resto (la «confianza»: cuántas veces la dispersión normal); con un
   subtítulo de otra cosa no sobresale nada.
4. Luego, por tramos (como la herramienta «alass»): a cada línea se le busca su desfase (±10 min del de
   todo junto) y cambiar de desfase entre una línea y la siguiente cuesta una penalización, así que solo hay
   un salto si una escena entera coincide mucho mejor con otro desfase. Cada tramo tiene que tener su propia
   coincidencia clara; si no, se une al vecino. Si en un salto el desfase baja (al subtítulo le sobra una
   escena que este video no tiene), las líneas de esa escena se quitan.

Uso:  python subsync_voz.py alinear VIDEO IDX CANALES SUB.srt [SUB2.srt …] [--cache CARPETA]
Escribe el resultado como JSON en la salida estándar.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np

import subsync

SR = 16000
HOP = 160                 # 10 ms
WIN = 512
FPS = SR // HOP           # 100 cuadros por segundo
BAND = (300, 3400)        # donde está la voz
FLOOR_SEC = 20            # el «fondo» de cada escena: ±20 s
SYLLABLE = 30             # 0,3 s: lo que sube y baja como las sílabas
SPEEDS = [1.0, 25 / 23.976, 23.976 / 25, 24 / 23.976, 23.976 / 24, 25 / 24, 24 / 25]
GLOBAL_SEC = 900          # desfase máximo de todo junto
DP_SEC = 600              # desfase de un tramo respecto al de todo junto
DP_STEP = 5               # los tramos se buscan cada 50 ms y luego se afinan al cuadro
LOCAL_SEC = 60            # para la coincidencia propia de cada tramo
PEAK_GAP = 2.0            # s: lo que está a menos de esto del mejor desfase no cuenta como «el resto»
PENALTY = 50              # lo que cuesta un salto: 50 veces lo que varía por azar la coincidencia de una línea
NEAR = (-150, -100, -50, 50, 100, 150)   # cuadros: con qué se compara cada desfase en cue_scores
MIN_JUMP = 0.5            # s: saltos más chicos son ruido, no escenas
# Cuándo la coincidencia es clara. Medido con 3 películas y 2 episodios reales (subtítulos corridos a propósito):
# con el subtítulo correcto, confianza de 7 a 25 (las más bajas, con un salto) y el mejor desfase le gana al
# segundo lejano ×1,6 a ×3,7; con el de otra película u otro episodio de la misma serie, confianza de 2 a 5 y
# ×1,0 a ×1,3. La confianza de un tramo solo (±60 s) varía más, así que ahí manda cuánto le gana.
Z_MIN, R_MIN = 6.0, 1.4   # confianza mínima de todo junto, y cuánto le gana al segundo mejor desfase
Z_SEG, R_SEG = 4.0, 1.4   # lo mismo para cada tramo
MIN_SEG_CUES = 8
ON_TIME = 0.25            # s: un desfase menor ya es «a tiempo» (la voz no empieza justo con la línea)
VERSION = 2               # cambia si cambia el cálculo de la voz (invalida la caché)


# ---------- la voz ----------

def _mix(channels):
    if channels >= 6:
        return "pan=mono|c0=c2"   # el canal central: los diálogos
    if channels >= 2:
        return "pan=mono|c0=0.5*c0+0.5*c1"
    return "pan=mono|c0=c0"


def band_energy(path, index, channels):
    """Energía entre 300 y 3400 Hz cada 10 ms; el cuadro 0 es el inicio del archivo."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{index}", "-vn", "-sn", "-dn",
           "-af", f"{_mix(channels)},aresample={SR}:async=1:first_pts=0", "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    freqs = np.fft.rfftfreq(WIN, 1 / SR)
    band = (freqs >= BAND[0]) & (freqs < BAND[1])
    window = np.hanning(WIN).astype(np.float32)
    out, tail = [], np.zeros(0, dtype=np.float32)
    chunk = SR * 60 * 4   # bytes de un minuto
    while True:
        raw = proc.stdout.read(chunk)
        if not raw:
            break
        x = np.concatenate([tail, np.frombuffer(raw[:len(raw) // 4 * 4], dtype=np.float32)])
        n = (len(x) - WIN) // HOP + 1
        if n <= 0:
            tail = x
            continue
        frames = np.lib.stride_tricks.as_strided(x, (n, WIN), (x.strides[0] * HOP, x.strides[0]))
        spec = np.abs(np.fft.rfft(frames * window, axis=1)[:, band]) ** 2
        out.append(spec.sum(axis=1))
        tail = x[n * HOP:]
    proc.wait()
    if not out:
        raise RuntimeError("no se pudo leer el audio")
    return np.concatenate(out).astype(np.float64)


def _rank(x):
    """De 0 a 1 según el orden (los empates, igual)."""
    return np.searchsorted(np.sort(x), x).astype(np.float32) / max(len(x), 1)


def speech(energy):
    """«Hay voz», de 0 a 1, cada 10 ms."""
    le = np.log(energy + 1e-9)
    n = len(le)
    secs = max(n // FPS, 1)
    per_sec = np.percentile(np.resize(le, secs * FPS).reshape(secs, FPS), 20, axis=1)
    pad = np.pad(per_sec, FLOOR_SEC, mode="edge")
    floor = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * FLOOR_SEC + 1), axis=1)
    floor = np.resize(np.repeat(floor, FPS), n)
    if n > secs * FPS:
        floor[secs * FPS:] = floor[secs * FPS - 1]
    above = le - floor
    # Sílabas: cuánto sube y baja la energía en los 0,3 s de antes Y en los de después (si se mirara una sola
    # ventana centrada, el borde entre silencio y voz también «variaría» y la voz parecería empezar antes).
    k = SYLLABLE
    c1 = np.concatenate([[0], np.cumsum(le)])
    c2 = np.concatenate([[0], np.cumsum(le * le)])
    mean = (c1[k:] - c1[:-k]) / k
    std = np.sqrt(np.maximum((c2[k:] - c2[:-k]) / k - mean * mean, 0))   # std[j]: de le[j:j+k]
    after, before = np.zeros(n), np.zeros(n)
    after[:len(std)] = std
    before[k - 1:k - 1 + len(std)] = std
    return (_rank(above) + _rank(np.minimum(before, after))) / 2


def voice(path, index, channels, cache=None):
    key = None
    if cache:
        st = os.stat(path)
        key = hashlib.sha1(f"{VERSION}|{path}|{st.st_size}|{int(st.st_mtime)}|{index}|{channels}".encode()) \
            .hexdigest()[:16]
        try:
            return np.load(os.path.join(cache, key + ".npy")).astype(np.float32) / 255
        except (OSError, ValueError):
            pass
    v = speech(band_energy(path, index, channels))
    if key:
        try:
            os.makedirs(cache, exist_ok=True)
            tmp = os.path.join(cache, key + ".tmp.npy")
            np.save(tmp, np.round(v * 255).astype(np.uint8))
            os.replace(tmp, os.path.join(cache, key + ".npy"))
        except OSError:
            pass
    return v


# ---------- comparar ----------

def indicator(starts, ends, n, shift=0.0):
    """1 mientras hay una línea en pantalla (tiempos ya en segundos del video, más «shift»)."""
    s = np.zeros(n, dtype=np.float32)
    a = np.clip(np.round((starts + shift) * FPS).astype(int), 0, n)
    b = np.clip(np.round((ends + shift) * FPS).astype(int), 0, n)
    d = np.zeros(n + 1, dtype=np.float32)
    np.add.at(d, a, 1)
    np.add.at(d, b, -1)
    s[:] = np.cumsum(d)[:n] > 0
    return s


def _peak(lags, corr):
    """(desfase en s, confianza, cuánto le gana al segundo mejor desfase lejano)."""
    k = int(np.argmax(corr))
    shift = float(lags[k])
    if 0 < k < len(corr) - 1:   # entre cuadros, con una parábola
        y0, y1, y2 = corr[k - 1:k + 2]
        den = y0 - 2 * y1 + y2
        if den < 0:
            shift += 0.5 * (y0 - y2) / den
    shift = float(shift)
    rest = corr[np.abs(lags - lags[k]) > PEAK_GAP * FPS]
    if len(rest) < 10:
        return shift / FPS, 0.0, 1.0
    med = np.median(rest)
    mad = np.median(np.abs(rest - med)) * 1.4826 + 1e-9
    second = rest.max()
    return shift / FPS, float((corr[k] - med) / mad), float(corr[k] / second) if second > 0 else 99.0


def correlate(v_spec, m, s, maxlag):
    c = np.fft.irfft(v_spec * np.conj(np.fft.rfft(s - s.mean(), m)), m)
    lags = np.arange(-maxlag, maxlag + 1)
    return lags, c[lags % m]


def global_match(v, starts, ends):
    """El mejor desfase de todo el subtítulo con cada velocidad, de la más clara a la menos."""
    n = len(v)
    # Hasta ±15 min, pero no más de un cuarto del video: con desfases mayores casi nada se superpone y la
    # comparación con «el resto» quedaría engañosa (en un episodio corto todo parecería sobresalir).
    maxlag = int(min(GLOBAL_SEC * FPS, n / 4))
    longest = max(SPEEDS) * float(ends.max()) * FPS
    m = 1 << int(np.ceil(np.log2(n + max(n, longest) + maxlag + 1)))
    v_spec = np.fft.rfft(v - v.mean(), m)
    length = int(max(n, longest)) + 1
    out = []
    for speed in SPEEDS:
        lags, corr = correlate(v_spec, m, indicator(starts * speed, ends * speed, length), maxlag)
        off, z, r = _peak(lags, corr)
        out.append({"speed": speed, "offset": off, "z": z, "r": r})
    return sorted(out, key=lambda g: -g["z"])


def local_match(vc, starts, ends, offset):
    """La coincidencia propia de un tramo (tiempos ya a la velocidad del video), cerca de «offset»."""
    n = len(vc)
    a = max(int((starts.min() + offset - LOCAL_SEC) * FPS), 0)
    b = min(int((ends.max() + offset + LOCAL_SEC) * FPS) + 1, n)
    if b - a < LOCAL_SEC * FPS:   # el tramo cae casi entero fuera del audio
        return offset, 0.0, 1.0
    w = vc[a:b] - vc[a:b].mean()
    maxlag = LOCAL_SEC * FPS
    m = 1 << int(np.ceil(np.log2(len(w) + 2 * maxlag + 1)))
    s = indicator(starts, ends, len(w), offset - a / FPS)
    lags, corr = correlate(np.fft.rfft(w, m), m, s, maxlag)
    lag, z, r = _peak(lags, corr)
    return offset + lag, z, r


def _cum(vc):
    return np.concatenate([[0.0], np.cumsum(vc, dtype=np.float64)])


def cue_scores(C, starts, ends, shifts):
    """Cuánto mejor cae cada línea con cada desfase (en cuadros) que medio segundo a un segundo y medio antes o
    después: así cuenta que la línea calce justo con su frase, no solo que caiga donde se habla mucho.
    -> (líneas × desfases)"""
    n = len(C) - 1
    a0 = np.round(starts * FPS).astype(int)[:, None]
    b0 = np.round(ends * FPS).astype(int)[:, None]

    def raw(sh):
        return C[np.clip(b0 + sh[None, :], 0, n)] - C[np.clip(a0 + sh[None, :], 0, n)]
    near = sum(raw(shifts + d) for d in NEAR) / len(NEAR)
    return raw(shifts) - near


def split_dp(C, starts, ends, offset, penalty):
    """Desfase de cada línea (alineación por tramos con penalización por salto). -> desfases en s"""
    half = int(DP_SEC * FPS / DP_STEP)
    shifts = int(round(offset * FPS)) + np.arange(-half, half + 1) * DP_STEP
    n = len(starts)
    best = cue_scores(C, starts[:1], ends[:1], shifts)[0]
    jumped = np.zeros((n, len(shifts)), dtype=bool)
    source = np.zeros(n, dtype=int)
    for i in range(1, n):
        k = int(np.argmax(best))
        jump = best[k] - penalty
        jumped[i] = jump > best
        source[i] = k
        best = np.where(jumped[i], jump, best) + cue_scores(C, starts[i:i + 1], ends[i:i + 1], shifts)[0]
    k = int(np.argmax(best))
    out = np.zeros(n, dtype=int)
    for i in range(n - 1, -1, -1):
        out[i] = k
        if i and jumped[i, k]:
            k = source[i]
    return shifts[out] / FPS


def _runs(offsets):
    """Tramos de líneas seguidas con el mismo desfase: [[primera, última+1, desfase]]."""
    runs = []
    for i, o in enumerate(offsets):
        if runs and abs(runs[-1][2] - o) < 1e-9:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, float(o)])
    return runs


def _merge(runs, i, into):
    """Une el tramo i con su vecino «into» (i-1 o i+1), con el desfase del vecino."""
    a, b = sorted((i, into))
    runs[a:b + 1] = [[runs[a][0], runs[b][1], runs[into][2]]]


def _cut(C, starts, ends, A, B):
    """Dónde va el salto entre dos tramos seguidos y qué líneas sobran. Si el desfase baja (al subtítulo le
    sobra una escena), se quita la ventana de líneas que mejor lo explica. -> (primera de B, [quitadas])"""
    gap = max(A[2] - B[2], 0.0)      # segundos (de video) que el subtítulo tiene de más
    lo, hi = A[0], B[1]
    t = starts[lo:hi]
    sa = cue_scores(C, t, ends[lo:hi], np.array([int(round(A[2] * FPS))]))[:, 0]
    sb = cue_scores(C, t, ends[lo:hi], np.array([int(round(B[2] * FPS))]))[:, 0]
    pa = np.concatenate([[0.0], np.cumsum(sa)])
    pb = np.concatenate([[0.0], np.cumsum(sb)])
    options = set()
    for k in range(len(t) + 1):   # A = líneas [:p], quitadas [p:q], B = [q:]
        if gap == 0:
            options.add((k, k))
            continue
        if k < len(t):   # la escena que sobra empieza con la línea k…
            options.add((k, max(int(np.searchsorted(t, t[k] + gap - 1e-6)), k)))
        q = k            # …o termina justo antes de la línea k
        options.add((min(int(np.searchsorted(t, (t[q] if q < len(t) else t[-1] + gap) - gap + 1e-6)), q), q))
    p, q = max(sorted(options), key=lambda o: pa[o[0]] + pb[-1] - pb[o[1]])
    return lo + q, list(range(lo + p, lo + q))


def _checks(vc, starts, ends, runs):
    out = []
    for a, b, o in runs:
        off, z, r = local_match(vc, starts[a:b], ends[a:b], o)
        out.append({"ok": b - a >= MIN_SEG_CUES and z >= Z_SEG and r >= R_SEG and abs(off - o) < 1.0,
                    "offset": off, "z": z, "r": r})
    return out


def segment(vc, C, starts, ends, offset, penalty):
    """Tramos de un subtítulo ya llevado a una velocidad: [[primera, última+1, desfase]], sus revisiones y qué
    tan bien calza todo (para comparar velocidades). Sin tramos claros: (None, revisiones, -inf)."""
    runs = _runs(split_dp(C, starts, ends, offset, penalty))
    # Cada tramo con su propia coincidencia clara; si no, se une al vecino que mejor le queda.
    checks = None
    while len(runs) > 1:
        small = [i for i in range(1, len(runs)) if abs(runs[i][2] - runs[i - 1][2]) < MIN_JUMP]
        if small:
            i = small[0]
            _merge(runs, i, i - 1 if runs[i][1] - runs[i][0] <= runs[i - 1][1] - runs[i - 1][0] else i)
            checks = None
            continue
        if checks is None:
            checks = _checks(vc, starts, ends, runs)
        bad = [i for i, c in enumerate(checks) if not c["ok"]]
        if not bad:
            break
        i = min(bad, key=lambda j: checks[j]["z"])
        a, b = runs[i][0], runs[i][1]
        into = max((j for j in (i - 1, i + 1) if 0 <= j < len(runs)),
                   key=lambda j: cue_scores(C, starts[a:b], ends[a:b], np.array([int(round(runs[j][2] * FPS))])).sum())
        _merge(runs, i, into)
        lo = min(i, into)
        checks[lo:lo + 2] = _checks(vc, starts, ends, runs[lo:lo + 1])   # solo cambia el tramo unido
    if len(runs) == 1:
        runs = [[0, len(starts), offset]]
        checks = _checks(vc, starts, ends, runs)
        if checks[0]["r"] < R_MIN:   # la confianza de todo junto ya se revisó antes
            return None, checks, -np.inf
    for run, c in zip(runs, checks):   # afinado al cuadro
        run[2] = c["offset"]
    fit = sum(cue_scores(C, starts[a:b], ends[a:b], np.array([int(round(o * FPS))])).sum() for a, b, o in runs)
    return runs, checks, fit - penalty * (len(runs) - 1)


def align(v, cues):
    """La corrección de un subtítulo (ver el principio del archivo)."""
    if len(cues) < 2 * MIN_SEG_CUES:
        return {"ok": True, "action": "dudoso", "why": "tiene muy pocas líneas para comparar", "confidence": None}
    starts0 = np.array(sorted(c["start"] for c in cues))
    ends0 = np.array([c["end"] for c in sorted(cues, key=lambda c: c["start"])])
    found = global_match(v, starts0, ends0)
    g = found[0]
    detail = {"global": {k: round(x, 4) for k, x in g.items()}}
    dudoso = {"ok": True, "action": "dudoso", "why": "no coinciden claramente con la voz",
              "confidence": round(g["z"], 1), "detail": detail}
    if g["z"] < Z_MIN:
        return dudoso
    vc = v - v.mean()
    C = _cum(vc)
    # Lo que varía por azar la coincidencia de una línea (con desfases cualquiera): de eso depende el costo
    # de un salto, así un audio con más ruido no inventa saltos.
    rng = np.random.default_rng(0)
    penalty = PENALTY * cue_scores(C, starts0 * g["speed"], ends0 * g["speed"],
                                   rng.integers(-GLOBAL_SEC * FPS, GLOBAL_SEC * FPS, 64)).std()
    # Con un salto a medio video, una velocidad apenas distinta puede parecer tan buena como la verdadera:
    # se prueban las parecidas y se queda la que mejor calza con sus tramos (cambiar la velocidad cuesta
    # como un salto: sin una mejora clara, la misma velocidad).
    best = None
    for cand in [c for c in found if c["z"] >= max(Z_MIN, 0.7 * g["z"])][:3]:
        starts, ends = starts0 * cand["speed"], ends0 * cand["speed"]
        runs, checks, fit = segment(vc, C, starts, ends, cand["offset"], penalty)
        fit -= 0 if cand["speed"] == 1.0 else penalty
        if runs and (best is None or fit > best[3]):
            best = (cand, runs, checks, fit, starts, ends)
    if not best:
        return dudoso
    g, runs, checks, _, starts, ends = best
    speed = g["speed"]
    detail["global"] = {k: round(x, 4) for k, x in g.items()}
    quitar, dropped = [], 0
    for A, B in zip(runs, runs[1:]):
        first, gone = _cut(C, starts, ends, A, B)
        A[1] = gone[0] if gone else first
        B[0] = first
        if gone:
            quitar.append([round(float(starts0[gone[0]]), 3), round(float(starts0[gone[-1]]) + 0.001, 3)])
            dropped += len(gone)
    if len(runs) > 1:   # afinado otra vez, ya sin las líneas del otro tramo ni las quitadas
        checks = _checks(vc, starts, ends, runs)
        for run, c in zip(runs, checks):
            run[2] = c["offset"]
    segments = [[0.0 if n == 0 else round(float(starts0[run[0]]), 3), round(run[2], 3)] for n, run in enumerate(runs)]
    detail["segments"] = [[s[0], s[1], round(c["z"], 1), round(c["r"], 2)] for s, c in zip(segments, checks)]
    if len(segments) == 1 and speed == 1.0 and abs(segments[0][1]) < ON_TIME:
        return {"ok": True, "action": "a tiempo", "confidence": round(g["z"], 1), "speed": 1.0,
                "segments": segments, "detail": detail}
    return {"ok": True, "action": "corregir", "confidence": round(g["z"], 1), "speed": speed,
            "segments": segments, "quitar": quitar, "dropped": dropped, "detail": detail}


def main(argv):
    if len(argv) < 6 or argv[1] != "alinear":
        print(json.dumps({"ok": False, "why": "uso: alinear VIDEO IDX CANALES SUB …"}, ensure_ascii=False))
        return
    args, cache = argv[2:], None
    if "--cache" in args:
        k = args.index("--cache")
        cache = args[k + 1]
        args = args[:k] + args[k + 2:]
    video, index, channels, subs = args[0], int(args[1]), int(args[2]), args[3:]
    t0 = time.time()
    try:
        v = voice(video, index, channels, cache)
    except (OSError, RuntimeError) as e:
        print(json.dumps({"ok": False, "why": str(e)}, ensure_ascii=False))
        return
    results = []
    for path in subs:
        try:
            cues = [c for c in subsync.read(path) if c["end"] > c["start"]]
        except OSError as e:
            results.append({"ok": False, "why": f"no se pudo abrir ({e.strerror or e})"})
            continue
        if not cues:
            results.append({"ok": False, "why": "el archivo no tiene líneas de subtítulos"})
            continue
        results.append(align(v, cues))
    print(json.dumps({"ok": True, "secs": round(time.time() - t0, 1), "subs": results}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
