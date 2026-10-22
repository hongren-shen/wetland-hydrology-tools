"""Small analytical checks for seed geometry, first-hit routing, and clipping."""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import MultiPolygon, box

from library.delineation import build_seed_groups, delineate_depressions, trace_d8


class DelineationTests(unittest.TestCase):
    def test_all_eight_direction_codes(self):
        flow = np.array([[2, 4, 8], [1, 0, 16], [128, 64, 32]], dtype='uint8')
        seeds = np.zeros((3, 3), dtype='int32')
        seeds[1, 1] = 3
        np.testing.assert_array_equal(trace_d8(flow, seeds, np.ones((3, 3), dtype=bool)), np.full((3, 3), 3))

    def test_against_independent_downstream_trace(self):
        rng = np.random.default_rng(103)
        codes = [1, 2, 4, 8, 16, 32, 64, 128, 0, 5]
        offsets = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
        flow = rng.choice(codes, size=(15, 17))
        valid = rng.random(flow.shape) > 0.1
        seeds = np.where((rng.random(flow.shape) > 0.9) & valid, rng.integers(1, 9, size=flow.shape), 0)
        expected = np.zeros(flow.shape, dtype='int32')
        for start_row, start_col in np.ndindex(flow.shape):
            row, col, seen = start_row, start_col, set()
            while 0 <= row < flow.shape[0] and 0 <= col < flow.shape[1] and valid[row, col]:
                if seeds[row, col]:
                    expected[start_row, start_col] = seeds[row, col]
                    break
                if (row, col) in seen or flow[row, col] not in codes[:8]:
                    break
                seen.add((row, col))
                dr, dc = offsets[codes.index(flow[row, col])]
                row, col = row + dr, col + dc
        np.testing.assert_array_equal(trace_d8(flow, seeds, valid), expected)

    def test_branch_and_two_serial_seeds(self):
        flow = np.array([[2, 4, 8], [1, 4, 16], [1, 1, 0]], dtype='uint8')
        seeds = np.zeros((3, 3), dtype='int32')
        seeds[1, 1], seeds[2, 2] = 1, 2
        actual = trace_d8(flow, seeds, np.ones_like(flow, dtype=bool))
        np.testing.assert_array_equal(actual, [[1, 1, 1], [1, 1, 1], [2, 2, 2]])

    def test_nodata_terminal_and_cycle(self):
        flow = np.array([[1, 5, 1, 16], [1, 1, 1, 0]], dtype='uint8')
        seeds = np.array([[0, 7, 0, 0], [0, 0, 0, 9]], dtype='int32')
        valid = np.ones_like(flow, dtype=bool)
        valid[1, 2] = False
        np.testing.assert_array_equal(trace_d8(flow, seeds, valid), [[7, 7, 0, 0], [0, 0, 0, 9]])
        seeds[1, 2] = 4
        with self.assertRaisesRegex(ValueError, 'valid FDR'):
            trace_d8(flow, seeds, valid)

    def test_unknown_direction_rejected(self):
        with self.assertRaisesRegex(ValueError, '0..255'):
            trace_d8(np.array([[256]]), np.array([[1]]), np.array([[True]]))

    def test_shared_signature_positive_sliver_and_boundary_contact(self):
        parts = {1: box(0, 0, 1, 1), 2: box(0.999, 0.2, 1.001, 0.8), 3: box(2, 0, 3, 1)}
        seeds, groups, details = build_seed_groups(parts, np.ones((1, 3), dtype=bool), from_origin(0, 1, 1, 1))
        self.assertEqual(groups, {1: (1, 2), 2: (2,), 3: (3,)})
        np.testing.assert_array_equal(seeds, [[1, 2, 3]])
        self.assertEqual(details['shared_seed_cells'], 1)

    def test_missing_seed_and_empty_input_fail(self):
        for parts, mask in [({1: box(1, 0, 2, 1)}, np.array([[True]])),
                            ({1: box(0, 0, 1, 1)}, np.array([[False]])),
                            ({}, np.array([[True]]))]:
            with self.assertRaises(ValueError):
                build_seed_groups(parts, mask, from_origin(0, 1, 1, 1))

    def _run(self, depressions, owners, flow, nodata=255):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fdr.tif'
            with rasterio.open(path, 'w', driver='GTiff', height=flow.shape[0], width=flow.shape[1],
                               count=1, dtype=flow.dtype, crs='EPSG:3161',
                               transform=from_origin(0, flow.shape[0], 1, 1), nodata=nodata) as target:
                target.write(flow, 1)
            return delineate_depressions(depressions, owners, path)

    def test_shared_owner_clip_and_body_coverage(self):
        owners = gpd.GeoDataFrame({'SubId': [1, 2]}, geometry=[box(0, 0, 1.5, 1), box(1.5, 0, 3, 1)], crs=3161)
        wetlands = gpd.GeoDataFrame({'SubId': [1, 2]}, geometry=[box(1.1, 0.1, 1.4, 0.9), box(1.6, 0.1, 1.9, 0.9)], crs=3161)
        output, labels, profile, details = self._run(wetlands, owners, np.array([[1, 1, 0]], dtype='uint8'))
        np.testing.assert_array_equal(labels, [[1, 1, 0]])
        self.assertEqual(details['shared_seed_cells'], 1)
        self.assertEqual(details['crop_edge_labels'], [1])
        self.assertEqual(profile['nodata'], 0)
        self.assertEqual(list(output.SubId), [1, 2])
        self.assertAlmostEqual(output.geometry.iloc[0].area, 1.5)
        self.assertAlmostEqual(output.geometry.iloc[1].area, 0.5)
        for index in range(2):
            self.assertTrue(output.geometry.iloc[index].covers(wetlands.geometry.iloc[index]))
            self.assertEqual(output.geometry.iloc[index].difference(owners.geometry.iloc[index]).area, 0)

    def test_each_multipart_piece_requires_seed(self):
        owners = gpd.GeoDataFrame({'SubId': [1]}, geometry=[box(0, 0, 3, 1)], crs=3161)
        wetland = MultiPolygon([box(0.1, 0.1, 0.9, 0.9), box(2.1, 0.1, 2.9, 0.9)])
        wetlands = gpd.GeoDataFrame({'SubId': [1]}, geometry=[wetland], crs=3161)
        with self.assertRaisesRegex(ValueError, 'no positive-area overlap'):
            self._run(wetlands, owners, np.array([[1, 1, 255]], dtype='uint8'))

    def test_no_depressions_returns_empty_output(self):
        owners = gpd.GeoDataFrame({'SubId': [1]}, geometry=[box(0, 0, 1, 1)], crs=3161)
        wetlands = gpd.GeoDataFrame({'SubId': []}, geometry=[], crs=3161)
        output, labels, _, details = self._run(wetlands, owners, np.array([[0]], dtype='uint8'))
        self.assertTrue(output.empty)
        self.assertEqual(labels[0, 0], 0)
        self.assertEqual(details['seed_groups'], 0)


if __name__ == '__main__':
    unittest.main()
