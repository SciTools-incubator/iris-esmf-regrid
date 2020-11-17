"""Common testing infrastructure."""

import pathlib

import numpy as np


# Base directory of the test results.
_RESULT_PATH = pathlib.Path(__file__).parent.resolve() / "results"


def get_result_path(relative_path, unit=True):
    """
    Form the absolute path to the results test file.

    Parameters
    ----------
    relative_path : str, path, iterable str/path
        The relative path to the target test file.
    unit : bool, optional
        Specify whether the `relative_path` is for a unit test.
        Default is True.

    Returns
    -------
    Path
        The absolute result path.

    """
    if isinstance(relative_path, str):
        relative_path = pathlib.Path(relative_path)

    if not isinstance(relative_path, pathlib.PurePath):
        relative_path = pathlib.Path(*relative_path)

    if unit:
        relative_path = pathlib.Path("unit") / relative_path

    result = _RESULT_PATH / relative_path

    return result.resolve(strict=True)


def make_grid_args(x, y):
    """
    Return arguments for a small grid.
    
    Parameters
    ----------
    x : int
        The number of cells spanned by the longitude.
    y : int
        The number of cells spanned by the latutude

    Returns
    -------
    Tuple
        Arguments which can be passed to
        :class:`~esmf_regrid.esmf_regridder.GridInfo.make_esmf_field`
    """
    small_grid_lon = np.array(range(x)) * 10 / x
    small_grid_lat = np.array(range(y)) * 10 / y

    small_grid_lon_bounds = np.array(range(x + 1)) * 10 / x
    small_grid_lat_bounds = np.array(range(y + 1)) * 10 / y
    return (
        small_grid_lon,
        small_grid_lat,
        small_grid_lon_bounds,
        small_grid_lat_bounds,
    )
