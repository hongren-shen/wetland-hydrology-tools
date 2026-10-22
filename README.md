# wetland-hydrology-tools

Simple Python workflows for wetland reclassification and depression contributing
area delineation, with a small watershed example. Both workflows run in serial
using GeoPandas and Rasterio. ArcGIS and flow accumulation are not required.

## Setup

Use Python 3.10 or newer. From this repository:

```bash
python -m pip install -r requirements.txt
```

The included example is **02HB033, Mountsberg Creek near Carlisle**, Ontario,
with a drainage area of **51.46 km2**. Its inputs total less than 1 MB. No regional
download is needed to run the example.

## Two workflows

Settings are at the top of each script. Paths are relative to the repository,
regardless of where the script is launched.

1. **Reclassify wetlands.** Uses the full-resolution OLRRP river and lake layers
   to produce depression, river, lake, and non-wetland classes.

   ```bash
   python workflows/1_reclassify_wetlands.py
   ```

2. **Delineate depression contributing areas.** Run workflow 1 first, then:

   ```bash
   python workflows/2_delineate_contributing_areas.py
   ```

Outputs are written to `outputs/`:

| File | Content |
| --- | --- |
| `wetland_classes.gpkg` | Wetland classes, parent wetland IDs, and owner `SubId` |
| `contributing_areas.gpkg` | DCA polygons merged and clipped by owner subbasin |
| `contributing_areas.tif` | Final DCA on the input grid, labelled by `SubId`; 0 is NoData |
| `subbasin_metrics.csv` | Areas in m2, `F_num`, `F_den`, and `Flush_frct` in 0..1 |

## Processing rules

- Touching and overlapping wetlands are dissolved into singlepart parents
  before classification. A parent within **60 m** of a river is river-connected;
  lake connection uses direct intersection. Lake connection takes precedence.
- Wetlands are split by subbasin after connection tests. A lake-connected
  parent's portion in a subbasin with `Lake_Cat <= 0` becomes river wetland.
  Wetlands connected to neither are classified as `WETLAND_DEP`.
- The optional `depression_lakes` layer imprints headwater lakes omitted from
  the model's simplified lake inventory as `WETLAND_DEP`. The example contains
  one such lake. Set `DEPRESSION_LAKES_LAYER = None` to skip this step.
- Every valid flow-direction cell with positive-area overlap with a depression
  is a seed. Shared cells retain all overlapping depression identities. Cells
  that only touch a polygon boundary are not seeds. Every polygon part must
  have valid seed coverage.
- One simultaneous ESRI D8 traversal assigns each cell to the first depression
  seed reached downstream. These are incremental contributing zones. Each
  owner's zones and depression bodies are unioned, then clipped to that owner.
- `F_den` is subbasin area excluding retained routing lakes and all wetland
  classes. `F_num` is the owner's DCA intersected with that eligible land.
  `Flush_frct = F_num / F_den`, or zero when `F_den` is zero. Overlapping masks
  are unioned before measuring area. Background land-cover WATER is not inferred.

The flow-direction grid must use ESRI D8 codes: east=1, southeast=2, south=4,
southwest=8, west=16, northwest=32, north=64, northeast=128. Other valid byte
values are terminal cells. NoData, paths without a seed, and seed-free cycles
remain unassigned. Input rasters must have north-up square cells in metre units.

## Example inputs and another watershed

`examples/data/inputs.gpkg` contains:

| Layer | Required fields / purpose |
| --- | --- |
| `boundary` | OWL-Hydro gauge boundary, used to prepare the example |
| `subbasins` | Full-resolution `SubId` and `Lake_Cat`; one polygon per owner |
| `wetlands` | Complete source wetland components intersecting the basin |
| `rivers` | Full-resolution river geometry for connection tests |
| `lakes` | Full-resolution lake geometry for connection tests |
| `depression_lakes` | Optional omitted headwater lake polygons |
| `routing_lakes` | Retained model lake polygons used only for eligible-land metrics |

All vector layers use **EPSG:3161**. `flow_direction.tif` retains the original
**30 m** OIH grid, with a **1,000 m** margin around the basin bounding box.
`manifest.json` records source paths, selection rules, grid details, and hashes.

For another basin, provide the same layers and change the workflow paths.
Preserve complete connected wetland components and nearby river/lake context
before classification. Use an aligned rectangular flow-direction crop with
surrounding context; do not mask it to the watershed polygon before routing.
Workflow 2 stops if a contributing zone reaches the crop edge, so enlarge the
crop when needed. Final vector results are clipped to the subbasins.

To rebuild the supplied inputs from regional source data, edit the two source
paths at the top of `examples/prepare_example.py`, then run that script. This
optional preparation step is separate from the two processing workflows.

## Checks and scope

```bash
python -m unittest discover -s tests -v
```

Tests cover classification precedence, parent connectivity across boundaries,
headwater lake overrides, shared seeds, all eight D8 directions, missing seed
coverage, owner clipping, and union-based fractions.

A fixed-seed comparison with the source project's archived ArcPy Watershed
result matched all 145,633 cells assigned within the example-area raster crop.
Another 3,159 archived cells depended on paths or seeds outside that crop;
following the regional paths recovered all of their archived labels. This
checks the D8 implementation for that footprint, not every possible ArcGIS run.
The example's new seed grid also matches the original seed-building library.
Expanding its FDR margin from 1 km to 3 km leaves all six owner DCA polygons
unchanged; no contributing zone reaches the example crop edge.

This is a compact implementation of the source processing rules. It omits
regional batch processing, resume archives, HRU editing, and routing-product
publication. The example uses full-resolution subbasin owners and newly
classified wetlands, so its metrics are not the published OWL-Hydro HRU metrics.
Planar distance and overlay operations use Shapely; ArcGIS geometry tolerances
and buffer approximations can produce small boundary differences.

## License and sources

Code: [MIT License](LICENSE), copyright 2019-2026 Hongren Shen. Adapted from the
author's Ontario wetland and depression processing scripts. Example data retain
their source terms; see [data sources and attribution](examples/DATA_SOURCES.md).
