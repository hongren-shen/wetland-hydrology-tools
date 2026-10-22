"""Check geometry unions and the eligible-land fraction."""

import unittest
import geopandas as gpd
from shapely.geometry import box
from library.metrics import subbasin_metrics


def frame(records):
    return gpd.GeoDataFrame(records, geometry='geometry', crs='EPSG:3161')


class MetricsTests(unittest.TestCase):
    def test_union_exclusions_and_multiple_dca_pieces(self):
        owners = frame([{'SubId': 1, 'geometry': box(0, 0, 10, 10)}])
        classes = frame([
            {'SubId': 1, 'wetld_name': 'WETLAND_DEP', 'geometry': box(0, 0, 2, 10)},
            {'SubId': 1, 'wetld_name': 'WETLAND_RIVER', 'geometry': box(2, 0, 3, 10)}])
        lakes = frame([{'geometry': box(1, 0, 4, 10)}])
        dca = frame([{'SubId': 1, 'geometry': box(0, 0, 6, 10)},
                     {'SubId': 1, 'geometry': box(5, 0, 8, 10)}])
        row = subbasin_metrics(owners, classes, lakes, dca).iloc[0]
        self.assertEqual(row.F_den, 60)
        self.assertEqual(row.F_num, 40)
        self.assertAlmostEqual(row.Flush_frct, 2 / 3)
        self.assertEqual(row.DCA_m2, 80)

    def test_zero_eligible_land(self):
        owners = frame([{'SubId': 1, 'geometry': box(0, 0, 10, 10)}])
        classes = frame([{'SubId': 1, 'wetld_name': 'WETLAND_DEP',
                          'geometry': box(0, 0, 10, 10)}])
        lakes = frame([{'geometry': box(0, 0, 10, 10)}])
        row = subbasin_metrics(owners, classes, lakes, owners).iloc[0]
        self.assertEqual(row.F_den, 0)
        self.assertEqual(row.Flush_frct, 0)


if __name__ == '__main__':
    unittest.main()
