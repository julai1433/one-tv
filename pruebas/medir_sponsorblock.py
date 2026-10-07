# Mide si SponsorBlock valdría la pena: NO construye nada, solo cuenta.
# Junta los videos de YouTube que has visto (youtube.json, progreso.json y, si hay, historial de Takeout)
# y le pregunta a la API por prefijo de hash (4 hex de sha256), así no se revelan los IDs exactos.
# Uso: python3 pruebas/medir_sponsorblock.py [carpeta_datos] [takeout-*.zip]
#   carpeta_datos: por omisión ~/Library/Application Support/cine-roku/datos (solo se lee)
import collections, hashlib, json, re, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path

API = "https://sponsor.ajay.app/api/skipSegments/"
CATEGORIES = ["sponsor", "selfpromo", "interaction", "intro", "outro"]
ID = re.compile(r"[\w-]{11}")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def takeout_ids(zip_path):
    """IDs del historial de reproducciones dentro de un Takeout (watch-history.json / .html)."""
    ids = set()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if "watch-history" not in name and "historial de reproducciones" not in name.lower():
                continue
            text = z.read(name).decode("utf-8", "replace")
            ids.update(re.findall(r"watch\?v=([\w-]{11})", text))
    return ids


def collect(data_dir, takeouts):
    ids, channels = {}, {}
    for h in read_json(data_dir / "youtube.json") or []:
        ids[h["id"]] = h.get("duration") or 0
        channels[h["id"]] = h.get("channel") or ""
    for k in (read_json(data_dir / "progreso.json") or {}).get("progress", {}):
        if k.startswith("yt:") and ID.fullmatch(k[3:]):
            ids.setdefault(k[3:], 0)
    account = read_json(data_dir / "youtube_cuenta.json")
    for h in (account.get("history", []) if isinstance(account, dict) else account or []):
        if isinstance(h, dict) and ID.fullmatch(h.get("id") or ""):
            ids.setdefault(h["id"], 0)
            channels.setdefault(h["id"], h.get("channel") or "")
    for z in takeouts:
        for v in takeout_ids(z):
            ids.setdefault(v, 0)
    return ids, channels


def query(vid):
    """Tramos de ese video (lista de {category, segment:[a,b]}), o [] si no hay. Pregunta por prefijo de hash."""
    prefix = hashlib.sha256(vid.encode()).hexdigest()[:4]
    url = API + prefix + "?categories=" + urllib.parse.quote(json.dumps(CATEGORIES))
    req = urllib.request.Request(url, headers={"User-Agent": "cine-en-casa-medicion"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return next((r["segments"] for r in rows if r.get("videoID") == vid), [])


def main():
    args = sys.argv[1:]
    takeouts = [a for a in args if a.endswith(".zip")]
    dirs = [a for a in args if not a.endswith(".zip")]
    data_dir = Path(dirs[0]) if dirs else Path.home() / "Library" / "Application Support" / "cine-roku" / "datos"
    ids, channels = collect(data_dir, takeouts)
    print(f"Videos de YouTube vistos: {len(ids)}")
    if not ids:
        return
    with_sponsor = with_any = failed = 0
    saved, by_channel = [], collections.Counter()
    for i, vid in enumerate(sorted(ids), 1):
        try:
            segs = query(vid)
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed += 1
            print(f"  ! {i}/{len(ids)} falló: {e}")
            time.sleep(1)
            continue
        if segs:
            with_any += 1
            by_channel[channels.get(vid) or "(canal desconocido)"] += len(segs)
        if any(s.get("category") == "sponsor" for s in segs):
            with_sponsor += 1
        saved.append(sum(max(0, s["segment"][1] - s["segment"][0]) for s in segs))
        time.sleep(0.2)
    n = len(saved)
    if not n:
        print("Ninguna consulta funcionó.")
        return
    print(f"Consultados: {n} (fallaron {failed})")
    print(f"Con al menos un tramo «sponsor»: {with_sponsor} ({100 * with_sponsor / n:.1f} %)")
    print(f"Con cualquier categoría {CATEGORIES}: {with_any} ({100 * with_any / n:.1f} %)")
    print(f"Segundos promedio que se ahorrarían por video: {sum(saved) / n:.1f} s "
          f"(solo entre los que tienen tramos: {sum(saved) / max(1, with_any):.1f} s)")
    print("Canales con más tramos:")
    for name, c in by_channel.most_common(5):
        print(f"  {c:3d}  {name}")


if __name__ == "__main__":
    main()
