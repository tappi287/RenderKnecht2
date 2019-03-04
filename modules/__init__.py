from modules.settings import KnechtSettings

try:
    KnechtSettings.load()
    print('Settings loaded from file.')
except Exception as e:
    print('Error loading settings from file!\n%s', e)
