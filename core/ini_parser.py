import configparser
import logging
import os

from utils.helpers import resource_path

logger = logging.getLogger(__name__)


def parse_depots_ini():
    config = configparser.ConfigParser()
    depot_descriptions = {}

    ini_path = resource_path("res/depots.ini")

    try:
        if not os.path.exists(ini_path):
            logger.warning(
                f"'depots.ini' file not found at {ini_path}. Depot names may be generic."
            )
            return {}

        config.read(ini_path, encoding="utf-8")

        if "depots" in config:
            for depot_id, name in config["depots"].items():
                depot_descriptions[depot_id] = name
            logger.debug(
                f"Successfully loaded {len(depot_descriptions)} depot descriptions from .ini."
            )
        else:
            logger.warning(f"No [depots] section found in '{ini_path}'.")

    except configparser.Error as e:
        logger.error(f"Failed to parse 'depots.ini' at {ini_path}: {e}")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while reading 'depots.ini': {e}",
            exc_info=True,
        )

    return depot_descriptions
