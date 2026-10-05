import shutil
import os
import unittest

from test_install import InstallerContract, snapshot


@unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable; Windows CI runs installer tests')
class PowerShellInstallerTests(InstallerContract, unittest.TestCase):
    shell = shutil.which('pwsh')
    filename = 'install.ps1'
    dest_flag = '-Dest'
    upgrade_flag = '-Upgrade'

    @unittest.skipUnless(os.name == 'nt', 'Windows path separators')
    def test_source_containment_with_windows_path_variants(self):
        for skill in ('gws-drive', 'gws-sheets'):
            nested = self.repo / skill / 'new' / 'nested'
            source_before = snapshot(self.repo / skill)
            for separator in ('/', '\\'):
                for suffix in ('', separator, separator + '..' + separator + 'nested'):
                    dest = str(nested).replace('\\', separator) + suffix
                    with self.subTest(skill=skill, dest=dest):
                        result = self.run_install(dest=dest)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('Destination is inside source skill', result.stderr)
                        self.assertEqual(source_before, snapshot(self.repo / skill))
