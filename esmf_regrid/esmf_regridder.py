"""Provides ESMF representations of grids/UGRID meshes and a modified regridder."""

import cartopy.crs as ccrs
import ESMF
import numpy as np
from numpy import ma
import scipy.sparse


__all__ = [
    "GridInfo",
    "Regridder",
]


class GridInfo:
    """
    Class for handling structured grids.

    This class holds information about lat-lon type grids. That is, grids
    defined by lists of latitude and longitude values for points/bounds
    (with respect to some coordinate reference system i.e. rotated pole).
    It contains methods for translating this information into ESMF objects.
    In particular, there are methods for representing as an ESMF Grid and
    as an ESMF Field containing that Grid. This ESMF Field is designed to
    contain enough information for area weighted regridding and may be
    inappropriate for other ESMF regridding schemes.

    """

    # TODO: Edit GridInfo so that it is able to handle 2D lat/lon arrays.

    def __init__(
        self,
        lons,
        lats,
        lonbounds,
        latbounds,
        crs=None,
        circular=False,
        areas=None,
    ):
        """
        Create a GridInfo object describing the grid.

        Parameters
        ----------
        lons : array_like
            A 1D numpy array or list describing the longitudes of the
            grid points.
        lats : array_like
            A 1D numpy array or list describing the latitudes of the
            grid points.
        lonbounds : array_like
            A 1D numpy array or list describing the longitude bounds of
            the grid. Should have length one greater than lons.
        latbounds : array_like
            A 1D numpy array or list describing the latitude bounds of
            the grid. Should have length one greater than lats.
        crs : cartopy projection, optional
            None or a cartopy.crs projection describing how to interpret the
            above arguments. If None, defaults to Geodetic().
        circular : bool, optional
            A boolean value describing if the final longitude bounds should
            be considered contiguous with the first. Defaults to False.
        areas : array_line, optional
            either None or a numpy array describing the areas associated with
            each face. If None, then ESMF will use its own calculated areas.

        """
        self.lons = lons
        self.lats = lats
        self.lonbounds = lonbounds
        self.latbounds = latbounds
        if crs is None:
            self.crs = ccrs.Geodetic()
        else:
            self.crs = crs
        self.circular = circular
        self.areas = areas
        self.shape = (len(lats), len(lons))
        self.dims = 2

    def _as_esmf_info(self):
        shape = np.array(self.shape)

        if self.circular:
            adjustedlonbounds = self.lonbounds[:-1]
        else:
            adjustedlonbounds = self.lonbounds

        centerlons, centerlats = np.meshgrid(self.lons, self.lats)
        cornerlons, cornerlats = np.meshgrid(adjustedlonbounds, self.latbounds)

        truecenters = ccrs.Geodetic().transform_points(self.crs, centerlons, centerlats)
        truecorners = ccrs.Geodetic().transform_points(self.crs, cornerlons, cornerlats)

        # The following note in xESMF suggests that the arrays passed to ESMPy ought to
        # be fortran ordered:
        # https://xesmf.readthedocs.io/en/latest/internal_api.html#xesmf.backend.warn_f_contiguous
        # It is yet to be determined what effect this has on performance.
        truecenterlons = np.asfortranarray(truecenters[..., 0])
        truecenterlats = np.asfortranarray(truecenters[..., 1])
        truecornerlons = np.asfortranarray(truecorners[..., 0])
        truecornerlats = np.asfortranarray(truecorners[..., 1])

        info = (
            shape,
            truecenterlons,
            truecenterlats,
            truecornerlons,
            truecornerlats,
            self.circular,
            self.areas,
        )
        return info

    def _make_esmf_grid(self):
        info = self._as_esmf_info()
        (
            shape,
            truecenterlons,
            truecenterlats,
            truecornerlons,
            truecornerlats,
            circular,
            areas,
        ) = info

        if circular:
            grid = ESMF.Grid(
                shape,
                pole_kind=[1, 1],
                num_peri_dims=1,
                periodic_dim=1,
                pole_dim=0,
            )
        else:
            grid = ESMF.Grid(shape, pole_kind=[1, 1])

        grid.add_coords(staggerloc=ESMF.StaggerLoc.CORNER)
        grid_corner_x = grid.get_coords(0, staggerloc=ESMF.StaggerLoc.CORNER)
        grid_corner_x[:] = truecornerlons
        grid_corner_y = grid.get_coords(1, staggerloc=ESMF.StaggerLoc.CORNER)
        grid_corner_y[:] = truecornerlats

        # Grid center points would be added here, this is not necessary for
        # conservative area weighted regridding
        # grid.add_coords(staggerloc=ESMF.StaggerLoc.CENTER)
        # grid_center_x = grid.get_coords(0, staggerloc=ESMF.StaggerLoc.CENTER)
        # grid_center_x[:] = truecenterlons
        # grid_center_y = grid.get_coords(1, staggerloc=ESMF.StaggerLoc.CENTER)
        # grid_center_y[:] = truecenterlats

        if areas is not None:
            grid.add_item(ESMF.GridItem.AREA, staggerloc=ESMF.StaggerLoc.CENTER)
            grid_areas = grid.get_item(
                ESMF.GridItem.AREA, staggerloc=ESMF.StaggerLoc.CENTER
            )
            grid_areas[:] = areas.T

        return grid

    def make_esmf_field(self):
        """Return an ESMF field representing the grid."""
        grid = self._make_esmf_grid()
        field = ESMF.Field(grid, staggerloc=ESMF.StaggerLoc.CENTER)
        return field

    @property
    def size(self):
        """Return the number of cells in the grid."""
        return len(self.lons) * len(self.lats)

    def _index_offset(self):
        return 1

    def _array_to_matrix(self, array):
        """
        Reshape data to a form that is compatible with weight matrices.

        The data should be presented in the form of a matrix (i.e. 2D) in order
        to be compatible with the weight matrix.
        Weight matrices deriving from ESMF use fortran ordering when flattening
        grids to determine cell indices so we use the same order for reshaping.
        We then take the transpose so that matrix multiplication happens over
        the appropriate axes.
        """
        return array.reshape(-1, self.size, order="F").T

    def _matrix_to_array(self, array, extra_dims):
        """
        Reshape data to restore original dimensions.

        This is the inverse operation of `_array_to_matrix`.
        """
        return array.T.reshape(extra_dims + self.shape, order="F")


def _get_regrid_weights_dict(src_field, tgt_field):
    regridder = ESMF.Regrid(
        src_field,
        tgt_field,
        ignore_degenerate=True,
        regrid_method=ESMF.RegridMethod.CONSERVE,
        unmapped_action=ESMF.UnmappedAction.IGNORE,
        # Choosing the norm_type DSTAREA allows for mdtol type operations
        # to be performed using the weights information later on.
        norm_type=ESMF.NormType.DSTAREA,
        factors=True,
    )
    # Without specifying deep_copy=true, the information in weights_dict
    # would be corrupted when the ESMF regridder is destoyed.
    weights_dict = regridder.get_weights_dict(deep_copy=True)
    # The weights_dict contains all the information needed for regridding,
    # the ESMF objects can be safely removed.
    regridder.destroy()
    return weights_dict


def _weights_dict_to_sparse_array(weights, shape, index_offsets):
    matrix = scipy.sparse.csr_matrix(
        (
            weights["weights"],
            (
                weights["row_dst"] - index_offsets[0],
                weights["col_src"] - index_offsets[1],
            ),
        ),
        shape=shape,
    )
    return matrix


class Regridder:
    """TBD: public class docstring."""

    def __init__(self, src, tgt, precomputed_weights=None):
        """
        TBD: public method docstring summary (one line).

        Create a regridder designed to regrid data from a specified
        source mesh/grid to a specified target mesh/grid.

        Parameters
        ----------
        src : object
            A MeshInfo or GridInfo object describing the source mesh/grid.
            Data supplied to this regridder should be in a numpy array
            whose shape is compatible with src.
        tgt : object
            A MeshInfo or GridInfo oject describing the target mesh/grid.
            Data output by this regridder will be a numpy array whose
            shape is compatible with tgt.
        precomputed_weights : sparse-matix object, optional
            None or a scipy.sparse matrix. If None, ESMF will be used to
            calculate regridding weights. Otherwise, ESMF will be bypassed
            and precomputed_weights will be used as the regridding weights.
        """
        self.src = src
        self.tgt = tgt

        if precomputed_weights is None:
            weights_dict = _get_regrid_weights_dict(
                src.make_esmf_field(), tgt.make_esmf_field()
            )
            self.weight_matrix = _weights_dict_to_sparse_array(
                weights_dict,
                (self.tgt.size, self.src.size),
                (self.tgt._index_offset(), self.src._index_offset()),
            )
        else:
            if not scipy.sparse.isspmatrix(precomputed_weights):
                raise ValueError(
                    "Precomputed weights must be given as a sparse matrix."
                )
            if precomputed_weights.shape != (self.tgt.size, self.src.size):
                msg = "Expected precomputed weights to have shape {}, got shape {} instead."
                raise ValueError(
                    msg.format(
                        (self.tgt.size, self.src.size),
                        precomputed_weights.shape,
                    )
                )
            self.weight_matrix = precomputed_weights

    def regrid(self, src_array, norm_type="fracarea", mdtol=1):
        """
        Perform regridding on an array of data.

        Parameters
        ----------
        src_array : array_like
            A numpy array whose shape is compatible with self.src
        norm_type : string
            Either "fracarea" or "dstarea", defaults to "fracarea". Determines the
            type of normalisation applied to the weights. Normalisations correspond
            to ESMF constants ESMF.NormType.FRACAREA and ESMF.NormType.DSTAREA.
        mdtol : float, optional
            A number between 0 and 1 describing the missing data tolerance.
            Depending on the value of `mdtol`, if a cell in the target grid is not
            sufficiently covered by unmasked cells of the source grid, then it will
            be masked. An `mdtol` of 1 means that only target cells which are not
            covered at all will be masked, an `mdtol` of 0 means that all target
            cells that are not entirely covered will be masked, and an `mdtol` of
            0.5 means that all target cells that are less than half covered will
            be masked.

        Returns
        -------
        array_like
            A numpy array whose shape is compatible with self.tgt.

        """
        array_shape = src_array.shape
        main_shape = array_shape[-self.src.dims :]
        if main_shape != self.src.shape:
            raise ValueError(
                f"Expected an array whose shape ends in {self.src.shape}, "
                f"got an array with shape ending in {main_shape}."
            )
        extra_shape = array_shape[: -self.src.dims]
        extra_size = max(1, np.prod(extra_shape))
        src_inverted_mask = self.src._array_to_matrix(~ma.getmaskarray(src_array))
        weight_sums = self.weight_matrix * src_inverted_mask
        # Set the minimum mdtol to be slightly higher than 0 to account for rounding
        # errors.
        mdtol = max(mdtol, 1e-8)
        tgt_mask = weight_sums > 1 - mdtol
        masked_weight_sums = weight_sums * tgt_mask
        normalisations = np.ones([self.tgt.size, extra_size])
        if norm_type == "fracarea":
            normalisations[tgt_mask] /= masked_weight_sums[tgt_mask]
        elif norm_type == "dstarea":
            pass
        else:
            raise ValueError(f'Normalisation type "{norm_type}" is not supported')
        normalisations = ma.array(normalisations, mask=np.logical_not(tgt_mask))

        flat_src = self.src._array_to_matrix(ma.filled(src_array, 0.0))
        flat_tgt = self.weight_matrix * flat_src
        flat_tgt = flat_tgt * normalisations
        tgt_array = self.tgt._matrix_to_array(flat_tgt, extra_shape)
        return tgt_array
