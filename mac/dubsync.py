"""Sincroniza el doblaje de OTRA versión de una película con el video de la biblioteca.

Dos versiones de la misma película casi nunca empiezan en el mismo instante (logos distintos al
principio) y a veces una corre un 4 % más rápido (las europeas, a 25 cuadros por segundo). Pero todos
los doblajes comparten la música y los efectos, así que se comparan esos sonidos:

1. Lo mejor: la otra versión casi siempre trae TAMBIÉN el audio original. Se compara inglés con inglés
   (idénticos salvo el formato) y el doblaje de esa versión ya viene sincronizado con su propio video.
   Si no lo trae, se compara con el doblaje mismo, sin el canal central (ahí van los diálogos, que
   cambian con el idioma): quedan la música y los efectos.
2. Se resume cada pista en «huellas» de 20 ms: la energía en 32 franjas de frecuencia.
3. En 30 puntos repartidos por la película se busca dónde encaja la huella del original en la otra.
4. Si casi todos los puntos dicen lo mismo, se tiene la correspondencia: t_otra = A · t_nuestra + B.
   Si no (otra edición, con escenas de más o de menos), no se agrega nada.

Necesita numpy, así que corre aparte, con su propio Python:
    python dubsync.py analizar  REF IDX CANALES  OTRA IDX CANALES  mismo|distinto   (idioma de las dos pistas)
    python dubsync.py preparar  OTRA IDX CANALES  A B DURACION  SALIDA.m4a  [TITULO]
Escribe el resultado como JSON en la salida estándar.
"""

import json
import subprocess
import sys

import numpy as np

SR = 8000            # muestras por segundo (sobra para música y efectos)
HOP = 160            # 20 ms entre huellas
WIN = 512
FPS = SR / HOP       # huellas por segundo
BANDS = 32
ANCHORS = 30
ANCHOR_SEC = 30
SEARCH_SEC = 240     # cuánto puede estar corrido el principio (logos, avisos)
INLIER_SEC = 0.08
# Velocidades conocidas: 23,976 / 24 / 25 cuadros por segundo entre sí.
SPEEDS = [1.0, 25 / 23.976, 23.976 / 25, 24 / 23.976, 23.976 / 24, 25 / 24, 24 / 25]


def _mix(channels, center=True):
    """Una sola señal; sin el canal central (los diálogos) si se comparan idiomas distintos."""
    if channels >= 6:
        rest = "+".join(f"c{i}" for i in range(4, channels))
        return f"pan=mono|c0=c0+c1+{'c2+' if center else ''}{rest}"
    if channels == 2:
        return "pan=mono|c0=c0+c1"
    return "pan=mono|c0=c0"


def _filterbank():
    freqs = np.fft.rfftfreq(WIN, 1 / SR)
    edges = np.geomspace(80, 3800, BANDS + 1)
    fb = np.zeros((len(freqs), BANDS), dtype=np.float32)
    for b in range(BANDS):
        fb[(freqs >= edges[b]) & (freqs < edges[b + 1]), b] = 1
        if not fb[:, b].any():   # franjas muy angostas en los graves: el bin más cercano
            fb[np.argmin(abs(freqs - (edges[b] + edges[b + 1]) / 2)), b] = 1
    return fb


def features(path, index, channels, center=True, seconds=None):
    """Huellas (cuadros × franjas) de una pista; el cuadro 0 es el inicio del archivo.
    Con «seconds» solo se lee el principio (la entrada de las series está en los primeros minutos)."""
    limit = ["-t", f"{seconds:.1f}"] if seconds else []
    cmd = ["ffmpeg", "-v", "error", "-nostdin", *limit, "-i", path, "-map", f"0:{index}", "-vn", "-sn", "-dn",
           "-af", f"{_mix(channels, center)},aresample={SR}:async=1:first_pts=0", "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    window = np.hanning(WIN).astype(np.float32)
    fb = _filterbank()
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
        spec = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
        out.append(np.log(spec.astype(np.float32) @ fb + 1e-7))
        tail = x[n * HOP:]
    proc.wait()
    if not out:
        raise RuntimeError("no se pudo leer el audio")
    f = np.concatenate(out)
    # Lo que importa son los cambios (golpes, notas, cortes), no el volumen de fondo.
    kernel = np.ones(int(FPS)) / int(FPS)
    base = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, f)
    f = f - base
    f -= f.mean(axis=0)
    f /= f.std(axis=0) + 1e-6
    return f.astype(np.float32)


def rescale(f, speed):
    """Huellas de la otra versión llevadas a nuestro ritmo: cuadro k ↔ su cuadro speed·k."""
    if speed == 1.0:
        return f
    n = int(len(f) / speed)
    pos = np.arange(n) * speed
    i = np.minimum(pos.astype(int), len(f) - 2)
    w = (pos - i)[:, None].astype(np.float32)
    return f[i] * (1 - w) + f[i + 1] * w


def match(ref, other, start, width, search):
    """Dónde encaja ref[start:start+width] en other, a ±search cuadros. (corrimiento, parecido, nitidez)"""
    seg = ref[start:start + width]
    lo = start - search
    region = np.zeros((width + 2 * search, ref.shape[1]), dtype=np.float32)
    a, b = max(lo, 0), min(lo + len(region), len(other))
    if b - a < width:
        return None
    region[a - lo:b - lo] = other[a:b]
    n = 1 << int(np.ceil(np.log2(len(region) + width)))
    spec = np.fft.rfft(region, n, axis=0) * np.conj(np.fft.rfft(seg, n, axis=0))
    corr = np.fft.irfft(spec.sum(axis=1), n)[:len(region) - width + 1]
    energy = np.concatenate([[0], np.cumsum((region ** 2).sum(axis=1))])
    local = np.sqrt(np.maximum(energy[width:] - energy[:-width], 1e-6))
    score = corr / (local * np.sqrt((seg ** 2).sum()) + 1e-6)
    best = int(np.argmax(score))
    shift = float(best)
    if 0 < best < len(score) - 1:   # afinar entre cuadros con una parábola
        y0, y1, y2 = score[best - 1:best + 2]
        den = y0 - 2 * y1 + y2
        if den < 0:
            shift += 0.5 * (y0 - y2) / den
    far = np.abs(np.arange(len(score)) - best) > FPS   # el segundo mejor, lejos del primero
    runner_up = score[far].max() if far.any() else 0
    return (shift - search) / FPS, float(score[best]), float(score[best] / max(runner_up, 1e-6))


def analyze(ref_f, other_f):
    dur_ref, dur_other = len(ref_f) / FPS, len(other_f) / FPS
    ratio = dur_other / dur_ref
    speeds = [s for s in SPEEDS if s == 1.0 or abs(s - ratio) < 0.015]
    width, search = int(ANCHOR_SEC * FPS), int(SEARCH_SEC * FPS)
    starts = np.linspace(0.02 * len(ref_f), 0.98 * len(ref_f) - width, ANCHORS).astype(int)
    best = None
    for speed in speeds:
        other = rescale(other_f, speed)
        points = []
        for s in starts:
            m = match(ref_f, other, int(s), width, search)
            if m:
                points.append((float(s) / FPS + ANCHOR_SEC / 2, *m))
        good = [p for p in points if p[3] > 1.15 and p[2] > 0.05]
        if not good:
            continue
        shifts = np.array([p[1] for p in good])
        center = max(shifts, key=lambda c: (np.abs(shifts - c) < INLIER_SEC).sum())
        inl = [p for p in good if abs(p[1] - center) < INLIER_SEC * 2]
        t = np.array([p[0] for p in inl])
        c = np.array([p[1] for p in inl])
        drift, offset = np.polyfit(t, c, 1) if len(inl) >= 3 and np.ptp(t) > 0 else (0.0, float(center))
        resid = c - (drift * t + offset)
        keep = np.abs(resid) < INLIER_SEC
        cand = {"speed": speed, "points": points, "inliers": int(keep.sum()), "anchors": len(points),
                "drift": float(drift), "offset": float(offset),
                "rms_ms": float(np.sqrt((resid[keep] ** 2).mean()) * 1000) if keep.any() else None,
                "span": float(np.ptp(t[keep]) / dur_ref) if keep.sum() > 1 else 0.0}
        if best is None or cand["inliers"] > best["inliers"]:
            best = cand
    if not best:
        return {"ok": False, "why": "no se parecen en nada (¿es la misma película?)"}
    # t_otra = speed · (t + drift·t + offset)
    a = best["speed"] * (1 + best["drift"])
    b = best["speed"] * best["offset"]
    ok = best["inliers"] >= 0.7 * best["anchors"] and best["inliers"] >= 8 and best["span"] > 0.6
    out = {"ok": bool(ok), "a": a, "b": b, "inliers": best["inliers"], "anchors": best["anchors"],
           "rms_ms": best["rms_ms"], "speed": best["speed"], "dur_ref": dur_ref, "dur_other": dur_other,
           "points": [[round(p[0], 1), round(p[1], 3), round(p[2], 3), round(p[3], 2)] for p in best["points"]]}
    if not ok:
        out["why"] = "los cortes no coinciden en toda la película (¿otra edición?)"
    return out


def prepare(path, index, channels, a, b, duration, dest, title="Latino"):
    """Escribe la pista ya sincronizada: empieza donde empieza nuestro video y dura lo mismo."""
    filters = ["aresample=async=1:first_pts=0"]
    if b > 0:
        filters += [f"atrim=start={b:.4f}", "asetpts=PTS-STARTPTS"]
    if abs(a - 1) > 1e-5:
        filters.append(f"atempo={a:.6f}")
    if b < 0:
        filters.append(f"adelay={-b / a * 1000:.1f}:all=1")
    if channels > 2:   # igual que en la conversión al vuelo: al pasar a estéreo se suben los diálogos
        filters += ["aformat=channel_layouts=stereo", "volume=1.6", "alimiter=limit=0.97"]
    filters.append("apad")
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", path, "-map", f"0:{index}", "-vn", "-sn", "-dn",
           "-af", ",".join(filters), "-t", f"{duration:.3f}", "-ac", "2", "-ar", "48000",
           "-c:a", "aac", "-b:a", "192k", "-map_metadata", "-1", "-metadata:s:a:0", "language=spa",
           "-metadata:s:a:0", f"title={title}", "-movflags", "+faststart", "-f", "mp4", dest]
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return {"ok": r.returncode == 0, "why": r.stderr.strip()[-300:]}


def main(argv):
    if argv[1] == "analizar":
        center = len(argv) <= 8 or argv[8] == "mismo"
        ref = features(argv[2], int(argv[3]), int(argv[4]), center)
        other = features(argv[5], int(argv[6]), int(argv[7]), center)
        result = analyze(ref, other)
    elif argv[1] == "preparar":
        result = prepare(argv[2], int(argv[3]), int(argv[4]), float(argv[5]), float(argv[6]),
                         float(argv[7]), argv[8], argv[9] if len(argv) > 9 else "Latino")
    else:
        result = {"ok": False, "why": f"orden desconocida: {argv[1]}"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
