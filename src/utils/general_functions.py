from pathlib import Path
import pandas as pd
from loguru import logger


def get_repo_root():
    return Path(__file__).parent.parent.parent


def load_data(url: str, file_path: str, use_cache: bool = True, index_col=None) -> pd.DataFrame:
    """
    Loads data from a URL or from a cached file.

    Args:
        url (str): The URL to download the data from.
        file_path (str): The path of the cached file.
        use_cache (bool): Whether to use the cached file if it exists.

    Returns:
        pd.DataFrame: The loaded data.
    """
    if use_cache:
        try:
            data = pd.read_csv(f"{file_path}", index_col=index_col)
            logger.info(f"Loaded cached data from {file_path}.")
            return data
        except FileNotFoundError:
            logger.info(f"No cached data found for {file_path}, downloading...")

    # Download data (either use_cache=False or cache loading failed)
    logger.info(f"Downloading data from {url}...")
    data = pd.read_csv(url, index_col=index_col)
    data.to_csv(f"{file_path}")
    logger.info(f"Saved data to {file_path}.")

    return data
