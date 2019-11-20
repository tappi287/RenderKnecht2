from pathlib import Path
from typing import Union

from knechtapp import VERSION
from subprocess import Popen
from private.sftp import Remote
from modules.globals import UPDATE_INSTALL_FILE, UPDATE_VERSION_FILE
from distutils.dir_util import copy_tree

from lxml import etree as Et

import shutil
import winreg

EXTERNAL_APP_DIRS = [Path(Path('.').absolute().parent / 'KnechtViewer' / 'dist' / 'KnechtViewer'),
                     Path(Path('.').absolute().parent / 'PosSchnuffi' / 'dist' / 'PosSchnuffi')]

SPEC_FILE = "knechtapp.spec"
ISS_FILE = "knechtapp_win64_setup.iss"
ISS_VER_LINE = '#define MyAppVersion'
ISS_SETUP_EXE_FILE = UPDATE_INSTALL_FILE.format(version=VERSION)
MANIFEST_FILE = "build/RenderKnecht.exe.manifest"

DIST_DIR = "dist"
DIST_EXE_DIR = "RenderKnecht2"

REMOTE_DIR = '/knecht2'


class FindInnoSetup:
    inno_console_compiler_name = "ISCC.exe"

    @staticmethod
    def _open_registry():
        return winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)

    @classmethod
    def _get_by_inno_studio_compiler_option(cls, reg) -> Union[None, Path]:
        """ Find the key set by Inno Studio when compiler path set in options"""
        try:
            key = winreg.OpenKey(reg, r"SOFTWARE\Classes\InnoSetupScriptFile\shell\Compile\command", 0, winreg.KEY_READ)
        except OSError:
            return

        value = winreg.EnumValue(key, 0)[1]  # "C:\\Program Files (x86)\\Inno Setup 6\\Compil32.exe" /cc "%1"
        value = value[0:value.find('/cc') - 1]  # "C:\\Program Files (x86)\\Inno Setup 6\\Compil32.exe"
        return Path(value.replace('"', '')).parent

    @classmethod
    def _get_by_inno_setup_uninstall_key(cls, reg) -> Union[None, Path]:
        """ Find by either Inno Setup 5 or 6 Uninstall Key """
        keys = [r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"]
        key = None

        while keys:
            try:
                key = winreg.OpenKey(reg, keys.pop(), 0, winreg.KEY_READ)
            except OSError:
                pass

        if key is None:
            return

        idx, name, value = 0, str(), str()
        while 1:
            try:
                name, value, __ = winreg.EnumValue(key, idx)
            except OSError:
                # Will break when no more sub key values are available
                return

            idx += 1
            if name == 'InstallLocation' and value:
                break

        return Path(value.replace('"', ''))

    @classmethod
    def compiler_path(cls) -> Union[None, Path]:
        methods = [cls._get_by_inno_setup_uninstall_key, cls._get_by_inno_studio_compiler_option]
        reg = cls._open_registry()

        value = None
        while methods:
            m = methods.pop()
            value = m(reg)

            if value is not None:
                break

        if value is None:
            return

        return value / cls.inno_console_compiler_name  # eg. 'C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe'


def update_manifest_version():
    xml = Et.parse(MANIFEST_FILE)
    e = xml.find('./')  # Element assemblyIdentity
    e.set('version', VERSION)  # Update Version

    with open(MANIFEST_FILE, 'wb') as f:
        xml.write(f, pretty_print=True, xml_declaration=True, encoding='UTF-8')


def update_version_info(out_dir: Path):
    # Write version file
    print('Creating/Updating version info file.\n')
    file = out_dir / UPDATE_VERSION_FILE
    with open(file.as_posix(), 'w') as f:
        f.write(VERSION)

    with open(ISS_FILE, 'r') as f:
        iss_lines = f.readlines()

    print('Updating Inno Setup Script')
    for idx, line in enumerate(iss_lines):
        if line.startswith(ISS_VER_LINE):
            line = f'{ISS_VER_LINE} "{VERSION}"\n'
            iss_lines[idx] = line
            print('updated: ' + iss_lines[idx] + '\n')

    with open(ISS_FILE, 'w') as f:
        f.writelines(iss_lines)

    # Update exe manifest
    # update_manifest_version()


def upload_release() -> bool:
    setup_exe = Path(DIST_DIR) / Path(ISS_SETUP_EXE_FILE)

    if not setup_exe.exists():
        print('Can not upload Windows Installer. File not found in: ' + setup_exe.as_posix())
        return False

    sftp = Remote(REMOTE_DIR)
    if not sftp.connect():
        print('Could not connect to remote host!')
        return False

    if sftp.put(setup_exe):
        version_txt = Path(DIST_DIR) / UPDATE_VERSION_FILE
        sftp.put(version_txt)
        return True
    return False


def main(process: int=0):
    if process == -1:
        print('Aborting process.')
        return

    print('\n### STARTING RENDER KNECHT BUILD ###')
    # Create distribution directory
    out_dir = Path(DIST_DIR)
    if not out_dir.exists():
        out_dir.mkdir()

    update_version_info(out_dir)

    if process in (0, 1, 2):
        # Build with PyInstaller
        args = ['pyinstaller', '--noconfirm', SPEC_FILE]
        p = Popen(args=args)
        p.wait()
        print('Pyinstaller result: ' + str(p.returncode))

        if p.returncode != 0:
            print('PyInstaller could not build executable!')
            return

        # Copy/Add external applications
        dist_dir = Path(DIST_DIR) / Path(DIST_EXE_DIR)

        for src_dir in EXTERNAL_APP_DIRS:
            print('Adding external application from dir: ', src_dir.as_posix())
            result = copy_tree(src_dir.absolute().as_posix(), dist_dir.absolute().as_posix(), update=1)
            if result:
                print('Added app folder: ', src_dir.name)

    if process in (1, 2):
        iss_path = FindInnoSetup.compiler_path()
        if iss_path is None or not iss_path.exists():
            print('Could not find Inno Setup compiler path.')
            return

        args = [FindInnoSetup.compiler_path().as_posix(), ISS_FILE]
        print('\nRunning Inno Setup console-mode compiler...\n', args)
        p = Popen(args, cwd=Path(__file__).parent)
        p.wait()

        print('Inno Setup console-mode compiler result: ' + str(p.returncode))

        if p.returncode != 0:
            print('Inno Script Studio encountered an error!')
            return

        rm_dir = Path(DIST_DIR) / Path(DIST_EXE_DIR)
        if rm_dir.exists():
            print('\nRemoving executable folder: ' + DIST_EXE_DIR)
            shutil.rmtree(rm_dir)

        print('\nBuild completed!')

    if process in (2, 3):
        if not upload_release():
            print('Error while updating remote directory!')
            return

        print('Update remote location finished!')


def ask_process() -> int:
    print("\n\n"
          "##########################################################")
    print("Choose which process you'd like to proceed with:\n"
          "\t\t0 - Build Executable\n"
          "\t\t1 - Build Executable + Installer\n"
          "\t\t2 - Build Executable + Installer + Upload\n"
          "\t\t3 - Only upload existing Installer to remote directory.\n")
    answer = input('Answer: ')

    if answer not in ['0', '1', '2', '3', 'q', 'exit', 'quit']:
        ask_process()

    if answer.isdigit():
        return int(answer)
    else:
        return -1


if __name__ == '__main__':
    process_option = ask_process()

    main(process_option)
