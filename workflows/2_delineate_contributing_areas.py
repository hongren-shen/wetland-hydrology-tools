"""Delineate depression contributing areas and calculate subbasin fractions."""

from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from library.delineation import delineate_depressions
from library.metrics import subbasin_metrics

# Run workflow 1 first. Keep these paths consistent when changing the example.
INPUTS = ROOT / 'examples/data/inputs.gpkg'
FLOW_DIRECTION = ROOT / 'examples/data/flow_direction.tif'
WETLAND_CLASSES = ROOT / 'outputs/wetland_classes.gpkg'
OUTPUT_FOLDER = ROOT / 'outputs'


def main():
    subbasins = gpd.read_file(INPUTS, layer='subbasins')
    lakes = gpd.read_file(INPUTS, layer='routing_lakes')
    classes = gpd.read_file(WETLAND_CLASSES, layer='wetland_classes')
    depressions = classes[classes.wetld_name == 'WETLAND_DEP'].copy()
    drainage, process_labels, profile, diagnostics = delineate_depressions(
        depressions, subbasins, FLOW_DIRECTION)
    if diagnostics.get('crop_edge_labels'):
        raise ValueError('A contributing zone reaches the raster edge. Enlarge the FDR crop.')
    metrics = subbasin_metrics(subbasins.to_crs(drainage.crs),
                              classes.to_crs(drainage.crs),
                              lakes.to_crs(drainage.crs), drainage)
    shapes = [(row.geometry, int(row.SubId)) for row in drainage.itertuples()]
    if shapes and max(value for _, value in shapes) > np.iinfo(np.int32).max:
        raise ValueError('SubId must fit a signed 32-bit output raster.')
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    drainage.to_file(OUTPUT_FOLDER / 'contributing_areas.gpkg',
                     layer='contributing_areas', driver='GPKG', engine='pyogrio')
    # Rasterize the final owner-clipped vectors, not the unconstrained process zones.
    merged = (rasterize(shapes, out_shape=process_labels.shape,
                        transform=profile['transform'], fill=0, dtype='int32')
              if shapes else np.zeros(process_labels.shape, dtype='int32'))
    profile.update(driver='GTiff', dtype='int32', count=1, nodata=0,
                   compress='deflate')
    with rasterio.open(OUTPUT_FOLDER / 'contributing_areas.tif', 'w', **profile) as dst:
        dst.write(merged, 1)
    metrics.to_csv(OUTPUT_FOLDER / 'subbasin_metrics.csv', index=False)
    print(metrics.to_string(index=False))
    print(f'Saved contributing areas and metrics in {OUTPUT_FOLDER}')


if __name__ == '__main__':
    main()
