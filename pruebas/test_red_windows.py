# Windows: que la TV y el teléfono puedan conectarse (mac/winfirewall.py): cómo se lee lo que dice el firewall, la regla
# «One TV» que se crea (solo el puerto, solo la misma red, cualquier tipo de red), el permiso de administrador una sola
# vez, «cine permitir-red», el aviso en «cine estado», en el registro y en /api/status. Corren en cualquier sistema (lo
# de Windows se simula). Con PowerShell (pwsh o powershell) corren además los guiones de verdad, con los comandos del
# firewall reemplazados por unos falsos: así no cambian nada de la computadora. Sin red.
# python3 -m unittest discover -s pruebas -p "test_red_windows.py"
import base64, io, os, shutil, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mac"))
import cine
import winfirewall

ROOT = Path(__file__).resolve().parent.parent
PWSH = shutil.which("pwsh") or (shutil.which("powershell") if os.name == "nt" else None)


def corrida(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def guion_de(args):
    """El guion de PowerShell que va dentro de un comando hecho por powershell_args (-EncodedCommand)."""
    return base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16-le")


BUENA = "regla|True|Allow|Inbound|TCP|8765|LocalSubnet|Any"


class LeerElFirewall(unittest.TestCase):
    def test_con_la_regla_entra(self):
        self.assertIs(winfirewall.parse(f"perfiles|Domain,Private,Public\n{BUENA}\n", 8765), False)

    def test_sin_regla_esta_bloqueada(self):
        self.assertIs(winfirewall.parse("perfiles|Private,Public\n", 8765), True)

    def test_la_regla_de_otro_puerto_o_apagada_no_sirve(self):
        self.assertIs(winfirewall.parse(f"perfiles|Public\n{BUENA}\n", 8790), True)
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|False|Allow|Inbound|TCP|8765|LocalSubnet|Any", 8765), True)
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|True|Block|Inbound|TCP|8765|LocalSubnet|Any", 8765), True)
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|True|Allow|Outbound|TCP|8765|Any|Any", 8765), True)
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|True|Allow|Inbound|UDP|8765|Any|Any", 8765), True)

    def test_varios_puertos_o_cualquiera(self):
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|True|Allow|Inbound|TCP|8765,8766|LocalSubnet|Any", 8766),
                      False)
        self.assertIs(winfirewall.parse("perfiles|Public\nregla|True|Allow|Inbound|Any|Any|Any|Any", 8765), False)

    def test_firewall_apagado_no_hay_nada_que_abrir(self):
        self.assertIs(winfirewall.parse("perfiles|\n", 8765), False)

    def test_si_no_se_pudo_saber_no_se_asusta_a_nadie(self):
        self.assertIsNone(winfirewall.parse("", 8765))
        self.assertIsNone(winfirewall.parse("Get-NetFirewallRule : Acceso denegado", 8765))
        self.assertIsNone(winfirewall.status(8765, run=lambda *a, **k: corrida(1, "", "no existe")))
        self.assertIsNone(winfirewall.status(8765, run=mock.Mock(side_effect=FileNotFoundError("powershell"))))

    def test_el_guion_que_revisa_no_pide_permisos(self):
        llamadas = []
        winfirewall.status(8765, run=lambda args, **k: llamadas.append(args) or corrida(0, f"perfiles|Public\n{BUENA}"))
        guion = guion_de(llamadas[0])
        self.assertIn("Get-NetFirewallRule -DisplayName 'One TV'", guion)
        self.assertNotIn("RunAs", guion)
        self.assertNotIn("New-NetFirewallRule", guion)
        self.assertIn("-NonInteractive", llamadas[0])


class CrearLaRegla(unittest.TestCase):
    def test_la_regla(self):
        guion = winfirewall.ALLOW.format(port=8799)
        self.assertLess(guion.index("Remove-NetFirewallRule -DisplayName 'One TV'"), guion.index("New-NetFirewallRule"))
        for parte in ("-DisplayName 'One TV'", "-Group 'One TV'", "-Direction Inbound", "-Action Allow",
                      "-Protocol TCP", "-LocalPort 8799", "-RemoteAddress LocalSubnet", "-Profile Any"):
            self.assertIn(parte, guion)

    def test_como_administrador_no_pregunta(self):
        llamadas = []
        error = winfirewall.allow(8799, run=lambda args, **k: llamadas.append(args) or corrida(0), admin=True)
        self.assertEqual(error, "")
        self.assertIn("New-NetFirewallRule", guion_de(llamadas[0]))
        self.assertNotIn("RunAs", guion_de(llamadas[0]))

    def test_sin_ser_administrador_pide_permiso_una_vez(self):
        llamadas = []
        error = winfirewall.allow(8799, run=lambda args, **k: llamadas.append(args) or corrida(0), admin=False)
        self.assertEqual(error, "")
        self.assertEqual(len(llamadas), 1)
        afuera = guion_de(llamadas[0])
        self.assertIn("-Verb RunAs", afuera)
        self.assertIn("-Wait", afuera)
        encoded = afuera.split("'-EncodedCommand','")[1].split("'")[0]
        adentro = base64.b64decode(encoded).decode("utf-16-le")
        self.assertIn("New-NetFirewallRule", adentro)
        self.assertIn("-LocalPort 8799", adentro)

    def test_si_dicen_que_no(self):
        self.assertEqual(winfirewall.allow(8799, run=lambda *a, **k: corrida(winfirewall.CANCELLED), admin=False),
                         "cancelado")
        self.assertIn("no se pudo", winfirewall.allow(8799, run=lambda *a, **k: corrida(1, "", "no se pudo"), admin=True))

    def test_ensure_explica_antes_y_confirma(self):
        respuestas = iter([corrida(0, "perfiles|Public\n"), corrida(0), corrida(0, f"perfiles|Public\n{BUENA}")])
        dichos = []
        self.assertTrue(winfirewall.ensure(8765, say=dichos.append, run=lambda *a, **k: next(respuestas), admin=False))
        self.assertIn("di que sí", dichos[0])
        self.assertIn("TV y tu teléfono", dichos[0])
        self.assertIn("✓ Listo", dichos[-1])

    def test_ensure_sin_permiso_dice_que_hacer(self):
        respuestas = iter([corrida(0, "perfiles|Public\n"), corrida(winfirewall.CANCELLED)])
        dichos = []
        self.assertFalse(winfirewall.ensure(8765, say=dichos.append, run=lambda *a, **k: next(respuestas), admin=False))
        self.assertIn("No se dio el permiso", dichos[-1])
        self.assertIn("cine permitir-red", dichos[-1])

    def test_ensure_con_la_regla_puesta_no_molesta(self):
        dichos = []
        run = mock.Mock(return_value=corrida(0, f"perfiles|Public\n{BUENA}"))
        self.assertTrue(winfirewall.ensure(8765, say=dichos.append, run=run, admin=False))
        self.assertEqual(dichos, [])
        self.assertEqual(run.call_count, 1)


class ComandosDeCine(unittest.TestCase):
    """«cine permitir-red», «cine autoarranque», «cine estado» y el servidor, en Windows (simulado)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conf = Path(tmp.name) / "config.json"
        conf.write_text("{}")
        for p in (mock.patch.object(cine.hostos, "MAC", False), mock.patch.object(cine.hostos, "WINDOWS", True),
                  mock.patch.object(cine.hostos, "SYSTEM", "Windows"), mock.patch.object(cine.hostos, "CINE", "cine"),
                  mock.patch.object(cine, "CONFIG", conf)):
            p.start()
            self.addCleanup(p.stop)

    def main(self, *args, cfg=None):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["cine.py", *args]), \
                mock.patch.object(cine, "load_config", return_value=cfg or {"puerto": 8765}), redirect_stdout(out):
            cine.main()
        return out.getvalue()

    def test_permitir_red(self):
        with mock.patch.object(winfirewall, "status", return_value=True), \
                mock.patch.object(winfirewall, "ensure", return_value=True) as ensure:
            self.main("permitir-red", cfg={"puerto": 8799})
        self.assertEqual(ensure.call_args.args, (8799,))
        with mock.patch.object(winfirewall, "status", return_value=False), mock.patch.object(winfirewall, "ensure") as e:
            self.assertIn("ya deja que la TV y el teléfono se conecten", self.main("permitir-red"))
        e.assert_not_called()
        with mock.patch.object(winfirewall, "status", return_value=True), \
                mock.patch.object(winfirewall, "ensure", return_value=False), self.assertRaises(SystemExit):
            self.main("permitir-red")

    def test_permitir_red_fuera_de_windows(self):
        with mock.patch.object(cine.hostos, "WINDOWS", False), mock.patch.object(cine.hostos, "SYSTEM", "macOS"), \
                mock.patch.object(winfirewall, "ensure") as ensure:
            self.assertIn("solo hace falta en Windows", self.main("permitir-red"))
        ensure.assert_not_called()

    def test_autoarranque_pide_el_permiso_antes(self):
        orden = []
        with mock.patch.object(winfirewall, "ensure", lambda port, say=print: orden.append(("firewall", port)) or True), \
                mock.patch.object(cine, "install_service", lambda cfg: orden.append("tarea")), \
                mock.patch.object(cine, "wait_for_server", return_value=None), \
                mock.patch.object(cine, "print_status"):
            self.main("autoarranque", cfg={"puerto": 8799})
        self.assertEqual(orden, [("firewall", 8799), "tarea"])
        orden.clear()
        with mock.patch.object(winfirewall, "ensure", lambda port, say=print: orden.append("firewall") or True), \
                mock.patch.object(cine, "install_service", lambda cfg: orden.append("tarea")), \
                mock.patch.object(cine, "wait_for_server", return_value=None), mock.patch.object(cine, "print_status"):
            self.main("autoarranque", cfg={"puerto": 8799, "escuchar": "127.0.0.1"})   # solo esta computadora
        self.assertEqual(orden, ["tarea"])

    def test_el_instalador_pide_el_permiso_antes_de_la_tarea(self):
        orden = []
        with mock.patch.object(winfirewall, "ensure", lambda port, say=print: orden.append(("firewall", port)) or True), \
                mock.patch.object(cine, "install_service", lambda cfg: orden.append("tarea")), \
                mock.patch.object(cine, "service_installed", return_value=False), \
                mock.patch.object(cine.windowsservice, "problem", return_value=""), \
                mock.patch.object(cine, "wait_for_server", return_value={"items": 0}), \
                mock.patch.object(cine, "load_config", return_value={"puerto": 8799, "bienvenida_hecha": False}), \
                mock.patch.object(cine.hostos, "lan_url", return_value=None), \
                mock.patch.object(cine.hostos, "open_browser", lambda url: orden.append(url) or True), \
                mock.patch.dict(os.environ, {"ONE_TV_SIN_AUTOARRANQUE": "", "CINE_NO_BROWSER": ""}), \
                redirect_stdout(io.StringIO()):
            cine.finish_install({"puerto": 8799, "bienvenida_hecha": False})
        self.assertEqual(orden, [("firewall", 8799), "tarea", "http://localhost:8799/bienvenida"])

    def test_estado_avisa(self):
        out = io.StringIO()
        with mock.patch.object(cine, "service_pid", return_value=None), \
                mock.patch.object(cine, "service_installed", return_value=False), \
                mock.patch.object(winfirewall, "status", return_value=True), redirect_stdout(out):
            cine.print_status({"puerto": 8765}, None)
        self.assertIn("Windows bloquea la entrada. Corre «cine permitir-red»", out.getvalue())
        out = io.StringIO()
        with mock.patch.object(cine, "service_pid", return_value=None), \
                mock.patch.object(cine, "service_installed", return_value=False), \
                mock.patch.object(winfirewall, "status", return_value=None), redirect_stdout(out):
            cine.print_status({"puerto": 8765}, None)
        self.assertNotIn("bloquea", out.getvalue())   # sin saberlo, no se asusta a nadie

    def test_el_servidor_lo_dice_en_el_registro_y_en_el_estado(self):
        dichos = []
        app = mock.Mock(spec=["cfg", "network_blocked"])
        app.cfg = {"puerto": 8765}
        app.network_blocked = False
        revisiones = iter([True, False])
        with mock.patch.object(winfirewall, "status", lambda port: next(revisiones)), \
                mock.patch.object(cine, "say", dichos.append), mock.patch.object(cine.time, "sleep"):
            cine.App.watch_firewall(app)
        self.assertEqual(dichos, [f"⚠ {winfirewall.BLOCKED}", "✓ Windows ya deja que la TV y el teléfono se conecten."])
        self.assertIs(app.network_blocked, False)


@unittest.skipUnless(PWSH, "hace falta PowerShell (pwsh)")
class GuionesDePowerShell(unittest.TestCase):
    """Los guiones de verdad, con los comandos del firewall y Start-Process reemplazados por unos falsos."""

    FALSOS = r"""
function Get-NetFirewallProfile { @([pscustomobject]@{Name='Domain'; Enabled='False'}, [pscustomobject]@{Name='Private'; Enabled='True'}, [pscustomobject]@{Name='Public'; Enabled='True'}) }
function Get-NetFirewallRule { param($DisplayName, $ErrorAction) $env:REGLAS -split ';' | Where-Object { $_ } | ForEach-Object { $c = $_ -split ','; [pscustomobject]@{Enabled=$c[0]; Action=$c[1]; Direction='Inbound'; Profile='Any'; Port=$c[2]} } }
function Get-NetFirewallPortFilter { process { [pscustomobject]@{Protocol='TCP'; LocalPort=$_.Port} } }
function Get-NetFirewallAddressFilter { process { [pscustomobject]@{RemoteAddress='LocalSubnet'} } }
"""

    def correr(self, guion, **env):
        args = winfirewall.powershell_args(guion)
        args[0] = PWSH
        r = subprocess.run(args, capture_output=True, text=True, timeout=120, env={**os.environ, **env})
        return r.returncode, r.stdout, r.stderr

    def test_revisar(self):
        code, out, err = self.correr(self.FALSOS + winfirewall.CHECK, REGLAS="True,Allow,8765")
        self.assertEqual(code, 0, err)
        self.assertIs(winfirewall.parse(out, 8765), False)
        self.assertIs(winfirewall.parse(out, 8790), True)
        code, out, err = self.correr(self.FALSOS + winfirewall.CHECK, REGLAS="")
        self.assertIs(winfirewall.parse(out, 8765), True, out + err)

    def test_pedir_permiso(self):
        falso = r"""
function Start-Process { param($FilePath, $Verb, $WindowStyle, [switch]$Wait, [switch]$PassThru, $ArgumentList)
  if ($env:NEGAR) { throw 'La operación fue cancelada por el usuario.' }
  $adentro = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($ArgumentList[-1]))
  Write-Host "VERBO=$Verb"   # (Write-Host: lo de Write-Output quedaría dentro de $p)
  Write-Host $adentro
  [pscustomobject]@{ExitCode = 0}
}
"""
        guion = falso + winfirewall.elevated_script(8799)
        code, out, err = self.correr(guion)
        self.assertEqual(code, 0, err)
        self.assertIn("VERBO=RunAs", out)
        self.assertIn("-LocalPort 8799 -RemoteAddress LocalSubnet -Profile Any", out)
        code, _, _ = self.correr(guion, NEGAR="1")
        self.assertEqual(code % 256, winfirewall.CANCELLED % 256)   # (fuera de Windows, el código de salida es de 8 bits)

    def test_los_guiones_de_windows_se_leen_sin_errores(self):
        for archivo in (ROOT / "windows" / "instalar.ps1", ROOT / "windows" / "cine.ps1"):
            guion = ("$errores = $null; [System.Management.Automation.Language.Parser]::ParseFile('"
                     + str(archivo).replace("'", "''") + "', [ref]$null, [ref]$errores) | Out-Null; "
                     "$errores | ForEach-Object { $_.Message }; exit $errores.Count")
            code, out, err = self.correr(guion)
            self.assertEqual(code, 0, f"{archivo.name}: {out}{err}")


@unittest.skipUnless(os.name == "nt", "solo en Windows de verdad")
class EnWindowsDeVerdad(unittest.TestCase):
    def test_se_puede_revisar_sin_cambiar_nada(self):
        self.assertIn(winfirewall.status(8765), (True, False))


if __name__ == "__main__":
    unittest.main()
