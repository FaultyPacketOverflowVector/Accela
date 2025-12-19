import multiprocessing
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        import ctypes

        myappid = "god.is.in.the.wired.accela"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass


from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.main_window import MainWindow
from utils.helpers import resource_path
from utils.logger import setup_logging
from utils.settings import get_settings

project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    pass
except ImportError:
    pass


def update_appearance(app, accent="#C06C84", background="#000000", font=None):
    """Apply a dynamic palette and custom font to the application"""
    app.setStyle("Fusion")
    dark_palette = QPalette()

    background_color = QColor(background)
    accent_color = QColor(accent)

    dark_palette.setColor(QPalette.ColorRole.Window, background_color)
    dark_palette.setColor(QPalette.ColorRole.WindowText, accent_color)
    dark_palette.setColor(QPalette.ColorRole.Base, background_color.darker(120))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, background_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, accent_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, background_color)
    dark_palette.setColor(QPalette.ColorRole.Text, accent_color)
    dark_palette.setColor(QPalette.ColorRole.Button, background_color)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, accent_color)
    dark_palette.setColor(QPalette.ColorRole.BrightText, accent_color.lighter(120))
    dark_palette.setColor(QPalette.ColorRole.Link, accent_color.lighter(120))
    dark_palette.setColor(QPalette.ColorRole.Highlight, accent_color)
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, background_color)
    dark_palette.setColor(QPalette.ColorRole.PlaceholderText, accent_color.darker(120))

    app.setPalette(dark_palette)

    hover_lightness = 120
    selected_lightness = 150
    checked_lightness = 200
    doubled_lightness = 250
    background_color_effect = background_color
    if background_color_effect == QColor("#000000"):
        background_color_effect = QColor("#282828")

    gradient_border = f"""
            border-top: 2px solid {accent_color.lighter(120).name()};
            border-bottom: 2px solid {accent_color.lighter(120).name()};
            border-left: 2px solid qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_color.lighter(120).name()}, stop:0.5 {background_color.lighter(120).name()}, stop:1 {accent_color.lighter(120).name()});
            border-right: 2px solid qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_color.lighter(120).name()}, stop:0.5 {background_color.lighter(120).name()}, stop:1 {accent_color.lighter(120).name()});
    """
    gradient_border_full = f"""
            border-top: 2px solid {accent_color.lighter(120).name()};
            border-bottom: 2px solid {accent_color.lighter(120).name()};
            border-left: 2px solid {accent_color.lighter(120).name()};
            border-right: 2px solid {accent_color.lighter(120).name()};
    """

    app.setStyleSheet(f"""
        QLineEdit {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
            border: 1px solid {accent_color.name()};
            padding: 8px;
        }}

        QLineEdit:hover {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
        }}

        QCheckBox {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
            padding: 8px;
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 12px;
            height: 12px;
            background: {background_color.name()};
            {gradient_border}
        }}

        QCheckBox::indicator:checked {{
            background: {accent_color.name()};
        }}

        QCheckBox::indicator:hover {{
            {gradient_border_full}
        }}

        QDialog {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
        }}

        QListWidget {{
            background-color: {background_color.darker(120).name()};
            color: {accent_color.name()};
            border-radius: 4px;
            /* VVV REMOVES THE WEIRD LITTLE TEXT BORDER/BACKGROUND IN DEPOT SELECTION VVV */
            outline: 0;
            border: none;
        }}

        QListWidget::item {{
            background-color: {background_color.darker(120).name()};
            color: {accent_color.name()};
            border-radius: 4px;
            padding: 6px;
        }}

        QListWidget::item:hover {{
            background-color: {background_color_effect.lighter(hover_lightness).name()};
            color: {accent_color.name()};
        }}

        QListWidget::item:selected {{
            background-color: {background_color_effect.lighter(selected_lightness).name()};
            color: {accent_color.name()};
        }}

        QListWidget::item:checked {{
            background-color: {background_color_effect.lighter(checked_lightness).name()};
            color: {accent_color.name()};
            font-weight: bold;
        }}

        QListWidget::item:checked:selected {{
            background-color: {background_color_effect.lighter(doubled_lightness).name()};
            color: {accent_color.name()};
        }}

        QListWidget::indicator {{
            {gradient_border}
            border-radius: 4px;
        }}

        QListWidget::indicator:unchecked {{
            background-color: {background_color.name()};
        }}

        QListWidget::indicator:checked {{
            background-color: {accent_color.name()};
        }}

        QListWidget::indicator:hover {{
            {gradient_border_full}
        }}

        QPushButton {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
            padding: 6px 6px;
            {gradient_border}
            font-weight: bold;
        }}

        QPushButton:hover {{
            background-color: {accent_color.name()};
            color: {background_color.name()};
            {gradient_border_full}
        }}

        QLabel {{
            color: {accent_color.name()};
        }}

        QToolTip {{
            background-color: {background_color.name()};
            color: {accent_color.name()};
            padding: 6px;
        }}
    """)

    # Load & apply custom font
    font_path = resource_path("res/TrixieCyrG-Plain Regular.otf")
    font_id = QFontDatabase.addApplicationFont(font_path)

    if font_id == -1:
        return False, font_path

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return False, font_path

    if not font:
        font_name = families[0]
        font = QFont(font_name, 10)
    app.setFont(font)

    return True, font.families()[0]


def main():
    logger = setup_logging()
    version_file = resource_path("res/version")
    version = "unknown version"

    if Path(version_file).is_file():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                version = f.read().strip() or "unknown version"
        except Exception as e:
            logger.warning(f"Failed to read version file: {e}")
    else:
        logger.warning("Version file not found, using unknown version")

    logger.info("========================================")
    logger.info(f"ACCELA {version} starting...")
    logger.info("========================================")

    # People only have substance within the memories of other people.

    app = QApplication(sys.argv)

    # Parse command-line arguments for ZIP files
    command_line_zips = []
    for arg in sys.argv[1:]:  # Skip script name
        if arg.lower().endswith('.zip'):
            # Normalize path to handle relative paths correctly
            zip_path = os.path.abspath(arg)
            if os.path.exists(zip_path):
                command_line_zips.append(zip_path)
                logger.info(f"Found ZIP file from command line: {zip_path}")
            else:
                logger.warning(f"ZIP file not found: {arg}")

    if command_line_zips:
        logger.info(f"Will process {len(command_line_zips)} ZIP file(s) from command line after initialization")

    # Load settings
    settings = get_settings()
    accent_color = settings.value("accent_color", "#C06C84")
    bg_color = settings.value("background_color", "#000000")

    # Apply palette + font (font logic moved inside)
    font_ok, font_info = update_appearance(app, accent_color, bg_color)

    if font_ok:
        logger.info(f"Successfully loaded and applied custom font: '{font_info}'")
    else:
        logger.warning(f"Failed to load custom font from: {font_info}")

    try:
        main_win = MainWindow()
        main_win.show()
        logger.info("Main window displayed successfully.")

        # Process command-line ZIP files after window is fully initialized
        if command_line_zips:
            def process_command_line_zips():
                """Add command-line ZIP files to queue after window initialization completes"""
                logger.info(f"Adding {len(command_line_zips)} ZIP file(s) from command line to queue")
                for zip_path in command_line_zips:
                    logger.info(f"Adding to queue: {os.path.basename(zip_path)}")
                    main_win.job_queue.add_job(zip_path)

            # Use singleShot to defer until after window initialization
            QTimer.singleShot(0, process_command_line_zips)

        sys.exit(app.exec())
    except Exception as e:
        logger.critical(
            f"A critical error occurred, and the application must close. Error: {e}",
            exc_info=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
