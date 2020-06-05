"""
    As of PySide2 5.12.1 shiboken2 libary will not load when frozen with only it's compiled *.pyc files
    https://bugreports.qt.io/browse/PYSIDE-942
"""
from PyInstaller.utils.hooks import collect_data_files


def reroute(collected, dest_dir):
    rerouted_collecton = list()
    for (src, dest) in collected:
        rerouted_collecton.append(
            (src, dest_dir)
            )
    return rerouted_collecton


# Collect shiboken2/files.dir
datas = collect_data_files('shiboken2', include_py_files=True, subdir='files.dir')

# Collect dll's from shiboken2 dir and place in app root dir
data = collect_data_files('shiboken2', include_py_files=False, includes=('*.dll', ))
datas += reroute(data, '.')

# Collect VCRUNTIME140_1.dll which is missing on some systems
datas += [('bin/vcruntime140_1.dll', '.')]
