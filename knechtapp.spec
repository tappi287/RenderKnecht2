# -*- mode: python -*-

block_cipher = None
knecht_files = [('license.txt', '.'),
                ('db_config.zip', '.'),
                ('ui/*.py', 'ui'),
                ('ui/*.ui', 'ui'),
                ('ui/*.json', 'ui'),
                ('ui/*.qrc', 'ui'),
                ('ui/*.qss', 'ui'),
                ('locale/de/LC_MESSAGES/*.mo', 'locale/de/LC_MESSAGES'),
                ('locale/en/LC_MESSAGES/*.mo', 'locale/en/LC_MESSAGES'),
                ('locale/help/', 'locale/help'),
                ]

local_hooks = ['hooks']

a = Analysis(['knechtapp.py'],
             pathex=['I:\\Nextcloud\\py\\RenderKnecht2'],
             binaries=[],
             datas=knecht_files,
             hiddenimports=[],
             hookspath=local_hooks,
             runtime_hooks=[],
             excludes=['zmq', 'jupyter', 'tornado', 'paramiko', 'IPython', 'tk', 'tkinter', 'lib2to3'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='RenderKnecht',
          icon='./ui/res/RK_Icon.ico',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               name='RenderKnecht2')
