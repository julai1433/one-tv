# El instalador de un paso en un NAS (instalar.sh, la parte de Docker): reconoce cada NAS (Synology, Unraid, QNAP,
# TrueNAS SCALE, OpenMediaVault) por sus archivos, elige sus carpetas compartidas y la de datos, arma el comando de
# Docker (red «host», arranque con el NAS, carpetas de solo lectura en la misma ruta, /dev/dri si lo hay), dice cómo
# conseguir Docker donde no se puede instalar desde la terminal, lo instala con el oficial en un Linux común y, al poner
# al día, conserva lo que tenía el de antes. Un One TV de Docker hecho a mano (Portainer, otro nombre, /biblioteca, un
# volumen, -p 8080:8765) se cambia solo si dices que sí, conservando todo eso, y vuelve como estaba si el nuevo no
# arranca; con dos, no se toca nada; en un Linux sin --docker, un One TV de Docker se pone al día ahí. Todo con un
# sistema de archivos falso (ONE_TV_RAIZ) y programas falsos (docker, sudo, curl, ip…): sin red, sin Docker y sin NAS.
# También revisa que los docker-compose de docs/INSTALAR-DOCKER.md monten lo mismo que dicen en ONE_TV_COMPARTIDAS.
# python3 -m unittest discover -s pruebas -p "test_instalador_nas.py"
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALAR = ROOT / "instalar.sh"
BASH = shutil.which("bash") if sys.platform != "win32" else None
PUERTO = "8808"   # nunca el 8765 (el del servidor de verdad)
IMAGEN = "ghcr.io/julai1433/one-tv"


def guion(path, texto, inicio="#!/bin/sh\n"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(inicio + texto + "\n")
    path.chmod(0o755)
    return path


# Un «docker» falso (en Python): anota cada llamada en $LOG y guarda sus contenedores en $DOCKER_ESTADO (JSON:
# nombre → imagen, etiquetas, env, montajes, puertos, red, prendido). Si todavía no hay estado y está DOCKER_HAY, empieza
# con un «one-tv» de la imagen de One TV, con la etiqueta one-tv.instalador DOCKER_ETIQUETA y las variables DOCKER_ENV
# (con \n). DOCKER_APAGADO: no responde; DOCKER_SOLO_ADMIN: solo responde con sudo (CON_SUDO); DOCKER_NO_ARRANCA: el
# contenedor nuevo se crea pero se detiene enseguida.
DOCKER_FALSO = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["LOG"], "a") as f:
    f.write(" ".join(args) + "\n")
if os.environ.get("DOCKER_APAGADO") or (os.environ.get("DOCKER_SOLO_ADMIN") and not os.environ.get("CON_SUDO")
                                        and os.getuid() != 0):
    sys.exit(1)
RUTA = os.environ["DOCKER_ESTADO"]

def cargar():
    if os.path.exists(RUTA):
        with open(RUTA) as f:
            return json.load(f)
    estado = {}
    if os.environ.get("DOCKER_HAY"):
        estado["one-tv"] = {"imagen": "ghcr.io/julai1433/one-tv:latest",
                            "etiquetas": {"one-tv.instalador": os.environ.get("DOCKER_ETIQUETA", "")},
                            "env": os.environ.get("DOCKER_ENV", "").replace("\\n", "\n").split("\n"),
                            "montajes": [], "puertos": {}, "red": "host", "prendido": True}
    return estado

def guardar(estado):
    with open(RUTA, "w") as f:
        json.dump(estado, f)

def mostrar(nombre, c, formato):
    e = c["etiquetas"]
    if "Config.Image" in formato:
        return "/%s|%s|%s|%s\n" % (nombre, c["imagen"], e.get("one-tv.instalador", ""),
                                   e.get("org.opencontainers.image.source", ""))
    if "State.Running" in formato:
        return ("true" if c["prendido"] else "false") + "\n"
    if "Config.Env" in formato:
        return "".join(v + "\n" for v in c["env"]) + "\n"
    if ".Mounts" in formato:
        return "".join("%s|%s|%s|%s\n" % (m["tipo"], m["nombre"], m["origen"], m["destino"])
                       for m in c["montajes"]) + "\n"
    if "PortBindings" in formato:
        return "".join("%s|%s \n" % (p, " ".join(h)) for p, h in c["puertos"].items()) + "\n"
    if "NetworkMode" in formato:
        return c["red"] + "\n"
    if "com.docker.compose.project" in formato:
        return e.get("com.docker.compose.project", "") + "\n"
    return "{}\n"

def crear(args, estado):
    c = {"imagen": "", "etiquetas": {}, "env": [], "montajes": [], "puertos": {}, "red": "bridge",
         "prendido": not os.environ.get("DOCKER_NO_ARRANCA")}
    nombre, i = None, 0
    while i < len(args):
        a = args[i]
        if a in ("--name", "--label", "--network", "--restart", "-e", "-v", "--device", "-p"):
            v = args[i + 1]
            i += 2
            if a == "--name":
                nombre = v
            elif a == "--label":
                k, _, x = v.partition("=")
                c["etiquetas"][k] = x
            elif a == "--network":
                c["red"] = v
            elif a == "-e":
                c["env"].append(v)
            elif a == "-v":
                origen, destino = v.split(":")[:2]
                if origen.startswith("/"):
                    c["montajes"].append({"tipo": "bind", "nombre": "", "origen": origen, "destino": destino})
                else:
                    c["montajes"].append({"tipo": "volume", "nombre": origen, "destino": destino,
                                          "origen": "/var/lib/docker/volumes/%s/_data" % origen})
            elif a == "-p":
                afuera, _, adentro = v.rpartition(":")
                c["puertos"].setdefault(adentro + "/tcp", []).append(afuera)
            continue
        if a.startswith("-"):
            i += 1
            continue
        c["imagen"] = a
        break
    if nombre in estado:
        sys.exit("docker: Error response from daemon: Conflict. The container name is already in use.")
    estado[nombre] = c

estado = cargar()
orden = args[1:] if args[0] == "container" else args
accion, resto = orden[0], orden[1:]
nombres = [a for a in resto if not a.startswith("-")]
falta = [n for n in nombres if n not in estado]
if accion in ("info", "pull", "load", "image"):
    sys.exit(0)
if accion == "ps":
    print("\n".join(estado))
elif accion == "inspect":
    formato = resto[resto.index("-f") + 1] if "-f" in resto else ""
    nombres = [n for n in resto if n != formato and not n.startswith("-")]
    sys.stdout.write("".join(mostrar(n, estado[n], formato) for n in nombres if n in estado))
    if any(n not in estado for n in nombres):
        sys.exit("Error: No such container")
elif accion == "run":
    if os.environ.get("DOCKER_RUN_FALLA"):
        sys.exit("docker: Error response from daemon: algo falló.")
    crear(resto, estado)
elif accion == "logs":
    print("Error: algo salió mal al arrancar")
elif accion in ("stop", "start", "rm", "rename"):
    if falta and accion != "rename":
        sys.exit("Error: No such container")
    if accion == "stop" or accion == "start":
        estado[nombres[0]]["prendido"] = accion == "start"
    elif accion == "rm":
        if estado[nombres[0]]["prendido"] and "-f" not in resto:
            sys.exit("Error: cannot remove a running container")
        del estado[nombres[0]]
    elif accion == "rename":
        viejo, nuevo = nombres
        if viejo not in estado or nuevo in estado:
            sys.exit("Error: no se puede cambiar el nombre")
        estado[nuevo] = estado.pop(viejo)
guardar(estado)
'''

# «sudo» falso: sin contraseña guardada (-n falla), -v la «pide» y lo demás corre tal cual (como administrador).
SUDO_FALSO = r'''
echo "sudo $*" >> "$LOG"
case "$1" in
  -n) exit 1 ;;
  -v) exit 0 ;;
esac
export CON_SUDO=1
exec "$@"
'''

# «curl» falso: file:// se copia (el instalador oficial de Docker de prueba) y /api/status contesta $ESTADO.
CURL_FALSO = r'''
echo "curl $*" >> "$LOG"
salida=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) salida="$2"; shift ;;
    -*) ;;
    *) url="$1" ;;
  esac
  shift
done
case "$url" in
  file://*) cp "${url#file://}" "$salida" ;;
  */api/status) [ -n "$ESTADO" ] || exit 7; echo "$ESTADO" > "$salida" ;;
  *) exit 6 ;;
esac
'''


def contenedor(imagen=IMAGEN + ":latest", etiquetas=None, env=(), montajes=(), puertos=None, red="bridge",
               prendido=True):
    """Un contenedor para el docker falso. montajes: («origen», «destino»); origen sin «/» es un volumen con nombre."""
    return {"imagen": imagen, "etiquetas": dict(etiquetas or {}), "env": ["PATH=/usr/bin", *env],
            "montajes": [{"tipo": "bind", "nombre": "", "origen": o, "destino": d} if o.startswith("/") else
                         {"tipo": "volume", "nombre": o, "origen": f"/var/lib/docker/volumes/{o}/_data", "destino": d}
                         for o, d in montajes],
            "puertos": dict(puertos or {}), "red": red, "prendido": prendido}


@unittest.skipUnless(BASH, "instalar.sh necesita bash")
class InstaladorNas(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.raiz = self.dir / "raiz"
        self.raiz.mkdir()
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.log = self.dir / "llamadas.txt"
        self.log.touch()
        guion(self.bin / "uname", 'echo Linux')
        guion(self.bin / "sudo", SUDO_FALSO)
        guion(self.bin / "curl", CURL_FALSO)
        guion(self.bin / "ip", 'echo "1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.20 uid 1000"')
        guion(self.bin / "sleep", "exit 0")
        for programa in ("service", "systemctl"):   # (nunca el de verdad: arrancaría el Docker de esta computadora)
            guion(self.bin / programa, f'echo "{programa} $*" >> "$LOG"')

    def con_docker(self, contenedores=None):
        """El docker falso en bin/ (y, si se dan, los contenedores que ya tiene)."""
        shutil.copy(self.docker_falso(), self.bin / "docker")
        if contenedores is not None:
            self.estado_docker().write_text(json.dumps({n: contenedor(**c) for n, c in contenedores.items()}))

    def docker_falso(self):
        return guion(self.dir / "docker-falso", DOCKER_FALSO, inicio=f"#!{sys.executable}\n")

    def estado_docker(self):
        return self.dir / "docker.json"

    def contenedores(self):
        """Los contenedores que quedaron en el docker falso."""
        return json.loads(self.estado_docker().read_text()) if self.estado_docker().exists() else {}

    def nas(self, *rutas, archivos=()):
        for r in rutas:
            (self.raiz / r).mkdir(parents=True, exist_ok=True)
        for a in archivos:
            (self.raiz / a).parent.mkdir(parents=True, exist_ok=True)
            (self.raiz / a).write_text("x\n")

    def bash(self, codigo, solo_funciones=True, **env):
        script = (f'ONE_TV_SOLO_FUNCIONES=1 source "{INSTALAR}"\nTMP="{self.dir}"\n' + codigo if solo_funciones
                  else codigo)
        entorno = {"PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.dir / "casa"),
                   "LANG": "C.UTF-8", "ONE_TV_RAIZ": str(self.raiz), "LOG": str(self.log), "TMPDIR": str(self.dir),
                   # que no encuentre el Docker de verdad de la máquina (en GitHub, Ubuntu lo trae): solo el de la prueba
                   "ONE_TV_SOLO_DOCKER_EN": str(self.dir), "DOCKER_ESTADO": str(self.estado_docker()),
                   **env}
        # En una sesión aparte, sin terminal: así nunca se queda esperando una respuesta en la terminal de quien prueba.
        r = subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=entorno, timeout=60,
                           start_new_session=True)
        return r.returncode, r.stdout + r.stderr

    def instalar(self, *args, **env):
        return self.bash(f'bash "{INSTALAR}" {" ".join(args)}', solo_funciones=False, **env)

    def llamadas(self):
        return self.log.read_text()

    def corrida(self):
        """Los argumentos del «docker run» que se hizo (uno por elemento), o None."""
        for linea in self.llamadas().splitlines():
            if linea.startswith("run "):
                return linea.split(" ")
        return None

    # ---------- qué NAS es ----------

    def test_reconoce_cada_nas_por_sus_archivos(self):
        casos = {"synology": ["etc/synoinfo.conf"], "unraid": ["etc/unraid-version"], "qnap": ["etc/config/qpkg.conf"],
                 "omv": ["etc/openmediavault/config.xml"], "": ["etc/os-release"]}
        for esperado, archivos in casos.items():
            shutil.rmtree(self.raiz)
            self.nas(archivos=archivos)
            self.assertEqual(self.bash("que_nas")[1].strip(), esperado, archivos)
        shutil.rmtree(self.raiz)
        guion(self.raiz / "usr" / "bin" / "midclt", "exit 0")   # TrueNAS SCALE: su programa de administración
        self.assertEqual(self.bash("que_nas")[1].strip(), "truenas")
        shutil.rmtree(self.raiz)
        self.nas(archivos=["etc/version"])
        (self.raiz / "etc" / "version").write_text("TrueNAS-SCALE-24.10.2\n")
        self.assertEqual(self.bash("que_nas")[1].strip(), "truenas")

    # ---------- sus carpetas ----------

    def carpetas_y_datos(self, nas):
        code, out = self.bash(f'carpetas_nas {nas}; echo "DATOS=$(datos_nas {nas})"')
        self.assertEqual(code, 0, out)
        lineas = out.strip().splitlines()
        return lineas[:-1], lineas[-1].removeprefix("DATOS=")

    def test_synology_cada_volumen_y_los_datos_en_la_carpeta_docker(self):
        self.nas("volume1/video", "volume2/docker", "volumeUSB1/usbshare", "volume1/@docker")
        self.assertEqual(self.carpetas_y_datos("synology"),
                         (["/volume1", "/volume2", "/volumeUSB1"], "/volume2/docker/one-tv"))
        self.nas("volume1/docker")   # la de Container Manager en el primero: ahí
        self.assertEqual(self.carpetas_y_datos("synology")[1], "/volume1/docker/one-tv")

    def test_unraid_qnap_truenas_y_openmediavault(self):
        self.nas("mnt/user/Peliculas", "mnt/disks/usb", "mnt/disk1")
        self.assertEqual(self.carpetas_y_datos("unraid"), (["/mnt/user", "/mnt/disks"], "/mnt/user/appdata/one-tv"))
        shutil.rmtree(self.raiz / "mnt")
        self.nas("share/CACHEDEV1_DATA/Multimedia")
        self.assertEqual(self.carpetas_y_datos("qnap"), (["/share"], "/share/CACHEDEV1_DATA/docker/one-tv"))
        self.nas("share/Container")
        self.assertEqual(self.carpetas_y_datos("qnap"), (["/share"], "/share/Container/one-tv"))
        self.nas("mnt/tanque/peliculas", "mnt/.ix-apps/docker")   # /mnt/.ix-apps es de las apps: no
        self.assertEqual(self.carpetas_y_datos("truenas"), (["/mnt/tanque"], "/mnt/tanque/docker/one-tv"))
        self.nas("srv/dev-disk-by-uuid-1234/videos", "srv/salt", "srv/pillar")   # salt y pillar son del sistema
        self.assertEqual(self.carpetas_y_datos("omv"),
                         (["/srv/dev-disk-by-uuid-1234"], "/srv/dev-disk-by-uuid-1234/docker/one-tv"))

    def test_otro_linux_las_carpetas_con_algo_y_los_datos_en_tu_carpeta(self):
        self.nas("home/ana/Videos", "mnt", "media/usb")   # /mnt vacía: no
        carpetas, datos = self.carpetas_y_datos("")
        self.assertEqual(carpetas, ["/home", "/media"])
        self.assertEqual(datos, f"{self.dir}/casa/docker/one-tv")

    # ---------- el comando de Docker ----------

    def test_comando_de_docker(self):
        self.nas("dev/dri")
        (self.raiz / "etc").mkdir()
        os.symlink("/usr/share/zoneinfo/America/Mexico_City", self.raiz / "etc" / "localtime")
        code, out = self.bash('armar_docker /volume1/docker/one-tv /volume1 "/volume2/Mis videos"; '
                              'printf "%s\\n" "${ARGS_DOCKER[@]}"', ONE_TV_PUERTO="")
        self.assertEqual(code, 0, out)
        args = out.strip().split("\n")
        self.assertEqual(args[:4], ["run", "-d", "--name", "one-tv"])
        texto = " ".join(args)
        for parte in ("--network host", "--restart unless-stopped", "--label one-tv.instalador=1", "-e PUID=0",
                      "-e PGID=0", "-e TZ=America/Mexico_City", "-v /volume1/docker/one-tv:/datos",
                      "-v /volume1:/volume1:ro", "--device /dev/dri:/dev/dri"):
            self.assertIn(parte, texto)
        self.assertIn("ONE_TV_COMPARTIDAS=/volume1:/volume2/Mis videos", args)   # un solo argumento, con su espacio
        self.assertIn("/volume2/Mis videos:/volume2/Mis videos:ro", args)
        self.assertEqual(args[-1], "ghcr.io/julai1433/one-tv:latest")
        self.assertNotIn("PUERTO=", texto)
        # Sin chip de video, sin --device (Docker no arrancaría el contenedor).
        shutil.rmtree(self.raiz / "dev")
        code, out = self.bash('armar_docker /d /volume1; printf "%s\\n" "${ARGS_DOCKER[@]}"')
        self.assertNotIn("--device", out)

    def test_lo_del_contenedor_de_antes_se_conserva_sin_repetir(self):
        code, out = self.bash('VARIABLES_DE_ANTES="$(printf "ROKU_PASSWORD=mi clave\\nTZ=UTC\\nPUERTO=9000")"; '
                              'armar_docker /d /volume1; printf "%s\\n" "${ARGS_DOCKER[@]}"', ONE_TV_PUERTO="8808")
        args = out.strip().split("\n")
        self.assertIn("ROKU_PASSWORD=mi clave", args)
        self.assertIn("TZ=UTC", args)   # (aquí no se sabe la zona: se queda la de antes)
        self.assertIn("PUERTO=8808", args)
        self.assertNotIn("PUERTO=9000", args)   # una sola vez cada cosa
        self.assertEqual(sum(a.startswith("PUID=") for a in args), 1)

    # ---------- de principio a fin, con un docker falso ----------

    def test_synology_de_principio_a_fin(self):
        self.con_docker()
        self.nas("volume1/docker", "volume1/video", "volume2/musica", archivos=["etc/synoinfo.conf"])
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": true}', ONE_TV_PUERTO=PUERTO)
        self.assertEqual(code, 0, out)
        self.assertIn("en tu Synology con Docker", out)
        self.assertIn("Docker listo", out)
        self.assertIn(f"http://192.168.1.20:{PUERTO}/bienvenida", out)
        self.assertIn("(/volume1, /volume2) solo para leerlas", out)
        self.assertIn("Sus datos quedan en /volume1/docker/one-tv", out)
        run = self.corrida()
        self.assertIsNotNone(run, self.llamadas())
        self.assertIn("/volume1:/volume1:ro", run)
        self.assertIn("/volume2:/volume2:ro", run)
        self.assertIn("ONE_TV_COMPARTIDAS=/volume1:/volume2", run)
        self.assertIn(f"PUERTO={PUERTO}", run)
        self.assertIn("pull -q ghcr.io/julai1433/one-tv:latest", self.llamadas())
        # La primera vez deja pendiente el asistente del navegador (la página principal manda a /bienvenida).
        self.assertIn('"bienvenida_hecha": false', (self.raiz / "volume1/docker/one-tv/config.json").read_text())
        self.assertNotIn("sudo", self.llamadas())   # docker respondió sin sudo: no pidió contraseña

    def test_con_docker_solo_como_administrador_pide_la_contrasena_y_dice_para_que(self):
        self.con_docker()
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": true}', ONE_TV_PUERTO=PUERTO, DOCKER_SOLO_ADMIN="1")
        self.assertEqual(code, 0, out)
        self.assertIn("Te voy a pedir tu contraseña (la de tu usuario de tu Synology) una sola vez, para que Docker "
                      "pueda crear el contenedor de One TV", out)

    def test_ya_instalado_se_pone_al_dia_y_conserva_lo_de_antes(self):
        self.con_docker()
        self.nas("mnt/user/appdata/one-tv", archivos=["etc/unraid-version"])
        (self.raiz / "mnt/user/appdata/one-tv/config.json").write_text('{"bienvenida_hecha": true}\n')
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}', DOCKER_HAY="1", DOCKER_ETIQUETA="1",
                                  DOCKER_ENV="PATH=/usr/bin\\nROKU_PASSWORD=secreta\\nPUERTO=8809\\nPUID=99")
        self.assertEqual(code, 0, out)
        self.assertIn("http://192.168.1.20:8809\n", out)   # ya sin /bienvenida (se terminó), en su puerto de antes
        self.assertNotIn("/bienvenida", out)
        run = self.corrida()
        self.assertIn("ROKU_PASSWORD=secreta", run)
        self.assertIn("PUERTO=8809", run)
        self.assertNotIn("PUID=99", run)
        self.assertIn("rm -f one-tv", self.llamadas())
        self.assertEqual((self.raiz / "mnt/user/appdata/one-tv/config.json").read_text(), '{"bienvenida_hecha": true}\n')

    # ---------- un One TV de Docker hecho a mano ----------

    def synology_con_un_one_tv_a_mano(self, **cambios):
        """Un Synology con un One TV hecho a mano en Portainer: otro nombre, de una versión vieja de la imagen, la
        biblioteca en /biblioteca, sus datos en un volumen con nombre, publicado en el 8080, con su clave del Roku y un
        PUID que no podía leer la biblioteca. Al lado, otro contenedor que no es One TV."""
        self.nas("volume1/docker", "volume1/video", archivos=["etc/synoinfo.conf"])
        viejo = dict(imagen=IMAGEN + ":1.0.40", etiquetas={"com.docker.compose.project": "onetv"},
                     env=["ROKU_PASSWORD=clave del roku", "PUID=1026", "PGID=100", "ONE_TV_COMPARTIDAS=/otra"],
                     montajes=[("onetv_datos", "/datos"), ("/volume1/video", "/biblioteca")],
                     puertos={"8765/tcp": ["8080"]})
        viejo.update(cambios)
        self.con_docker({"onetv-portainer": viejo, "postgres": dict(imagen="postgres:17")})
        return self.contenedores()["onetv-portainer"]

    def test_uno_a_mano_se_cambia_conservando_todo(self):
        self.synology_con_un_one_tv_a_mano()
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}', ONE_TV_RESPUESTA="s")
        self.assertEqual(code, 0, out)
        self.assertIn("· Encontré One TV instalado a mano en Docker (el contenedor «onetv-portainer»).\n"
                      "¿Lo cambio por uno que se pone al día solo? Tus datos y tus carpetas se quedan. [S/n]", out)
        run = self.corrida()
        self.assertIsNotNone(run, self.llamadas())
        texto = " ".join(run)
        for parte in ("--name one-tv", "--label one-tv.instalador=1", "--network host", "-e PUID=0", "-e PGID=0",
                      "-v onetv_datos:/datos",                     # sus datos: el mismo volumen
                      "-v /volume1/video:/biblioteca:ro",           # su biblioteca, donde la busca su configuración
                      "-v /volume1:/volume1:ro", "-e ONE_TV_COMPARTIDAS=/volume1",
                      "-e PUERTO=8080"):                            # donde la TV lo encuentra
            self.assertIn(parte, texto)
        self.assertIn("ROKU_PASSWORD=clave", texto)
        self.assertNotIn("PUID=1026", texto)
        self.assertNotIn("/otra", texto)
        self.assertNotIn("-p ", texto)
        # Primero la imagen nueva; luego se detiene y aparta el viejo; el nuevo; y solo cuando responde, se borra el viejo.
        llamadas = [l for l in self.llamadas().splitlines() if l.split(" ")[0] in ("pull", "stop", "rename", "run", "rm")]
        self.assertEqual([l.split(" ")[0] for l in llamadas], ["pull", "stop", "rename", "run", "rm"], llamadas)
        self.assertEqual(llamadas[2], "rename onetv-portainer one-tv-anterior")
        self.assertEqual(llamadas[4], "rm one-tv-anterior")
        quedan = self.contenedores()
        self.assertEqual(sorted(quedan), ["one-tv", "postgres"])   # el otro contenedor, ni se mira
        self.assertTrue(quedan["one-tv"]["prendido"])
        self.assertIn("http://192.168.1.20:8080\n", out)
        self.assertIn("Cambié tu One TV de antes («onetv-portainer») por este", out)
        self.assertIn("(/volume1, /biblioteca) solo para leerlas", out)
        self.assertIn("Sus datos siguen donde estaban (el volumen «onetv_datos» de Docker)", out)
        self.assertIn("El stack «onetv» (de Portainer o de la app de Docker) ya no hace falta; si lo borras, no borres "
                      "sus datos.", out)
        self.assertFalse((self.raiz / "volume1/docker/one-tv").exists())   # no se inventó otra carpeta de datos
        # Y al volver a correrlo (ya es «nuestro»), lo pone al día sin preguntar y sin perder /biblioteca ni el volumen.
        self.log.write_text("")
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}')
        self.assertEqual(code, 0, out)
        self.assertNotIn("instalado a mano", out)
        texto = " ".join(self.corrida())
        for parte in ("-v onetv_datos:/datos", "-v /volume1/video:/biblioteca:ro", "-e PUERTO=8080",
                      "ROKU_PASSWORD=clave"):
            self.assertIn(parte, texto)
        self.assertEqual(texto.count("/volume1:/volume1:ro"), 1)

    def test_uno_a_mano_que_se_llama_one_tv(self):
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        self.con_docker({"one-tv": dict(imagen=IMAGEN, red="host", env=["NOMBRE=Sala"],
                                        montajes=[("/volume1/docker/onetv", "/datos"), ("/volume1", "/volume1")])})
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}', ONE_TV_RESPUESTA="", ONE_TV_PUERTO=PUERTO)
        self.assertEqual(code, 0, out)   # (Enter, sin escribir nada: es que sí)
        self.assertIn("(el contenedor «one-tv»)", out)
        self.assertIn("rename one-tv one-tv-anterior", self.llamadas())
        self.assertIn("rm one-tv-anterior", self.llamadas())
        texto = " ".join(self.corrida())
        self.assertIn("-v /volume1/docker/onetv:/datos", texto)
        self.assertIn("NOMBRE=Sala", texto)
        self.assertEqual(texto.count("/volume1:/volume1:ro"), 1)   # su /volume1 ya es una de las compartidas
        self.assertEqual(list(self.contenedores()), ["one-tv"])
        self.assertEqual(self.contenedores()["one-tv"]["etiquetas"], {"one-tv.instalador": "1"})
        self.assertIn("Sus datos quedan en /volume1/docker/onetv", out)
        self.assertNotIn("stack", out)   # no venía de un stack

    def test_un_one_tv_llamado_one_tv_sin_terminal_no_se_toca(self):
        self.con_docker()
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        code, out = self.instalar(ESTADO="{}", DOCKER_HAY="1", DOCKER_ETIQUETA="")
        self.assertNotEqual(code, 0)
        self.assertIn("Encontré One TV instalado a mano en Docker (el contenedor «one-tv»)", out)
        self.assertIn("No te puedo preguntar si lo cambio (no hay una terminal), así que no lo toco.", out)
        self.assertIn("corre este mismo comando en una terminal y contesta «s»", out)
        for accion in ("pull", "stop", "rename", "rm", "run"):
            self.assertNotIn(f"\n{accion} ", "\n" + self.llamadas())

    def test_uno_a_mano_sin_terminal_o_con_un_no_no_se_toca(self):
        antes = self.synology_con_un_one_tv_a_mano()
        for respuesta, codigo, frase in ((None, 1, "no hay una terminal"), ("n", 0, "No lo toco"),
                                         ("no", 0, "No lo toco")):
            self.log.write_text("")
            env = {"ONE_TV_RESPUESTA": respuesta} if respuesta is not None else {}
            code, out = self.instalar(ESTADO="{}", **env)
            self.assertEqual(code, codigo, out)
            self.assertIn(frase, out)
            self.assertEqual(self.contenedores()["onetv-portainer"], antes)
            self.assertNotIn("one-tv", self.contenedores())
            for accion in ("pull", "stop", "rename", "rm", "run"):
                self.assertNotIn(f"\n{accion} ", "\n" + self.llamadas())

    def test_si_el_nuevo_no_arranca_el_de_antes_vuelve_tal_cual(self):
        for falla, frase in (("DOCKER_NO_ARRANCA", "One TV no arrancó"),
                             ("DOCKER_RUN_FALLA", "Docker no pudo crear el contenedor de One TV")):
            shutil.rmtree(self.raiz)
            self.raiz.mkdir()
            self.log.write_text("")
            antes = self.synology_con_un_one_tv_a_mano()
            code, out = self.instalar(ONE_TV_RESPUESTA="s", **{falla: "1"})   # (sin ESTADO: el nuevo no responde)
            self.assertNotEqual(code, 0, out)
            self.assertIn(frase, out)
            self.assertIn("Dejé tu One TV de antes («onetv-portainer») como estaba: no cambió nada.", out)
            self.assertEqual(self.contenedores()["onetv-portainer"], antes)   # su nombre, prendido, lo mismo
            self.assertEqual(sorted(self.contenedores()), ["onetv-portainer", "postgres"])
            self.assertIn("rename one-tv-anterior onetv-portainer", self.llamadas())
            self.assertIn("start onetv-portainer", self.llamadas())
        # Si estaba apagado, vuelve apagado.
        shutil.rmtree(self.raiz)
        self.raiz.mkdir()
        self.log.write_text("")
        antes = self.synology_con_un_one_tv_a_mano(prendido=False)
        code, out = self.instalar(ONE_TV_RESPUESTA="s", DOCKER_NO_ARRANCA="1")
        self.assertNotEqual(code, 0, out)
        self.assertEqual(self.contenedores()["onetv-portainer"], antes)
        self.assertNotIn("\nstart ", "\n" + self.llamadas())

    def test_con_dos_one_tv_no_se_toca_nada(self):
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        self.con_docker({"one-tv": dict(etiquetas={"one-tv.instalador": "1"}, red="host"),
                         # (una imagen sin nombre, pero con la etiqueta de la imagen de One TV)
                         "tele-vieja": dict(imagen="sha256:0123abcd", prendido=False, etiquetas={
                             "org.opencontainers.image.source": "https://github.com/julai1433/one-tv"}),
                         "postgres": dict(imagen="postgres:17")})
        antes = self.contenedores()
        code, out = self.instalar(ESTADO="{}", ONE_TV_RESPUESTA="s")
        self.assertNotEqual(code, 0, out)
        self.assertIn("Encontré más de un One TV en Docker («one-tv», «tele-vieja»). Para no romper nada, no toco "
                      "ninguno.", out)
        self.assertIn("Deja solo el que usas", out)
        self.assertEqual(self.contenedores(), antes)
        for accion in ("pull", "stop", "rename", "rm", "run"):
            self.assertNotIn(f"\n{accion} ", "\n" + self.llamadas())

    def test_reconoce_la_imagen_de_one_tv_con_cualquier_version(self):
        si = ["ghcr.io/julai1433/one-tv", "ghcr.io/julai1433/one-tv:latest", "ghcr.io/julai1433/one-tv:1.0.42",
              "ghcr.io/julai1433/one-tv@sha256:0123", "one-tv-prueba:local"]
        no = ["ghcr.io/julai1433/one-tv-otra:latest", "postgres:17", "sha256:0123", "julai1433/one-tv:latest", ""]
        codigo = "; ".join(f'es_imagen_one_tv "{i}" && echo "si {i}" || echo "no {i}"' for i in si + no)
        code, out = self.bash(codigo, ONE_TV_IMAGEN="one-tv-prueba:local")
        self.assertEqual([l.strip() for l in out.strip().splitlines()],
                         [f"si {i}".strip() for i in si] + [f"no {i}".strip() for i in no])

    # ---------- sin Docker ----------

    def test_sin_docker_cada_nas_dice_como_tenerlo(self):
        casos = {"etc/synoinfo.conf": ["Centro de paquetes", "Container Manager", "vuelve a correr este mismo comando"],
                 "etc/config/qpkg.conf": ["App Center", "Container Station"],
                 "etc/unraid-version": ["Enable Docker"]}
        for archivo, frases in casos.items():
            shutil.rmtree(self.raiz)
            self.raiz.mkdir()
            self.nas(archivos=[archivo])
            code, out = self.instalar()
            self.assertNotEqual(code, 0, out)
            for frase in frases:
                self.assertIn(frase, out)
            self.assertNotIn("get.docker.com", self.llamadas())   # en un NAS no se usa el instalador de Linux
        # TrueNAS con Docker apagado (sin «pool» para las apps).
        shutil.rmtree(self.raiz)
        guion(self.raiz / "usr" / "bin" / "midclt", "exit 0")
        self.con_docker()
        code, out = self.instalar(DOCKER_APAGADO="1")
        self.assertNotEqual(code, 0, out)
        self.assertIn("Choose Pool", out)

    def test_linux_comun_instala_docker_con_el_instalador_oficial(self):
        # El «instalador oficial» de prueba deja un docker falso donde lo buscaría el de verdad.
        oficial = guion(self.dir / "get-docker.sh", f'cp "{self.docker_falso()}" "{self.bin}/docker"')
        self.nas("home/ana/Videos")
        code, out = self.instalar("--docker", ESTADO='{"bienvenida_pendiente": true}', ONE_TV_PUERTO=PUERTO,
                                  ONE_TV_DOCKER_OFICIAL=f"file://{oficial}")
        self.assertEqual(code, 0, out)
        self.assertIn("Falta Docker", out)
        self.assertIn("instalador oficial de Docker", out)
        self.assertIn("Te voy a pedir tu contraseña (la de tu usuario de este equipo) una sola vez, para instalar Docker",
                      out)
        self.assertIn("Docker instalado", out)
        self.assertIn(f":{PUERTO}/bienvenida", out)
        self.assertIn("sudo sh", self.llamadas())   # el instalador de Docker corre como administrador
        self.assertIn("/home:/home:ro", self.corrida())

    def test_otro_linux_sin_pedir_docker_con_un_one_tv_en_docker_lo_pone_al_dia_ahi(self):
        self.nas("home/ana/Videos", archivos=["etc/os-release"])
        self.con_docker({"one-tv": dict(etiquetas={"one-tv.instalador": "1"}, red="host",
                                        montajes=[("/home/ana/docker/one-tv", "/datos"), ("/home", "/home")])})
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}', ONE_TV_PUERTO=PUERTO,
                                  ONE_TV_FUENTE="/no/existe.tar.gz", ONE_TV_DIR=str(self.dir / "one-tv"))
        self.assertEqual(code, 0, out)
        self.assertIn("One TV ya está en Docker en este equipo: lo pongo al día ahí, en Docker.", out)
        self.assertNotIn("en esta computadora", out)
        self.assertNotIn("No pude bajar One TV", out)   # no se fue por el camino directo
        self.assertFalse((self.dir / "one-tv").exists())
        texto = " ".join(self.corrida())
        self.assertIn("-v /home/ana/docker/one-tv:/datos", texto)
        self.assertIn("rm -f one-tv", self.llamadas())

    def test_otro_linux_sin_pedir_docker_con_docker_solo_de_administrador(self):
        # Docker pide sudo y hay un One TV de Docker corriendo (se ve en la lista de procesos): pide la contraseña una
        # vez, diciendo para qué, y lo pone al día ahí.
        self.nas("home/ana/Videos", archivos=["etc/os-release"])
        self.con_docker({"one-tv": dict(etiquetas={"one-tv.instalador": "1"}, red="host")})
        guion(self.bin / "ps", 'echo "/usr/bin/tini -- /app/entrypoint.sh"; echo "python3 /app/mac/cine.py servir"')
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": false}', ONE_TV_PUERTO=PUERTO,
                                  DOCKER_SOLO_ADMIN="1", ONE_TV_FUENTE="/no/existe.tar.gz",
                                  ONE_TV_DIR=str(self.dir / "one-tv"))
        self.assertEqual(code, 0, out)
        self.assertIn("Te voy a pedir tu contraseña (la de tu usuario de este equipo) una sola vez, para poner al día "
                      "One TV, que ya está en Docker.", out)
        self.assertIn("lo pongo al día ahí, en Docker", out)
        self.assertIsNotNone(self.corrida())
        # Sin un One TV corriendo, no pide la contraseña: sigue por el camino directo.
        guion(self.bin / "ps", 'echo "/usr/sbin/sshd"')
        code, out = self.instalar(DOCKER_SOLO_ADMIN="1", ONE_TV_FUENTE="/no/existe.tar.gz",
                                  ONE_TV_DIR=str(self.dir / "one-tv"))
        self.assertNotEqual(code, 0)
        self.assertNotIn("contraseña", out)
        self.assertIn("No pude bajar One TV", out)

    def test_otro_linux_sin_pedir_docker_sigue_como_siempre(self):
        self.con_docker()
        self.nas("home/ana/Videos", archivos=["etc/os-release"])
        code, out = self.instalar(ONE_TV_FUENTE="/no/existe.tar.gz", ONE_TV_DIR=str(self.dir / "one-tv"))
        self.assertNotEqual(code, 0)
        self.assertIn("en esta computadora", out)
        self.assertIn("No pude bajar One TV", out)   # el camino directo (sin Docker), cortado aquí a propósito
        self.assertNotIn("Docker", out)
        self.assertEqual(self.llamadas().count("info"), 0)


class ComposeDeLaGuia(unittest.TestCase):
    """Los docker-compose «para pegar» (docs/INSTALAR-DOCKER.md y docker-compose.yml): montan de solo lectura justo lo
    que dicen en ONE_TV_COMPARTIDAS, en la misma ruta, con red host, arranque solo y la carpeta de datos."""

    def bloques(self):
        texto = (ROOT / "docs" / "INSTALAR-DOCKER.md").read_text(encoding="utf-8")
        bloques = [b for b in re.findall(r"```yaml\n(.*?)```", texto, re.S) if "services:" in b]
        bloques.append((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        return bloques

    def test_montan_lo_que_dicen(self):
        bloques = self.bloques()
        self.assertGreaterEqual(len(bloques), 5)   # Synology, QNAP, Unraid, TrueNAS y el del proyecto
        for b in bloques:
            sin_comentarios = "\n".join(l for l in b.splitlines() if not l.strip().startswith("#"))
            compartidas = re.search(r"ONE_TV_COMPARTIDAS:\s*(\S+)", sin_comentarios).group(1).split(":")
            montadas = re.findall(r"^\s*-\s*(\S+):(\S+):ro\s*$", sin_comentarios, re.M)
            self.assertEqual([a for a, _ in montadas], compartidas, b)
            self.assertTrue(all(a == c for a, c in montadas), b)   # en la misma ruta que en el NAS
            self.assertRegex(sin_comentarios, re.compile(r"^\s*-\s*/\S+:/datos\s*$", re.M))
            self.assertIn("network_mode: host", sin_comentarios)
            self.assertIn("restart: unless-stopped", sin_comentarios)
            self.assertIn("image: ghcr.io/julai1433/one-tv:latest", sin_comentarios)


if __name__ == "__main__":
    unittest.main()
