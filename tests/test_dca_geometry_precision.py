"""Check final DCA geometry cleanup without changing source seed allocation."""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
import shapely
from shapely.geometry import MultiPolygon, Polygon, box

from library.delineation import delineate_depressions


class FinalGeometryPrecisionTests(unittest.TestCase):
    def _run(self, owner, depression, flow):
        owners = gpd.GeoDataFrame({'SubId': [1]}, geometry=[owner], crs=3161)
        bodies = gpd.GeoDataFrame({'SubId': [1]}, geometry=[depression], crs=3161)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fdr.tif'
            with rasterio.open(path, 'w', driver='GTiff', height=flow.shape[0],
                               width=flow.shape[1], count=1, dtype='uint8',
                               crs='EPSG:3161', transform=from_origin(0, 1, 1, 1),
                               nodata=255) as target:
                target.write(flow, 1)
            return delineate_depressions(bodies, owners, path)

    def test_final_geometry_removes_numeric_sliver_and_short_segments(self):
        epsilon = 1e-10
        main = Polygon([(1, 0), (2, 0), (2, 1), (1 + epsilon, 1), (1, 1), (1, 0)])
        sliver = Polygon([(0.5, 0.5), (0.5 + epsilon, 0.5),
                          (0.5, 0.5 + epsilon), (0.5, 0.5)])
        owner = MultiPolygon([main, sliver])
        body = box(1.1, 0.1, 1.9, 0.9)
        result, labels, profile, _ = self._run(owner, body, np.array([[1, 0, 0]], dtype='uint8'))
        geometry = result.geometry.iloc[0]

        np.testing.assert_array_equal(labels, [[1, 1, 0]])
        self.assertTrue(geometry.is_valid)
        self.assertTrue(geometry.equals(box(1, 0, 2, 1)))
        self.assertTrue(geometry.covers(body))
        self.assertLess(geometry.difference(owner).area, 1.0)
        self.assertEqual(result.Area_km2.iloc[0], geometry.area / 1e6)
        self.assertEqual(shapely.get_precision(geometry), 0.0)
        parts = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
        self.assertEqual(len(parts), 1)
        distances = np.hypot(*np.diff(np.asarray(parts[0].exterior.coords), axis=0).T)
        self.assertGreaterEqual(distances.min(), 1.0)
        final_raster = rasterize([(geometry, 1)], out_shape=labels.shape,
                                 transform=profile['transform'], fill=0, dtype='int32')
        np.testing.assert_array_equal(final_raster, [[0, 1, 0]])

    def test_final_cleanup_preserves_submicrometre_seed_overlap(self):
        owner = box(0, 0, 3, 1)
        body = box(1 - 2e-7, 0.2, 1.2, 0.8)
        result, labels, _, diagnostics = self._run(owner, body, np.zeros((1, 3), dtype='uint8'))

        self.assertEqual(diagnostics['seed_cells'], 2)
        np.testing.assert_array_equal(labels, [[1, 1, 0]])
        self.assertTrue(result.geometry.iloc[0].equals(box(0, 0, 2, 1)))


if __name__ == '__main__':
    unittest.main()
