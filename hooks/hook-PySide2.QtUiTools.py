# Loading *.ui files from PySide2.QtUiTools will fail in freezed app
# from PySide2.QtUiTools.QUiLoader depends on QtXml
hiddenimports = ["PySide2.QtXml"]