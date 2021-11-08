"""
Scripts for generating supporting data for benchmarking.

Data generated using iris-esmf-regrid should use
:func:`run_function_elsewhere`, which means that data is generated using a
fixed version of iris-esmf-regrid and a fixed environment, rather than those
that get changed when the benchmarking run checks out a new commit.

Downstream use of data generated 'elsewhere' requires saving; usually in a
NetCDF file. Could also use pickling but there is a potential risk if the
benchmark sequence runs over two different Python versions.

"""
from inspect import getsource
from subprocess import CalledProcessError, check_output, run
from os import environ
from pathlib import Path
from textwrap import dedent

from iris import load_cube

#: Python executable used by :func:`run_function_elsewhere`, set via env
#:  variable of same name. Must be path of Python within an environment that
#:  supports iris-esmf-regrid and has iris-esmf-regrid installed via
#:  ``pip install -e``.
try:
    DATA_GEN_PYTHON = environ["DATA_GEN_PYTHON"]
    _ = check_output([DATA_GEN_PYTHON, "-c", "a = True"])
except KeyError:
    error = "Env variable DATA_GEN_PYTHON not defined."
    raise KeyError(error)
except (CalledProcessError, FileNotFoundError, PermissionError):
    error = "Env variable DATA_GEN_PYTHON not a runnable python executable path."
    raise ValueError(error)


def run_function_elsewhere(func_to_run, *args, **kwargs):
    """
    Run a given function using the :const:`DATA_GEN_PYTHON` executable.

    This structure allows the function to be written natively.

    Parameters
    ----------
    func_to_run : FunctionType
        The function object to be run.
        NOTE: the function must be completely self-contained, i.e. perform all
        its own imports (within the target :const:`DATA_GEN_PYTHON`
        environment).
    *args : tuple, optional
        Function call arguments. Must all be expressible as simple literals,
        i.e. the ``repr`` must be a valid literal expression.
    **kwargs: dict, optional
        Function call keyword arguments. All values must be expressible as
        simple literals (see ``*args``).

    Returns
    -------
    str
        The ``stdout`` from the run.

    """
    func_string = dedent(getsource(func_to_run))
    func_call_term_strings = [repr(arg) for arg in args]
    func_call_term_strings += [f"{name}={repr(val)}" for name, val in kwargs.items()]
    func_call_string = (
        f"{func_to_run.__name__}(" + ",".join(func_call_term_strings) + ")"
    )
    python_string = "\n".join([func_string, func_call_string])
    result = run(
        [DATA_GEN_PYTHON, "-c", python_string], capture_output=True, check=True
    )
    return result.stdout


def _grid_cube(
    n_lons,
    n_lats,
    lon_outer_bounds,
    lat_outer_bounds,
    circular=False,
    alt_coord_system=False,
):
    """Wrapper for calling _grid_cube via :func:`run_function_elsewhere`."""

    def external(*args, **kwargs):
        """
        Prep and call _grid_cube, saving to a NetCDF file.

        Saving to a file allows the original python executable to pick back up.

        Remember that all arguments must work as strings, hence the fresh
        construction of a ``coord_system`` within the function.

        """
        from iris import save
        from iris.coord_systems import RotatedGeogCS

        from esmf_regrid.tests.unit.schemes.test__cube_to_GridInfo import (
            _grid_cube as original,
        )

        save_path = kwargs.pop("save_path")

        if kwargs.pop("alt_coord_system"):
            kwargs["coord_system"] = RotatedGeogCS(0, 90, 90)

        cube = original(*args, **kwargs)
        save(cube, save_path)

    save_dir = (Path(__file__).parent.parent / ".data").resolve()
    save_dir.mkdir(exist_ok=True)
    # TODO: caching? Currently written assuming overwrite every time.
    save_path = save_dir / "_grid_cube.nc"

    _ = run_function_elsewhere(
        external,
        n_lons,
        n_lats,
        lon_outer_bounds,
        lat_outer_bounds,
        circular,
        alt_coord_system=alt_coord_system,
        save_path=str(save_path),
    )
    return_cube = load_cube(str(save_path))
    return return_cube
