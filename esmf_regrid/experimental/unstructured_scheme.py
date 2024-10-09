"""Provides an iris interface for unstructured regridding."""

try:
    from iris.mesh import MeshXY
except ImportError as exc:
    # Prior to v3.10.0, `MeshXY` could was named `Mesh`.
    try:
        from iris.experimental.ugrid import Mesh as MeshXY
    except ImportError:
        raise exc
from esmf_regrid import check_method, Constants
from esmf_regrid.schemes import (
    _ESMFRegridder,
    _get_mask,
    _regrid_rectilinear_to_unstructured__perform,
    _regrid_rectilinear_to_unstructured__prepare,
    _regrid_unstructured_to_rectilinear__perform,
    _regrid_unstructured_to_rectilinear__prepare,
    _regrid_unstructured_to_unstructured__perform,
    _regrid_unstructured_to_unstructured__prepare,
)


def regrid_unstructured_to_rectilinear(
    src_cube,
    grid_cube,
    mdtol=0,
    method=Constants.Method.CONSERVATIVE,
    tgt_resolution=None,
    use_src_mask=False,
    use_tgt_mask=False,
):
    r"""
    Regrid unstructured :class:`~iris.cube.Cube` onto rectilinear grid.

    Return a new :class:`~iris.cube.Cube` with :attr:`~iris.cube.Cube.data`
    values calculated using weights generated by :mod:`esmpy` to give the weighted
    mean of :attr:`~iris.cube.Cube.data` values from ``src_cube`` regridded onto the
    horizontal grid of ``grid_cube``. The dimension on the :class:`~iris.cube.Cube`
    belonging to the :attr:`~iris.cube.Cube.mesh`
    will be replaced by the two dimensions associated with the grid.
    This function requires that the horizontal dimension of ``src_cube`` is
    described by a 2D mesh with data located on the faces of that mesh
    for conservative regridding and located on either faces or nodes for
    bilinear regridding.
    This function allows the horizontal grid of ``grid_cube`` to be either
    rectilinear or curvilinear (i.e. expressed in terms of two orthogonal
    1D coordinates or via a pair of 2D coordinates).
    This function also requires that the :class:`~iris.coords.Coord`\\ s describing the
    horizontal grid have :attr:`~iris.coords.Coord.bounds`.

    Parameters
    ----------
    src_cube : :class:`iris.cube.Cube`
        An unstructured instance of :class:`~iris.cube.Cube` that supplies the data,
        metadata and coordinates.
    grid_cube : :class:`iris.cube.Cube`
        An instance of :class:`~iris.cube.Cube` that supplies the desired
        horizontal grid definition.
    mdtol : float, default=0
        Tolerance of missing data. The value returned in each element of the
        returned :class:`~iris.cube.Cube`\\ 's :attr:`~iris.cube.Cube.data`
        array will be masked if the fraction of masked
        data in the overlapping cells of ``src_cube`` exceeds ``mdtol``. This
        fraction is calculated based on the area of masked cells within each
        target cell. ``mdtol=0`` means no missing data is tolerated while ``mdtol=1``
        will mean the resulting element will be masked if and only if all the
        overlapping cells of ``src_cube`` are masked.
    method : :class:`Constants.Method`, default=Constants.Method.CONSERVATIVE
        The method used to calculate weights.
    tgt_resolution : int, optional
        If present, represents the amount of latitude slices per cell
        given to ESMF for calculation.
    use_src_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the source to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``src_cube``. If False, no mask will be taken and all points will
        be used in weights calculation.
    use_tgt_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the target to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``grid_cube``. If False, no mask will be taken and all points
        will be used in weights calculation.

    Returns
    -------
    :class:`iris.cube.Cube`
        A new :class:`~iris.cube.Cube` instance.

    """
    if src_cube.mesh is None:
        raise ValueError("src_cube has no mesh.")
    src_mask = _get_mask(src_cube, use_src_mask)
    tgt_mask = _get_mask(grid_cube, use_tgt_mask)
    method = check_method(method)

    regrid_info = _regrid_unstructured_to_rectilinear__prepare(
        src_cube,
        grid_cube,
        method=method,
        tgt_resolution=tgt_resolution,
        src_mask=src_mask,
        tgt_mask=tgt_mask,
    )
    result = _regrid_unstructured_to_rectilinear__perform(src_cube, regrid_info, mdtol)
    return result


class MeshToGridESMFRegridder(_ESMFRegridder):
    r"""Regridder class for unstructured to rectilinear :class:`~iris.cube.Cube`\\ s."""

    def __init__(
        self,
        src,
        tgt,
        mdtol=None,
        method=Constants.Method.CONSERVATIVE,
        precomputed_weights=None,
        tgt_resolution=None,
        use_src_mask=False,
        use_tgt_mask=False,
        esmf_args=None,
    ):
        """
        Create regridder for conversions between source mesh and target grid.

        Parameters
        ----------
        src_mesh_cube : :class:`iris.cube.Cube`
            The unstructured :class:`~iris.cube.Cube` providing the source mesh.
        target_grid_cube : :class:`iris.cube.Cube`
            The :class:`~iris.cube.Cube` providing the target grid.
        mdtol : float, optional
            Tolerance of missing data. The value returned in each element of
            the returned array will be masked if the fraction of masked data
            exceeds ``mdtol``. ``mdtol=0`` means no missing data is tolerated while
            ``mdtol=1`` will mean the resulting element will be masked if and only
            if all the contributing elements of data are masked. Defaults to 1
            for conservative regregridding and 0 for bilinear regridding.
        method : :class:`Constants.Method`, default=Constants.Method.CONSERVATIVE
            The method used to calculate weights.
        precomputed_weights : :class:`scipy.sparse.spmatrix`, optional
            If ``None``, :mod:`esmpy` will be used to
            calculate regridding weights. Otherwise, :mod:`esmpy` will be bypassed
            and ``precomputed_weights`` will be used as the regridding weights.
        tgt_resolution : int, optional
            If present, represents the amount of latitude slices per cell
            given to ESMF for calculation. If ``tgt_resolution`` is set, ``tgt``
            must have strictly increasing bounds (bounds may be transposed plus or
            minus 360 degrees to make the bounds strictly increasing).
        use_src_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
            Either an array representing the cells in the source to ignore, or else
            a boolean value. If True, this array is taken from the mask on the data
            in ``src``. If False, no mask will be taken and all points will
            be used in weights calculation.
        use_tgt_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
            Either an array representing the cells in the target to ignore, or else
            a boolean value. If True, this array is taken from the mask on the data
            in ``tgt``. If False, no mask will be taken and all points
            will be used in weights calculation.
        esmf_args : dict, optional
            A dictionary of arguments to pass to ESMF.

        Raises
        ------
        ValueError
            If ``use_src_mask`` or ``use_tgt_mask`` are True while the masks on ``src``
            or ``tgt`` respectively are not constant over non-horizontal dimensions.


        """
        if src.mesh is None:
            raise ValueError("src has no mesh.")
        super().__init__(
            src,
            tgt,
            method,
            mdtol=mdtol,
            precomputed_weights=precomputed_weights,
            tgt_resolution=tgt_resolution,
            use_src_mask=use_src_mask,
            use_tgt_mask=use_tgt_mask,
            esmf_args=esmf_args,
        )
        self.resolution = tgt_resolution
        self.mesh, self.location = self._src
        self.grid_x, self.grid_y = self._tgt


def regrid_rectilinear_to_unstructured(
    src_cube,
    mesh_cube,
    mdtol=0,
    method=Constants.Method.CONSERVATIVE,
    src_resolution=None,
    use_src_mask=False,
    use_tgt_mask=False,
):
    r"""
    Regrid rectilinear :class:`~iris.cube.Cube` onto unstructured mesh.

    Return a new :class:`~iris.cube.Cube` with :attr:`~iris.cube.Cube.data`
    values calculated using weights generated by :mod:`esmpy` to give the weighted
    mean of :attr:`~iris.cube.Cube.data` values from ``src_cube`` regridded onto the
    horizontal mesh of ``mesh_cube``. The dimensions on the :class:`~iris.cube.Cube` associated
    with the grid will be replaced by a dimension associated with the
    :attr:`~iris.cube.Cube.mesh`.
    That dimension will be the first of the grid dimensions, whether
    it is associated with the ``x`` or ``y`` coordinate. Since two dimensions are
    being replaced by one, coordinates associated with dimensions after
    the grid will become associated with dimensions one lower.
    This function requires that the horizontal dimension of ``mesh_cube`` is
    described by a 2D mesh with data located on the faces of that mesh
    for conservative regridding and located on either faces or nodes for
    bilinear regridding.
    This function allows the horizontal grid of ``grid_cube`` to be either
    rectilinear or curvilinear (i.e. expressed in terms of two orthogonal
    1D coordinates or via a pair of 2D coordinates).
    This function also requires that the :class:`~iris.coords.Coord`\\ s describing the
    horizontal grid have :attr:`~iris.coords.Coord.bounds`.

    Parameters
    ----------
    src_cube : :class:`iris.cube.Cube`
        A rectilinear instance of :class:`~iris.cube.Cube` that supplies the data,
        metadata and coordinates.
    mesh_cube : :class:`iris.cube.Cube`
        An unstructured instance of :class:`~iris.cube.Cube` that supplies the desired
        horizontal mesh definition.
    mdtol : float, default=0
        Tolerance of missing data. The value returned in each element of the
        returned :class:`~iris.cube.Cube`\\ 's :attr:`~iris.cube.Cube.data` array
        will be masked if the fraction of masked
        data in the overlapping cells of the source cube exceeds ``mdtol``. This
        fraction is calculated based on the area of masked cells within each
        target cell. ``mdtol=0`` means no missing data is tolerated while ``mdtol=1``
        will mean the resulting element will be masked if and only if all the
        overlapping cells of the ``src_cube`` are masked.
    method : :class:`Constants.Method`, default=Constants.Method.CONSERVATIVE
        The method used to calculate weights.
    src_resolution : int, optional
        If present, represents the amount of latitude slices per cell
        given to ESMF for calculation.
    use_src_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the source to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``src_cube``. If False, no mask will be taken and all points will
        be used in weights calculation.
    use_tgt_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the target to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``grid_cube``. If False, no mask will be taken and all points
        will be used in weights calculation.

    Returns
    -------
    :class:`iris.cube.Cube`
        A new :class:`~iris.cube.Cube` instance.

    """
    if mesh_cube.mesh is None:
        raise ValueError("mesh_cube has no mesh.")
    src_mask = _get_mask(src_cube, use_src_mask)
    tgt_mask = _get_mask(mesh_cube, use_tgt_mask)
    method = check_method(method)

    regrid_info = _regrid_rectilinear_to_unstructured__prepare(
        src_cube,
        mesh_cube,
        method=method,
        src_resolution=src_resolution,
        src_mask=src_mask,
        tgt_mask=tgt_mask,
    )
    result = _regrid_rectilinear_to_unstructured__perform(src_cube, regrid_info, mdtol)
    return result


class GridToMeshESMFRegridder(_ESMFRegridder):
    r"""Regridder class for rectilinear to unstructured :class:`~iris.cube.Cube`\\ s."""

    def __init__(
        self,
        src,
        tgt,
        mdtol=None,
        method=Constants.Method.CONSERVATIVE,
        precomputed_weights=None,
        src_resolution=None,
        use_src_mask=False,
        use_tgt_mask=False,
        tgt_location=None,
        esmf_args=None,
    ):
        """
        Create regridder for conversions between source grid and target mesh.

        Parameters
        ----------
        src : :class:`iris.cube.Cube`
            The rectilinear :class:`~iris.cube.Cube` cube providing the source grid.
        tgt : :class:`iris.cube.Cube` or :class:`iris.mesh.MeshXY`
            The unstructured :class:`~iris.cube.Cube`or
            :class:`~iris.mesh.MeshXY` providing the target mesh.
        mdtol : float, optional
            Tolerance of missing data. The value returned in each element of
            the returned array will be masked if the fraction of masked data
            exceeds ``mdtol``. ``mdtol=0`` means no missing data is tolerated while
            ``mdtol=1`` will mean the resulting element will be masked if and only
            if all the contributing elements of data are masked. Defaults to 1
            for conservative regregridding and 0 for bilinear regridding.
        method : :class:`Constants.Method`, default=Constants.Method.CONSERVATIVE
            The method used to calculate weights.
        precomputed_weights : :class:`scipy.sparse.spmatrix`, optional
            If ``None``, :mod:`esmpy` will be used to
            calculate regridding weights. Otherwise, :mod:`esmpy` will be bypassed
            and ``precomputed_weights`` will be used as the regridding weights.
        src_resolution : int, optional
            If present, represents the amount of latitude slices per cell
            given to ESMF for calculation. If ``src_resolution`` is set, ``src``
            must have strictly increasing bounds (bounds may be transposed plus or
            minus 360 degrees to make the bounds strictly increasing).
        use_src_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
            Either an array representing the cells in the source to ignore, or else
            a boolean value. If True, this array is taken from the mask on the data
            in ``src``. If False, no mask will be taken and all points will
            be used in weights calculation.
        use_tgt_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
            Either an array representing the cells in the target to ignore, or else
            a boolean value. If True, this array is taken from the mask on the data
            in ``tgt``. If False, no mask will be taken and all points
            will be used in weights calculation.
        tgt_location : str or None, default=None
            Either "face" or "node". Describes the location for data on the mesh
            if the target is not a :class:`~iris.cube.Cube`.
        esmf_args : dict, optional
            A dictionary of arguments to pass to ESMF.

        Raises
        ------
        ValueError
            If ``use_src_mask`` or ``use_tgt_mask`` are True while the masks on ``src``
            or ``tgt`` respectively are not constant over non-horizontal dimensions.

        """
        if not isinstance(tgt, MeshXY) and tgt.mesh is None:
            raise ValueError("tgt has no mesh.")
        super().__init__(
            src,
            tgt,
            method,
            mdtol=mdtol,
            precomputed_weights=precomputed_weights,
            src_resolution=src_resolution,
            use_src_mask=use_src_mask,
            use_tgt_mask=use_tgt_mask,
            tgt_location=tgt_location,
            esmf_args=esmf_args,
        )
        self.resolution = src_resolution
        self.mesh, self.location = self._tgt
        self.grid_x, self.grid_y = self._src


def regrid_unstructured_to_unstructured(
    src_mesh_cube,
    tgt_mesh_cube,
    mdtol=0,
    method=Constants.Method.CONSERVATIVE,
    use_src_mask=False,
    use_tgt_mask=False,
):
    r"""
    Regrid rectilinear :class:`~iris.cube.Cube` onto unstructured mesh.

    Return a new :class:`~iris.cube.Cube` with :attr:`~iris.cube.Cube.data`
    values calculated using weights generated by :mod:`esmpy` to give the weighted
    mean of :attr:`~iris.cube.Cube.data` values from ``src_mesh_cube`` regridded onto the
    horizontal mesh of ``tgt_mesh_cube``. The resulting cube will have the same
    ``mesh_dim`` as ``src_mesh_cube``.

    Parameters
    ----------
    src_mesh_cube : :class:`iris.cube.Cube`
        A unstructured instance of :class:`~iris.cube.Cube` that supplies the data,
        metadata and coordinates.
    tgt_mesh_cube : :class:`iris.cube.Cube`
        An unstructured instance of :class:`~iris.cube.Cube` that supplies the desired
        horizontal mesh definition.
    mdtol : float, default=0
        Tolerance of missing data. The value returned in each element of the
        returned :class:`~iris.cube.Cube`\\ 's :attr:`~iris.cube.Cube.data` array
        will be masked if the fraction of masked
        data in the overlapping cells of the source cube exceeds ``mdtol``. This
        fraction is calculated based on the area of masked cells within each
        target cell. ``mdtol=0`` means no missing data is tolerated while ``mdtol=1``
        will mean the resulting element will be masked if and only if all the
        overlapping cells of the ``src_cube`` are masked.
    method : :class:`Constants.Method`, default=Constants.Method.CONSERVATIVE
            The method used to calculate weights.
    use_src_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the source to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``src_cube``. If False, no mask will be taken and all points will
        be used in weights calculation.
    use_tgt_mask : :obj:`~numpy.typing.ArrayLike` or bool, default=False
        Either an array representing the cells in the target to ignore, or else
        a boolean value. If True, this array is taken from the mask on the data
        in ``grid_cube``. If False, no mask will be taken and all points
        will be used in weights calculation.

    Returns
    -------
    :class:`iris.cube.Cube`
        A new :class:`~iris.cube.Cube` instance.

    """
    method = check_method(method)
    if tgt_mesh_cube.mesh is None:
        raise ValueError("mesh_cube has no mesh.")
    src_mask = _get_mask(src_mesh_cube, use_src_mask)
    tgt_mask = _get_mask(tgt_mesh_cube, use_tgt_mask)

    regrid_info = _regrid_unstructured_to_unstructured__prepare(
        src_mesh_cube,
        tgt_mesh_cube,
        method=method,
        src_mask=src_mask,
        tgt_mask=tgt_mask,
    )
    result = _regrid_unstructured_to_unstructured__perform(
        src_mesh_cube, regrid_info, mdtol
    )
    return result
