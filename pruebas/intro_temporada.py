# Detecta la entrada de los episodios de una temporada (como lo hará el servicio) y muestra una tabla.
# Uso: python3 pruebas/intro_temporada.py "<carpeta de la temporada>" [otra carpeta o video …] [--detalle]
# Solo lee los videos. Corre la comparación con el Python de numpy del doblaje y con prioridad baja.
# Con --detalle muestra además qué tramo común salió de cada par de episodios (✓ = cumple largo y posición).
import os, resource, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
from intro import pick_tracks, run_introsync
from library import VIDEO_EXTS, natural_key, probe

PYTHON = os.environ.get("CINE_NUMPY", str(Path.home() / "Library/Application Support/cine-roku/doblaje/bin/python"))
SCRIPT = Path(__file__).resolve().parent.parent / "mac" / "introsync.py"

args = [a for a in sys.argv[1:] if a != "--detalle"]
if not args:
    sys.exit("Uso: python3 pruebas/intro_temporada.py <carpeta de la temporada> [otra carpeta o video …] [--detalle]")
files = []
for a in map(Path, args):
    if a.is_dir():
        files += sorted((f for f in a.iterdir() if f.suffix.lower() in VIDEO_EXTS and not f.name.startswith(".")),
                        key=lambda f: natural_key(f.name))
    else:
        files.append(a)
infos = [probe(f) for f in files]
tracks = pick_tracks(infos)
eps = [(str(f), t["index"], t["channels"], i["duration"]) for f, i, t in zip(files, infos, tracks) if t]
names = [f.stem for f, t in zip(files, tracks) if t]

t0, before = time.time(), resource.getrusage(resource.RUSAGE_CHILDREN)
r = run_introsync(PYTHON, SCRIPT, eps, detail="--detalle" in sys.argv)
after = resource.getrusage(resource.RUSAGE_CHILDREN)
wall = time.time() - t0
cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)

if not r.get("ok"):
    sys.exit(f"✗ {r.get('why')}")
if r.get("detail"):
    print("Pares (inicio–fin en el primero | en el segundo):")
    print(r["detail"].rstrip())
    print()
width = max(len(n) for n in names)
print(f"{'Episodio':<{width}}  {'Inicio':>7}  {'Fin':>7}  {'Dura':>5}  Confianza")
fmt = lambda s: f"{int(s // 60)}:{s % 60:04.1f}"
for n, m in zip(names, r["episodes"]):
    if m:
        print(f"{n:<{width}}  {fmt(m['start']):>7}  {fmt(m['end']):>7}  {m['end'] - m['start']:5.1f}  "
              f"{m['confidence']:.2f} ({m['support']} de {m['compared']})")
    else:
        print(f"{n:<{width}}  {'—':>7}  {'—':>7}  {'':>5}  sin entrada")
found = sum(1 for m in r["episodes"] if m)
print(f"\n{found} de {len(eps)} episodios con entrada · {r['pairs']} pares · "
      f"{wall:.1f} s en total (leer {r['seconds']['read']} s, comparar {r['seconds']['compare']} s) · "
      f"CPU {cpu:.1f} s ({cpu / max(wall, 0.1) * 100:.0f} % de un núcleo) · "
      f"memoria máx. {after.ru_maxrss / 2**20:.0f} MB")   # macOS la da en bytes
