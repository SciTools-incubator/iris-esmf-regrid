"""Provides an iris interface for unstructured regridding"""

from numpy import ma
import iris
from iris.analysis._interpolation import get_xy_coords
from esmf_regrid.experimental.unstructured_regrid import MeshInfo
from esmf_regrid.esmf_regridder import GridInfo, Regridder


def _get_mesh_and_dim(cube):
    # Returns the cube's mesh and the dimension that mesh belongs to.
    # Likely to be of the form:
    # mesh = cube.mesh
    # mesh_dim = cube.mesh_dim(mesh)
    # return mesh, mesh_dim
    pass


def _cube_to_MeshInfo(cube):
    # Returns a MeshInfo object describing the mesh of the cube.
    pass


def _cube_to_GridInfo(cube):
    # Returns a GridInfo object describing the horizontal grid of the cube.
    # This may be inherited from code written for the rectilinear regridding scheme.
    pass


def _regrid_along_dims(regridder, data, src_dim, mdtol):
    # Before regridding, data is transposed to a standard form.
    # This will be done either with something like the following code
    # or else done within the regridder by specifying args.
    new_axes = list(range(len(data.shape)))
    new_axes.pop(src_dim)
    new_axes.append(src_dim)
    transposed_data = ma.transpose(data, axes=new_axes)

    result = regridder.regrid(transposed_data, mdtol=mdtol)
    return result


def _create_cube(data, src_cube, mesh_dim, mesh, grid_x, grid_y):
    new_cube = iris.cube.Cube(data)

    # TODO: add coords and metadata.

    return new_cube


def _regrid_unstructured_to_rectilinear__prepare(src_mesh_cube, target_grid_cube):
    # TODO: Perform checks on the arguments. (grid coords are contiguous,
    #  spherical and monotonic. Mesh is defined on faces)

    # TODO: Account for differences in units.

    # TODO: Account for differences in coord systems.

    # TODO: Record appropriate dimensions (i.e. which dimension the mesh belongs to)

    grid_x, grid_y = get_xy_coords(target_grid_cube)

    meshinfo = _cube_to_MeshInfo(src_mesh_cube)
    gridinfo = _cube_to_GridInfo(target_grid_cube)

    regridder = Regridder(meshinfo, gridinfo)

    partial_regrid_info = (grid_x, grid_y, regridder)

    return partial_regrid_info


def _regrid_unstructured_to_rectilinear__perform(src_cube, regrid_info, mdtol):
    mesh, mesh_dim, grid_x, grid_y, regridder = regrid_info

    # Perform regridding with realised data for the moment. This may be changed
    # in future to handle src_cube.lazy_data.
    new_data = _regrid_along_dims(src_cube.data, mesh_dim, mdtol)

    new_cube = _create_cube(
        new_data,
        src_cube,
        mesh_dim,
        mesh,
        grid_x,
        grid_y,
    )

    # TODO: apply tweaks to created cube (slice out length 1 dimensions)

    return new_cube


class MeshToGridESMFRegridder:
    """
    TODO: write docstrings.
    """

    def __init__(self, src_mesh_cube, target_grid_cube, mdtol=1):
        # TODO: Record information about the identity of the mesh. This would
        #  typically be a copy of the mesh, though given the potential size of
        #  the mesh, it may make sense to either retain a reference to the actual
        #  mesh or else something like a hash of the mesh.

        # Missing data tolerance.
        if not (0 <= mdtol <= 1):
            msg = "Value for mdtol must be in range 0 - 1, got {}."
            raise ValueError(msg.format(mdtol))
        self.mdtol = mdtol

        partial_regrid_info = _regrid_unstructured_to_rectilinear__prepare(
            src_mesh_cube, target_grid_cube
        )

        # Store regrid info.
        self.grid_x, self.grid_y, self.regridder = partial_regrid_info

    def __call__(self, cube):
        # TODO: Ensure cube has the same mesh as that of the recorded mesh.

        mesh, mesh_dim = _get_mesh_and_dim(cube)

        regrid_info = (mesh, mesh_dim, self.grid_x, self.grid_y, self.regridder)

        return _regrid_unstructured_to_rectilinear__perform(
            cube, regrid_info, self.mdtol
        )
