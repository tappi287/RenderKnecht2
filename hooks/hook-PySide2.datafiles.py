# Collect PySide2 data files
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('PySide2', include_py_files=True, subdir='support')
