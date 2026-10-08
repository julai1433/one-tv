# Una música de EJEMPLO del tamaño de una biblioteca grande (por omisión ~3 900 artistas, ~7 150 álbumes y 70 000
# canciones, como la de un amigo del dueño), inventada y sin datos de nadie, para medir y probar la sección Música.
#
# - En memoria (pruebas/test_musica_grande.py): llena un Music con lo «ya leído» sin tocar el disco.
# - En disco: python3 pruebas/musica_grande.py CARPETA [canciones]
#   Arma CARPETA/musica (cada canción es un enlace a la misma canción de 3 s, así no ocupa espacio; cada álbum con su
#   portada de un color) y CARPETA/datos/musica.json con las etiquetas ya leídas (no hace falta ffprobe). Para servirla:
#   config «musica»: [CARPETA/musica] y los datos del servidor en CARPETA/datos.
import json, os, random, subprocess, sys, time, zlib
from pathlib import Path
from types import SimpleNamespace

SILABAS = ["la", "luz", "mar", "sol", "ca", "ri", "bo", "te", "an", "dré", "mo", "ña", "el", "ví", "ro", "sa", "ne",
           "gro", "fue", "go", "ti", "em", "po", "cié", "lo", "nu", "be", "río", "ver", "de", "al", "ba", "can", "ción"]
PALABRAS = ["Amor", "Noche", "Ciudad", "Silencio", "Fuego", "Camino", "Ventana", "Lluvia", "Corazón", "Desierto",
            "Mañana", "Recuerdos", "Olvido", "Estrellas", "Viento", "Madrugada", "Espejo", "Distancia", "Río", "Verano",
            "Invierno", "Canción", "Sueños", "Luna", "Tiempo", "Océano", "Raíces", "Danza", "Horizonte", "Café"]
GENEROS = ["Rock", "Pop", "Jazz", "Electrónica", "Clásica", "Cumbia", "Bolero", "Hip hop", "Folk", "Salsa"]
VARIOS = "Varios artistas"


def _nombre(rnd, palabras=(1, 3)):
    return " ".join(rnd.choice(PALABRAS) for _ in range(rnd.randint(*palabras)))


def _artista(rnd):
    def palabra():
        return "".join(rnd.choice(SILABAS) for _ in range(rnd.randint(2, 4))).capitalize()
    return " ".join(palabra() for _ in range(rnd.randint(1, 3)))


def datos(artistas=3851, albumes=7153, canciones=70000, seed=7):
    """[(ruta relativa, info)] como las que deja ffprobe (mac/music.py, probe). Mismo resultado con la misma semilla.
    Un artista «Varios artistas» junta ~300 recopilaciones (miles de canciones): la página más grande."""
    rnd = random.Random(seed)
    nombres = set()
    while len(nombres) < artistas - 1:
        nombres.add(_artista(rnd))
    nombres = sorted(nombres) + [VARIOS]
    # Cuántos álbumes tiene cada artista: casi todos 1 o 2, unos pocos muchos; Varios artistas, ~300.
    por_artista = [1] * artistas
    por_artista[-1] = min(300, albumes - artistas + 1)
    resto = albumes - sum(por_artista)
    while resto > 0:
        i = int(rnd.paretovariate(1.2)) % (artistas - 1)
        por_artista[i] += 1
        resto -= 1
    lista_albumes = []
    for nombre, n in zip(nombres, por_artista):
        usados = set()
        for _ in range(n):
            titulo = _nombre(rnd)
            while titulo in usados:
                titulo = _nombre(rnd)
            usados.add(titulo)
            lista_albumes.append((nombre, titulo, rnd.randint(1965, 2025), rnd.choice(GENEROS)))
    # Canciones por álbum: alrededor de 10 (entre 1 y 30), justas para llegar al total.
    cuantas = [1] * len(lista_albumes)
    resto = canciones - len(lista_albumes)
    while resto > 0:
        i = rnd.randrange(len(lista_albumes))
        if cuantas[i] < 30:
            cuantas[i] += 1
            resto -= 1
    out = []
    for (artista, album, anio, genero), n in zip(lista_albumes, cuantas):
        carpeta = f"{artista}/{album} ({anio})"
        for k in range(1, n + 1):
            titulo = _nombre(rnd, (1, 4))
            interprete = _artista(rnd) if artista == VARIOS else artista
            info = {"title": titulo, "artist": interprete, "album_artist": artista, "album": album, "track": k,
                    "disc": 1, "year": anio, "genre": genero, "duration": round(rnd.uniform(90, 420), 2),
                    "codec": "mp3", "art": False}
            out.append((f"{carpeta}/{k:02d} {titulo}.mp3", info))
    return out


def listas(pistas, seed=7):
    """{nombre: [rutas relativas]}: unas listas .m3u8 (una enorme, de 5 000 canciones)."""
    rnd = random.Random(seed + 1)
    rutas = [p for p, _ in pistas]
    out = {"Para correr": rnd.sample(rutas, 60), "Todo mezclado": rnd.sample(rutas, min(5000, len(rutas)))}
    for i in range(1, 23):
        out[f"Lista {i:02d} · {rnd.choice(PALABRAS)}"] = rnd.sample(rutas, rnd.randint(8, 120))
    return out


def en_memoria(music, **kw):
    """Llena `music` (mac/music.py, Music) con la música grande ya «leída», sin archivos. -> cuántas canciones."""
    root = music.roots[0]
    pistas = datos(**kw)
    stats = {}
    for i, (rel, info) in enumerate(pistas):
        p = root / rel
        # «agregada» en fechas distintas por álbum: así «Agregadas hace poco» tiene un orden claro
        st = SimpleNamespace(st_mtime=1_700_000_000 + zlib.crc32(str(p.parent).encode()) % 10_000_000, st_size=1000 + i)
        stats[p] = st
        music.probes[str(p)] = {"mtime": st.st_mtime, "size": st.st_size, "info": info}
    music._build(stats, [])
    by_path = {t["path"]: t["id"] for t in music.tracks.values()}
    for i, (nombre, rutas) in enumerate(listas(pistas, kw.get("seed", 7)).items()):
        music.playlists.append({"id": f"lista{i:05d}", "title": nombre, "tracks": [by_path[str(root / r)] for r in rutas]})
    music.scanned_at = time.time() + 10 ** 9   # «recién leída»: no vuelve a mirar las carpetas (no existen)
    music._derive()
    return len(music.tracks)


def en_disco(base, canciones=70000):
    base = Path(base)
    root, data = base / "musica", base / "datos"
    root.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    fuente = base / "fuente.mp3"
    if not fuente.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=3",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(fuente)], check=True)
    portadas = []
    for i, color in enumerate(["0x8a2be2", "0x2e8b57", "0xb22222", "0x1e90ff", "0xdaa520", "0x708090",
                               "0xff7f50", "0x20b2aa", "0x9932cc", "0x556b2f", "0xcd5c5c", "0x4682b4"]):
        p = base / f"portada{i}.jpg"
        if not p.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=300x300:d=1",
                            "-frames:v", "1", str(p)], check=True)
        portadas.append(p)
    pistas = datos(canciones=canciones, albumes=max(1, round(canciones / 9.79)), artistas=max(2, round(canciones / 18.18)))
    st = fuente.stat()
    probes, carpetas = {}, set()
    for rel, info in pistas:
        p = root / rel
        if p.parent not in carpetas:
            p.parent.mkdir(parents=True, exist_ok=True)
            carpetas.add(p.parent)
            cover = p.parent / "cover.jpg"
            if not cover.exists():
                os.link(portadas[len(carpetas) % len(portadas)], cover)
        if not p.exists():
            os.link(fuente, p)
        probes[str(p)] = {"mtime": st.st_mtime, "size": st.st_size, "info": info}
    (data / "musica.json").write_text(json.dumps(probes, ensure_ascii=False))
    pl = root / "_Playlists"
    pl.mkdir(exist_ok=True)
    for nombre, rutas in listas(pistas).items():
        (pl / f"{nombre}.m3u8").write_text("#EXTM3U\n" + "\n".join("../" + r for r in rutas) + "\n", encoding="utf-8")
    return root, data, len(pistas)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python3 pruebas/musica_grande.py CARPETA [canciones=70000]")
    root, data, n = en_disco(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 70000)
    print(f"{n} canciones en {root}\nlo ya leído en {data / 'musica.json'}")
