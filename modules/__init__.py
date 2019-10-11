try:
    from modules.settings import KnechtSettings
    KnechtSettings.load()
    print('Settings loaded from file.')
except Exception as e:
    print('Error loading settings from file!\n', e)
