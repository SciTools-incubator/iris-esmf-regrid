"""Provides ESMF representations of grids/UGRID meshes and a modified regridder."""

import cartopy.crs as ccrs
import ESMF
import numpy as np
from numpy import ma
import sparse


__all__ = [
    "GridInfo",
    "Regridder",
]


class GridInfo:
    """
    TBD: public class docstring summary (one line).

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

    def _as_esmf_info(self):
        shape = np.array([len(self.lats), len(self.lons)])

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
        """TBD: public method docstring."""
        grid = self._make_esmf_grid()
        field = ESMF.Field(grid, staggerloc=ESMF.StaggerLoc.CENTER)
        return field

    def size(self):
        """TBD: public method docstring."""
        return len(self.lons) * len(self.lats)

    @property
    def shape(self):
        return self.lats.shape + self.lons.shape

    def _index_offset(self):
        return 1


def _get_regrid_weights(src_field, tgt_field):
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
    # Without specifying deep_copy=true, the information in weights
    # would be corrupted when the ESMF regridder is destoyed.
    weights = regridder.get_factors(deep_copy=True)
    # The weights contains all the information needed for regridding,
    # the ESMF objects can be safely removed.
    regridder.destroy()
    return weights


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
            src_field = src.make_esmf_field()
            tgt_field = tgt.make_esmf_field()
            factors, factors_index = _get_regrid_weights(src_field, tgt_field)
            src_shape = tuple(i - 1 for i in reversed(src_field.grid.size[ESMF.StaggerLoc.CORNER]))
            tgt_shape = tuple(i - 1 for i in reversed(tgt_field.grid.size[ESMF.StaggerLoc.CORNER]))
            tensor_shape = src_shape + tgt_shape
            src_inds = np.unravel_index(factors_index[:, 0]-1, src_shape)
            tgt_inds = np.unravel_index(factors_index[:, 1]-1, tgt_shape)
            inds = np.vstack(src_inds + tgt_inds)
            self.weights = sparse.COO(inds, factors.astype('d'), shape=tensor_shape)
        else:
            if precomputed_weights.shape != self.tgt.shape + self.src.shape:
                msg = "Expected precomputed weights to have shape {}, got shape {} instead."
                raise ValueError(
                    msg.format(
                        self.tgt.shape + self.src.shape,
                        precomputed_weights.shape,
                    )
                )
            self.weights = precomputed_weights

    def regrid(self, src_array, norm_type="FRACAREA", mdtol=1):
        """
        Perform regridding on an array of data.

        Parameters
        ----------
        src_array : array_like
            A numpy array whose shape is compatible with self.src
        mdtol : int, optional
            A number between 0 and 1 describing the missing data tolerance.
            Depending on the value of mdtol, if an element in the target mesh/grid
            is not sufficiently covered by elements of the source mesh/grid, then
            the corresponding data point will be masked. An mdtol of 1 means that
            only target elements which are completely uncovered will be masked,
            an mdtol of 0 means that only target elements which are completely
            covered will be unmasked and an mdtol of 0.5 means that target elements
            whose area is at least half uncovered by source elements will be masked.

        Returns
        -------
        array_like
            A numpy array whose shape is compatible with self.tgt.

        """
        filled_src = ma.filled(src_array, 0.)
        tgt_array = np.tensordot(filled_src, self.weights)

        weight_sums = np.tensordot(~ma.getmaskarray(src_array), self.weights)
        # Set the minimum mdtol to be slightly higher than 0 to account for rounding
        # errors.
        mdtol = max(mdtol, 1e-8)
        tgt_mask = weight_sums > 1. - mdtol
        if norm_type == "FRACAREA":
            tgt_array[tgt_mask] /= weight_sums[tgt_mask]
        elif norm_type == "DSTAREA":
            pass
        else:
            raise ValueError(f'Normalisation type "{norm_type}" is not supported')

        result = ma.masked_array(tgt_array, tgt_mask)
        return result
