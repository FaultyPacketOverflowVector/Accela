import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QMutex, QObject, QThread, pyqtSignal

from utils.helpers import resource_path
from utils.settings import get_settings

logger = logging.getLogger(__name__)


class SteamlessIntegration(QObject):
    """
    Integration module for Steamless CLI to remove Steam DRM from games.
    """

    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(
        self,
        steamless_path: Optional[str] = None,
        preferred_proton_version: Optional[str] = None,
    ):
        super().__init__()
        self.steamless_path = steamless_path or os.path.join(os.getcwd(), "Steamless")
        self.is_windows = sys.platform == "win32"
        self.preferred_proton_version = preferred_proton_version
        self.wine_command = None
        self._wine_check_message = None
        self._current_process = None
        self._process_mutex = QMutex()
        self._available_proton_versions = []
        self._wine_arch = None  # Will store "win32" or "win64"
        try:
            self.wine_available = self._check_wine_availability()
        except Exception as e:
            logger.error(
                f"Failed to initialize Steamless integration: {e}", exc_info=True
            )
            self.wine_available = False
            self.wine_command = None
        self.dotnet_available = False

    def _find_proton_installation(self) -> Optional[str]:
        """Find Proton installation from Steam directories."""
        # Common Steam installation paths (comprehensive for all distros including SteamOS)
        steam_paths = [
            # Native Steam
            Path.home() / ".local/share/Steam/steamapps/common",  # Official Protons
            Path.home() / ".local/share/Steam/compatibilitytools.d",  # Unofficial Protons
            # Flatpak Steam
            #Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/common",
            #Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d",
            # Snap Steam (rare/deprecated)
            #Path.home() / "snap/steam/common/.local/share/Steam/steamapps/common",
            #Path.home() / "snap/steam/common/.local/share/Steam/compatibilitytools.d",
            # Distro Specific
            Path("/usr/share/steam/compatibilitytools.d"),  # CachyOS Protons
        ]

        proton_installations = []

        for steam_path in steam_paths:
            try:
                # Skip if path doesn't exist or we can't access it
                if not steam_path.exists() or not os.access(steam_path, os.R_OK):
                    continue

                # Look for Proton directories (case-insensitive to match both "Proton*" and "proton*")
                for proton_dir in list(steam_path.glob("Proton*")) + list(
                    steam_path.glob("proton*")
                ):
                    try:
                        if not proton_dir.is_dir():
                            continue

                        # Check for wine binary in common Proton locations
                        wine_paths = [
                            proton_dir / "files" / "bin" / "wine",
                            proton_dir / "dist" / "bin" / "wine",
                        ]

                        for wine_path in wine_paths:
                            try:
                                if (
                                    wine_path.exists()
                                    and wine_path.is_file()
                                    and os.access(wine_path, os.X_OK)
                                ):
                                    proton_installations.append(
                                        {
                                            "name": proton_dir.name,
                                            "path": str(wine_path),
                                            "dir": str(proton_dir),
                                        }
                                    )
                                    break
                            except Exception as e:
                                logger.debug(
                                    f"Error checking wine path {wine_path}: {e}"
                                )
                                continue
                    except Exception as e:
                        logger.debug(
                            f"Error scanning Proton directory {proton_dir}: {e}"
                        )
                        continue
            except Exception as e:
                logger.debug(f"Error scanning {steam_path}: {e}")
                continue

        if (
            proton_installations or True
        ):  # Always check for Wine even if no Proton found
            # Separate experimental versions and sort by preference
            # Proton Experimental should always be preferred first
            experimental_versions = [
                p for p in proton_installations if "experimental" in p["name"].lower()
            ]
            regular_versions = [
                p
                for p in proton_installations
                if "experimental" not in p["name"].lower()
            ]

            # Sort regular versions by version (prefer newer versions)
            # Proton versions are typically named like "Proton 9.0" or "Proton-9.0-4"
            # Extract version numbers for proper sorting
            def extract_version(proton_dict):
                try:
                    # Extract numeric version from name (e.g., "9.0" from "Proton 9.0")
                    match = re.search(r"(\d+)\.(\d+)", proton_dict["name"])
                    if match:
                        major = int(match.group(1))
                        minor = int(match.group(2))
                        return (major, minor)
                    # If no version found, return low priority
                    return (0, 0)
                except:
                    return (0, 0)

            # Sort regular versions by version number (newest first)
            regular_versions.sort(key=extract_version, reverse=True)

            # Experimental versions always come first, sorted by version within experimental
            experimental_versions.sort(key=extract_version, reverse=True)

            # Find system Wine installation
            wine_installation = self._find_wine_installation()

            # Combine in priority order:
            # 1. Proton Experimental (newest first)
            # 2. System Wine (if available)
            # 3. Regular Proton versions (newest first)
            proton_installations = experimental_versions.copy()
            if wine_installation:
                proton_installations.append(
                    {
                        "name": "System Wine",
                        "path": wine_installation,
                        "dir": os.path.dirname(wine_installation),
                    }
                )
            proton_installations.extend(regular_versions)

            # Store all discovered versions
            self._available_proton_versions = proton_installations

            # Return the first available option (highest priority)
            if proton_installations:
                selected = proton_installations[0]
                logger.info(
                    f"Found installation: {selected['name']} at {selected['path']}"
                )
                return selected["path"]

        logger.debug("No Proton or Wine installations found")
        return None

    def _find_wine_installation(self) -> Optional[str]:
        """Find system Wine installation."""
        # Check common Wine installation paths
        wine_paths = [
            "/usr/bin/wine",
            "/usr/local/bin/wine",
            shutil.which("wine"),
        ]

        for wine_path in wine_paths:
            if (
                wine_path
                and os.path.exists(wine_path)
                and os.access(wine_path, os.X_OK)
            ):
                logger.info(f"Found system Wine installation: {wine_path}")
                return wine_path

        logger.debug("No system Wine installation found")
        return None

    def _detect_wine_architecture(self) -> str:
        """
        Detect Wine architecture to use based on existing prefix.
        Returns "win32" if prefix supports it, otherwise "win64".
        Only applies to system Wine, not Proton.
        """
        # On Windows or if no wine command, skip
        if self.is_windows or not self.wine_command:
            return "win64"  # Default

        # Determine if we're using Proton or System Wine
        wine_path_lower = self.wine_command.lower()
        is_proton = "proton" in wine_path_lower

        # For Proton, always use win32 (Proton supports it)
        if is_proton:
            logger.debug("Using Proton - will use win32 architecture")
            return "win32"

        # For system Wine, check the existing prefix architecture
        logger.info("Checking Wine prefix architecture...")

        try:
            prefix_path = str(Path.home() / ".wine")

            # If no prefix exists yet, we can use win32
            if not os.path.exists(prefix_path):
                logger.info("No existing Wine prefix found, will use win32")
                return "win32"

            # Check if prefix exists
            if not os.path.exists(os.path.join(prefix_path, "system.reg")):
                logger.info("Wine prefix not fully initialized, will use win32")
                return "win32"

            # Read the system.reg to check architecture
            try:
                with open(
                    os.path.join(prefix_path, "system.reg"),
                    "r",
                    encoding="utf-8",
                    errors="ignore",
                ) as f:
                    first_lines = f.read(500)  # Read first 500 chars
                    if "#arch=win64" in first_lines:
                        logger.info("Existing Wine prefix is 64-bit, will use win64")
                        return "win64"
                    else:
                        logger.info("Existing Wine prefix is 32-bit, will use win32")
                        return "win32"
            except Exception as e:
                logger.warning(f"Could not read Wine prefix architecture: {e}")
                # Fall back to test mode

        except Exception as e:
            logger.warning(f"Error checking Wine prefix: {e}")

        # If we can't determine from existing prefix, test Wine's capability
        logger.info("Testing Wine 32-bit prefix capability...")
        test_prefix = None
        try:
            test_prefix = os.path.join(
                tempfile.gettempdir(), f"wine_arch_test_{os.getpid()}"
            )

            # Try to initialize with win32
            env = os.environ.copy()
            env["WINEDEBUG"] = "-all"
            env["WINEPREFIX"] = test_prefix
            env["WINE"] = self.wine_command
            env["WINEARCH"] = "win32"

            logger.debug(f"Testing Wine with WINEARCH=win32 and prefix={test_prefix}")

            # Try a simple command
            result = subprocess.run(
                [self.wine_command, "cmd", "/c", "echo test"],
                capture_output=True,
                timeout=5,
                env=env,
            )

            # Check for the specific error
            stderr_output = result.stderr.decode("utf-8", errors="ignore").lower()
            if (
                "winear ch is set to 'win32' but this is not supported in wow64 mode"
                in stderr_output
            ):
                logger.warning(
                    "Wine does not support 32-bit prefixes, falling back to 64-bit"
                )
                return "win64"
            else:
                logger.info("Wine supports 32-bit prefixes")
                return "win32"

        except subprocess.TimeoutExpired:
            logger.warning("Wine architecture test timed out, assuming win64")
            return "win64"
        except Exception as e:
            logger.warning(f"Wine architecture test failed: {e}, assuming win64")
            return "win64"
        finally:
            # Clean up test prefix
            if test_prefix and os.path.exists(test_prefix):
                try:
                    shutil.rmtree(test_prefix)
                    logger.debug(f"Cleaned up test prefix: {test_prefix}")
                except Exception:
                    pass  # Don't fail on cleanup

    def _get_wine_architecture(self) -> str:
        """
        Get the Wine architecture to use.
        Returns cached result if available, otherwise detects it.
        """
        if self._wine_arch is None:
            self._wine_arch = self._detect_wine_architecture()
        return self._wine_arch

    def get_available_proton_versions(self) -> List[dict]:
        """
        Get list of all available Proton versions discovered by _find_proton_installation.
        Returns a list of dictionaries with 'name', 'path', and 'dir' keys.
        """
        # If we haven't discovered versions yet, do it now
        if not self._available_proton_versions:
            self._find_proton_installation()

        return self._available_proton_versions.copy()

    def _check_wine_availability(self) -> bool:
        """Check if Proton or Wine is available for Steamless execution."""
        try:
            # On Windows, Wine/Proton is not needed
            if self.is_windows:
                logger.info("Running on Windows - Wine/Proton not required")
                self.wine_command = None  # Not needed on Windows
                return True

            # Discover all available Proton/Wine installations
            logger.info("Searching for Proton or Wine installation...")
            proton_wine = self._find_proton_installation()

            if not proton_wine:
                # Neither Proton nor Wine found
                logger.error(
                    "Neither Proton nor Wine found - Steamless requires Proton or Wine on Linux/SteamOS"
                )
                return False

            # Use selected Proton version if specified
            if (
                self.preferred_proton_version
                and self.preferred_proton_version != "auto"
            ):
                logger.info(
                    f"Looking for preferred Proton version: {self.preferred_proton_version}"
                )

                # Find the preferred version in the list of discovered versions
                for version_info in self._available_proton_versions:
                    if version_info["path"] == self.preferred_proton_version:
                        self.wine_command = self.preferred_proton_version
                        proton_name = version_info["name"]
                        logger.info(f"Using selected Proton version: {proton_name}")
                        self._wine_check_message = f"Using Proton ({proton_name})"
                        return True

                # Preferred version not found, fall back to auto-detection
                logger.warning(
                    f"Preferred Proton version not found: {self.preferred_proton_version}. "
                    "Falling back to auto-detection."
                )

            # Auto-detect: use the newest version (already selected by _find_proton_installation)
            self.wine_command = proton_wine
            logger.info(f"Using Proton: {proton_wine}")
            # Store message to emit later when signals are connected
            proton_name = Path(proton_wine).parent.parent.name
            self._wine_check_message = f"Using Proton ({proton_name})"
            return True

        except Exception as e:
            logger.error(f"Error checking Proton availability: {e}", exc_info=True)
            self.wine_command = None
            return False

    def _create_dotnet_marker(self, prefix_path: str):
        """Create a marker file to track .NET installation."""
        marker_file = os.path.join(prefix_path, ".dotnet48_installed")
        try:
            with open(marker_file, "w") as f:
                f.write("OK\n")
            logger.debug(f"Created .NET installation marker: {marker_file}")
        except Exception as e:
            logger.warning(f"Failed to create marker file: {e}")

    def _check_dotnet_marker_exists(self, prefix_path: str) -> bool:
        """Check if .NET installation marker file exists."""
        marker_file = os.path.join(prefix_path, ".dotnet48_installed")
        if os.path.exists(marker_file):
            logger.info(f"Found .NET installation marker: {marker_file}")
            return True
        return False

    def _check_dotnet_files_exist(self, prefix_path: str) -> bool:
        """Check if .NET Framework 4.8 files exist in the Wine prefix (fallback detection)."""
        try:
            logger.debug(f"Checking for .NET files in prefix: {prefix_path}")

            if not os.path.exists(prefix_path):
                logger.debug(f"Prefix path does not exist: {prefix_path}")
                return False

            # List what exists in the prefix
            try:
                items = os.listdir(prefix_path)
                logger.debug(f"Items in prefix: {items}")
            except Exception as e:
                logger.debug(f"Error listing prefix: {e}")

            # Check for .NET 4.8 specific files - both 32-bit and 64-bit paths
            possible_paths = [
                os.path.join(
                    prefix_path,
                    "drive_c",
                    "windows",
                    "Microsoft.NET",
                    "Framework",
                    "v4.0.30319",
                    "clr.dll",
                ),
                os.path.join(
                    prefix_path,
                    "drive_c",
                    "windows",
                    "Microsoft.NET",
                    "Framework64",
                    "v4.0.30319",
                    "clr.dll",
                ),
            ]

            for dll_path in possible_paths:
                if os.path.exists(dll_path):
                    logger.info(f"Found .NET DLL at: {dll_path}")
                    try:
                        clr_size = os.path.getsize(dll_path)
                        logger.info(f"clr.dll size: {clr_size} bytes")
                        if clr_size > 500000:  # > 500KB
                            logger.info(
                                f".NET Framework detected via file check: {dll_path}"
                            )
                            self._create_dotnet_marker(prefix_path)
                            return True
                    except OSError as e:
                        logger.debug(f"Error checking file size: {e}")

            logger.debug("No .NET files found")
            return False
        except Exception as e:
            logger.debug(f"Error checking for .NET files: {e}", exc_info=True)
            return False

    def _is_prefix_corrupted(self, prefix_path: str) -> bool:
        """Check if a Wine prefix appears to be corrupted or incomplete."""
        try:
            # Check if basic Wine prefix structure exists
            drive_c = os.path.join(prefix_path, "drive_c")
            if not os.path.exists(drive_c):
                return False  # Fresh prefix is fine

            # Check if windows directory exists (indicates initialization started)
            windows_dir = os.path.join(drive_c, "windows")
            if not os.path.exists(windows_dir):
                return False  # Fresh prefix

            # Check for system.reg (Wine prefix database)
            system_reg = os.path.join(prefix_path, "system.reg")
            if not os.path.exists(system_reg):
                return True  # Missing registry = corrupted/incomplete

            # Check file count - if very few files, might be incomplete
            try:
                file_count = sum(1 for _ in os.walk(prefix_path))
                if file_count < 20:  # Very minimal files
                    return True
            except Exception:
                pass

            return False  # Prefix looks OK
        except Exception as e:
            logger.debug(f"Error checking prefix corruption: {e}")
            return False

    def _check_dotnet_availability(self) -> bool:
        """Check if .NET framework 4.8 is installed."""
        # On Windows, .NET is built-in
        if self.is_windows:
            logger.info("Running on Windows - .NET Framework is built-in")
            return True

        if not self.wine_command:
            logger.warning("Wine command not available for .NET check")
            return False

        try:
            prefix_path = self._get_steamless_prefix_path()
            if not prefix_path:
                logger.warning("Steamless prefix path not available for .NET check")
                return False

            # Check if prefix is corrupted
            if self._is_prefix_corrupted(prefix_path):
                logger.warning(f"Wine prefix appears corrupted: {prefix_path}")
                logger.info("Will reinstall .NET in a fresh prefix")

            # Check for .NET installation marker
            if self._check_dotnet_marker_exists(prefix_path):
                logger.info(".NET Framework 4.8 installation confirmed via marker file")
                return True

            # Query the registry for .NET 4.8 installation
            env = os.environ.copy()
            env["WINEDEBUG"] = "-all"
            env["WINEPREFIX"] = prefix_path

            # Using Proton or Wine (based on priority order)
            env["WINE"] = self.wine_command
            env["WINEARCH"] = self._get_wine_architecture()

            # Determine if we're using Proton or System Wine
            wine_path_lower = self.wine_command.lower()
            is_proton = "proton" in wine_path_lower

            if is_proton:
                # Set LD_LIBRARY_PATH for Proton
                wine_bin_dir = Path(self.wine_command).parent
                proton_root = wine_bin_dir.parent.parent
                proton_lib_dir = proton_root / "lib"
                proton_lib64_dir = proton_root / "lib64"

                ld_library_path = str(proton_lib_dir)
                if proton_lib64_dir.exists():
                    ld_library_path = f"{proton_lib64_dir}:{ld_library_path}"

                existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                if existing_ld_path:
                    ld_library_path = f"{ld_library_path}:{existing_ld_path}"

                env["LD_LIBRARY_PATH"] = ld_library_path
                logger.debug(f"Set LD_LIBRARY_PATH for .NET check: {ld_library_path}")
            else:
                # Using System Wine - no need to set LD_LIBRARY_PATH
                logger.debug(
                    "Using system Wine for .NET check - relying on system library paths"
                )

            # Query the registry for .NET 4.8
            test_cmd = [
                self.wine_command,
                "reg",
                "query",
                "HKLM/Software/Microsoft/NET Framework Setup/NDP/v4/Full",
                "/v",
                "Release",
            ]

            logger.debug(
                f"Checking .NET installation with command: {' '.join(test_cmd)}"
            )
            logger.debug(
                f"Using WINEPREFIX: {prefix_path}, WINEARCH: {env.get('WINEARCH')}, WINE: {env.get('WINE')}"
            )

            result = subprocess.run(
                test_cmd, capture_output=True, text=True, timeout=30, env=env
            )

            # Check if Wine doesn't support 32-bit (shouldn't happen with Proton, but keep for safety)
            if (
                result.stderr
                and "WINEARCH is set to 'win32' but this is not supported in wow64 mode"
                in result.stderr
            ):
                logger.error("Wine does not support 32-bit prefixes (wow64 mode)")
                self.error.emit(
                    "The Wine/Proton installation does not support 32-bit prefixes (unexpected).\n\n"
                    "Please ensure:\n"
                    "1. Steam is up to date (if using Proton)\n"
                    "2. Proton is enabled in Steam settings\n"
                    "3. Try using a newer Proton version or system Wine\n"
                )
                return False

            if result.returncode == 0:
                output = result.stdout.strip()
                logger.debug(f"Registry query output: {output}")

                # Parse the Release value (expected: "Release    REG_DWORD    528040")
                release_match = re.search(
                    r"Release\s+REG_DWORD\s+(\d+)", output, re.IGNORECASE
                )
                if release_match:
                    release_value = int(release_match.group(1))
                    # .NET 4.8 requires Release >= 528040
                    if release_value >= 528040:
                        logger.info(
                            f".NET Framework 4.8 is installed (Release: {release_value})"
                        )
                        self._create_dotnet_marker(prefix_path)
                        return True
                    else:
                        logger.debug(
                            f".NET version insufficient (Release: {release_value}, need >= 528040)"
                        )
                        return False
                else:
                    logger.warning("Could not parse Release value from registry")
                    # Fallback: check if .NET files exist
                    if self._check_dotnet_files_exist(prefix_path):
                        logger.info(
                            "Found .NET Framework files, assuming .NET 4.8 is installed"
                        )
                        self._create_dotnet_marker(prefix_path)
                        return True
                    return False
            else:
                stderr_output = (
                    result.stderr.strip() if result.stderr else "No error output"
                )
                logger.warning(f".NET check failed (exit code: {result.returncode})")
                logger.warning(f"Registry query failed - stderr: {stderr_output}")

                # Fallback: check if .NET files exist
                if self._check_dotnet_files_exist(prefix_path):
                    logger.info("Found .NET Framework 4.8 files, .NET is installed")
                    self._create_dotnet_marker(prefix_path)
                    return True

                # Check if the prefix exists but just doesn't have .NET
                if (
                    "does not exist" in stderr_output.lower()
                    or "no such file" in stderr_output.lower()
                ):
                    logger.info(
                        "Wine prefix does not exist yet, will be created during installation"
                    )
                else:
                    logger.debug(
                        f"Registry query returned non-zero exit code, assuming .NET not installed"
                    )

                return False

        except subprocess.TimeoutExpired:
            logger.warning(".NET check timed out")
            return False
        except Exception as e:
            logger.debug(f"Error checking .NET installation: {e}")
            return False

    def _get_steamless_prefix_path(self) -> Optional[str]:
        """Get or create the Steamless Wine prefix directory."""
        # Wine prefixes are only needed on Linux
        if self.is_windows:
            logger.debug("No Wine prefix needed on Windows")
            return None

        try:
            # Determine if we're using Proton or System Wine
            wine_path_lower = self.wine_command.lower() if self.wine_command else ""
            is_proton = "proton" in wine_path_lower

            if is_proton:
                # Using Proton - use XDG-compliant location for Proton prefix
                prefix_path = (
                    Path.home()
                    / ".local"
                    / "share"
                    / "ACCELA"
                    / "steamless"
                    / "bin"
                    / "pfx"
                )

                # Create directory if it doesn't exist
                prefix_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using Proton Steamless Wine prefix at: {prefix_path}")
                return str(prefix_path)
            else:
                # Using System Wine - use the standard default wine prefix
                # This allows the .NET check to run in the user's existing Wine prefix
                prefix_path = str(Path.home() / ".wine")
                logger.info(
                    f"Using system Wine - will use default wine prefix ({prefix_path})"
                )
                return prefix_path

        except Exception as e:
            logger.error(f"Failed to create Steamless prefix directory: {e}")
            return None

    def _initialize_wine_prefix(self, prefix_path: str) -> bool:
        """Initialize Wine prefix to prevent configuration dialogs."""
        if self.is_windows:
            return True

        if not self.wine_command:
            logger.warning("Wine command not available for prefix initialization")
            return False

        try:
            logger.info(f"Initializing Wine prefix: {prefix_path}")

            env = os.environ.copy()
            env["WINEDEBUG"] = "-all"
            env["WINEPREFIX"] = prefix_path

            # Using Proton or Wine
            env["WINE"] = self.wine_command
            env["WINEARCH"] = self._get_wine_architecture()

            # Determine if we're using Proton or System Wine
            wine_path_lower = self.wine_command.lower()
            is_proton = "proton" in wine_path_lower

            if is_proton:
                # Set LD_LIBRARY_PATH for Proton
                wine_bin_dir = Path(self.wine_command).parent
                proton_root = wine_bin_dir.parent.parent
                proton_lib_dir = proton_root / "lib"
                proton_lib64_dir = proton_root / "lib64"

                ld_library_path = str(proton_lib_dir)
                if proton_lib64_dir.exists():
                    ld_library_path = f"{proton_lib64_dir}:{ld_library_path}"

                existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                if existing_ld_path:
                    ld_library_path = f"{ld_library_path}:{existing_ld_path}"

                env["LD_LIBRARY_PATH"] = ld_library_path
                logger.debug(f"Set LD_LIBRARY_PATH for prefix init: {ld_library_path}")
            else:
                # Using System Wine - no need to set LD_LIBRARY_PATH
                logger.debug(
                    "Using system Wine for prefix init - relying on system library paths"
                )

            # Initialize the prefix
            logger.debug("Initializing Wine prefix...")
            result = subprocess.run(
                [self.wine_command, "cmd", "/c", "echo test >nul"],
                capture_output=True,
                timeout=30,
                env=env,
                cwd=str(Path.home()),
            )

            if result.returncode == 0:
                logger.info("Wine prefix initialized successfully")
                return True
            else:
                logger.warning(
                    f"Wine prefix initialization returned exit code: {result.returncode}"
                )
                return True

        except subprocess.TimeoutExpired:
            logger.warning("Wine prefix initialization timed out")
            return False
        except Exception as e:
            logger.warning(f"Wine prefix initialization failed: {e}")
            return True

    def _get_winetricks_path(self) -> Optional[str]:
        """Get the path to winetricks script."""
        # Check local winetricks in deps directory
        # Use resource_path for PyInstaller compatibility
        try:
            local_winetricks = resource_path("deps/winetricks/winetricks")
        except Exception:
            # Fallback to direct path if resource_path fails
            local_winetricks = os.path.join(
                os.getcwd(), "deps", "winetricks", "winetricks"
            )

        if os.path.exists(local_winetricks) and os.access(local_winetricks, os.X_OK):
            logger.debug(f"Using local winetricks: {local_winetricks}")
            return local_winetricks
        elif os.path.exists(local_winetricks):
            # Make it executable if it exists but isn't executable
            try:
                os.chmod(local_winetricks, 0o755)
                logger.debug(f"Made winetricks executable: {local_winetricks}")
                return local_winetricks
            except Exception as e:
                logger.warning(f"Could not make winetricks executable: {e}")

        # Check if we can use system winetricks
        if shutil.which("winetricks"):
            logger.debug("Using system winetricks")
            return "winetricks"

        logger.error("winetricks not found in deps/winetricks/ or system PATH")
        return None

    def _install_dotnet(self) -> bool:
        """Install .NET Framework 4.8 using winetricks."""
        if self.is_windows:
            logger.info("Running on Windows - .NET Framework is built-in")
            return True

        winetricks_path = self._get_winetricks_path()
        if not winetricks_path:
            self.error.emit(
                "winetricks not found. Please ensure winetricks is installed or available in deps/winetricks/winetricks"
            )
            return False

        if not self.wine_command:
            self.error.emit("Wine command not available for .NET installation")
            return False

        try:
            prefix_path = self._get_steamless_prefix_path()
            if not prefix_path:
                self.error.emit("Steamless prefix path not available")
                return False

            # Clean up corrupted prefix if needed
            if os.path.exists(prefix_path):
                if self._is_prefix_corrupted(prefix_path):
                    logger.warning(f"Removing corrupted Wine prefix: {prefix_path}")
                    self.progress.emit("Cleaning up corrupted Wine prefix...")
                    try:
                        shutil.rmtree(prefix_path)
                        logger.info("Corrupted prefix removed")
                    except Exception as e:
                        logger.error(f"Failed to remove corrupted prefix: {e}")
                        self.error.emit(f"Failed to clean up corrupted prefix: {e}")
                        return False

            os.makedirs(prefix_path, exist_ok=True)

            env = os.environ.copy()
            env["WINEDEBUG"] = "-all"
            env["WINEPREFIX"] = prefix_path

            # Using Proton or Wine
            env["WINE"] = self.wine_command
            env["WINEARCH"] = self._get_wine_architecture()

            # Determine if we're using Proton or System Wine
            wine_path_lower = self.wine_command.lower()
            is_proton = "proton" in wine_path_lower

            if is_proton:
                # Set LD_LIBRARY_PATH for Proton
                wine_bin_dir = Path(self.wine_command).parent
                proton_root = wine_bin_dir.parent.parent
                proton_lib_dir = proton_root / "lib"
                proton_lib64_dir = proton_root / "lib64"

                ld_library_path = str(proton_lib_dir)
                if proton_lib64_dir.exists():
                    ld_library_path = f"{proton_lib64_dir}:{ld_library_path}"

                existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                if existing_ld_path:
                    ld_library_path = f"{ld_library_path}:{existing_ld_path}"

                env["LD_LIBRARY_PATH"] = ld_library_path
                logger.debug(
                    f"Set LD_LIBRARY_PATH for .NET installation: {ld_library_path}"
                )
            else:
                # Using System Wine - no need to set LD_LIBRARY_PATH
                logger.debug(
                    "Using system Wine for .NET installation - relying on system library paths"
                )

            wine_cmd = self.wine_command

            # Verify the Proton/Wine binary exists
            if not os.path.exists(wine_cmd):
                logger.error(f"Wine binary not found at {wine_cmd}")
                self.error.emit(
                    "Proton/Wine not found or installation is incomplete.\n"
                    "\n"
                    "For SteamOS: Ensure Steam is installed and up to date\n"
                    "For other Linux distributions:\n"
                    "  - Install Steam with Proton support, or\n"
                    "  - Install Wine: sudo apt install wine (or your distro's package manager)\n"
                )
                return False

            self.progress.emit("Installing .NET Framework 4.8...")

            cmd = [winetricks_path, "-q", "-f", "dotnet48"]

            logger.info(f"Installing .NET 4.8 using winetricks")
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.debug(
                f"Using WINEPREFIX: {prefix_path}, WINEARCH: {env.get('WINEARCH')}, WINE: {wine_cmd}"
            )

            # Run winetricks
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
                env=env,
                cwd=str(Path.home()),
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

            output_lines = []
            last_progress_time = time.time()
            no_output_timeout = 60

            if process.stdout:
                while True:
                    if process.poll() is not None:
                        break

                    try:
                        line_bytes = process.stdout.readline()
                        if not line_bytes:
                            if time.time() - last_progress_time > no_output_timeout:
                                self.progress.emit(
                                    "Still installing .NET (this can take 10-15 minutes)..."
                                )
                                last_progress_time = time.time()
                            time.sleep(0.1)
                            continue

                        try:
                            line = line_bytes.decode("utf-8").strip()
                            if line:
                                output_lines.append(line)
                                if len(output_lines) % 10 == 0 or any(
                                    keyword in line.lower()
                                    for keyword in [
                                        "installing",
                                        "done",
                                        "error",
                                        "success",
                                        "completed",
                                        "setting",
                                        "download",
                                    ]
                                ):
                                    self.progress.emit(f"winetricks: {line}")
                                    last_progress_time = time.time()
                        except UnicodeDecodeError:
                            logger.debug("Skipping non-UTF-8 output from winetricks")
                            continue
                    except Exception as e:
                        logger.debug(f"Error reading line: {e}")
                        break

            process.wait()

            # Check for 32-bit support error (shouldn't happen with Proton)
            if process.returncode != 0 and output_lines:
                error_output = "\n".join(output_lines[-10:])
                if (
                    "WINEARCH is set to 'win32' but this is not supported in wow64 mode"
                    in error_output
                ):
                    logger.error(
                        "Wine does not support 32-bit prefixes (unexpected with Proton/Wine)"
                    )
                    self.error.emit(
                        "The Wine/Proton installation does not support 32-bit prefixes (unexpected).\n\n"
                        "Please ensure:\n"
                        "1. Steam is up to date (if using Proton)\n"
                        "2. Proton is enabled in Steam settings\n"
                        "3. Try using a newer Proton version or system Wine\n"
                    )
                    return False

            if process.returncode == 0:
                logger.info("Successfully installed .NET Framework 4.8")
                self.progress.emit("Successfully installed .NET Framework 4.8")

                # Create marker file
                marker_file = os.path.join(prefix_path, ".dotnet48_installed")
                try:
                    with open(marker_file, "w") as f:
                        f.write("OK\n")
                    logger.info(f"Created .NET installation marker: {marker_file}")
                except Exception as e:
                    logger.warning(f"Failed to create marker file: {e}")

                return True
            else:
                logger.error(f"winetricks failed with exit code: {process.returncode}")
                self.error.emit(
                    f"Failed to install .NET Framework 4.8 (exit code: {process.returncode}). "
                    f"Please ensure you have sufficient disk space and try running the installer manually."
                )
                return False

        except Exception as e:
            logger.error(f"Error installing .NET: {e}", exc_info=True)
            self.error.emit(f"Error installing .NET: {str(e)}")
            return False

    def find_game_executables(self, game_directory: str) -> List[dict]:
        """
        Find all executable files in the game directory and subdirectories.
        Returns a list of .exe files sorted by priority.
        """
        try:
            if not os.path.exists(game_directory):
                logger.error(f"Game directory not found: {game_directory}")
                return []

            exe_files = []
            game_name = os.path.basename(game_directory.rstrip("/"))

            # Walk through all subdirectories
            logger.debug(f"Searching for executables in: {game_directory}")
            all_files_found = []

            try:
                for root, dirs, files in os.walk(game_directory):
                    try:
                        logger.debug(
                            f"Scanning directory: {root} - Found {len(files)} files"
                        )
                        all_files_found.extend(files)

                        for file in files:
                            try:
                                if file.lower().endswith(".exe"):
                                    file_path = os.path.join(root, file)
                                    logger.debug(f"Found executable: {file_path}")

                                    # Skip system/uninstaller files
                                    if self._should_skip_exe(file, file_path):
                                        logger.info(
                                            f"Skipping executable (system/utility): {file}"
                                        )
                                        continue

                                    # Get file size for priority calculation and size check
                                    try:
                                        file_size = os.path.getsize(file_path)
                                        # Additional check: ensure the file is not a broken symlink
                                        if file_size == 0 and os.path.islink(file_path):
                                            logger.warning(
                                                f"Skipping broken symlink: {file_path}"
                                            )
                                            continue
                                    except (OSError, FileNotFoundError) as e:
                                        logger.warning(
                                            f"Cannot access file {file_path}: {e}"
                                        )
                                        # Skip files we can't read (permissions, broken symlinks, etc.)
                                        continue

                                    # Skip very small files (likely utilities)
                                    if file_size < 100 * 1024:  # < 100KB
                                        logger.info(
                                            f"Skipping executable (too small, likely utility): {file} ({file_size} bytes)"
                                        )
                                        continue

                                    exe_files.append(
                                        {
                                            "path": file_path,
                                            "name": file,
                                            "size": file_size,
                                            "priority": self._calculate_exe_priority(
                                                file, game_name, file_size
                                            ),
                                        }
                                    )
                                else:
                                    # Log non-exe files for debugging
                                    if file.lower().endswith((".dll", ".so", ".bin")):
                                        logger.debug(f"Found binary file: {file}")
                            except Exception as e:
                                logger.warning(
                                    f"Error processing file {file} in {root}: {e}"
                                )
                                continue
                    except Exception as e:
                        logger.warning(f"Error scanning directory {root}: {e}")
                        continue
            except Exception as e:
                logger.error(
                    f"Critical error during directory walk: {e}", exc_info=True
                )
                return []

            # Log summary of what was found
            exe_count = len([f for f in all_files_found if f.lower().endswith(".exe")])
            logger.debug(
                f"Directory scan complete. Total files: {len(all_files_found)}, EXE files: {exe_count}, After filtering: {len(exe_files)}"
            )

            if exe_count == 0:
                logger.warning(f"No .exe files found in {game_directory}")
                logger.debug(f"First 10 files found: {all_files_found[:10]}")
            elif len(exe_files) == 0:
                logger.warning(
                    f"Found {exe_count} .exe files but all were filtered out"
                )
                try:
                    for root, dirs, files in os.walk(game_directory):
                        for file in files:
                            if file.lower().endswith(".exe"):
                                logger.debug(
                                    f"Filtered EXE: {os.path.join(root, file)}"
                                )
                except Exception:
                    pass  # Don't crash on logging errors

            # Sort by priority (higher first)
            exe_files.sort(key=lambda x: x["priority"], reverse=True)

            if len(exe_files) == 0:
                logger.warning(f"No executables found in {game_directory}")
            else:
                logger.debug(
                    f"Found {len(exe_files)} executable(s) in {game_directory}"
                )
                for exe in exe_files[:3]:  # Log top 3 candidates only in debug
                    logger.debug(
                        f"  - {exe['name']} ({exe['size']} bytes, priority: {exe['priority']})"
                    )

            return exe_files  # Return full dictionaries with path, name, size, priority

        except Exception as e:
            logger.error(f"Critical error in find_game_executables: {e}", exc_info=True)
            return []

    def _should_skip_exe(self, filename: str, file_path: Optional[str] = None) -> bool:
        """Check if an executable should be skipped based on name patterns."""
        try:
            skip_patterns = [
                r"^unins.*\.exe$",  # uninstallers
                r"^setup.*\.exe$",  # installers
                r"^config.*\.exe$",  # configuration tools
                r"^launcher.*\.exe$",  # launchers (usually not the main game)
                r"^updater.*\.exe$",  # updaters
                r"^patch.*\.exe$",  # patches
                r"^redist.*\.exe$",  # redistributables
                r"^vcredist.*\.exe$",  # Visual C++ redistributables
                r"^dxsetup.*\.exe$",  # DirectX setup
                r"^physx.*\.exe$",  # PhysX installers
                r".*crash.*\.exe$",  # crash handlers
                r".*handler.*\.exe$",  # handlers
                r"^unity.*\.exe$",  # Unity crash handlers and utilities
                r".*unity.*\.exe$",  # Unity-related utilities
                r".*\.original\.exe$",  # Steamless backup files
            ]

            filename_lower = filename.lower()
            for pattern in skip_patterns:
                if re.match(pattern, filename_lower):
                    return True

            # Skip very small files (likely utilities) - but allow main game executables
            try:
                # Use full path if available, otherwise assume it's a relative path
                path_to_check = file_path if file_path else filename
                file_size = os.path.getsize(path_to_check)
                # Only skip if smaller than 100KB AND not matching game name patterns
                if file_size < 100 * 1024:  # < 100KB
                    return True
            except OSError:
                # Only skip if we can't get the file size AND it's not a likely main executable
                # Main game executables should exist, so this might be a broken symlink
                if file_path is None:
                    return True
                # If we have a full path but can't read it, log but don't skip (might be permission issue)
                logger.debug(f"Cannot read file size for {filename}, but not skipping")
                return False

            return False
        except Exception as e:
            logger.warning(f"Error in _should_skip_exe for {filename}: {e}")
            return False  # Don't skip on error - let it be processed

    def _calculate_exe_priority(
        self, filename: str, game_name: str, file_size: int
    ) -> int:
        """Calculate priority score for an executable file."""
        try:
            filename_lower = filename.lower()
            game_name_lower = game_name.lower()

            priority = 0

            # High priority: exact match with game name (remove spaces and special chars)
            game_name_clean = "".join(c for c in game_name_lower if c.isalnum())
            game_name_with_spaces = game_name_lower.replace(" ", "")

            if filename_lower.startswith(game_name_clean):
                priority += 100
            elif filename_lower.startswith(game_name_with_spaces):
                priority += 90
            elif game_name_clean in filename_lower:
                priority += 80  # Partial match still gets good priority
            elif game_name_with_spaces in filename_lower:
                priority += 70

            # Medium priority: common main executable names
            main_exe_patterns = ["game.exe", "main.exe", "play.exe", "start.exe"]
            if filename_lower in main_exe_patterns:
                priority += 50

            # Bonus for larger files (likely the main game)
            if file_size > 50 * 1024 * 1024:  # > 50MB
                priority += 30
            elif file_size > 10 * 1024 * 1024:  # > 10MB
                priority += 20
            elif file_size > 5 * 1024 * 1024:  # > 5MB
                priority += 10

            # Penalty for common non-game executables
            if any(
                word in filename_lower
                for word in ["editor", "tool", "config", "settings"]
            ):
                priority -= 20

            # High penalty for crash handlers and utilities
            if any(
                word in filename_lower
                for word in ["crash", "handler", "debug", "unitycrash"]
            ):
                priority -= 50

            # Very high penalty for Unity system files (extra safety)
            if any(
                word in filename_lower
                for word in ["unityplayer", "unity crash", "crash handler"]
            ):
                priority -= 100  # Effectively exclude these files

            return max(0, priority)
        except Exception as e:
            logger.warning(f"Error calculating priority for {filename}: {e}")
            return 0  # Return lowest priority on error

    def process_game_with_steamless(self, game_directory: str) -> bool:
        """
        Main method to process a game directory with Steamless.
        Returns True if successful, False otherwise.
        """
        try:
            # Emit stored message from Wine check if any
            if self._wine_check_message:
                self.progress.emit(self._wine_check_message)
                self._wine_check_message = None  # Clear after emitting

            if not self.wine_available:
                self.error.emit(
                    "Wine/Proton is not available for Steamless execution.\n"
                    "Please install Wine or ensure Steam with Proton is installed."
                )
                return False

            # Initialize Wine prefix to prevent configuration dialogs
            # Note: On Windows, _get_steamless_prefix_path() returns None, so this is skipped
            prefix_path = self._get_steamless_prefix_path()
            if prefix_path:
                self.progress.emit("Initializing Wine environment...")
                if not self._initialize_wine_prefix(prefix_path):
                    logger.warning(
                        "Wine prefix initialization failed, but continuing..."
                    )
            else:
                logger.debug("No Wine prefix needed (running on Windows)")

            # Check and install .NET Framework if needed
            self.progress.emit("Checking .NET Framework 4.8 availability...")
            self.dotnet_available = self._check_dotnet_availability()

            if not self.dotnet_available:
                self.progress.emit(".NET Framework 4.8 not found in prefix")
                self.progress.emit(
                    "Installing .NET Framework 4.8 (first-time installation - this may take 10-20 minutes)..."
                )
                if not self._install_dotnet():
                    return False
                self.dotnet_available = True

            if not os.path.exists(self.steamless_path):
                self.error.emit(f"Steamless directory not found: {self.steamless_path}")
                return False

            steamless_cli = os.path.join(self.steamless_path, "Steamless.CLI.exe")
            if not os.path.exists(steamless_cli):
                self.error.emit(f"Steamless.CLI.exe not found: {steamless_cli}")
                return False

            # Validate game_directory is actually a directory
            if not os.path.isdir(game_directory):
                self.error.emit(f"Game path is not a directory: {game_directory}")
                return False

            # Ensure game_directory is an absolute path
            if not os.path.isabs(game_directory):
                game_directory = os.path.abspath(game_directory)
                logger.debug(f"Converted to absolute path: {game_directory}")

            # Check if directory is readable
            if not os.access(game_directory, os.R_OK):
                self.error.emit(f"Game directory is not readable: {game_directory}")
                return False

            self.progress.emit("Searching for game executables...")
            exe_files = self.find_game_executables(game_directory)

            if not exe_files:
                self.error.emit("No suitable game executables found.")
                return False

            # Try executables in order of priority until one works
            max_attempts = min(3, len(exe_files))  # Try up to 3 executables

            self.progress.emit(f"Found {len(exe_files)} executable(s) to evaluate")

            # Log all candidates for user transparency
            for i, exe_info in enumerate(exe_files[:5]):  # Show top 5 candidates
                self.progress.emit(
                    f"  Candidate {i + 1}: {exe_info['name']} (priority: {exe_info['priority']}, size: {exe_info['size']:,} bytes)"
                )

            for i in range(max_attempts):
                exe_info = exe_files[i]
                target_exe = exe_info["path"]
                exe_name = exe_info["name"]
                priority = exe_info["priority"]

                self.progress.emit(
                    f"Attempt {i + 1}/{max_attempts}: Processing {exe_name} (priority: {priority})"
                )

                if self._run_steamless_on_exe(target_exe):
                    self.progress.emit(f"Successfully processed: {exe_name}")
                    return True
                else:
                    self.progress.emit(f"Failed to process {exe_name}, trying next...")
                    continue

            # If all attempts failed
            self.error.emit(f"Failed to process all {max_attempts} executable(s).")
            return False

        except Exception as e:
            logger.error(
                f"Critical error in process_game_with_steamless: {e}", exc_info=True
            )
            self.error.emit(f"Unexpected error during Steamless processing: {str(e)}")
            return False

    def _run_steamless_on_exe(self, exe_path: str) -> bool:
        """Run Steamless CLI on a specific executable."""
        try:
            # Convert Linux path to Windows path for Wine
            target_path = self._convert_to_windows_path(exe_path)
            if not target_path:
                return False

            steamless_dir = self.steamless_path
            steamless_cli = os.path.join(steamless_dir, "Steamless.CLI.exe")

            # Prepare environment
            env = None
            if not self.is_windows:
                env = os.environ.copy()
                env["WINEDEBUG"] = "-all"
                prefix_path = self._get_steamless_prefix_path()
                if prefix_path:
                    env["WINEPREFIX"] = prefix_path
                    logger.debug(f"Using WINEPREFIX: {prefix_path}")

                # Prepare command for Linux (Proton or Wine)
                if not self.wine_command:
                    self.error.emit("Proton/Wine not available")
                    return False

                cmd = [
                    self.wine_command,
                    steamless_cli,
                    "-f",
                    target_path,
                    "--quiet",
                    "--realign",
                    "--recalcchecksum",
                ]

                # Using Proton or Wine
                env["WINE"] = self.wine_command
                env["WINEARCH"] = self._get_wine_architecture()

                # Determine if we're using Proton or System Wine
                wine_path_lower = self.wine_command.lower()
                is_proton = "proton" in wine_path_lower

                if is_proton:
                    # Set LD_LIBRARY_PATH for Proton
                    wine_bin_dir = Path(self.wine_command).parent
                    proton_root = wine_bin_dir.parent.parent
                    proton_lib_dir = proton_root / "lib"
                    proton_lib64_dir = proton_root / "lib64"

                    ld_library_path = str(proton_lib_dir)
                    if proton_lib64_dir.exists():
                        ld_library_path = f"{proton_lib64_dir}:{ld_library_path}"

                    existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                    if existing_ld_path:
                        ld_library_path = f"{ld_library_path}:{existing_ld_path}"

                    env["LD_LIBRARY_PATH"] = ld_library_path
                    logger.info(f"Set LD_LIBRARY_PATH for Proton: {ld_library_path}")

                    # Find Proton's wineserver
                    wineserver_path = str(wine_bin_dir / "wineserver")

                    if os.path.exists(wineserver_path):
                        env["WINESERVER"] = wineserver_path
                        logger.info(f"Using Proton wineserver: {wineserver_path}")

                        # Kill existing wineserver processes to prevent version mismatch
                        try:
                            result = subprocess.run(
                                ["pkill", "-9", "-f", "wineserver"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if result.returncode == 0:
                                logger.info("Killed existing wineserver processes")
                        except Exception as e:
                            logger.debug(f"Error killing wineserver: {e}")
                    else:
                        logger.warning(
                            f"Proton wineserver not found at: {wineserver_path}"
                        )
                        logger.warning("This may cause version mismatch errors")
                        # Try alternative location
                        alt_wineserver = str(
                            wine_bin_dir.parent / "dist" / "bin" / "wineserver"
                        )
                        if os.path.exists(alt_wineserver):
                            env["WINESERVER"] = alt_wineserver
                            logger.info(
                                f"Using alternative Proton wineserver: {alt_wineserver}"
                            )

                            # Kill existing wineservers
                            try:
                                subprocess.run(
                                    ["pkill", "-9", "-f", "wineserver"],
                                    capture_output=True,
                                    timeout=5,
                                )
                                logger.info("Killed existing wineserver processes")
                            except Exception:
                                pass
                else:
                    # Using System Wine - let it find its own libraries and wineserver
                    logger.info("Using system Wine - relying on system library paths")
                    # Kill any existing wineserver processes to ensure clean state
                    try:
                        subprocess.run(
                            ["pkill", "-9", "-f", "wineserver"],
                            capture_output=True,
                            timeout=5,
                        )
                        logger.info("Killed existing wineserver processes")
                    except Exception:
                        pass  # Don't fail if we can't kill wineservers
            else:
                # Prepare command for Windows
                cmd = [
                    steamless_cli,
                    "-f",
                    target_path,
                    "--quiet",
                    "--realign",
                    "--recalcchecksum",
                ]

            self.progress.emit(f"Running Steamless: {' '.join(cmd)}")

            # Run Steamless CLI
            if self.is_windows:
                creationflags = (
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                )
                process = subprocess.Popen(
                    cmd,
                    cwd=steamless_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    bufsize=0,
                    creationflags=creationflags,
                )
            else:
                # Determine if we're using Proton or System Wine
                wine_path_lower = self.wine_command.lower()
                is_proton = "proton" in wine_path_lower

                # Use setsid for both Proton and Wine (it helps with process management)
                preexec = os.setsid if hasattr(os, "setsid") else None

                process = subprocess.Popen(
                    cmd,
                    cwd=steamless_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    env=env,
                    preexec_fn=preexec,
                )

            # Store process for cleanup
            self._process_mutex.lock()
            self._current_process = process
            self._process_mutex.unlock()

            # Monitor output
            has_drm = False
            unpacked_created = False
            output_lines = []

            # Debug logging
            logger.debug(
                f"Starting to read output from Steamless process (PID: {process.pid})"
            )
            logger.debug(f"Process stdout exists: {process.stdout is not None}")

            # Small delay to let process start and produce initial output
            import time

            time.sleep(0.1)

            if process.stdout:
                try:
                    for line in iter(process.stdout.readline, ""):
                        if self._current_process != process:
                            logger.debug(
                                "Process was terminated, stopping output monitoring"
                            )
                            break

                        if not line:
                            break

                        line = line.strip()
                        if line:
                            # Filter out Wine messages
                            if line.startswith("wine:"):
                                logger.debug(f"Wine output filtered: {line}")
                            elif line.startswith("Steamless:"):
                                self.progress.emit(f"{line}")
                                output_lines.append(line)
                            elif line.startswith("[Steamless]"):
                                self.progress.emit(f"{line}")
                                output_lines.append(line)
                            else:
                                self.progress.emit(f"{line}")
                                output_lines.append(line)

                        # Check for DRM detection
                        if (
                            "steam stub" in line.lower()
                            or "drift" in line.lower()
                            or "steamstub" in line.lower()
                            or "packed with" in line.lower()
                        ):
                            has_drm = True

                        # Check for unpacked file creation
                        if (
                            "unpacked file saved to disk" in line.lower()
                            or "unpacked file saved as" in line.lower()
                            or "successfully unpacked file" in line.lower()
                            or ("unpacked" in line.lower() and ".exe" in line.lower())
                        ):
                            unpacked_created = True

                except ValueError as e:
                    logger.debug(f"stdout closed during read: {e}")
                except Exception as e:
                    logger.debug(f"Error reading process output: {e}")

            process.wait()

            # Log output summary
            if output_lines:
                logger.debug(
                    f"Steamless output ({len(output_lines)} lines): {output_lines[:3]}..."
                )
            else:
                logger.warning(
                    f"No output captured from Steamless (return code: {process.returncode})"
                )
                self.progress.emit("Warning: No output captured from Steamless")

            # Check exit codes
            # 0 = success, DRM removed
            # 1 = no Steam DRM (not an error, try next executable)
            # >1 = error
            if process.returncode == 1:
                self.progress.emit(
                    "No Steam DRM detected in executable, trying next..."
                )
                return False
            elif process.returncode > 1:
                self.error.emit(
                    f"Steamless failed with exit code: {process.returncode}"
                )
                return False

            # Exit code 0 - check if unpacked file was created
            unpacked_exe = f"{exe_path}.unpacked.exe"
            actual_unpacked_created = os.path.exists(unpacked_exe)

            if actual_unpacked_created:
                self.progress.emit(
                    f"Unpacked file detected: {os.path.basename(unpacked_exe)}"
                )
                return self._handle_unpacked_files(exe_path)
            else:
                if unpacked_created:
                    self.progress.emit(
                        "Steamless output indicated unpacked file was created, but file not found."
                    )
                else:
                    self.progress.emit(
                        "Steamless completed but no unpacked file was created."
                    )
                self.finished.emit(True)
                return True

        except Exception as e:
            logger.error(f"Error running Steamless: {e}", exc_info=True)
            self.error.emit(f"Error running Steamless: {str(e)}")
            return False
        finally:
            # Clean up process reference
            self._process_mutex.lock()
            self._current_process = None
            self._process_mutex.unlock()

    def terminate_process(self):
        """Terminate any running Steamless process (thread-safe)."""
        self._process_mutex.lock()
        try:
            process = self._current_process
            if process and process.poll() is None:
                logger.info("Terminating running Steamless process...")
                try:
                    # CRITICAL: Close stdout first to unblock any readline() calls
                    # This prevents deadlock where the thread is waiting on I/O
                    if process.stdout:
                        try:
                            process.stdout.close()
                        except Exception:
                            pass
                        # Also close stderr if it's separate
                        if hasattr(process, "stderr") and process.stderr:
                            try:
                                process.stderr.close()
                            except Exception:
                                pass

                    # Now terminate the process
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        try:
                            process.kill()
                        except Exception:
                            pass
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            logger.error(
                                "Failed to kill Steamless process even with SIGKILL"
                            )
                    logger.info("Steamless process terminated")
                except Exception as e:
                    logger.error(f"Error terminating Steamless process: {e}")
                finally:
                    self._current_process = None
            else:
                # Process already finished or doesn't exist
                self._current_process = None
        finally:
            self._process_mutex.unlock()

    def _convert_to_windows_path(self, linux_path: str) -> Optional[str]:
        """Convert Linux path to Windows path format for Wine."""
        try:
            if self.is_windows:
                logger.debug("Running on Windows - no path conversion needed")
                return linux_path

            # Try winepath with timeout (Proton or Wine)
            if self.wine_command:
                # Using Proton or Wine
                wine_bin_dir = Path(self.wine_command).parent
                winepath_cmd = str(wine_bin_dir / "winepath")

                if not Path(winepath_cmd).exists():
                    logger.warning(
                        f"Proton winepath not found at {winepath_cmd}, using system winepath"
                    )
                    winepath_cmd = "winepath"
            else:
                # Windows or no Proton available
                winepath_cmd = "winepath"

            try:
                result = subprocess.run(
                    [winepath_cmd, "-w", linux_path],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                if result.returncode == 0:
                    windows_path = result.stdout.strip()
                    logger.debug(
                        f"Converted path (winepath): {linux_path} -> {windows_path}"
                    )
                    return windows_path
                else:
                    logger.warning(
                        f"winepath failed with exit code {result.returncode}, using manual conversion"
                    )
            except FileNotFoundError:
                logger.warning(f"winepath not found, using manual conversion")
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"winepath timed out after 3 seconds, using manual conversion"
                )
            except Exception as e:
                logger.warning(f"Error running winepath: {e}, using manual conversion")

            # Fallback: Manual path conversion
            if linux_path.startswith("/"):
                # Convert /home/user/path/file.exe to Z:\home\user\path\file.exe
                windows_path = "Z:" + linux_path.replace("/", "\\")
                logger.info(f"Converted path (manual): {linux_path} -> {windows_path}")
                return windows_path
            else:
                logger.error(f"Path is not absolute: {linux_path}")
                return None

        except Exception as e:
            logger.error(
                f"Critical error in _convert_to_windows_path: {e}", exc_info=True
            )
            return None

    def _handle_unpacked_files(self, original_exe: str) -> bool:
        """Handle the renaming of files after successful Steamless processing."""
        try:
            # Steamless creates: original.exe.unpacked.exe
            unpacked_exe = f"{original_exe}.unpacked.exe"
            original_backup = f"{original_exe}.original.exe"

            if os.path.exists(unpacked_exe):
                if os.path.exists(original_backup):
                    logger.warning(f"Backup file already exists: {original_backup}")
                    os.remove(original_backup)

                # Perform atomic renames with rollback
                try:
                    shutil.move(original_exe, original_backup)
                    self.progress.emit(
                        f"Renamed original: {os.path.basename(original_exe)} -> {os.path.basename(original_backup)}"
                    )

                    try:
                        shutil.move(unpacked_exe, original_exe)
                        self.progress.emit(
                            f"Renamed unpacked: {os.path.basename(unpacked_exe)} -> {os.path.basename(original_exe)}"
                        )
                    except Exception as e2:
                        logger.error(
                            f"Failed to rename unpacked file, rolling back: {e2}"
                        )
                        try:
                            shutil.move(original_backup, original_exe)
                            logger.info("Rollback successful")
                        except Exception as e3:
                            logger.critical(f"Rollback failed: {e3}")
                            self.error.emit(
                                f"CRITICAL ERROR: Failed to restore original executable!\n"
                                f"The game is in a broken state. Please manually:\n"
                                f"1. Rename '{os.path.basename(original_backup)}' back to '{os.path.basename(original_exe)}'\n"
                                f"2. Delete '{os.path.basename(unpacked_exe)}' if it exists\n"
                                f"Location: {os.path.dirname(original_exe)}"
                            )
                            return False
                        raise e2

                    self.progress.emit("Steam DRM successfully removed!")
                    self.finished.emit(True)
                    return True
                except Exception as e:
                    logger.error(f"Error during file operations: {e}", exc_info=True)
                    raise
            else:
                self.progress.emit(
                    "Unpacked file not found. DRM may not have been present or removable."
                )
                self.finished.emit(True)
                return True

        except Exception as e:
            logger.error(f"Error handling unpacked files: {e}", exc_info=True)
            self.error.emit(f"Error handling unpacked files: {str(e)}")
            return False


class SteamlessTask(QThread):
    """Task for removing Steam DRM using Steamless"""

    progress = pyqtSignal(str)
    progress_percentage = pyqtSignal(int)
    completed = pyqtSignal()
    error = pyqtSignal(tuple)  # Emits (Exception, message, traceback) like TaskRunner
    result = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._is_running = True
        self._thread_completed = False  # Track thread completion state
        self._game_directory = None

        # Steamless configuration
        self.steamless_path = self._get_steamless_path()
        self.steamless_integration = None
        self._integration_mutex = QMutex()  # Thread-safe access to integration
        self.wine_available = False
        self.dotnet_available = False

        # Get Proton version selection from settings
        self.settings = get_settings()
        self.proton_version = self.settings.value(
            "steamless_proton_version", "auto", type=str
        )
        logger.info(f"Proton version setting loaded: {self.proton_version}")

    def _get_steamless_path(self):
        """Get path to Steamless directory"""
        relative_path = "deps/Steamless"

        # For PyInstaller, use resource_path
        try:
            return Path(resource_path(relative_path))
        except Exception:
            return Path(relative_path)

    def _setup_steamless_integration(self):
        """Initialize Steamless integration and check prerequisites"""
        # Check if Steamless directory exists
        if not self.steamless_path.exists():
            error_msg = f"Steamless directory not found at {self.steamless_path}"
            self.progress.emit(error_msg)
            self.error.emit((Exception, error_msg, ""))
            return False

        # Check if Steamless.CLI.exe exists
        steamless_cli = self.steamless_path / "Steamless.CLI.exe"
        if not steamless_cli.exists():
            error_msg = f"Steamless.CLI.exe not found at {steamless_cli}"
            self.progress.emit(error_msg)
            self.error.emit((Exception, error_msg, ""))
            return False

        # Create a temporary integration to check Wine availability
        temp_integration = SteamlessIntegration(
            steamless_path=str(self.steamless_path),
            preferred_proton_version=self.proton_version,
        )

        # Check if Wine/Proton is available (always needed on Linux, not on Windows)
        self.wine_available = temp_integration.wine_available
        if not self.wine_available:
            if sys.platform == "win32":
                error_msg = "Steamless initialization failed on Windows."
            else:
                error_msg = (
                    "Neither Proton nor Wine is installed or available. Steamless requires Proton or Wine to run on Linux/SteamOS.\n"
                    "\n"
                    "For SteamOS: Proton should be included with Steam. If missing, ensure:\n"
                    "  - Steam is installed and updated\n"
                    "  - Proton is enabled in Steam settings\n"
                    "\n"
                    "For other Linux distributions: Install Steam with Proton, or install Wine:\n"
                    "  - Ubuntu/Debian: sudo apt install wine\n"
                    "  - Fedora: sudo dnf install wine\n"
                    "  - Arch: sudo pacman -S wine\n"
                )
            self.progress.emit(error_msg)
            self.error.emit((Exception, error_msg, ""))
            return False

        self.progress.emit("Steamless integration initialized successfully")
        logger.info(f"Steamless initialized at: {self.steamless_path}")
        return True

    def set_game_directory(self, game_directory: str):
        """Set the game directory to process (called before start())"""
        self._game_directory = game_directory

    def run(self):
        """Run Steamless on the game directory (QThread main loop)"""
        try:
            success = False  # Default to failure

            if not self._game_directory:
                error_msg = "Game directory not set"
                self.progress.emit(error_msg)
                self.error.emit((Exception, error_msg, ""))
                self.result.emit(success)
                self.completed.emit()
                self._thread_completed = True
                return

            logger.info(
                f"Starting Steamless task for directory: {self._game_directory}"
            )

            try:
                # Check if directory exists
                if not os.path.exists(self._game_directory):
                    error_msg = f"Game directory not found: {self._game_directory}"
                    self.progress.emit(error_msg)
                    self.error.emit((Exception, error_msg, ""))
                    self.result.emit(success)
                    self.completed.emit()
                    self._thread_completed = True
                    return

                # Check prerequisites (Wine/Proton, Steamless files)
                if not self._setup_steamless_integration():
                    # Error already emitted by _setup_steamless_integration
                    self.result.emit(success)
                    self.completed.emit()
                    self._thread_completed = True
                    return

                # Create SteamlessIntegration instance (created fresh for each run)
                self._integration_mutex.lock()
                try:
                    self.steamless_integration = SteamlessIntegration(
                        steamless_path=str(self.steamless_path),
                        preferred_proton_version=self.proton_version,
                    )
                    # Connect signals - SteamlessIntegration uses different signal types
                    # NOTE: We connect signals but they should be delivered synchronously since
                    # process_game_with_steamless() is called from within the same thread
                    self.steamless_integration.progress.connect(self._handle_progress)
                    self.steamless_integration.error.connect(
                        self._handle_integration_error
                    )
                    self.steamless_integration.finished.connect(
                        self._handle_integration_finished
                    )
                finally:
                    self._integration_mutex.unlock()

                # Process the game with Steamless
                logger.info(
                    f"Processing game directory with Steamless: {self._game_directory}"
                )
                success = self.steamless_integration.process_game_with_steamless(
                    self._game_directory
                )

                # Store result for emission
                final_success = success

                # Emit result and completion signals BEFORE thread exit
                # This ensures signals are delivered while the thread is still alive
                if self.isRunning():
                    self.result.emit(final_success)
                    self.completed.emit()
                self._thread_completed = True

            except Exception as e:
                error_msg = f"Unexpected error during Steamless processing: {e}"
                self.progress.emit(error_msg)
                logger.error(error_msg, exc_info=True)
                import traceback

                self.error.emit((type(e), str(e), traceback.format_exc()))
                self.result.emit(success)
                self.completed.emit()
                self._thread_completed = True
                return

        except Exception as e:
            # Catch any exception that might crash the thread on startup
            error_msg = f"CRITICAL: Thread crashed on startup: {e}"
            logger.critical(error_msg, exc_info=True)
            import traceback

            # Try to emit error even if thread is crashing
            try:
                self.result.emit(False)
                self.completed.emit()
            except:
                pass  # Thread is too broken to emit signals
            return

    def _handle_progress(self, message):
        """Handle progress messages from Steamless integration"""
        # Check if thread is still running before emitting
        if not self.isRunning() or not self._is_running:
            logger.debug(
                f"Ignoring progress message after thread exit: {message[:50]}..."
            )
            return

        # Emit progress message
        self.progress.emit(message)

    def _handle_integration_error(self, message):
        """Handle error messages from SteamlessIntegration"""
        # Check if thread is still running before emitting
        if not self.isRunning() or not self._is_running:
            logger.debug(f"Ignoring error message after thread exit: {message[:50]}...")
            return
        logger.error(f"Steamless error: {message}")
        # Forward to UI - error will be emitted in run() as well
        # This provides better user feedback

    def _handle_integration_finished(self, success):
        """Handle completion signal from SteamlessIntegration"""
        # Check if thread is still running before emitting
        if not self.isRunning() or not self._is_running:
            logger.debug(f"Ignoring finished callback after thread exit")
            return
        if success:
            self.progress.emit("Steamless processing completed successfully")
        else:
            self.progress.emit("Steamless processing completed with warnings")
        # Note: Don't emit completed signal here - it's handled in run()

    def _handle_error(self, message):
        """Legacy handler for errors - kept for compatibility"""
        # Check if thread is still running before emitting
        if not self.isRunning() or not self._is_running:
            logger.debug(f"Ignoring error message after thread exit: {message[:50]}...")
            return
        # This should not be used anymore since error signal now emits tuples
        logger.error(f"Steamless task error: {message}")

    def _handle_finished(self, success):
        """Legacy handler for completion - kept for compatibility"""
        # Check if thread is still running before emitting
        if not self.isRunning() or not self._is_running:
            logger.debug(f"Ignoring finished callback after thread exit")
            return
        if success:
            self.progress.emit("Steamless processing completed successfully")
        else:
            self.progress.emit("Steamless processing completed with warnings")

    def stop(self):
        """Stop the Steamless task (thread-safe)"""
        logger.debug("Stop signal received by Steamless task")

        # Return early if already stopped or completed
        if not self._is_running:
            return

        self._is_running = False

        # Terminate any running Steamless subprocess (thread-safe)
        self._integration_mutex.lock()
        try:
            if self.steamless_integration:
                try:
                    self.steamless_integration.terminate_process()
                except Exception as e:
                    logger.error(f"Error during process termination: {e}")
        finally:
            self._integration_mutex.unlock()

        # Disconnect SteamlessIntegration signals if connected (thread-safe)
        self._integration_mutex.lock()
        try:
            if self.steamless_integration:
                try:
                    # Disconnect all signals
                    self.steamless_integration.progress.disconnect(
                        self._handle_progress
                    )
                    self.steamless_integration.error.disconnect(
                        self._handle_integration_error
                    )
                    self.steamless_integration.finished.disconnect(
                        self._handle_integration_finished
                    )
                    logger.debug("SteamlessIntegration signals disconnected")
                except (TypeError, RuntimeError) as e:
                    # TypeError: signal not connected, RuntimeError: C++ object deleted
                    logger.debug(f"Signal disconnect during stop (expected): {e}")
        except Exception as e:
            logger.error(f"Error during signal cleanup: {e}")
        finally:
            self._integration_mutex.unlock()

        # Wait for thread to finish BEFORE cleaning up
        # This prevents QObject deletion crashes
        if self.isRunning():
            logger.debug("Waiting for SteamlessTask thread to finish...")
            self.quit()  # Ask thread to exit its event loop
            if not self.wait(
                600000
            ):  # Wait up to 10 minutes (first-time .NET install can take 10-20 minutes)
                logger.warning("SteamlessTask thread did not finish within timeout")
                # Force terminate if needed (rare)
                self.terminate()
                self.wait(5000)  # Wait another 5 seconds
        logger.debug("SteamlessTask thread has finished")

        # Clean up references
        self._integration_mutex.lock()
        try:
            self.steamless_integration = None
        finally:
            self._integration_mutex.unlock()

        # Legacy compatibility
        self.process = None

    def is_wine_available(self):
        """Check if Wine is available for Steamless execution"""
        return self.wine_available

    def is_dotnet_available(self):
        """Check if .NET Framework 4.8 is available for Steamless execution"""
        return self.dotnet_available

    def get_steamless_path(self):
        """Get the path to the Steamless directory"""
        return str(self.steamless_path)
