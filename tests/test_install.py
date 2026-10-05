"""Shared offline installer contract; fault injection changes temporary copies only."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ('gws-drive', 'gws-sheets')


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None
            for p in root.rglob('*')}


class InstallerContract:
    shell = 'bash'
    filename = 'install.sh'
    dest_flag = '--dest'
    upgrade_flag = '--upgrade'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows TEMP may use an 8.3 alias (RUNNER~1), while PowerShell
        # reports the expanded path. Use the canonical path for assertions.
        self.work = pathlib.Path(self.temp.name).resolve()
        self.repo = self.work / 'repo'
        self.repo.mkdir()
        for skill in SKILLS:
            shutil.copytree(ROOT / skill, self.repo / skill)
        shutil.copy2(ROOT / self.filename, self.repo / self.filename)
        self.dest = self.work / 'installed skills'

    def run_install(self, upgrade=False, dest=None):
        command = [self.shell]
        if self.filename.endswith('.ps1'):
            command += ['-NoProfile', '-File']
        command += [str(self.repo / self.filename), self.dest_flag, str(dest or self.dest)]
        if upgrade:
            command.append(self.upgrade_flag)
        return subprocess.run(command, cwd=self.work, capture_output=True, text=True)

    def assert_installed(self):
        for skill in SKILLS:
            self.assertEqual(snapshot(self.repo / skill), snapshot(self.dest / skill))

    def assert_clean(self):
        self.assertFalse(list(self.dest.glob('.gws-skills-install.*')))

    def backups(self):
        root = self.dest / '.gws-skills-backups'
        return list(root.iterdir()) if root.exists() else []

    def test_first_install_and_identical_repeat(self):
        result = self.run_install(dest='installed skills')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed()
        times = {p: p.stat().st_mtime_ns for p in self.dest.rglob('*')}
        for upgrade in (False, True):
            result = self.run_install(upgrade)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count('Already installed:'), 2)
            self.assertEqual(times, {p: p.stat().st_mtime_ns for p in self.dest.rglob('*')})
            self.assertEqual(self.backups(), [])
            self.assert_clean()

    def test_identical_and_missing(self):
        self.assertEqual(self.run_install().returncode, 0)
        shutil.rmtree(self.dest / 'gws-sheets')
        self.assertEqual(self.run_install().returncode, 0)
        self.assert_installed()

    def test_differences_block_all_publication(self):
        for change in ('changed', 'extra', 'missing', 'empty-directory'):
            with self.subTest(change=change):
                if self.dest.exists():
                    shutil.rmtree(self.dest)
                self.assertEqual(self.run_install().returncode, 0)
                target = self.dest / 'gws-sheets' / 'SKILL.md'
                if change == 'changed':
                    target.write_text('local edits')
                elif change == 'extra':
                    target.with_name('.extra').write_text('extra')
                elif change == 'missing':
                    target.unlink()
                else:
                    target.with_name('empty').mkdir()
                shutil.rmtree(self.dest / 'gws-drive')
                before = snapshot(self.dest)
                result = self.run_install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(self.upgrade_flag, result.stderr)
                self.assertEqual(before, snapshot(self.dest))
                self.assert_clean()

    def test_upgrade_preserves_original_and_removes_extra_files(self):
        self.assertEqual(self.run_install().returncode, 0)
        for skill in SKILLS:
            (self.dest / skill / 'SKILL.md').write_text('local edits')
            (self.dest / skill / '.extra').write_text('keep in backup')
        originals = {skill: snapshot(self.dest / skill) for skill in SKILLS}
        result = self.run_install(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed()
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertIn(str(backups[0]), result.stdout)
        for skill in SKILLS:
            self.assertEqual(originals[skill], snapshot(backups[0] / skill))
        self.assertEqual(self.run_install(True).returncode, 0)
        self.assertEqual(self.backups(), backups)
        self.assert_clean()

    def test_only_changed_skill_is_backed_up(self):
        self.assertEqual(self.run_install().returncode, 0)
        (self.dest / 'gws-sheets' / 'SKILL.md').write_text('changed')
        untouched = self.dest / 'gws-drive' / 'SKILL.md'
        before = untouched.stat().st_mtime_ns
        result = self.run_install(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(untouched.stat().st_mtime_ns, before)
        backup = self.backups()[0]
        self.assertEqual({p.name for p in backup.iterdir()}, {'gws-sheets'})
        self.assert_installed()

    def test_invalid_backup_root_keeps_existing_installation(self):
        self.assertEqual(self.run_install().returncode, 0)
        (self.dest / 'gws-sheets' / 'SKILL.md').write_text('changed')
        (self.dest / '.gws-skills-backups').write_text('not a directory')
        before = snapshot(self.dest)
        self.assertNotEqual(self.run_install(True).returncode, 0)
        self.assertEqual(snapshot(self.dest), before)
        self.assert_clean()

    def test_file_and_lock_conflicts(self):
        self.dest.mkdir()
        for name in ('gws-sheets', '.gws-skills-install.lock'):
            target = self.dest / name
            target.write_text('keep me')
            for upgrade in (False, True):
                result = self.run_install(upgrade)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.dest / 'gws-drive').exists())
                self.assertEqual(target.read_text(), 'keep me')
            target.unlink()

    def test_links_rejected(self):
        self.dest.mkdir()
        link = self.dest / 'gws-sheets'
        try:
            link.symlink_to(self.work / 'missing', target_is_directory=True)
        except OSError as error:
            self.skipTest(f'Symlink creation unavailable: {error}')
        self.assertNotEqual(self.run_install(True).returncode, 0)
        self.assertTrue(link.is_symlink())
        link.unlink()
        self.assertEqual(self.run_install().returncode, 0)
        nested = self.dest / 'gws-sheets' / 'nested-link'
        nested.symlink_to(self.repo / 'gws-drive', target_is_directory=True)
        self.assertNotEqual(self.run_install(True).returncode, 0)
        self.assertTrue(nested.is_symlink())
        nested.unlink()
        source_link = self.repo / 'gws-drive' / 'source-link'
        source_link.symlink_to(self.repo / 'gws-sheets', target_is_directory=True)
        self.assertNotEqual(self.run_install(True).returncode, 0)
        self.assert_clean()

    def inject_failure(self, rollback=False):
        script = self.repo / self.filename
        text = script.read_text()
        if self.filename.endswith('.ps1'):
            publish = '[IO.Directory]::Move((Join-Path $stage $skill), $target)'
            text = text.replace(publish, "if ($skill -eq 'gws-sheets') { throw 'Injected publication failure' }; " + publish)
            if rollback:
                restore = '[IO.Directory]::Move($original, $target)'
                text = text.replace(restore, "if ($skill -eq 'gws-drive') { throw 'Injected rollback failure' }; " + restore)
        else:
            publish = 'mv -- "$stage/$skill" "$dest/$skill"'
            text = text.replace(publish, '[[ "$skill" != gws-sheets ]] || fail "Injected publication failure"\n  ' + publish)
            if rollback:
                restore = 'mv -- "$backup/$skill" "$dest/$skill"'
                text = text.replace(restore, 'false')
        script.write_text(text)

    def test_publication_failure_rolls_back(self):
        for upgrade in (False, True):
            with self.subTest(upgrade=upgrade):
                if self.dest.exists():
                    shutil.rmtree(self.dest)
                shutil.copy2(ROOT / self.filename, self.repo / self.filename)
                if upgrade:
                    self.assertEqual(self.run_install().returncode, 0)
                    for skill in SKILLS:
                        (self.dest / skill / 'SKILL.md').write_text('original')
                originals = {skill: snapshot(self.dest / skill) for skill in SKILLS} if upgrade else {}
                self.inject_failure()
                result = self.run_install(upgrade)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Installed:', result.stdout)
                self.assertNotIn('Updated:', result.stdout)
                for skill in SKILLS:
                    if upgrade:
                        self.assertEqual(originals[skill], snapshot(self.dest / skill))
                    else:
                        self.assertFalse((self.dest / skill).exists())
                self.assert_clean()

    def test_rollback_failure_preserves_backup_and_reports_path(self):
        self.assertEqual(self.run_install().returncode, 0)
        for skill in SKILLS:
            (self.dest / skill / 'SKILL.md').write_text('original')
        originals = {skill: snapshot(self.dest / skill) for skill in SKILLS}
        self.inject_failure(rollback=True)
        result = self.run_install(True)
        self.assertNotEqual(result.returncode, 0)
        backup = self.backups()[0]
        self.assertEqual(originals['gws-drive'], snapshot(backup / 'gws-drive'))
        self.assertIn(str(backup / 'gws-drive'), result.stdout + result.stderr)
        self.assertIn('manually', result.stdout + result.stderr)
        self.assert_clean()

    def test_source_containment_and_invalid_arguments(self):
        nested = self.repo / 'gws-drive' / 'new' / 'nested'
        self.assertNotEqual(self.run_install(dest=nested).returncode, 0)
        self.assertFalse(nested.exists())
        prefix = [self.shell]
        if self.filename.endswith('.ps1'):
            prefix += ['-NoProfile', '-File']
        prefix += [str(self.repo / self.filename)]
        for args in ([], [self.dest_flag, ''], ['-Unknown', 'value']):
            self.assertNotEqual(subprocess.run(prefix + args, capture_output=True).returncode, 0)
        help_flag = '-Help' if self.filename.endswith('.ps1') else '--help'
        self.assertEqual(subprocess.run(prefix + [help_flag], capture_output=True).returncode, 0)


@unittest.skipUnless(shutil.which('bash'), 'Bash unavailable')
class BashInstallerTests(InstallerContract, unittest.TestCase):
    pass
