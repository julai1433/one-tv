# Genera zips de Takeout SINTÉTICOS (con IDs reales de canales y videos) para probar mac/ytaccount.py.
# Uso: python3 pruebas/takeout_de_prueba.py <carpeta>   -> deja en <carpeta>:
#   takeout-en.zip (inglés, historial JSON), takeout-es.zip (español, JSON),
#   takeout-en-html.zip / takeout-es-html.zip (historial en HTML, el formato por omisión),
#   takeout-viejo.zip (listas con metadatos arriba en el mismo CSV).
# Los nombres de carpetas y encabezados imitan lo que exporta Google; el formato real no se ha podido
# verificar con un zip auténtico (ver pruebas/LEEME.md).
import json, sys, zipfile
from pathlib import Path

CHANNELS = [  # (id, título) reales
    ("UC_x5XG1OV2P6uZZ5FSM9Ttw", "Google for Developers"), ("UCBJycsmduvYEL83R_U4JriQ", "Marques Brownlee"),
    ("UC8butISFwT-Wl7EV0hUK0BQ", "freeCodeCamp.org"), ("UCsBjURrPoezykLs9EqgamOA", "Fireship"),
    ("UCX6OQ3DkcsbYNE6H8uQQuVA", "MrBeast")]
VIDEOS = [  # (id, título, canal, canal_id)
    ("dQw4w9WgXcQ", "Rick Astley - Never Gonna Give You Up", "Rick Astley", "UCuAXFkgsw1L7xaCfnd5JJOw"),
    ("jNQXAC9IAdw", "Me at the zoo", "jawed", "UC4QobU6STFB0P71PMvOGN5A"),
    ("9bZkp7q19f0", "PSY - GANGNAM STYLE", "officialpsy", "UCrDkAvwZum-UTjHmzDI2iIw"),
    ("kJQP7kiw5Fk", "Luis Fonsi - Despacito ft. Daddy Yankee", "LuisFonsiVEVO", "UCLp8RBhQHu9wSsq62j_Md6A")]
PL = "PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb"
LL = "LLBJycsmduvYEL83R_U4JriQ"
STAMPS = ["2025-03-01T10:00:00+00:00", "2025-03-02T10:00:00+00:00", "2025-03-03T10:00:00+00:00"]

EN = dict(root="Takeout/YouTube and YouTube Music", subs="subscriptions/subscriptions.csv",
          subs_head="Channel Id,Channel Url,Channel Title", pl_dir="playlists", pl_meta="playlists/playlists.csv",
          pl_head="Playlist ID,Add new videos to top of playlist,Playlist Create Timestamp,Playlist Update Timestamp,"
                  "Playlist Video Order,Playlist Visibility,Playlist Title (Original),Playlist Title,"
                  "Playlist Title (Original) Language,Playlist Title Language",
          vid_head="Video ID,Playlist Video Creation Timestamp", list_file="My favorites-videos.csv",
          list_title="My favorites", hist="history/watch-history", watched="Watched", ads="From Google Ads",
          removed="Watched a video that has been removed")
ES = dict(root="Takeout/YouTube y YouTube Music", subs="suscripciones/suscripciones.csv",
          subs_head="ID del canal,URL del canal,Título del canal", pl_dir="listas de reproducción",
          pl_meta="listas de reproducción/listas de reproducción.csv",
          pl_head="ID de la lista de reproducción,Añadir vídeos nuevos al principio de la lista,"
                  "Marca de tiempo de creación de la lista,Marca de tiempo de actualización de la lista,"
                  "Orden de los vídeos,Visibilidad de la lista,Título de la lista (original),"
                  "Título de la lista,Idioma del título (original),Idioma del título",
          vid_head="ID del vídeo,Marca de tiempo de creación del vídeo de la lista",
          list_file="Mis favoritos-vídeos.csv", list_title="Mis favoritos", hist="historial/historial-de-reproducciones",
          watched="Has visto", ads="Desde Google Ads", removed="Has visto un vídeo que se ha eliminado")


# Español de Latinoamérica, copiado de un Takeout real (sep 2026): «playlists», «X videos.csv» y los anuncios
# marcados «De los anuncios de Google».
ES419 = dict(root="Takeout/YouTube y YouTube\xa0Music", subs="suscripciones/suscripciones.csv",
             subs_head="ID del canal,URL del canal,Título del canal", pl_dir="playlists",
             pl_meta="playlists/playlists.csv",
             pl_head="ID de playlist,Agregar los videos nuevos a la parte superior,"
                     "Marca de tiempo de creación de la playlist,Marca de tiempo de actualización de la playlist,"
                     "Orden de la playlist de video,Visibilidad de la playlist,Título de la playlist (original),"
                     "Título de la playlist,Idioma del título de la playlist (original),Idioma del título",
             vid_head="ID de video,Marca de tiempo de creación del video de la playlist",
             list_file="Mis favoritos videos.csv", list_title="Mis favoritos",
             hist="historial de videos/historial de reproducciones", watched="Has visto",
             ads="De los anuncios de Google", removed="Has visto un video que se eliminó")


def history_json(L):
    rows = []
    for i, (vid, title, ch, cid) in enumerate(VIDEOS):
        rows.append({"header": "YouTube", "title": f"{L['watched']} {title}",
                     "titleUrl": f"https://www.youtube.com/watch?v={vid}",
                     "subtitles": [{"name": ch, "url": f"https://www.youtube.com/channel/{cid}"}],
                     "time": f"2025-09-0{i + 1}T12:00:00.000Z", "products": ["YouTube"],
                     "activityControls": ["YouTube watch history"]})
    rows.append({"header": "YouTube", "title": f"{L['watched']} https://www.youtube.com/watch?v=abcdefghijk",
                 "titleUrl": "https://www.youtube.com/watch?v=abcdefghijk", "time": "2025-09-05T12:00:00.000Z"})
    rows.append({"header": "YouTube", "title": L["removed"], "time": "2025-09-06T12:00:00.000Z"})
    rows.append({"header": "YouTube", "title": f"{L['watched']} Un anuncio", "description": "",
                 "titleUrl": "https://www.youtube.com/watch?v=ADSADSADS12",
                 "details": [{"name": L["ads"]}], "time": "2025-09-07T12:00:00.000Z"})
    return json.dumps(rows, ensure_ascii=False, indent=1)


def history_html(L, months):
    cells = []
    for i, (vid, title, ch, cid) in enumerate(VIDEOS):
        when = months(i + 1)
        cells.append(f'<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">'
                     f'<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">YouTube<br></p></div>'
                     f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">{L["watched"]}\xa0'
                     f'<a href="https://www.youtube.com/watch?v={vid}">{title}</a><br>'
                     f'<a href="https://www.youtube.com/channel/{cid}">{ch}</a><br>{when}</div>'
                     f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div>'
                     f'<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;YouTube<br></div>'
                     f'</div></div>')
    cells.append(f'<div class="outer-cell mdl-cell"><div class="mdl-grid"><div class="content-cell mdl-cell">'
                 f'{L["watched"]}\xa0<a href="https://www.youtube.com/watch?v=ADSADSADS12">Anuncio</a><br>'
                 f'Sep 7, 2025, 3:04:05 PM CST</div><div class="content-cell mdl-typography--caption"><b>Products:</b><br>'
                 f'&emsp;YouTube<br><b>Details:</b><br>&emsp;{L["ads"]}<br></div></div></div>')
    cells.append(f'<div class="outer-cell mdl-cell"><div class="mdl-grid"><div class="content-cell mdl-cell">'
                 f'{L["removed"]}<br>Sep 8, 2025, 3:04:05 PM CST</div></div></div>')
    return "<html><body>" + "".join(cells) + "</body></html>"


def build(path, L, hist="json", old=False):
    root = L["root"]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{root}/{L['subs']}", L["subs_head"] + "\n" + "\n".join(
            f"{i},http://www.youtube.com/channel/{i},{t}" for i, t in CHANNELS) + "\n")
        vids = "\n".join(f"{v[0]},{STAMPS[k % 3]}" for k, v in enumerate(VIDEOS[:3]))
        if old:   # formato viejo: metadatos de la lista arriba, en el mismo CSV
            vals = f"{PL},false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Private,{L['list_title']},{L['list_title']},,"
            z.writestr(f"{root}/{L['pl_dir']}/{L['list_file']}", f"{L['pl_head']}\n{vals}\n\n{L['vid_head']}\n{vids}\n")
        else:
            z.writestr(f"{root}/{L['pl_meta']}", f"{L['pl_head']}\n{PL},false,2025-01-01T00:00:00+00:00,"
                       f"2025-01-02T00:00:00+00:00,manual,Private,{L['list_title']},{L['list_title']},,\n"
                       f"{LL},false,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,manual,Private,Liked videos,Liked videos,,\n")
            z.writestr(f"{root}/{L['pl_dir']}/{L['list_file']}", f"{L['vid_head']}\n{vids}\n")
            z.writestr(f"{root}/{L['pl_dir']}/Liked videos-videos.csv", f"{L['vid_head']}\n{VIDEOS[3][0]},{STAMPS[0]}\n")
        z.writestr(f"{root}/channels/channel.csv", "Channel ID,Channel Title (Original),Channel URL,Channel Create Timestamp,Channel Visibility\n"
                   "UCzzzzzzzzzzzzzzzzzzzzzz,Canal Zeta,http://www.youtube.com/channel/UCzzzzzzzzzzzzzzzzzzzzzz,2015-01-01T00:00:00+00:00,Public\n")
        if hist == "json":
            z.writestr(f"{root}/{L['hist']}.json", history_json(L))
        else:
            months = (lambda n: f"Sep {n}, 2025, 3:04:05 PM CST") if L is EN else (lambda n: f"{n} sept 2025, 15:04:05 GMT-6")
            z.writestr(f"{root}/{L['hist']}.html", history_html(L, months))


def build_all(folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    build(folder / "takeout-en.zip", EN); build(folder / "takeout-es.zip", ES)
    build(folder / "takeout-en-html.zip", EN, "html"); build(folder / "takeout-es-html.zip", ES, "html")
    build(folder / "takeout-viejo.zip", EN, old=True)
    build(folder / "takeout-es419.zip", ES419)
    return folder


if __name__ == "__main__":
    print(build_all(sys.argv[1] if len(sys.argv) > 1 else "."))
