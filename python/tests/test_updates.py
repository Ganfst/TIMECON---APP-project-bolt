"""Pruebas del gestor de versiones (manifiesto, descarga verificada e instalación)."""
import hashlib
import json
import os
import runpy
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from radio_timer import __version__, updates


def make_release_zip(path: Path, version: str, extra: tuple = ()) -> tuple[str, int]:
    """Crea un ZIP con la forma de un paquete de la app y devuelve (sha256, tamaño)."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("radio_timer/__init__.py", f'__version__ = "{version}"\n')
        archive.writestr("radio_timer/app.py", f"# código de la versión {version}\n")
        archive.writestr("run.py", f"# arranque {version}\n")
        for name, data in extra:
            archive.writestr(name, data)
    body = path.read_bytes()
    return hashlib.sha256(body).hexdigest(), len(body)


def publish(folder: Path, version: str, **overrides) -> dict:
    """Publica una versión en una carpeta local: ZIP + entrada en updates.json."""
    zip_path = folder / f"radio-timer-{version}.zip"
    sha, size = make_release_zip(zip_path, version)
    entry = {"version": version, "date": "2026-09-20", "title": f"Versión {version}",
             "notes": {"nuevo": [f"Función de {version}"]},
             "file": zip_path.name, "sha256": sha, "size": size}
    entry.update(overrides)
    manifest_path = folder / "updates.json"
    manifest = {"app": "radio-timer", "releases": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["releases"].insert(0, entry)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return entry


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updates.parse_version("3.2.0"), (3, 2, 0))
        self.assertEqual(updates.parse_version("3.10"), (3, 10))
        self.assertEqual(updates.parse_version("3.2.1-beta"), (3, 2, 1))
        self.assertEqual(updates.parse_version("beta"), ())

    def test_compare_versions(self):
        self.assertGreater(updates.compare_versions("3.10.0", "3.2.0"), 0)
        self.assertLess(updates.compare_versions("3.2", "3.2.1"), 0)
        self.assertEqual(updates.compare_versions("3.2.0", "3.2"), 0)

    def test_prerelease_ordering_follows_semver(self):
        ordered = ["3.3.0", "3.3.1-dev.2", "3.3.1-dev.10", "3.3.1-rc.1", "3.3.1", "3.4.0-dev.1", "3.4.0"]
        self.assertEqual(sorted(reversed(ordered), key=updates.version_key), ordered)
        self.assertGreater(updates.compare_versions("3.4.0", "3.4.0-rc1"), 0)   # la final supera a la rc
        self.assertEqual(updates.parse_version("3.3.1-dev.57"), (3, 3, 1))
        self.assertTrue(updates.is_prerelease_version("3.3.1-dev.57"))
        self.assertFalse(updates.is_prerelease_version("3.3.1"))

    def test_next_dev_version(self):
        self.assertEqual(updates.next_dev_version("3.3.0", 57), "3.3.1-dev.57")
        self.assertEqual(updates.next_dev_version("3.4", 1), "3.4.1-dev.1")
        self.assertEqual(updates.next_dev_version("3.4.0-rc.1", 3), "3.4.0-dev.3")
        # Una compilación de desarrollo siempre supera a la estable de la que parte.
        self.assertGreater(updates.compare_versions(updates.next_dev_version("3.3.0", 1), "3.3.0"), 0)


class ShouldCheckTests(unittest.TestCase):
    NOW = datetime(2026, 9, 14, 10, 0, 0)

    def test_manual_never_checks(self):
        self.assertFalse(updates.should_check("", "manual", self.NOW))
        self.assertFalse(updates.should_check("", "otra-cosa", self.NOW))

    def test_daily_and_weekly(self):
        self.assertTrue(updates.should_check("", "daily", self.NOW))
        self.assertFalse(updates.should_check("2026-09-13T11:00:00", "daily", self.NOW))   # hace 23 h
        self.assertTrue(updates.should_check("2026-09-13T09:00:00", "daily", self.NOW))    # hace 25 h
        self.assertFalse(updates.should_check("2026-09-08T10:00:01", "weekly", self.NOW))  # hace 6 días
        self.assertTrue(updates.should_check("2026-09-07T10:00:00", "weekly", self.NOW))   # hace 7 días

    def test_bad_stamp_checks_again(self):
        self.assertTrue(updates.should_check("no es una fecha", "daily", self.NOW))


class ManifestTests(unittest.TestCase):
    def test_parse_sorts_and_skips_broken_entries(self):
        releases = updates.parse_manifest({"releases": [
            {"version": "1.0.0", "file": "a.zip", "sha256": "0" * 64, "date": "2026-01-01"},
            {"version": "2.0.0", "file": "b.zip", "sha256": "1" * 64, "date": "2026-02-01",
             "title": "Grande", "size": 123,
             "notes": {"nuevo": ["Una función", "  otra  función  "], "arreglado": ["Un fallo"],
                       "cambiado": [], "ignorado": ["x"]}},
            {"version": "3.0.0", "file": "c.zip", "sha256": "corto"},          # hash inválido
            {"version": "", "file": "d.zip", "sha256": "2" * 64},              # sin versión
            "basura",
        ]})
        self.assertEqual([release.version for release in releases], ["2.0.0", "1.0.0"])
        self.assertEqual(releases[0].notes_lines(), [
            ("Nuevo", "Una función"), ("Nuevo", "otra función"), ("Arreglado", "Un fallo"),
        ])
        self.assertEqual(releases[0].size, 123)

    def test_prerelease_flag_and_channels(self):
        releases = updates.parse_manifest({"releases": [
            {"version": "3.3.1-dev.4", "file": "a.zip", "sha256": "0" * 64},
            {"version": "3.3.0", "file": "b.zip", "sha256": "1" * 64},
            {"version": "3.3.5", "file": "c.zip", "sha256": "2" * 64, "prerelease": True},
        ]})
        self.assertEqual([(r.version, r.prerelease) for r in releases],
                         [("3.3.5", True), ("3.3.1-dev.4", True), ("3.3.0", False)])
        stable = updates.for_channel(releases, "stable")
        self.assertEqual([r.version for r in stable], ["3.3.0"])
        self.assertEqual(updates.first_newer(stable, current="3.3.0"), None)
        self.assertEqual(updates.first_newer(updates.for_channel(releases, "dev"), current="3.3.0").version, "3.3.5")
        # Quien está en una compilación de desarrollo recibe la estable siguiente en el canal Estable.
        releases.append(updates.Release(version="3.3.1", date="", title="", file="d.zip", sha256="3" * 64))
        self.assertEqual(updates.first_newer(updates.for_channel(
            sorted(releases, key=lambda r: updates.version_key(r.version), reverse=True), "stable"),
            current="3.3.1-dev.4").version, "3.3.1")

    def test_bad_shapes_are_rejected(self):
        for bad in (None, [], {}, {"releases": "no"}):
            with self.assertRaises(updates.UpdateError):
                updates.parse_manifest(bad)

    def test_first_newer(self):
        releases = updates.parse_manifest({"releases": [
            {"version": "9.9.0", "file": "a.zip", "sha256": "0" * 64},
            {"version": "0.1.0", "file": "b.zip", "sha256": "1" * 64},
        ]})
        self.assertEqual(updates.first_newer(releases).version, "9.9.0")
        self.assertIsNone(updates.first_newer(releases, current="9.9.0"))
        self.assertIsNone(updates.first_newer([]))

    def test_locations_and_sizes(self):
        self.assertEqual(updates._manifest_location("https://x.com/app"), "https://x.com/app/updates.json")
        self.assertEqual(updates._manifest_location("https://x.com/app/updates.json"),
                         "https://x.com/app/updates.json")
        self.assertEqual(updates._resolve_file("https://x.com/app", "r-1.zip"), "https://x.com/app/r-1.zip")
        self.assertEqual(updates._resolve_file("https://x.com/app", "https://cdn.x.com/r.zip"),
                         "https://cdn.x.com/r.zip")
        self.assertEqual(updates.format_size(0), "")
        self.assertEqual(updates.format_size(51_200), "50 KB")
        self.assertEqual(updates.format_size(3 * 1024 * 1024), "3.0 MB")
        with self.assertRaises(updates.UpdateError):
            updates._manifest_location("   ")


class LocalSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_and_download_from_a_folder(self):
        publish(self.folder, "2.0.0")
        publish(self.folder, "2.1.0")
        releases = updates.fetch_releases(str(self.folder))
        self.assertEqual([release.version for release in releases], ["2.1.0", "2.0.0"])
        dest = self.folder / "descargas"
        zip_path = updates.download_release(releases[0], str(self.folder), dest)
        self.assertTrue(zip_path.exists())
        self.assertEqual(updates.packaged_version(zip_path), "2.1.0")
        # También sirve apuntar directo al archivo updates.json.
        again = updates.fetch_releases(str(self.folder / "updates.json"))
        self.assertEqual(len(again), 2)

    def test_tampered_package_is_rejected(self):
        publish(self.folder, "2.0.0", sha256="f" * 64)
        release = updates.fetch_releases(str(self.folder))[0]
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.download_release(release, str(self.folder), self.folder / "d")
        self.assertIn("verificación de integridad", str(ctx.exception))

    def test_wrong_size_is_rejected(self):
        publish(self.folder, "2.0.0", size=1)
        release = updates.fetch_releases(str(self.folder))[0]
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.download_release(release, str(self.folder), self.folder / "d")
        self.assertIn("tamaño", str(ctx.exception))

    def test_missing_folder_gives_readable_error(self):
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.fetch_manifest(str(self.folder / "no-existe"))
        self.assertIn("No se pudo leer", str(ctx.exception))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app_dir = root / "app"
        (self.app_dir / "radio_timer").mkdir(parents=True)
        (self.app_dir / "radio_timer" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        (self.app_dir / "radio_timer" / "obsoleto.py").write_text("# módulo viejo\n", encoding="utf-8")
        (self.app_dir / "run.py").write_text("# arranque 1.0.0\n", encoding="utf-8")
        (self.app_dir / "datos.txt").write_text("no me toques\n", encoding="utf-8")
        self.backups = root / "backups"
        self.zip_path = root / "radio-timer-2.0.0.zip"
        make_release_zip(self.zip_path, "2.0.0")

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_replaces_backs_up_and_preserves(self):
        replaced = updates.install_release(self.zip_path, self.app_dir, self.backups, expect_version="2.0.0")
        self.assertEqual(replaced, ["radio_timer", "run.py"])
        self.assertIn("2.0.0", (self.app_dir / "radio_timer" / "__init__.py").read_text(encoding="utf-8"))
        self.assertIn("2.0.0", (self.app_dir / "run.py").read_text(encoding="utf-8"))
        # El módulo que la versión nueva ya no trae desaparece (la carpeta se reemplaza completa)...
        self.assertFalse((self.app_dir / "radio_timer" / "obsoleto.py").exists())
        # ...lo ajeno al paquete se conserva, y lo anterior queda respaldado.
        self.assertEqual((self.app_dir / "datos.txt").read_text(encoding="utf-8"), "no me toques\n")
        backup = self.backups / "v1.0.0"
        self.assertTrue((backup / "radio_timer" / "obsoleto.py").exists())
        self.assertIn("1.0.0", (backup / "run.py").read_text(encoding="utf-8"))

    def test_version_mismatch_leaves_the_app_intact(self):
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.install_release(self.zip_path, self.app_dir, self.backups, expect_version="9.9.9")
        self.assertIn("dice ser v2.0.0", str(ctx.exception))
        self.assertIn("1.0.0", (self.app_dir / "radio_timer" / "__init__.py").read_text(encoding="utf-8"))
        self.assertTrue((self.app_dir / "radio_timer" / "obsoleto.py").exists())

    def test_unsafe_paths_are_rejected(self):
        for evil in ("../fuera.py", "C:/absoluto.py", "/raiz.py", "sub/../../fuera.py"):
            bad = Path(self.tmp.name) / "malo.zip"
            with zipfile.ZipFile(bad, "w") as archive:
                archive.writestr("radio_timer/__init__.py", '__version__ = "2.0.0"\n')
                archive.writestr(evil, "peligro")
            with self.assertRaises(updates.UpdateError) as ctx:
                updates.install_release(bad, self.app_dir, self.backups)
            self.assertIn("ruta insegura", str(ctx.exception))

    def test_zip_without_the_app_is_rejected(self):
        bad = Path(self.tmp.name) / "vacio.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("run.py", "# nada")
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.install_release(bad, self.app_dir, self.backups)
        self.assertIn("no contiene la aplicación", str(ctx.exception))

    def test_corrupt_zip_is_rejected(self):
        bad = Path(self.tmp.name) / "roto.zip"
        bad.write_bytes(b"esto no es un zip")
        with self.assertRaises(updates.UpdateError):
            updates.install_release(bad, self.app_dir, self.backups)

    def test_two_backups_do_not_collide(self):
        updates.install_release(self.zip_path, self.app_dir, self.backups)
        make_release_zip(self.zip_path, "2.0.0")
        updates.install_release(self.zip_path, self.app_dir, self.backups)
        names = sorted(path.name for path in self.backups.iterdir())
        self.assertEqual(names, ["v1.0.0", "v2.0.0"])
        make_release_zip(self.zip_path, "2.0.0")
        updates.install_release(self.zip_path, self.app_dir, self.backups)
        self.assertIn("v2.0.0-2", {path.name for path in self.backups.iterdir()})


class MakeReleaseToolTests(unittest.TestCase):
    def test_tool_publishes_a_valid_release(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["make_release.py", "--out", tmp, "--titulo", "Prueba",
                    "--nuevo", "Algo nuevo", "--arreglado", "Un arreglo", "--fecha", "2026-09-26"]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(tool), run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)

            releases = updates.fetch_releases(tmp)
            self.assertEqual(len(releases), 1)
            release = releases[0]
            self.assertEqual(release.version, __version__)
            self.assertEqual(release.title, "Prueba")
            self.assertEqual(release.notes_lines(), [("Nuevo", "Algo nuevo"), ("Arreglado", "Un arreglo")])
            zip_path = updates.download_release(release, tmp, Path(tmp) / "d")  # verifica el sha256
            names = updates.validate_zip(zip_path)
            self.assertEqual(updates.packaged_version(zip_path), __version__)
            self.assertFalse(any(name.startswith(("tests/", "tools/")) for name in names))
            self.assertIn("run.py", names)



class ReviewRegressionTests(unittest.TestCase):
    """Casos salidos de la revisión adversaria del gestor."""

    NOW = datetime(2026, 9, 14, 10, 0, 0)

    def test_plain_http_is_rejected(self):
        with self.assertRaises(updates.UpdateError) as ctx:
            updates.fetch_manifest("http://ejemplo.com/actualizaciones")
        self.assertIn("https", str(ctx.exception))

    def test_manifest_with_utf8_bom_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            publish(folder, "2.0.0")
            raw = (folder / "updates.json").read_bytes()
            (folder / "updates.json").write_bytes(b"\xef\xbb\xbf" + raw)  # BOM de PowerShell
            self.assertEqual(updates.fetch_releases(str(folder))[0].version, "2.0.0")

    def test_versions_with_unsafe_characters_are_skipped(self):
        releases = updates.parse_manifest({"releases": [
            {"version": "1.2.0/../evil", "file": "a.zip", "sha256": "0" * 64},
            {"version": "1.2:beta", "file": "b.zip", "sha256": "1" * 64},
            {"version": "1.2.0", "file": "c.zip", "sha256": "2" * 64},
        ]})
        self.assertEqual([release.version for release in releases], ["1.2.0"])

    def test_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "grande.bin"
            big.write_bytes(b"x" * 64)
            with self.assertRaises(updates.UpdateError) as ctx:
                updates._read_source(str(big), timeout=5, limit=10)
            self.assertIn("tamaño máximo", str(ctx.exception))

    def test_should_check_tolerates_timezones_and_future_dates(self):
        # Una fecha con zona horaria (editada a mano o de otra herramienta) no debe reventar el tick.
        self.assertIsInstance(updates.should_check("2026-09-13T09:00:00+00:00", "daily", self.NOW), bool)
        self.assertIsInstance(updates.should_check("2026-09-01T09:00:00Z", "weekly", self.NOW), bool)
        # Una fecha futura (reloj que estuvo adelantado) cuenta como inválida: se comprueba.
        self.assertTrue(updates.should_check("2026-12-31T00:00:00", "weekly", self.NOW))


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app_dir = root / "app"
        (self.app_dir / "radio_timer").mkdir(parents=True)
        (self.app_dir / "radio_timer" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        (self.app_dir / "radio_timer" / "obsoleto.py").write_text("# viejo\n", encoding="utf-8")
        (self.app_dir / "run.py").write_text("# arranque 1.0.0\n", encoding="utf-8")
        (self.app_dir / "datos.txt").write_text("no me toques\n", encoding="utf-8")
        self.backups = root / "backups"
        self.zip_path = root / "radio-timer-2.0.0.zip"
        make_release_zip(self.zip_path, "2.0.0")

    def tearDown(self):
        self.tmp.cleanup()

    def test_failed_swap_restores_everything(self):
        """Si un renombre falla a mitad (archivo bloqueado), la app queda exactamente como estaba."""
        real_rename = os.rename

        def flaky(src, dst):
            # Falla justo al colocar el run.py nuevo, con radio_timer ya intercambiado.
            if Path(dst).name == "run.py" and Path(src).parent.name.startswith(".instalando-"):
                raise OSError("bloqueado por el antivirus")
            real_rename(src, dst)

        with mock.patch.object(updates.os, "rename", side_effect=flaky):
            with self.assertRaises(updates.UpdateError) as ctx:
                updates.install_release(self.zip_path, self.app_dir, self.backups)
        self.assertIn("bloqueado por el antivirus", str(ctx.exception))
        self.assertNotIn("ATENCIÓN", str(ctx.exception))  # la restauración fue completa
        self.assertIn("1.0.0", (self.app_dir / "radio_timer" / "__init__.py").read_text(encoding="utf-8"))
        self.assertTrue((self.app_dir / "radio_timer" / "obsoleto.py").exists())
        self.assertEqual((self.app_dir / "run.py").read_text(encoding="utf-8"), "# arranque 1.0.0\n")
        self.assertEqual((self.app_dir / "datos.txt").read_text(encoding="utf-8"), "no me toques\n")
        leftovers = [p.name for p in self.app_dir.iterdir() if p.name.startswith((".instalando", ".anterior"))]
        self.assertEqual(leftovers, [])          # sin carpetas temporales huérfanas
        self.assertFalse(self.backups.exists())  # y sin respaldo de una instalación que no ocurrió

    def test_swap_happens_inside_the_app_folder(self):
        """El intercambio usa renombres en la misma unidad; a %APPDATA% solo se copia al final."""
        seen = []
        real_rename = os.rename

        def spy(src, dst):
            seen.append(Path(dst))
            real_rename(src, dst)

        with mock.patch.object(updates.os, "rename", side_effect=spy):
            updates.install_release(self.zip_path, self.app_dir, self.backups)
        # Las colocaciones dentro de la carpeta de la app (el intercambio en sí) deben ser
        # renombres locales; la copia hacia backups (otra unidad en producción) va después.
        placements = [dest for dest in seen if dest.parent == self.app_dir]
        self.assertEqual(sorted(dest.name for dest in placements), ["radio_timer", "run.py"])


class MakeReleaseManifestSafetyTests(unittest.TestCase):
    def test_corrupt_manifest_aborts_instead_of_wiping_history(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "updates.json"
            manifest.write_text("{ esto no es json", encoding="utf-8")
            argv = ["make_release.py", "--out", tmp, "--titulo", "X"]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(tool), run_name="__main__")
            self.assertNotEqual(ctx.exception.code, 0)
            # El manifiesto roto sigue intacto: nadie pisó el historial.
            self.assertEqual(manifest.read_text(encoding="utf-8"), "{ esto no es json")



def github_release(tag, *, name="", body="", digest="sha256:" + "a" * 64, draft=False, prerelease=False,
                   asset_name=None, size=1234):
    asset_name = asset_name or f"radio-timer-{tag.lstrip('v')}.zip"
    return {
        "tag_name": tag, "name": name, "body": body, "draft": draft, "prerelease": prerelease,
        "published_at": "2026-09-27T15:00:00Z",
        "assets": [
            {"name": "otra-cosa.txt", "browser_download_url": "https://github.com/o/r/x.txt", "size": 1,
             "digest": "sha256:" + "b" * 64},
            {"name": asset_name, "size": size, "digest": digest,
             "browser_download_url": f"https://github.com/o/r/releases/download/{tag}/{asset_name}"},
        ],
    }


class GitHubTests(unittest.TestCase):
    def test_repo_links_are_recognized(self):
        expected = ("Ganfst", "TIMECON---APP-project-bolt")
        for link in ("https://github.com/Ganfst/TIMECON---APP-project-bolt.git",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt/",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt/releases",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt/releases/latest",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt/releases/tag/v3.3.0",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt/tree/main",
                     "https://github.com/Ganfst/TIMECON---APP-project-bolt?tab=readme-ov-file",
                     "github.com/Ganfst/TIMECON---APP-project-bolt",
                     '  "https://www.github.com/Ganfst/TIMECON---APP-project-bolt"  '):
            self.assertEqual(updates.github_repo(link), expected, link)
        for other in ("http://github.com/Ganfst/TIMECON---APP-project-bolt",
                      "https://ejemplo.com/Ganfst/repo", "D:/actualizaciones"):
            self.assertIsNone(updates.github_repo(other), other)
        self.assertEqual(updates.github_repo(updates.DEFAULT_UPDATE_URL), expected)

    def test_releases_are_mapped(self):
        releases = updates.parse_github_releases([
            github_release("v3.3.0", name="v3.3.0 · Actualizaciones desde GitHub",
                           body="### Nuevo\n- Fuente GitHub\n\n### Arreglado\n- Un fallo\n\n"
                                "**Full Changelog**: https://github.com/o/r/compare/v3.2.0...v3.3.0"),
            github_release("v3.4.0", name="Siguiente"),
        ])
        self.assertEqual([release.version for release in releases], ["3.4.0", "3.3.0"])
        releases = releases[1:]
        newest = releases[0]
        self.assertEqual(newest.title, "Actualizaciones desde GitHub")   # sin repetir la versión
        self.assertEqual(newest.date, "2026-09-27")
        self.assertEqual(newest.notes_lines(), [("Nuevo", "Fuente GitHub"), ("Arreglado", "Un fallo")])
        self.assertEqual(newest.sha256, "a" * 64)
        self.assertEqual(newest.size, 1234)
        self.assertTrue(newest.file.endswith("/releases/download/v3.3.0/radio-timer-3.3.0.zip"))
        # El ZIP es una URL absoluta: se descarga tal cual, sin pasar por updates.json.
        self.assertEqual(updates._resolve_file(updates.DEFAULT_UPDATE_URL, newest.file), newest.file)

    def test_unusable_releases_are_skipped(self):
        releases = updates.parse_github_releases([
            github_release("v9.0.0", draft=True),
            github_release("v8.0.0", prerelease=True),   # entra marcada; el canal decide si se ve
            github_release("v7.0.0", asset_name="Codigo fuente.zip"),   # sin paquete de la app
            github_release("v6.0.0", digest=""),                        # sin SHA-256: no se verifica
            github_release("v5.0.0", digest="md5:" + "c" * 32),
            github_release("nada-que-ver"),                             # etiqueta sin versión
            github_release("v3.2.0"),         # anterior al soporte de GitHub: no se ofrece para volver
            "basura",
            github_release("v3.3.1"),
        ])
        self.assertEqual([release.version for release in releases], ["8.0.0", "3.3.1"])
        self.assertEqual([release.prerelease for release in releases], [True, False])
        self.assertEqual([r.version for r in updates.for_channel(releases, "stable")], ["3.3.1"])
        self.assertEqual([r.version for r in updates.for_channel(releases, "dev")], ["8.0.0", "3.3.1"])
        with self.assertRaises(updates.UpdateError):
            updates.parse_github_releases({"message": "Not Found"})

    def test_release_notes_parsing(self):
        notes = updates.parse_release_notes(
            "Intro sin sección\n## Nuevas funciones\n- A\n* B\n## Corregido\n1. C\n"
            "## Security\n- D\n## Mejoras\n- E\n")
        self.assertEqual(notes, {"cambiado": ["Intro sin sección", "E"], "nuevo": ["A", "B"],
                                 "arreglado": ["C"], "seguridad": ["D"]})
        self.assertEqual(updates.parse_release_notes(updates.format_release_notes(notes)), notes)
        self.assertEqual(updates.format_release_notes({}), "")

    def test_multiline_bullets_rules_and_code_blocks(self):
        notes = updates.parse_release_notes(
            "### Nuevo\n"
            "- La app se actualiza desde GitHub: basta con el enlace\n"
            "  del repositorio como fuente.\n"
            "- Otra cosa.\n"
            "\n"
            "Un párrafo que sigue\n"
            "en la línea de abajo.\n"
            "\n"
            "```\n"
            "## Lunes\n"
            "- esto es código\n"
            "```\n"
            "---\n"
            "* * *\n"
            "### Arreglado\n"
            "1. Un fallo\n")
        self.assertEqual(notes, {
            "nuevo": ["La app se actualiza desde GitHub: basta con el enlace del repositorio como fuente.",
                      "Otra cosa.", "Un párrafo que sigue en la línea de abajo."],
            "arreglado": ["Un fallo"],
        })

    def test_fetch_uses_the_api_and_explains_errors(self):
        payload = json.dumps([github_release("v3.3.0")]).encode("utf-8")
        with mock.patch.object(updates, "_read_source", return_value=payload) as read:
            releases = updates.fetch_releases("https://github.com/Ganfst/TIMECON---APP-project-bolt.git")
        self.assertEqual([release.version for release in releases], ["3.3.0"])
        url = read.call_args.args[0]
        self.assertEqual(url, "https://api.github.com/repos/Ganfst/TIMECON---APP-project-bolt/releases?per_page=100")
        self.assertIn("application/vnd.github+json", read.call_args.kwargs["headers"]["Accept"])

        for code, text in ((403, "60 por hora"), (429, "60 por hora"), (404, "No se encontró el repositorio")):
            error = updates.HttpStatusError("x", code)
            with mock.patch.object(updates, "_read_source", side_effect=error):
                with self.assertRaises(updates.UpdateError) as ctx:
                    updates.fetch_releases(updates.DEFAULT_UPDATE_URL)
            self.assertIn(text, str(ctx.exception))


class ChangelogToolTests(unittest.TestCase):
    CHANGELOG = """# Cambios

```
## X.Y.Z — AAAA-MM-DD — Ejemplo que no debe leerse
### Nuevo
- Ejemplo
```

## {version} — 2026-09-27 — Título desde el changelog

### Nuevo
- Primera novedad
- Segunda novedad

### Arreglado
- Un arreglo

## 0.0.1 — 2020-01-01 — Viejísima

### Nuevo
- No debe mezclarse
"""

    def test_notes_title_and_date_come_from_changelog(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            changelog = Path(tmp) / "CHANGELOG.md"
            changelog.write_text(self.CHANGELOG.format(version=__version__), encoding="utf-8")
            out = Path(tmp) / "dist"
            argv = ["make_release.py", "--out", str(out), "--changelog", str(changelog)]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(tool), run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)

            release = updates.fetch_releases(str(out))[0]
            self.assertEqual(release.title, "Título desde el changelog")
            self.assertEqual(release.date, "2026-09-27")
            self.assertEqual(release.notes_lines(), [
                ("Nuevo", "Primera novedad"), ("Nuevo", "Segunda novedad"), ("Arreglado", "Un arreglo")])
            # Lo que la Action pone en el GitHub Release, y que la app vuelve a leer igual.
            body = (out / f"notas-v{__version__}.md").read_text(encoding="utf-8")
            self.assertEqual(updates.parse_release_notes(body), release.notes)
            title = (out / f"titulo-v{__version__}.txt").read_text(encoding="utf-8")
            self.assertEqual(title, f"v{__version__} · Título desde el changelog")

    def _tool(self):
        return runpy.run_path(str(Path(__file__).resolve().parent.parent / "tools" / "make_release.py"))

    def test_changelog_header_variants(self):
        tool = self._tool()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            for header, date, title in (
                    ("## 3.4.0 — 2026-10-01 — Título", "2026-10-01", "Título"),
                    ("## [3.4.0] - 2026-10-01", "2026-10-01", ""),
                    ("## 3.4.0 (2026-10-01)", "2026-10-01", ""),
                    ("## v3.4.0: Título", "", "Título"),
                    ("## 3.4.0 — 2026-10-1 — Título", "2026-10-01", "Título"),
                    ("## 3.4.0", "", "")):
                path.write_text(f"{header}\n### Nuevo\n- Algo\n", encoding="utf-8")
                section = tool["changelog_section"](path, "3.4.0")
                self.assertIsNotNone(section, header)
                self.assertEqual(section[:2], (date, title), header)
                self.assertEqual(section[2], {"nuevo": ["Algo"]}, header)
            # Un "## " dentro de un bloque de código no corta la sección.
            path.write_text("## 3.4.0\n### Cambiado\n- Nuevo formato:\n\n```\n## Lunes\n```\n\n"
                            "### Arreglado\n- Algo\n## 3.3.0\n- Otra\n", encoding="utf-8")
            self.assertEqual(tool["changelog_section"](path, "3.4.0")[2],
                             {"cambiado": ["Nuevo formato:"], "arreglado": ["Algo"]})
            # Una sección 3.4.0 dentro de un bloque de código (la plantilla) no se toma.
            path.write_text("```\n## 3.4.0 — 2026-01-01 — Plantilla\n- Ejemplo\n```\n", encoding="utf-8")
            self.assertIsNone(tool["changelog_section"](path, "3.4.0"))

    def test_manual_date_and_title_are_respected(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            changelog = Path(tmp) / "CHANGELOG.md"
            changelog.write_text(self.CHANGELOG.format(version=__version__), encoding="utf-8")
            out = Path(tmp) / "dist"
            argv = ["make_release.py", "--out", str(out), "--changelog", str(changelog),
                    "--fecha", "2030-01-02", "--titulo", "Título a mano"]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit):
                    runpy.run_path(str(tool), run_name="__main__")
            release = updates.fetch_releases(str(out))[0]
            self.assertEqual((release.date, release.title), ("2030-01-02", "Título a mano"))
            self.assertEqual(release.notes_lines()[0], ("Nuevo", "Primera novedad"))  # notas del CHANGELOG

    def test_dev_build_from_commits(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            commits = Path(tmp) / "commits.txt"
            commits.write_text("feat: canal de desarrollo en Versiones\n"
                               "fix(reloj): el anillo no avanzaba en compacto\n"
                               "Corrige el título largo\n"
                               "Merge branch 'main' of github.com:Ganfst/x\n"
                               "Ajusta textos del diálogo\n", encoding="utf-8")
            out = Path(tmp) / "dist"
            argv = ["make_release.py", "--out", str(out), "--dev", "57", "--commits", str(commits)]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(tool), run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
            dev = updates.next_dev_version(__version__, 57)
            self.assertEqual((out / "version.txt").read_text(encoding="utf-8"), dev)
            release = updates.fetch_releases(str(out))[0]
            self.assertEqual(release.version, dev)
            self.assertTrue(release.prerelease)
            self.assertEqual(release.title, "Desarrollo #57")
            self.assertEqual(release.notes, {
                "nuevo": ["Canal de desarrollo en Versiones"],
                "arreglado": ["El anillo no avanzaba en compacto", "Corrige el título largo"],
                "cambiado": ["Ajusta textos del diálogo"],
            })
            # El paquete declara la versión de desarrollo: la instalación lo verifica contra el release.
            zip_path = updates.download_release(release, str(out), Path(tmp) / "d")
            self.assertEqual(updates.packaged_version(zip_path), dev)
            # El código fuente no se tocó.
            self.assertIn(f'"{__version__}"', (tool.parent.parent / "radio_timer" / "__init__.py").read_text(encoding="utf-8"))

    def test_stable_release_requires_changelog_when_asked(self):
        tool = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "CHANGELOG.md"
            empty.write_text("# Cambios\n", encoding="utf-8")
            argv = ["make_release.py", "--out", str(Path(tmp) / "dist"), "--changelog", str(empty),
                    "--exigir-changelog"]
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(tool), run_name="__main__")
            self.assertIn("no tiene la sección", str(ctx.exception.code))
            self.assertFalse((Path(tmp) / "dist").exists())   # no se publicó nada

    def test_repo_changelog_has_the_current_version(self):
        """El CHANGELOG.md real debe tener la sección de la versión actual (la Action la necesita)."""
        tool_globals = runpy.run_path(str(Path(__file__).resolve().parent.parent / "tools" / "make_release.py"))
        section = tool_globals["changelog_section"](tool_globals["DEFAULT_CHANGELOG"], __version__)
        self.assertIsNotNone(section, f"Falta '## {__version__}' en CHANGELOG.md")
        _date, title, notes = section
        self.assertTrue(title)
        self.assertTrue(notes)


class WorkflowTests(unittest.TestCase):
    """Chequeos del workflow de integración y entrega (no se puede correr en local)."""

    PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "integracion-y-entrega.yml"

    def setUp(self):
        self.text = self.PATH.read_text(encoding="utf-8")

    def test_triggers_and_permissions(self):
        for fragment in ("branches: [main]", "pull_request:", "contents: write", "cancel-in-progress: false",
                         "needs: pruebas", "fetch-depth: 0", "github.ref == 'refs/heads/main'"):
            self.assertIn(fragment, self.text)

    def test_publishing_commands_use_the_tool_outputs(self):
        self.assertIn("make_release.py --out dist --exigir-changelog", self.text)
        self.assertIn('--dev "$GITHUB_RUN_NUMBER" --commits dist/commits.txt', self.text)
        self.assertIn('gh release create "v$VERSION"', self.text)
        self.assertIn('gh release create "v$DEV"', self.text)
        self.assertIn("--prerelease", self.text)
        self.assertIn('--target "$GITHUB_SHA"', self.text)
        # Con pipefail, un grep sin coincidencias no debe tumbar la limpieza.
        self.assertIn("{ grep -- '-dev\\.' || true; }", self.text)

    def test_no_tabs_and_python_version_supported(self):
        self.assertNotIn("\t", self.text)
        self.assertIn('python-version: "3.12"', self.text)


if __name__ == "__main__":
    unittest.main()
