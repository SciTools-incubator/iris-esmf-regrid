"""Scalability benchmarks for :mod:`esmf_regrid.esmf_regridder`."""

import os
from pathlib import Path

import numpy as np
import dask.array as da
import iris
from iris.cube import Cube

from esmf_regrid.experimental.io import load_regridder, save_regridder
from esmf_regrid.experimental.unstructured_scheme import (
    GridToMeshESMFRegridder,
    MeshToGridESMFRegridder,
)
from esmf_regrid.schemes import ESMFAreaWeightedRegridder

from .. import on_demand_benchmark, skip_benchmark
from ..generate_data import _grid_cube, _gridlike_mesh_cube


class PrepareScalabilityMixin:
    timeout = 180
    params = [50, 100, 200, 400, 600, 800]
    param_names = ["grid width"]
    height = 100
    regridder = ESMFAreaWeightedRegridder

    def src_cube(self, n):
        lon_bounds = (-180, 180)
        lat_bounds = (-90, 90)
        src = _grid_cube(n, n, lon_bounds, lat_bounds)
        return src

    def tgt_cube(self, n):
        lon_bounds = (-180, 180)
        lat_bounds = (-90, 90)
        grid = _grid_cube(n + 1, n + 1, lon_bounds, lat_bounds)
        return grid

    def setup(self, n):
        self.src = self.src_cube(n)
        self.tgt = self.tgt_cube(n)

    def _time_prepare(self, n):
        _ = self.regridder(self.src, self.tgt)


@on_demand_benchmark
class PrepareScalabilityGridToGrid(PrepareScalabilityMixin):
    def time_prepare(self, n):
        super()._time_prepare(n)


@on_demand_benchmark
class PrepareScalabilityMeshToGrid(PrepareScalabilityMixin):
    regridder = MeshToGridESMFRegridder

    def src_cube(self, n):
        src = _gridlike_mesh_cube(n, n)
        return src

    def setup_cache(self):
        SYNTH_DATA_DIR = Path().cwd() / "tmp_data"
        SYNTH_DATA_DIR.mkdir(exist_ok=True)
        destination_file = str(SYNTH_DATA_DIR.joinpath("dest_rg.nc"))
        file_dict = {"destination": destination_file}
        for n in self.params:
            super().setup(n)
            rg = self.regridder(self.src, self.tgt)
            source_file = str(SYNTH_DATA_DIR.joinpath(f"source_rg_{n}.nc"))
            save_regridder(rg, source_file)
            file_dict[n] = source_file
        return file_dict

    def setup(self, file_dict, n):
        super().setup(n)
        self.source_file = file_dict[n]
        self.destination_file = file_dict["destination"]
        self.rg = load_regridder(self.source_file)

    def teardown(self, _, n):
        if os.path.exists(self.destination_file):
            os.remove(self.destination_file)

    def time_load(self, _, n):
        load_regridder(self.source_file)

    def time_save(self, _, n):
        save_regridder(self.rg, self.destination_file)

    def time_prepare(self, _, n):
        super()._time_prepare(n)


@on_demand_benchmark
class PrepareScalabilityGridToMesh(PrepareScalabilityMixin):
    regridder = GridToMeshESMFRegridder

    def tgt_cube(self, n):
        tgt = _gridlike_mesh_cube(n + 1, n + 1)
        return tgt

    def setup_cache(self):
        SYNTH_DATA_DIR = Path().cwd() / "tmp_data"
        SYNTH_DATA_DIR.mkdir(exist_ok=True)
        destination_file = str(SYNTH_DATA_DIR.joinpath("dest_rg.nc"))
        file_dict = {"destination": destination_file}
        for n in self.params:
            super().setup(n)
            rg = self.regridder(self.src, self.tgt)
            source_file = str(SYNTH_DATA_DIR.joinpath(f"source_rg_{n}.nc"))
            save_regridder(rg, source_file)
            file_dict[n] = source_file
        return file_dict

    def setup(self, file_dict, n):
        super().setup(n)
        self.source_file = file_dict[n]
        self.destination_file = file_dict["destination"]
        self.rg = load_regridder(self.source_file)

    def teardown(self, _, n):
        if os.path.exists(self.destination_file):
            os.remove(self.destination_file)

    def time_load(self, _, n):
        load_regridder(self.source_file)

    def time_save(self, _, n):
        save_regridder(self.rg, self.destination_file)

    def time_prepare(self, _, n):
        super()._time_prepare(n)


class PerformScalabilityMixin:
    params = [100, 200, 400, 600, 800, 1000]
    param_names = ["height"]
    grid_size = 400
    # Define the target grid to be smaller so that time spent realising a large array
    # does not dominate the time spent on regridding calculation. A number which is
    # not a factor of the grid size is chosen so that the two grids will be slightly
    # misaligned.
    target_grid_size = 41
    chunk_size = [grid_size, grid_size, 10]
    regridder = ESMFAreaWeightedRegridder
    file_name = "chunked_cube.nc"

    def src_cube(self, height):
        data = da.ones([self.grid_size, self.grid_size, height], chunks=self.chunk_size)
        src = Cube(data)
        return src

    def add_src_metadata(self, cube):
        lon_bounds = (-180, 180)
        lat_bounds = (-90, 90)
        grid = _grid_cube(self.grid_size, self.grid_size, lon_bounds, lat_bounds)
        cube.add_dim_coord(grid.coord("latitude"), 0)
        cube.add_dim_coord(grid.coord("longitude"), 1)
        return cube

    def tgt_cube(self):
        lon_bounds = (-180, 180)
        lat_bounds = (-90, 90)
        grid = _grid_cube(
            self.target_grid_size, self.target_grid_size, lon_bounds, lat_bounds
        )
        return grid

    def setup_cache(self):
        SYNTH_DATA_DIR = Path().cwd() / "tmp_data"
        SYNTH_DATA_DIR.mkdir(exist_ok=True)
        file = str(SYNTH_DATA_DIR.joinpath(self.file_name))

        src = self.src_cube(max(self.params))
        # While iris is not able to save meshes, we add these after loading.
        # TODO: change this back after iris allows mesh saving.
        iris.save(src, file, chunksizes=self.chunk_size)
        loaded_src = iris.load_cube(file)
        loaded_src = self.add_src_metadata(loaded_src)
        tgt = self.tgt_cube()
        rg = self.regridder(loaded_src, tgt)
        return rg, file

    def setup(self, cache, height):
        regridder, file = cache
        src = iris.load_cube(file)[..., :height]
        self.src = self.add_src_metadata(src)
        # Realise data.
        self.src.data
        cube = iris.load_cube(file)[..., :height]
        cube = self.add_src_metadata(cube)
        self.result = regridder(cube)

    def _time_perform(self, cache, height):
        assert not self.src.has_lazy_data()
        rg, _ = cache
        _ = rg(self.src)

    def _time_lazy_perform(self, cache, height):
        # Don't touch result.data - permanent realisation plays badly with
        #  ASV's re-run strategy.
        assert self.result.has_lazy_data()
        self.result.core_data().compute()


@on_demand_benchmark
class PerformScalabilityGridToGrid(PerformScalabilityMixin):
    def time_perform(self, cache, height):
        super()._time_perform(cache, height)

    def time_lazy_perform(self, cache, height):
        super()._time_lazy_perform(cache, height)


@on_demand_benchmark
class PerformScalabilityMeshToGrid(PerformScalabilityMixin):
    regridder = MeshToGridESMFRegridder
    chunk_size = [PerformScalabilityMixin.grid_size ^ 2, 10]
    file_name = "chunked_cube_1d.nc"

    def setup_cache(self):
        return super().setup_cache()

    def src_cube(self, height):
        data = da.ones(
            [self.grid_size * self.grid_size, height], chunks=self.chunk_size
        )
        src = Cube(data)
        return src

    def add_src_metadata(self, cube):
        from esmf_regrid.tests.unit.experimental.unstructured_scheme.test__mesh_to_MeshInfo import (
            _gridlike_mesh,
        )

        mesh = _gridlike_mesh(self.grid_size, self.grid_size)
        mesh_coord_x, mesh_coord_y = mesh.to_MeshCoords("face")
        cube.add_aux_coord(mesh_coord_x, 0)
        cube.add_aux_coord(mesh_coord_y, 0)
        return cube

    def time_perform(self, cache, height):
        super()._time_perform(cache, height)

    def time_lazy_perform(self, cache, height):
        super()._time_lazy_perform(cache, height)


@on_demand_benchmark
class PerformScalabilityGridToMesh(PerformScalabilityMixin):
    regridder = GridToMeshESMFRegridder

    def setup_cache(self):
        return super().setup_cache()

    def tgt_cube(self):
        from esmf_regrid.tests.unit.experimental.unstructured_scheme.test__mesh_to_MeshInfo import (
            _gridlike_mesh,
        )

        tgt = Cube(np.ones([self.target_grid_size * self.target_grid_size]))
        mesh = _gridlike_mesh(self.target_grid_size, self.target_grid_size)
        mesh_coord_x, mesh_coord_y = mesh.to_MeshCoords("face")
        tgt.add_aux_coord(mesh_coord_x, 0)
        tgt.add_aux_coord(mesh_coord_y, 0)
        return tgt

    def time_perform(self, cache, height):
        super()._time_perform(cache, height)

    def time_lazy_perform(self, cache, height):
        super()._time_lazy_perform(cache, height)


# These benchmarks unusually long and are resource intensive so are skipped.
# They can be run by manually removing the skip.
@skip_benchmark
class PerformScalability1kGridToGrid(PerformScalabilityMixin):
    timeout = 600
    grid_size = 1100
    chunk_size = [grid_size, grid_size, 10]
    # Define the target grid to be smaller so that time spent realising a large array
    # does not dominate the time spent on regridding calculation. A number which is
    # not a factor of the grid size is chosen so that the two grids will be slightly
    # misaligned.
    target_grid_size = 111

    def setup_cache(self):
        return super().setup_cache()

    def time_perform(self, cache, height):
        super()._time_perform(cache, height)

    def time_lazy_perform(self, cache, height):
        super()._time_lazy_perform(cache, height)


# These benchmarks unusually long and are resource intensive so are skipped.
# They can be run by manually removing the skip.
@skip_benchmark
class PerformScalability2kGridToGrid(PerformScalabilityMixin):
    timeout = 600
    grid_size = 2200
    chunk_size = [grid_size, grid_size, 10]
    # Define the target grid to be smaller so that time spent realising a large array
    # does not dominate the time spent on regridding calculation. A number which is
    # not a factor of the grid size is chosen so that the two grids will be slightly
    # misaligned.
    target_grid_size = 221

    def setup_cache(self):
        return super().setup_cache()

    def time_perform(self, cache, height):
        super()._time_perform(cache, height)

    def time_lazy_perform(self, cache, height):
        super()._time_lazy_perform(cache, height)
