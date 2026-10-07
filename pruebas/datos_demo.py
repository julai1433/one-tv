# Biblioteca de ejemplo para mostrar One TV sin usar datos de nadie (capturas, demostraciones, pruebas a ojo).
# Arma, en una carpeta temporal:
#   biblioteca/  películas y una serie de DOMINIO PÚBLICO, con tramos reales de unos 5 min bajados de Internet Archive
#                (solo ese tramo, por HTTP, a 480p) y el código de IMDb o TheTVDB en la carpeta (de ahí salen los pósters)
#   musica/      álbumes con grabaciones CC0 / de dominio público (Musopen y Kimiko Ishizaka en Internet Archive),
#                con etiquetas y portadas hechas con pinturas de dominio público (Wikimedia Commons)
#   estado/      carpeta de datos SIN cuenta de YouTube; solo se le importa un «Takeout» inventado con canales públicos
#   config.json  de ejemplo (sin Roku, sin contraseñas)
# y arranca el servidor de prueba (pruebas/servidor_de_prueba.py) con eso. No toca el servicio real, ni su carpeta
# de datos. Todo lo que se baja queda en una caché FUERA del repositorio (~/Library/Caches/one-tv-demo, o lo que diga
# CINE_DEMO_CACHE); sin internet, las películas y la música caen a videos y tonos sintéticos.
#
# Uso:
#   python3 pruebas/datos_demo.py                       arma la biblioteca y sirve en http://localhost:8793
#                                                       (escucha en toda la red de la casa: otro aparato puede abrirla)
#   python3 pruebas/datos_demo.py servir [carpeta]      igual, en la carpeta que digas (se conserva si ya existe)
#   python3 pruebas/datos_demo.py servir --tv [IP]      además la app del Roku se instala apuntando a esta biblioteca
#   python3 pruebas/datos_demo.py capturas SALIDA       arma, sirve, toma las capturas (Chrome sin ventana), apaga todo
# Variable opcional: CINE_PUERTO (por omisión 8793). Necesita ffmpeg; las capturas, Google Chrome o Brave.
#
# «--tv»: pensado para tomar capturas de la TV con la biblioteca de ejemplo. Usa la IP y la contraseña del modo
# desarrollador de tu config.json (o de ROKU_IP / ROKU_PASSWORD) e INSTALA la app del Roku apuntando al puerto 8793.
# Cuando termines, vuelve a lo de siempre con  ./cine instalar  (la deja apuntando al servidor de verdad).
import base64, csv, hashlib, io, json, os, re, shutil, signal, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("CINE_PUERTO", "8793"))
CACHE = Path(os.environ.get("CINE_DEMO_CACHE") or Path.home() / "Library" / "Caches" / "one-tv-demo")
UA = {"User-Agent": "one-tv-demo/1.0 (https://github.com/julai1433/one-tv; ejemplos de documentación)"}
IA = "https://archive.org/download/{}/{}"
RECORTE = 330        # segundos de cada película o capítulo (el servidor ignora lo que dura menos de 150 s)
CANCION = 240        # segundos máximos de cada pieza de música

# ---- Películas y capítulos de dominio público -------------------------------------------------------------------
# (título, año, código de IMDb, identificador en archive.org, archivo, segundo donde empieza el tramo, doble audio)
# Dominio público en Estados Unidos: las anteriores a 1930 por su fecha de publicación (Nosferatu 1922, Metropolis 1927,
# The General 1926, The Kid 1921, Safety Last! 1923, Sherlock Jr. 1924, Caligari 1920, The Phantom of the Opera 1925 y
# A Trip to the Moon 1902); las demás, por no renovar el registro o no llevar aviso de derechos, según Wikipedia:
# Night of the Living Dead (1968, sin aviso de derechos), His Girl Friday (1940, no se renovó) y Detour (1945).
# Los códigos de IMDb se comprobaron con el buscador de IMDb. «Doble audio»: agrega una segunda pista marcada como
# español (copia de la misma) para que se llene la fila «En español»; es solo un ejemplo.
PELICULAS = [
    ("Nosferatu", 1922, "tt0013442", "Nosferatu_most_complete_version_93_mins.", "Nosferatu_1922_Symphony_of_Horror.avi", 900, True),
    ("Metropolis", 1927, "tt0017136", "Metropolis1927EnglishVersion", "Metropolis_1927_English_Version.mp4", 1500, True),
    ("The General", 1926, "tt0017925", "The_General_Buster_Keaton", "The_General.mp4", 1200, False),
    ("Night of the Living Dead", 1968, "tt0063350", "Night.Of.The.Living.Dead_1080p", "NightOfTheLivingDead_720p.mp4", 900, True),
    ("A Trip to the Moon", 1902, "tt0000417", "ATripToTheMoonGeorgeMelies", "A Trip to the Moon-George Méliès.mp4", 120, False),
    ("His Girl Friday", 1940, "tt0032599", "his_girl_friday", "his_girl_friday.mp4", 1200, True),
    ("The Kid", 1921, "tt0012349", "the-kid-1921_202208", "The Kid 1921.mp4", 600, False),
    ("Safety Last!", 1923, "tt0014429", "SafetyLastHaroldLloyd1923.FullMovieexcellentQuality.",
     "Safety Last - Harold Lloyd 1923. Full movie,excellent quality..mp4", 2400, False),
    ("Sherlock Jr.", 1924, "tt0015324", "MyMovie_20190318", "My Movie.mp4", 600, False),
    ("The Cabinet of Dr. Caligari", 1920, "tt0010323", "thecabinetofdrcaligari", "KabinettDesDoktorCaligariDas.avi", 1200, False),
    ("The Phantom of the Opera", 1925, "tt0016220", "ThePhantomoftheOpera", "Phantom_of_the_Opera.mpeg", 1800, False),
    ("Detour", 1945, "tt0037638", "Detour", "Detour.mp4", 900, False),
]
# Serie: «Our Gang» / «The Little Rascals» (1922-1930, mudas): según Wikipedia, todo lo producido de 1922 a 1930 es
# de dominio público en Estados Unidos. (nombre, año, código de TheTVDB, [(capítulo, título, identificador, archivo, inicio)]);
# los títulos de los capítulos son los de TVmaze.
SERIE = ("The Little Rascals", 1922, "70572", [
    (1, "One Terrible Day", "OneTerribleDay", "04-OurGang_OneTerribleDay1922.mp4", 60),
    (3, "Our Gang", "OurGang-1922", "OurGangSilentFilms-No.1OurGang.mp4", 240),
    (4, "Young Sherlocks", "OurGangSilentYoungSherlocks1922", "sherlockslJoined.mp4", 60),
    (6, "A Quiet Street", "AQuietStreet", "05-ourgang_aquietStreet1922.mp4", 30),
])

# ---- Música de dominio público / CC0 ----------------------------------------------------------------------------
# artista -> [(álbum, año de la obra, archivo de Wikimedia Commons de la portada, [(título, item de archive.org, patrón del archivo)])]
# Grabaciones: Kimiko Ishizaka (CC0, «Open Goldberg Variations» y «Open Well-Tempered Clavier»), Musopen (CC0, «The
# Complete Chopin Collection») y dos tomas con marca de dominio público de Musopen / Paul Pitman (Beethoven). Se usa
# solo el comienzo de cada pieza. Las obras son de Bach (1685-1750), Chopin (1810-49) y Beethoven (1770-1827).
# Portadas, pinturas de dominio público en Wikimedia Commons (autores muertos hace más de 100 años; cada archivo
# dice «Public domain»):
#   Monet, «Impression, soleil levant» (1872)            https://commons.wikimedia.org/wiki/File:Monet_-_Impression,_Sunrise.jpg
#   Hokusai, «La gran ola de Kanagawa» (c. 1831)         https://commons.wikimedia.org/wiki/File:Tsunami_by_hokusai_19th_century.jpg
#   Van Gogh, «La noche estrellada» (1889)               https://commons.wikimedia.org/wiki/File:Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg
#   Klimt, «El beso» (1908)                              https://commons.wikimedia.org/wiki/File:Gustav_Klimt_016.jpg
#   C. D. Friedrich, «El caminante sobre el mar de nubes» (c. 1818)
#                                                        https://commons.wikimedia.org/wiki/File:Caspar_David_Friedrich_-_Wanderer_above_the_sea_of_fog.jpg
GOLDBERG, CLAVE, CHOPIN, BEETHOVEN = "OpenGoldbergVariations", "bach-well-tempered-clavier-book-1", "musopen-chopin", None
MUSICA = {
    "Johann Sebastian Bach": [
        ("Variaciones Goldberg", 1741, "Monet_-_Impression,_Sunrise.jpg", [
            ("Aria", GOLDBERG, r"- 01 Aria\.mp3$"), ("Variación 1", GOLDBERG, r"- 02 Variatio 1 a"),
            ("Variación 2", GOLDBERG, r"- 03 Variatio 2 a"), ("Variación 3, canon al unísono", GOLDBERG, r"- 04 Variatio 3 a")]),
        ("El clave bien temperado, libro I", 1722, "Tsunami_by_hokusai_19th_century.jpg", [
            ("Preludio n.º 1 en do mayor", CLAVE, r"- 01 Prelude No\. 1 in C major.*\.mp3$"),
            ("Fuga n.º 1 en do mayor", CLAVE, r"- 02 Fugue No\. 1 in C major.*\.mp3$"),
            ("Preludio n.º 2 en do menor", CLAVE, r"- 03 Prelude No\. 2 in C minor.*\.mp3$"),
            ("Fuga n.º 2 en do menor", CLAVE, r"- 04 Fugue No\. 2 in C minor.*\.mp3$")]),
    ],
    "Frédéric Chopin": [
        ("Nocturnos", 1832, "Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg", [
            ("Nocturno op. 9 n.º 2", CHOPIN, r"^Nocturne Op\. 9 no\. 2 in E flat major\.mp3$"),
            ("Nocturno op. 15 n.º 1", CHOPIN, r"^Nocturne Op\. 15 no\. 1 In F major\.mp3$"),
            ("Nocturno op. 27 n.º 1", CHOPIN, r"^Nocturne Op\. 27 no\. 1 in C sharp minor\.mp3$"),
            ("Nocturno op. 48 n.º 1", CHOPIN, r"^Nocturne Op\. 48 no\. 1 in C minor\.mp3$")]),
        ("Valses", 1847, "Gustav_Klimt_016.jpg", [
            ("Vals op. 64 n.º 1, «del minuto»", CHOPIN, r"^Waltz Op\. 64 no\. 1 in D flat major\.mp3$"),
            ("Vals op. 64 n.º 2", CHOPIN, r"^Waltz Op\. 64 no\. 2 in C sharp minor\.mp3$"),
            ("Vals op. 69 n.º 1, «del adiós»", CHOPIN, r"^Waltz Op\. 69 no\. 1 in A flat major\.mp3$"),
            ("Vals op. 70 n.º 3", CHOPIN, r"^Waltz Op\. 70 no\. 3 in D flat major\.mp3$")]),
    ],
    "Ludwig van Beethoven": [
        ("Sinfonía n.º 5 y «Claro de luna»", 1808, "Caspar_David_Friedrich_-_Wanderer_above_the_sea_of_fog.jpg", [
            ("Sinfonía n.º 5: Allegro con brio", "SymphonyNo.5", r"\.mp3$"),
            ("Sonata «Claro de luna»: Presto agitato", "MoonlightSonata_845", r"\.mp3$")]),
    ],
}

# ---- Canales de YouTube con contenido libre (suscripciones del «Takeout» inventado) ------------------------------
# (id del canal, título). NASA y el telescopio James Webb publican obras del gobierno de EE. UU. (dominio público);
# ESA y Blender publican bajo licencias abiertas. Los IDs se comprobaron con su RSS público.
CANALES = [
    ("UCLA_DiR1FfKNvjuUpBHmylQ", "NASA"),
    ("UCfi4_aCc2nEhtUMSGqaim_Q", "James Webb Space Telescope (JWST)"),
    ("UCIBaDdAbGlFDeS33shmlD0A", "European Space Agency, ESA"),
    ("UCSMOQeBJ2RAnuFungnQOxLg", "Blender"),
]
# Lo que queda «a medias» en Inicio: (parte del título, segundo en que se quedó)
A_MEDIAS = [("The General", 60), ("Detour", 120), ("Safety Last", 200), ("One Terrible Day", 100), ("The Kid", 150),
            ("Sherlock Jr", 90), ("Caligari", 180)]


def ffmpeg(*args, tolerar=False):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], capture_output=True, text=True)
    if r.returncode and not tolerar:
        sys.exit(f"✗ ffmpeg falló: {r.stderr.strip()[:300]}")
    return r.returncode == 0


def fondo(c0, c1, size="640x360", dur=RECORTE):
    """Un degradado quieto (pesa muy poco): el «video» sintético, cuando no hay internet."""
    return f"gradients=s={size}:d={dur}:c0={c0}:c1={c1}:speed=0:rate=12"


def sintetico(path, c0, c1, hz, doblada):
    tono = lambda f: ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={RECORTE}:sample_rate=44100"]
    pistas = ["-map", "0:v", "-map", "1:a"] + (["-map", "2:a", "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=spa"]
                                                if doblada else [])
    ffmpeg("-f", "lavfi", "-i", fondo(c0, c1), *tono(hz), *(tono(hz * 2) if doblada else []), *pistas,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "34", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k",
           "-ac", "2", "-shortest", "-movflags", "+faststart", path)


def tramo(ident, archivo, inicio, doblada, destino):
    """Baja solo un tramo de la película de Internet Archive (ffmpeg lee por HTTP desde `inicio`), a 480p. Queda en la
    caché; si ya estaba, no vuelve a bajar. -> True si hay un tramo real en `destino`."""
    if destino.exists():
        return True
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = IA.format(ident, urllib.parse.quote(archivo))
    tmp = destino.with_suffix(".tmp.mp4")
    audio = ["-map", "0:v:0", "-map", "0:a:0?"] + (["-map", "0:a:0?", "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=spa"]
                                                  if doblada else [])
    ok = ffmpeg("-ss", inicio, "-i", url, "-t", RECORTE, *audio, "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "29", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-ac", "2", "-movflags", "+faststart",
                tmp, tolerar=True)
    if ok and tmp.exists() and tmp.stat().st_size > 200_000:
        tmp.replace(destino)
        return True
    tmp.unlink(missing_ok=True)
    return False


def video(destino, c0, c1, hz, ident, archivo, inicio, doblada=False):
    destino.parent.mkdir(parents=True, exist_ok=True)
    cache = CACHE / "videos" / f"{ident}-{inicio}{'-es' if doblada else ''}.mp4"
    if tramo(ident, archivo, inicio, doblada, cache):
        shutil.copy2(cache, destino)
        return True
    print(f"  (sin internet o sin ese archivo: «{destino.stem}» queda sintético)", flush=True)
    sintetico(destino, c0, c1, hz, doblada)
    return False


def metadatos(ident):
    try:
        req = urllib.request.Request(f"https://archive.org/metadata/{ident}", headers=UA)
        return json.load(urllib.request.urlopen(req, timeout=40))["files"]
    except (OSError, ValueError, KeyError):
        return []


def portada(archivo, destino):
    """Cuadrado de 600 px con una pintura de dominio público de Wikimedia Commons (en la caché, sin repetir la descarga)."""
    cache = CACHE / "portadas" / (Path(archivo).stem + ".jpg")
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(archivo) + "?width=900"
        try:
            crudo = cache.with_suffix(".src")
            crudo.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
            ok = ffmpeg("-i", crudo, "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=600:600", "-frames:v", "1", "-q:v", "3", cache,
                        tolerar=True)
            crudo.unlink(missing_ok=True)
            if not ok:
                cache.unlink(missing_ok=True)
        except OSError:
            pass
    if cache.exists():
        shutil.copy2(cache, destino)
    else:
        ffmpeg("-f", "lavfi", "-i", fondo("0x2a2a3a", "0x8890b8", "600x600", 1), "-frames:v", "1", "-q:v", "3", destino)


def pista(destino, ident, patron, titulo, artista, album, n, total, anio, hz):
    """Una grabación de dominio público (solo su comienzo) en AAC con etiquetas; sin internet, un tono."""
    cache = CACHE / "musica" / f"{ident}-{hashlib.md5(patron.encode()).hexdigest()[:8]}-{n}.src"
    etiquetas = ["-metadata", f"title={titulo}", "-metadata", f"artist={artista}", "-metadata", f"album_artist={artista}",
                 "-metadata", f"album={album}", "-metadata", f"track={n}/{total}", "-metadata", f"date={anio}"]
    if not cache.exists() and ident:
        nombre = next((f["name"] for f in metadatos(ident) if f["name"].lower().endswith(".mp3") and re.search(patron, f["name"])), None)
        if nombre:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            try:
                tmp.write_bytes(urllib.request.urlopen(urllib.request.Request(IA.format(ident, urllib.parse.quote(nombre)), headers=UA),
                                                       timeout=120).read())
                tmp.replace(cache)
            except OSError:
                tmp.unlink(missing_ok=True)
    if cache.exists() and ffmpeg("-i", cache, "-t", CANCION, "-vn", "-c:a", "aac", "-b:a", "128k", *etiquetas, destino, tolerar=True):
        return True
    ffmpeg("-f", "lavfi", "-i", f"sine=frequency={hz}:duration=20:sample_rate=44100", "-c:a", "aac", "-b:a", "96k", *etiquetas, destino)
    return False


def videos_de(cid, n):
    """Los últimos videos de un canal público (su RSS); [] sin internet."""
    try:
        req = urllib.request.Request(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", headers=UA)
        return re.findall(r"<yt:videoId>([\w-]{11})</yt:videoId>", urllib.request.urlopen(req, timeout=20).read().decode())[:n]
    except OSError:
        return []


LISTAS = [("Espacio y ciencia", "PLespacio00000001", [0, 1, 2]), ("Para ver con calma", "PLcalma0000000002", [1, 3])]   # canales de CANALES


def takeout(destino):
    """Un «Takeout» de YouTube inventado, con el formato real: suscripciones a canales públicos y dos listas hechas
    con videos de esos canales (sin historial)."""
    filas = io.StringIO()
    w = csv.writer(filas, lineterminator="\n")
    w.writerow(["Channel Id", "Channel Url", "Channel Title"])
    for cid, titulo in CANALES:
        w.writerow([cid, f"http://www.youtube.com/channel/{cid}", titulo])
    with zipfile.ZipFile(destino, "w") as z:
        z.writestr("Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv", filas.getvalue())
        z.writestr("Takeout/YouTube and YouTube Music/history/watch-history.json", "[]")
        pr = "Takeout/YouTube and YouTube Music/playlists/"
        recientes = {i: videos_de(c[0], 4) for i, c in enumerate(CANALES)}
        listas = [(t, pid, [v for k in canales for v in recientes[k][:2]]) for t, pid, canales in LISTAS]
        listas = [l for l in listas if l[2]]
        if listas:
            z.writestr(pr + "playlists.csv", "Playlist ID,Add new videos to top of playlist,Playlist Create Timestamp,"
                       "Playlist Update Timestamp,Playlist Video Order,Playlist Visibility,Playlist Title (Original),Playlist Title,"
                       "Playlist Title (Original) Language,Playlist Title Language\n" + "".join(
                           f"{pid},false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Public,{t},{t},,\n"
                           for t, pid, _ in listas))
            for t, pid, vids in listas:
                z.writestr(pr + f"{t}-videos.csv", "Video ID,Playlist Video Creation Timestamp\n" + "".join(
                    f"{v},2025-03-0{1 + k % 9}T10:00:00+00:00\n" for k, v in enumerate(vids)))


def armar(base):
    """Arma la biblioteca de ejemplo en `base` (si ya estaba armada, la deja como está). -> ruta del config.json"""
    base = Path(base)
    lib, music, state = base / "biblioteca", base / "musica", base / "estado"
    marca = base / "armada.txt"
    if not marca.exists():
        reales = 0
        print("Armando la biblioteca de ejemplo (la primera vez baja unos tramos de archive.org; después sale de la caché)…", flush=True)
        colores = [("0x1b2a49", "0x6b7fb0"), ("0x3a2a14", "0xd9a441"), ("0x24421f", "0x9bc27a"), ("0x3b1620", "0xb5546e")]
        for i, (nombre, anio, imdb, ident, archivo, inicio, doblada) in enumerate(PELICULAS):
            c0, c1 = colores[i % 4]
            reales += video(lib / "Películas" / f"{nombre} ({anio}) {{imdb-{imdb}}}" / f"{nombre} ({anio}).mp4", c0, c1, 220 + 30 * i,
                            ident, archivo, inicio, doblada)
            print(f"  ✓ {nombre} ({anio})", flush=True)
        nombre, anio, tvdb, capitulos = SERIE
        for n, titulo, ident, archivo, inicio in capitulos:
            reales += video(lib / "Series" / f"{nombre} ({anio}) {{tvdb-{tvdb}}}" / "Season 01"
                            / f"{nombre} ({anio}) - S01E{n:02d} - {titulo}.mp4", "0x3d2f10", "0xd8b45a", 300 + 30 * n,
                            ident, archivo, inicio)
            print(f"  ✓ {nombre} S01E{n:02d} {titulo}", flush=True)
        pistas, hz = [], 262
        for artista, albumes in MUSICA.items():
            for album, anio, cuadro, piezas in albumes:
                carpeta = music / artista / f"{album} ({anio})"
                carpeta.mkdir(parents=True, exist_ok=True)
                portada(cuadro, carpeta / "cover.jpg")
                for n, (titulo, ident, patron) in enumerate(piezas, 1):
                    archivo = carpeta / f"{n:02d} {titulo.replace('/', '-')}.m4a"
                    reales += pista(archivo, ident, patron, titulo, artista, album, n, len(piezas), anio, hz)
                    hz += 22
                    pistas.append(archivo.relative_to(music))
                print(f"  ✓ {artista}: {album}", flush=True)
        lista = [p for i, p in enumerate(pistas) if i % 3 == 0]
        (music / "Para estudiar.m3u8").write_text("#EXTM3U\n" + "\n".join(str(p) for p in lista) + "\n", encoding="utf-8")
        (state / "datos").mkdir(parents=True, exist_ok=True)   # vacía: sin cuenta de YouTube, sin historial
        (state / "cache").mkdir(parents=True, exist_ok=True)
        takeout(base / "takeout-de-ejemplo.zip")
        marca.write_text(f"Biblioteca de ejemplo de One TV. Piezas reales de dominio público: {reales}.\n", encoding="utf-8")
    config = base / "config.json"
    config.write_text(json.dumps({
        "carpetas": [str(lib)], "puerto": PORT, "roku_ip": "", "roku_password": "", "titulos": {},
        "musica": [str(music)], "descargas": [], "sin_conexion": str(base / "sin_conexion"), "sin_conexion_gb": 1,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def servir(base, tv=None):
    """Arranca el servidor de prueba con la biblioteca de ejemplo (no vuelve hasta que lo apagues con Ctrl + C).
    tv: None = sin TV; "" o una IP = instala la app del Roku apuntando a esta biblioteca."""
    config = armar(base)
    ejemplo = json.loads(config.read_text(encoding="utf-8"))
    os.environ["CINE_PRUEBA"] = str(Path(base) / "estado")
    os.environ["CINE_PUERTO"] = str(PORT)
    sys.path.insert(0, str(ROOT / "mac"))
    import cine
    propia = {}
    if tv is not None:   # la IP y la contraseña de TU Roku, de las variables o de tu config.json (nunca se muestran)
        try:
            propia = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    original = cine.load_config

    def cargar():   # lo del archivo de ejemplo manda sobre cualquier config.json de la casa
        c = original()
        c.update({k: ejemplo[k] for k in ("carpetas", "musica", "descargas", "sin_conexion", "sin_conexion_gb")})
        c["roku_ip"] = tv or os.environ.get("ROKU_IP") or propia.get("roku_ip", "") if tv is not None else ""
        c["roku_password"] = os.environ.get("ROKU_PASSWORD") or propia.get("roku_password", "") if tv is not None else ""
        return c
    cine.load_config = cargar
    iniciar = cine.App.__init__

    def con_ejemplos(self, *a, **k):
        iniciar(self, *a, **k)
        if tv is None:
            class TeleDeEjemplo:   # para que la web se vea con la TV «conectada» (dirección reservada para ejemplos)
                ip = "192.0.2.10"

                def __getattr__(self, _):
                    return lambda *a, **k: None
            self.roku = TeleDeEjemplo()
        import threading

        def youtube():   # canales públicos del «Takeout» inventado y lo nuevo de cada uno (el RSS público de YouTube)
            try:
                self.account.import_zip(Path(base) / "takeout-de-ejemplo.zip")
                self.account.refresh_feeds()
            except Exception:  # noqa: BLE001  (sin internet: la sección sale vacía)
                pass

        def posters():   # el servidor de prueba no calienta nada: aquí sí, los pósters y las sinopsis (necesita internet)
            for _ in range(120):
                if self.library.items:
                    break
                time.sleep(0.5)
            try:
                self.artwork.fetch_all(self.artwork.jobs_for(self.library), log=lambda *_: None)
            except Exception:  # noqa: BLE001  (sin internet: las tarjetas muestran el título)
                pass
            try:
                self.metadata.fetch_all(self.library, log=lambda *_: None)   # sin esto la ficha dice «Sin sinopsis»
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=youtube, daemon=True).start()
        threading.Thread(target=posters, daemon=True).start()
    cine.App.__init__ = con_ejemplos
    print(f"✓ Biblioteca de ejemplo en {base}\n  Servidor de prueba en http://localhost:{PORT}  (Ctrl + C para apagarlo)", flush=True)
    sys.argv = [str(ROOT / "pruebas" / "servidor_de_prueba.py")]
    fuente = (ROOT / "pruebas" / "servidor_de_prueba.py").read_text(encoding="utf-8")
    if tv is not None:   # con la TV de verdad: que sí la busque y le instale la app
        fuente = "\n".join(l for l in fuente.split("\n") if "connect_roku" not in l and "watch_roku" not in l)
    exec(compile(fuente, "servidor_de_prueba.py", "exec"), {"__name__": "__main__", "__file__": str(ROOT / "pruebas" / "servidor_de_prueba.py")})


# ------------------------------------------------------------------ capturas

def capturas(salida):
    sys.path.insert(0, str(ROOT / "mac"))
    from live import CDP, find_chrome
    chrome = find_chrome()
    if not chrome:
        sys.exit("✗ No encontré Google Chrome ni Brave.")
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="one-tv-demo-"))
    perfil = tempfile.mkdtemp(prefix="one-tv-demo-chrome-")
    armar(base)
    server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "servir", str(base)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    proc = None
    try:
        url = f"http://127.0.0.1:{PORT}/"

        def api(ruta, cuerpo=None):
            req = urllib.request.Request(url + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        for _ in range(120):
            try:
                if api("api/status"):
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            sys.exit("✗ El servidor de prueba no arrancó.")
        nuevos = 0
        for _ in range(90):   # lo nuevo de los canales llega por el RSS de YouTube
            try:
                nuevos = len(api("api/yt/subscriptions").get("videos", []))
            except Exception:  # noqa: BLE001
                pass
            if nuevos >= 12:
                break
            time.sleep(1.5)
        print(f"  videos nuevos de los canales: {nuevos}" + ("" if nuevos else "  ⚠ sin internet o YouTube no contestó"), flush=True)
        proc = subprocess.Popen([chrome, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={perfil}", "--no-first-run",
                                 "--mute-audio", "--autoplay-policy=no-user-gesture-required", "--hide-scrollbars", "about:blank"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        puerto_file = Path(perfil) / "DevToolsActivePort"
        for _ in range(100):
            if puerto_file.exists() and puerto_file.read_text().strip():
                break
            time.sleep(0.1)
        cport = int(puerto_file.read_text().split()[0])
        ws = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{cport}/json/version").read())["webSocketDebuggerUrl"]
        movil_ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/18.0 Mobile/15E148 Safari/604.1")

        def sesion(ancho, alto, movil):
            cdp = CDP(ws)
            target = cdp.call("Target.createTarget", {"url": "about:blank"})["targetId"]
            s = cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
            cdp.call("Emulation.setDeviceMetricsOverride", {"width": ancho, "height": alto, "deviceScaleFactor": 2 if movil else 1,
                                                            "mobile": movil}, s)
            if movil:
                cdp.call("Emulation.setUserAgentOverride", {"userAgent": movil_ua}, s)
                cdp.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, s)
            cdp.call("Page.enable", {}, s)
            cdp.call("Runtime.enable", {}, s)

            def js(expr):
                r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, s, timeout=30)
                return None if "exceptionDetails" in r else r.get("result", {}).get("value")

            def ir(hash_, pausa=1.8):
                js(f"location.hash = {json.dumps(hash_)}; true")
                time.sleep(pausa)

            def foto(nombre):
                # Espera a que lleguen las imágenes que ya se pidieron (pósters, portadas, miniaturas) y toma la captura.
                for _ in range(40):
                    if js("[...document.images].filter(i => i.offsetParent && !i.complete).length") == 0:
                        break
                    time.sleep(0.5)
                time.sleep(0.8)
                img = cdp.call("Page.captureScreenshot", {"format": "png"}, s)["data"]
                (salida / nombre).write_bytes(base64.b64decode(img))
                print(f"  ✓ {nombre}", flush=True)
            cdp.call("Page.navigate", {"url": url + "#inicio"}, s)
            for _ in range(60):
                if js("typeof lib !== 'undefined' && !!lib && lib.movies && lib.movies.length > 0") is True:
                    break
                time.sleep(0.5)
            js("localStorage.clear(); true")
            time.sleep(1)
            # Cosas a medias para «Seguir viendo» (en el servidor de ejemplo, no en datos de nadie).
            js("""(async () => { const it = Object.values(lib.items);
              for (const [t, p] of %s) { const x = it.find(i => i.title.includes(t) || (i.full_title || '').includes(t));
                if (x) await fetch('/api/progress', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ id: x.id, p, d: x.duration, ev: 'stop', state: 'pause', device: 'tv' }) }); }
              return true; })()""" % json.dumps(A_MEDIAS))
            # Los pósters se bajan en segundo plano: dales tiempo y recarga la página para verlos.
            for _ in range(40):
                faltan = js("[...Object.values(lib.items).filter(i => i.kind === 'movie'), ...lib.series].filter(x => !(x.art && /v=1/.test(x.art))).length")
                if faltan == 0:
                    break
                time.sleep(1.5)
                cdp.call("Page.reload", {}, s)
                time.sleep(2)
            cdp.call("Page.reload", {}, s)
            time.sleep(3)
            return cdp, s, js, ir, foto

        def tele(js, ir, foto, nombre, cuerpo, movil):
            """La TV reporta (como hace la app): aparece la barra «En la TV» y su panel."""
            api("api/progress", cuerpo)
            js("poll(); true")
            time.sleep(1.5)
            js("document.getElementById('mini').click(); true")
            time.sleep(1.5)
            foto(nombre)
            js("document.getElementById('rm-close').click(); true")
            time.sleep(0.8)

        print("Capturas:")
        cdp, s, js, ir, foto = sesion(1280, 900, False)
        ir("#inicio", 2.5)
        foto("laptop-inicio.png")
        ir("#youtube", 3)
        foto("laptop-youtube.png")

        canal = js("(yt.subscriptions || yt.subs || []).map(c => c.id)[0] || ''") or CANALES[0][0]
        ir(f"#canal={canal}", 4)
        foto("laptop-youtube-canal.png")
        try:
            v = api(f"api/yt/channel?id={canal}")["videos"][1]
            vid, vtitulo = v["id"], v.get("title") or "Video de YouTube"
        except Exception:  # noqa: BLE001
            vid, vtitulo = "", ""
        if vid:
            ir(f"#video={vid}", 3)
            foto("laptop-youtube-video.png")
        ir("#peliculas", 2.5)
        foto("laptop-peliculas.png")
        idn = js("Object.values(lib.items).find(i => i.kind === 'movie' && /Metropolis/.test(i.title)).id")
        ir(f"#ficha={idn}", 3)
        foto("laptop-ficha.png")
        ir("#series", 2.5)
        serie = js("lib.series[0].key")
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 1060, "deviceScaleFactor": 1, "mobile": False}, s)
        ir(f"#serie={urllib.parse.quote(serie)}", 3)
        foto("laptop-serie.png")
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False}, s)
        ir("#musica", 3)
        foto("laptop-musica.png")
        js("loadMusic(); true")
        time.sleep(1.5)
        album = js("(music.albums.find(a => /Nocturnos/.test(a.title)) || music.albums[0]).id")
        ir(f"#album={album}", 3)
        foto("laptop-album.png")
        # Una película reproduciéndose en esta computadora (imagen real).
        ir("#peliculas", 1.5)
        nid = js("Object.values(lib.items).find(i => i.kind === 'movie' && /His Girl Friday/.test(i.title)).id")
        js(f"playHere({json.dumps(nid)}, 40); true")
        time.sleep(5)
        foto("laptop-reproduciendo.png")
        js("document.getElementById('pl-close') && document.getElementById('pl-close').click(); closePlayer && closePlayer(); true")
        time.sleep(1)
        # Una fila de reproducción con de todo: películas, un video de YouTube y canciones.
        api("api/queue/clear", {})
        for tit in ("Safety Last", "The Kid", "Sherlock Jr"):
            x = js("(() => { const x = Object.values(lib.items).find(i => i.title.includes(%s)); return x && x.id; })()" % json.dumps(tit))
            if x:
                api("api/queue/add", {"kind": "item", "id": x})
        if vid:
            api("api/queue/add", {"kind": "yt", "id": vid, "title": vtitulo})
        for tid in js("music.albums.find(a => /Valses/.test(a.title)).tracks.slice(0, 2)") or []:
            api("api/queue/add", {"kind": "track", "id": tid})
        # El panel «En la TV»: primero con una película, luego con música (la TV reporta con POST a /api/progress).
        ir("#inicio", 2)
        peli = js("(() => { const x = Object.values(lib.items).find(i => /Metropolis/.test(i.title)); return {id: x.id, d: x.duration}; })()")
        tele(js, ir, foto, "laptop-tele-pelicula.png", {"id": peli["id"], "p": 140, "d": peli["d"], "ev": "tick", "state": "play"}, False)
        api("api/progress", {"id": peli["id"], "p": 140, "d": peli["d"], "ev": "stop", "state": "pause"})
        pistas = js("music.albums.find(a => /Nocturnos/.test(a.title)).tracks")
        t = js(f"music.tracks[{json.dumps(pistas[1])}]")
        tele(js, ir, foto, "laptop-tele-musica.png",
             {"id": "track:" + t["id"], "p": 70, "d": t["duration"] or 240, "ev": "tick", "state": "play", "song": {"i": 1, "n": len(pistas)}}, False)
        api("api/progress", {"id": "track:" + t["id"], "p": 190, "d": t["duration"] or 240, "ev": "end"})
        cdp.close()

        cdp, s, js, ir, foto = sesion(390, 844, True)
        ir("#inicio", 2.5)
        foto("telefono-inicio.png")
        ir("#youtube", 3)
        foto("telefono-youtube.png")
        ir(f"#canal={canal}", 4)
        foto("telefono-youtube-canal.png")
        if vid:
            ir(f"#video={vid}", 3)
            foto("telefono-youtube-video.png")
        ir("#peliculas", 2.5)
        foto("telefono-peliculas.png")
        ir("#musica", 3)
        foto("telefono-musica.png")
        tele(js, ir, foto, "telefono-tele-musica.png",
             {"id": "track:" + t["id"], "p": 70, "d": t["duration"] or 240, "ev": "tick", "state": "play", "song": {"i": 1, "n": len(pistas)}}, True)
        cdp.close()
    finally:
        for p in (proc,):
            if p:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
        try:
            os.killpg(server.pid, signal.SIGTERM)
        except OSError:
            pass
        server.wait()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(perfil, ignore_errors=True)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "servir"
    if not shutil.which("ffmpeg"):
        sys.exit("✗ Falta ffmpeg (brew install ffmpeg).")
    if cmd == "capturas":
        if len(sys.argv) < 3:
            sys.exit("Uso: python3 pruebas/datos_demo.py capturas CARPETA_DE_SALIDA")
        return capturas(sys.argv[2])
    if cmd == "servir":
        resto = sys.argv[2:]
        tv = None
        if "--tv" in resto:
            i = resto.index("--tv")
            tv = ""
            if i + 1 < len(resto) and re.match(r"^\d+\.\d+\.\d+\.\d+$", resto[i + 1]):
                tv = resto.pop(i + 1)
            resto.pop(i)
        base = Path(resto[0]) if resto else Path(tempfile.mkdtemp(prefix="one-tv-demo-"))
        return servir(base, tv)
    sys.exit("Uso: datos_demo.py [servir [carpeta] [--tv [IP]] | capturas carpeta]")


if __name__ == "__main__":
    main()
