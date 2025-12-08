from PyQt6.QtCore import QSettings

# --- Constants for QSettings ---
APP_NAME = "DepotDownloaderGUI"
ORG_NAME = "YourOrg"

def get_settings():
    """
    Provides a global access point to the application's QSettings object.
    """
    return QSettings(ORG_NAME, APP_NAME)
