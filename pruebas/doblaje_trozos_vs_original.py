import sys, subprocess, json, shutil, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import numpy as np
import library, transcode
SP = Path(sys.argv[1]); F = sys.argv[2]; SIDE = sys.argv[3]
info = library.probe(F)
info = {**info, "audio": info["audio"] + [{"index": "x0", "codec": "aac", "channels": 2, "lang": "spa",
                                           "title": "Latino", "default": False, "file": SIDE}]}
item = {"id": "prueba", "path": F, "duration": info["duration"], "info": info, "full_title": "prueba",
        "mode": "copy", "mtime": 1, "size": 1}
def run(plan, aud, i, tag):
    out = SP / f"pair-{tag}"; shutil.rmtree(out, ignore_errors=True); out.mkdir()
    p = subprocess.Popen(plan.command(aud, i, out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = time.time()
    while not (out / f"seg{i + 4}.ts").exists() and time.time() - t < 60: time.sleep(0.2)
    p.terminate(); p.wait()
    # trozos i+1..i+3 unidos, en su línea de tiempo (con -copyts) desde un instante fijo
    lst = out / "l.txt"; lst.write_text("".join(f"file 'seg{k}.ts'\n" for k in range(i + 1, i + 4)))
    t0 = plan.starts[i + 1] + 0.5
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-copyts",
                          "-af", f"aresample=async=1:first_pts=0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    first = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                       "stream=start_time", "-of", "json", str(out / f"seg{i + 1}.ts")],
                                      capture_output=True, text=True).stdout)["streams"][0]["start_time"]
    return x, float(first)
def lag(a, b, maxlag=9600):
    n = min(len(a), len(b)); a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    c = np.fft.irfft(np.fft.rfft(a, 2 * n) * np.conj(np.fft.rfft(b, 2 * n)))
    c = np.concatenate([c[-maxlag:], c[:maxlag + 1]]); k = int(np.argmax(c)) - maxlag
    return k / 48000, float(c.max() / (np.linalg.norm(a) * np.linalg.norm(b)))
kf = transcode.Keyframes(SP / "kf").get(item)
for name, plan in (("copia", transcode.CopyPlan(item, kf)), ("completa", transcode.FullPlan(item))):
    for i in (0, len(plan.starts) // 3, len(plan.starts) * 4 // 5):
        a, ta = run(plan, 2, i, "a")      # latino que viene dentro del archivo
        b, tb = run(plan, "x0", i, "x")   # latino agregado aparte
        l, sim = lag(a, b)
        # l > 0: el agregado va detrás. Se descuenta la diferencia de arranque de cada trozo.
        print(f"{name:8s} desde {plan.starts[i]:7.1f}s: diferencia {1000 * (l - (tb - ta)):+6.1f} ms (parecido {sim:.2f})")
