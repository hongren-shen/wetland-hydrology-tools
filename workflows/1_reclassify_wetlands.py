"""Classify the example wetlands using full-resolution rivers and lakes."""

from pathlib import Path
import sys

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from library.classification import classify_wetlands

# Edit these settings for another watershed. All layers use the same metre CRS.
INPUTS = ROOT / 'examples/data/inputs.gpkg'
OUTPUT = ROOT / 'outputs/wetland_classes.gpkg'
RIVER_BUFFER_M = 60.0
LAKE_BUFFER_M = 0.0
# Set to None to omit the optional headwater-lake depression override.
DEPRESSION_LAKES_LAYER = 'depression_lakes'


def main():
    layers = {name: gpd.read_file(INPUTS, layer=name) for name in
              ('wetlands', 'rivers', 'lakes', 'subbasins')}
    depression_lakes = (gpd.read_file(INPUTS, layer=DEPRESSION_LAKES_LAYER)
                        if DEPRESSION_LAKES_LAYER else None)
    result = classify_wetlands(**layers, river_buffer_m=RIVER_BUFFER_M,
                              lake_buffer_m=LAKE_BUFFER_M,
                              depression_lakes=depression_lakes)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(OUTPUT, layer='wetland_classes', driver='GPKG', engine='pyogrio')
    print(result.groupby('wetld_name').Area_km2.agg(['count', 'sum']).to_string())
    print(f'Saved {OUTPUT}')


if __name__ == '__main__':
    main()
