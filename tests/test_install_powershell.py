import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PWSH = shutil.which('pwsh')


@unittest.skipUnless(PWSH, 'PowerShell unavailable; Windows CI runs installer tests')
class PowerShellInstallerTests(unittest.TestCase):
    def run_installer(self, cwd, *args):
        return subprocess.run(
            [PWSH, '-NoProfile', '-File', str(ROOT / 'install.ps1'), *args],
            cwd=cwd, capture_output=True, text=True,
        )

    def test_copy_relative_path_with_spaces_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_installer(tmp, '-Dest', 'installed skills')
            self.assertEqual(result.returncode, 0, result.stderr)
            dest = pathlib.Path(tmp) / 'installed skills'
            for skill in ('gws-drive', 'gws-sheets'):
                source_files = {p.relative_to(ROOT / skill) for p in (ROOT / skill).rglob('*') if p.is_file()}
                copied_files = {p.relative_to(dest / skill) for p in (dest / skill).rglob('*') if p.is_file()}
                self.assertEqual(copied_files, source_files)
                for path in source_files:
                    self.assertEqual((dest / skill / path).read_bytes(), (ROOT / skill / path).read_bytes())
            sentinel = dest / 'gws-drive' / 'SKILL.md'
            sentinel.write_text('keep me', encoding='utf-8')
            result = self.run_installer(tmp, '-Dest', str(dest))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'keep me')
            self.assertFalse(list(dest.glob('.gws-skills-install.*')))

    def test_single_conflict_and_lock_prevent_publication(self):
        for conflict in ('gws-sheets', '.gws-skills-install.lock'):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                dest = pathlib.Path(tmp)
                (dest / conflict).write_text('keep me', encoding='utf-8')
                result = self.run_installer(tmp, '-Dest', tmp)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((dest / 'gws-drive').exists())
                self.assertEqual((dest / conflict).read_text(encoding='utf-8'), 'keep me')

    def test_arguments_and_source_containment(self):
        for args in ((), ('-Dest', ''), ('-Unknown', 'value'),
                     ('-Dest', str(ROOT / 'gws-drive' / 'nested'))):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_installer(ROOT, *args).returncode, 0)
        self.assertEqual(self.run_installer(ROOT, '-Help').returncode, 0)
