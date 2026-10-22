"""Geometric checks of classification rules and owner partitioning."""

import unittest

import geopandas as gpd
import shapely
from shapely.geometry import LineString, box

from library.classification import classify_wetlands, identify_depression_lakes


CRS = "EPSG:3161"


def layer(geometries, **fields):
    return gpd.GeoDataFrame(fields, geometry=geometries, crs=CRS)


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.empty = layer([])
        self.owners = layer([box(0, 0, 10, 10), box(10, 0, 20, 10)],
                            SubId=[1, 2], Lake_Cat=[1, 0])

    def assert_partition(self, result, owners):
        expected = shapely.union_all(owners.geometry.array)
        actual = shapely.union_all(result.geometry.array)
        self.assertLess(expected.symmetric_difference(actual).area, 1e-8)
        self.assertAlmostEqual(result.geometry.area.sum(), actual.area)
        self.assertTrue(result.geometry.is_valid.all())
        self.assertAlmostEqual(result.Area_km2.sum() * 1e6, expected.area)
        for row in result.itertuples():
            owner = owners.loc[owners.SubId == row.SubId].geometry.iloc[0]
            self.assertLess(row.geometry.difference(owner).area, 1e-8)

    def test_lake_precedence_and_nonlake_owner_override(self):
        wetland = layer([box(2, 2, 18, 4)])
        lake = layer([box(2, 3, 3, 5)])
        result = classify_wetlands(wetland, self.empty, lake, self.owners, 0)
        classified = result.loc[result.WET_ORIG > 0].set_index("SubId")
        self.assertEqual(classified.loc[1, "wetld_ID"], 3)
        self.assertEqual(classified.loc[2, "wetld_ID"], 2)
        self.assertEqual(classified.loc[2, "cnnct_s"], 1)
        self.assert_partition(result, self.owners)
        river = layer([LineString([(0, 3), (20, 3)])])
        both = classify_wetlands(wetland, river, lake, self.owners, 0)
        self.assertEqual(both.loc[(both.WET_ORIG > 0) & (both.SubId == 1), "wetld_ID"].iloc[0], 3)

    def test_complete_parent_uses_connection_outside_basin(self):
        owner = self.owners.iloc[[0]].copy()
        result = classify_wetlands(layer([box(8, 2, 14, 4)]), self.empty,
                                   layer([box(12, 3, 15, 5)]), owner, 0)
        self.assertEqual(result.loc[result.WET_ORIG > 0, "wetld_ID"].tolist(), [3])
        self.assert_partition(result, owner)

    def test_dissolve_parent_and_distance_threshold(self):
        wetlands = layer([box(1, 1, 3, 3), box(2, 2, 5, 5), box(7, 7, 8, 8)])
        river = layer([LineString([(0, 0), (0, 10)])])
        result = classify_wetlands(wetlands, river, self.empty, self.owners, river_buffer_m=1)
        wet = result.loc[result.WET_ORIG > 0]
        self.assertEqual(len(wet), 2)
        self.assertEqual(set(wet.wetld_ID), {1, 2})
        self.assertEqual(wet.loc[wet.wetld_ID == 2, "Area_km2"].sum(), 12 / 1e6)
        self.assert_partition(result, self.owners)

    def test_depression_lake_imprints_wetland_and_nonwetland(self):
        wetlands = layer([box(2, 2, 18, 4)])
        river = layer([LineString([(0, 3), (20, 3)])])
        depressions = layer([box(7, 1, 13, 5), box(9, 2, 14, 6)])
        result = classify_wetlands(wetlands, river, self.empty, self.owners, 0,
                                   depression_lakes=depressions)
        dep = result.loc[result.wetld_ID == 1]
        self.assertEqual(set(dep.SubId), {1, 2})
        self.assertEqual(set(dep.WET_ORIG), {0})
        self.assertEqual(dep.cnnct_s.sum() + dep.cnnct_l.sum(), 0)
        expected = shapely.union_all(depressions.geometry.array)
        actual = shapely.union_all(dep.geometry.array)
        self.assertAlmostEqual(expected.symmetric_difference(actual).area, 0)
        self.assert_partition(result, self.owners)

    def test_empty_wetlands_and_text_lake_categories(self):
        owners = self.owners.assign(Lake_Cat=["1.0", "0.0"])
        result = classify_wetlands(self.empty, self.empty, self.empty, owners)
        self.assertEqual(set(result.wetld_ID), {4})
        self.assert_partition(result, owners)

    def test_invalid_inputs_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            owners = layer([box(0, 0, 10, 10), box(5, 0, 15, 10)],
                           SubId=[1, 2], Lake_Cat=[0, 0])
            classify_wetlands(self.empty, self.empty, self.empty, owners)
        with self.assertRaisesRegex(ValueError, "metre"):
            owners = self.owners.to_crs("EPSG:4326")
            classify_wetlands(self.empty, self.empty, self.empty, owners)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            classify_wetlands(self.empty, self.empty, self.empty, self.owners, -1)
        with self.assertRaisesRegex(ValueError, "invalid geometry"):
            invalid = shapely.Polygon([(0, 0), (3, 3), (0, 3), (3, 0), (0, 0)])
            classify_wetlands(layer([invalid]), self.empty, self.empty, self.owners)

    def test_headwater_lakes_omitted_from_model_inventory(self):
        graph = layer([box(i, 0, i + 1, 1) for i in range(4)],
                      SubId=[1, 2, 3, 4], DowSubId=[3, 3, -1, -1],
                      HyLakeId=[101, 102, 103, 104])
        lakes = layer([box(i, 0, i + 1, 1) for i in range(4)], Hylak_id=[101, 102, 103, 104])
        selected = identify_depression_lakes(graph, lakes, {102})
        self.assertEqual(set(selected.Hylak_id), {101, 104})


if __name__ == "__main__":
    unittest.main()
