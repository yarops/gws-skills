import shutil
import unittest

from test_install import InstallerContract


@unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable; Windows CI runs installer tests')
class PowerShellInstallerTests(InstallerContract, unittest.TestCase):
    shell = shutil.which('pwsh')
    filename = 'install.ps1'
    dest_flag = '-Dest'
    upgrade_flag = '-Upgrade'
