# El instalador de un paso en un NAS (instalar.sh, la parte de Docker): reconoce cada NAS (Synology, Unraid, QNAP,
# TrueNAS SCALE, OpenMediaVault) por sus archivos, elige sus carpetas compartidas y la de datos, arma el comando de
# Docker (red «host», arranque con el NAS, carpetas de solo lectura en la misma ruta, /dev/dri si lo hay), dice cómo
# conseguir Docker donde no se puede instalar desde la terminal, lo instala con el oficial en un Linux común, no toca un
# contenedor «one-tv» ajeno y, al poner al día, conserva lo que tenía el de antes. Todo con un sistema de archivos falso
# (ONE_TV_RAIZ) y programas falsos (docker, sudo, curl, ip…): sin red, sin Docker y sin NAS. También revisa que los
# docker-compose de docs/INSTALAR-DOCKER.md monten lo mismo que dicen en ONE_TV_COMPARTIDAS.
# python3 -m unittest discover -s pruebas -p "test_instalador_nas.py"
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALAR = ROOT / "instalar.sh"
BASH = shutil.which("bash") if sys.platform != "win32" else None
PUERTO = "8808"   # nunca el 8765 (el del servidor de verdad)


def guion(path, texto):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + texto + "\n")
    path.chmod(0o755)
    return path


# Un «docker» falso: anota cada llamada en $LOG y contesta según DOCKER_APAGADO, DOCKER_HAY (ya hay un «one-tv»),
# DOCKER_ETIQUETA (la etiqueta one-tv.instalador de ese) y DOCKER_ENV (sus variables, con \n).
DOCKER_FALSO = r'''
echo "$*" >> "$LOG"
case "$1" in
  info) [ -n "$DOCKER_APAGADO" ] && exit 1; exit 0 ;;
  container)
    case "$*" in *State.Running*) echo true; exit 0 ;; esac
    [ -n "$DOCKER_HAY" ] || exit 1
    case "$*" in
      *one-tv.instalador*) echo "$DOCKER_ETIQUETA" ;;
      *Config.Env*) printf '%b\n' "$DOCKER_ENV" ;;
    esac
    exit 0 ;;
  *) exit 0 ;;
esac
'''

# «sudo» falso: sin contraseña guardada (-n falla), -v la «pide» y lo demás corre tal cual.
SUDO_FALSO = r'''
echo "sudo $*" >> "$LOG"
case "$1" in
  -n) exit 1 ;;
  -v) exit 0 ;;
esac
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

    def con_docker(self):
        guion(self.bin / "docker", DOCKER_FALSO)

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
                   **env}
        r = subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=entorno, timeout=60)
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
        guion(self.bin / "docker", 'case "$1" in info) [ "$(id -u)" = 0 ] || [ -n "$CON_SUDO" ] || exit 1 ;; esac\n'
              + DOCKER_FALSO)
        guion(self.bin / "sudo", 'case "$1" in -n) exit 1 ;; -v) exit 0 ;; esac\nCON_SUDO=1 exec "$@"')
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        code, out = self.instalar(ESTADO='{"bienvenida_pendiente": true}', ONE_TV_PUERTO=PUERTO)
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

    def test_un_contenedor_one_tv_ajeno_no_se_toca(self):
        self.con_docker()
        self.nas("volume1/docker", archivos=["etc/synoinfo.conf"])
        code, out = self.instalar(ESTADO="{}", DOCKER_HAY="1", DOCKER_ETIQUETA="")
        self.assertNotEqual(code, 0)
        self.assertIn("no creó este instalador", out)
        self.assertNotIn("rm -f", self.llamadas())
        self.assertIsNone(self.corrida())

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
        oficial = guion(self.dir / "get-docker.sh", f'cat > "{self.bin}/docker" <<"FIN"\n#!/bin/sh{DOCKER_FALSO}FIN\n'
                        f'chmod +x "{self.bin}/docker"')
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
