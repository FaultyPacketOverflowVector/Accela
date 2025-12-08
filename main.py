import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor, QFontDatabase, QFont

# Add the project root to the Python path. This allows absolute imports
# (e.g., 'from core.tasks...') to work from any submodule.
# This must be done BEFORE importing any project modules.
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ui.main_window import MainWindow
from utils.logger import setup_logging

def main():
    """
    The main entry point for the Depot Downloader GUI application.
    Initializes logging, sets the application style, and launches the main window.
    """
    # Set up the application-wide logger to capture logs from all modules.
    logger = setup_logging()
    logger.info("========================================")
    logger.info("Application starting...")
    logger.info("========================================")

    app = QApplication(sys.argv)

    # Set a custom dark theme based on the provided image.
    app.setStyle("Fusion")
    dark_palette = QPalette()
    
    # Define colors from the image
    dark_color = QColor("#1E1E1E")
    pink_color = QColor("#C06C84")

    dark_palette.setColor(QPalette.ColorRole.Window, dark_color)
    dark_palette.setColor(QPalette.ColorRole.WindowText, pink_color)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#282828"))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, pink_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, dark_color)
    dark_palette.setColor(QPalette.ColorRole.Text, pink_color)
    dark_palette.setColor(QPalette.ColorRole.Button, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, pink_color)
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0)) # Keep bright text red for errors
    dark_palette.setColor(QPalette.ColorRole.Link, pink_color.lighter())
    dark_palette.setColor(QPalette.ColorRole.Highlight, pink_color)
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, dark_color)
    app.setPalette(dark_palette)

    # --- MODIFICATION START ---
    # Load and Apply Custom Font
    font_path = "TrixieCyrG-Plain Regular.otf"
    font_id = QFontDatabase.addApplicationFont(font_path)
    
    if font_id == -1:
        logger.warning(f"Failed to load custom font from: {font_path}")
    else:
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        if font_families:
            font_name = font_families[0]
            custom_font = QFont(font_name, 10)
            app.setFont(custom_font)
            logger.info(f"Successfully loaded and applied custom font: '{font_name}'")
        else:
            logger.warning(f"Could not retrieve font family name from: {font_path}")
    # --- MODIFICATION END ---

    try:
        main_win = MainWindow()
        main_win.show()
        logger.info("Main window displayed successfully.")
        # Start the Qt event loop.
        sys.exit(app.exec())
    except Exception as e:
        # A global catch-all for any unhandled exceptions during initialization.
        logger.critical(f"A critical error occurred, and the application must close. Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
