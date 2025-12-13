import pandas as pd
from src.utils.general_functions import load_data


def test_load_data_uses_cache(tmp_path):
    """Test that load_data() loads from cache when use_cache=True."""
    # Create a mock cached file
    cache_file = tmp_path / "data" / "test_file.csv"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Create sample cached data
    cached_data = pd.DataFrame(
        {"value": [1, 2, 3]},
        index=pd.MultiIndex.from_tuples([("A", 1), ("A", 2), ("B", 1)], names=["level1", "level2"]),
    )
    cached_data.to_csv(cache_file, index=True)

    # Call load_data with use_cache=True
    result = load_data(
        url="example_data.csv",
        file_path=str(cache_file),
        use_cache=True,
        index_col=["level1", "level2"],
    )

    # Assert the cached data was loaded
    pd.testing.assert_frame_equal(result, cached_data)


def test_load_data_downloads_when_use_cache_false(tmp_path):
    """Test that load_data() downloads data when use_cache=False."""
    # Define a mock URL and cache file path
    url = "https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_2030.csv"
    cache_file = tmp_path / "data" / "test_file.csv"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Call load_data with use_cache=False
    result = load_data(url=url, file_path=str(cache_file), use_cache=False)

    # Assert that data was downloaded and saved to cache
    assert cache_file.exists()
    assert not result.empty


def test_load_data_downloads_when_no_cache(tmp_path):
    """Test that load_data() downloads data when cache is missing."""
    # Define a mock URL and cache file path
    url = "https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_2030.csv"
    cache_file = tmp_path / "data" / "test_file.csv"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Ensure the cache file does not exist
    if cache_file.exists():
        cache_file.unlink()

    # Call load_data with use_cache=True
    result = load_data(url=url, file_path=str(cache_file), use_cache=True)

    # Assert that data was downloaded and saved to cache
    assert cache_file.exists()
    assert not result.empty
