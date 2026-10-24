# wetland-hydrology-tools

Python workflows for classifying wetlands, delineating depression contributing
areas (DCA), and calculating subbasin area fractions (`Flush_frct`). The
workflows run in serial using GeoPandas and Rasterio.

## Setup

Use Python 3.11. The included example was tested with Python 3.11.14 and the
package versions in [environment.yml](environment.yml). From the repository root:

```bash
conda env create -f environment.yml
conda activate wetland-hydrology-tools
```

A pip alternative is provided in [requirements.txt](requirements.txt):

```bash
python -m pip install -r requirements.txt
```

## Included example

The repository includes prepared inputs for **02HB033, Mountsberg Creek near
Carlisle**, Ontario, Canada. The watershed covers **51.46 km2**. Its vector
and flow direction inputs total less than 1 MB.

Run the two workflows in order:

```bash
python workflows/1_reclassify_wetlands.py
python workflows/2_delineate_contributing_areas.py
```

Workflow 1 classifies wetlands using river and lake connections. Workflow 2
uses the resulting depression polygons and a D8 flow direction raster to
calculate DCA and flushing fractions. Paths are resolved relative to the
repository, regardless of where the scripts are launched.

## Inputs and configuration

For another watershed, prepare the following layers in a GeoPackage and edit
the settings at the top of each workflow. The example uses
`examples/data/inputs.gpkg`:

| Layer | Content |
| --- | --- |
| `subbasins` | One polygon per subbasin, with `SubId` and `Lake_Cat` |
| `wetlands` | Complete source wetland components intersecting the watershed |
| `rivers` | River geometry used for connection tests |
| `lakes` | Lake geometry used for connection tests |
| `depression_lakes` | Optional headwater lakes omitted from the retained model lake inventory |
| `routing_lakes` | Retained model lakes excluded from eligible land when calculating fractions |

The example also includes a `boundary` layer with the gauge watershed outline.

| Setting | Workflow | Default and meaning |
| --- | --- | --- |
| `INPUTS` | Both | `examples/data/inputs.gpkg`; vector input file |
| `OUTPUT` | 1 | `outputs/wetland_classes.gpkg`; classified polygons |
| `RIVER_BUFFER_M` | 1 | `60.0`; maximum distance in metres for river connection |
| `LAKE_BUFFER_M` | 1 | `0.0`; lake connection requires touching or overlapping geometry |
| `DEPRESSION_LAKES_LAYER` | 1 | `depression_lakes`; set to `None` to skip the lake override |
| `FLOW_DIRECTION` | 2 | `examples/data/flow_direction.tif`; ESRI D8 flow direction raster |
| `WETLAND_CLASSES` | 2 | `outputs/wetland_classes.gpkg`; must match workflow 1's `OUTPUT` |
| `OUTPUT_FOLDER` | 2 | `outputs`; DCA vectors, raster, and metrics |

Vector inputs must share a projected CRS with metre units. Distance settings
must be finite and nonnegative. Preserve complete connected wetlands and
nearby river and lake geometry before classification.

The flow direction raster must use a projected CRS with metre units and an
unrotated, north-up grid with square cells. Use a rectangular crop with surrounding context;
do not mask it to the watershed polygon before routing. Workflow 2 stops if
a contributing zone reaches the crop edge, so enlarge the crop when needed.

The example vectors use **EPSG:3161**. Its flow direction raster retains the
original **30 m** OIH grid with a **1,000 m** margin around the watershed's
bounding box. Source dates and preparation are documented in
[example data sources](examples/DATA_SOURCES.md).

## Processing rules

- Overlapping wetlands and polygons sharing a boundary segment are merged
  before connection tests. Polygons meeting only at a point remain separate.
  River connection uses the configured distance; lake connection takes
  precedence when both tests pass.
- Wetlands are split by subbasin after connection tests. A lake-connected
  portion in a subbasin with `Lake_Cat <= 0` becomes river wetland. The classes
  are `WETLAND_DEP`, `WETLAND_RIVER`, `WETLAND_LAKE`, and `NO_WETLAND`.
- The optional `depression_lakes` layer assigns omitted headwater lakes to
  `WETLAND_DEP`, overriding the preceding classification. The example contains
  one such lake. The library's `identify_depression_lakes` helper can identify
  these lakes from the complete routing graph and retained lake IDs.
- Every valid flow direction cell with positive area overlap with a depression
  is a seed. Shared cells retain all overlapping depression identities.
  Boundary contact alone does not create a seed. Every depression polygon
  part must overlap at least one valid cell.
- Each cell is assigned to the first depression seed reached downstream.
  The resulting contributing zones and depression bodies are combined by
  subbasin, then clipped to that subbasin's boundary.
- `F_den` is subbasin area excluding retained routing lakes and all three
  wetland classes. `F_num` is the area of eligible land within that subbasin's DCA.
  `Flush_frct = F_num / F_den`, or zero when `F_den` is zero. Overlapping
  exclusions are combined before measuring area. The background WATER land
  cover class is not inferred.

Flow directions must use ESRI D8 codes: east=1, southeast=2, south=4,
southwest=8, west=16, northwest=32, north=64, northeast=128. Other valid byte
values are terminal cells. NoData, paths without a seed, and cycles without
a seed remain unassigned.

The example uses subbasins at their original resolution and newly classified
vector wetlands. Published OWL-Hydro DCA and fractions use the corresponding
final model HRUs and subbasin configuration.

## Outputs

Both workflows write to `outputs/`:

| File | Content |
| --- | --- |
| `wetland_classes.gpkg` | Layer `wetland_classes`: class, generated parent ID `WET_ORIG`, `SubId`, and `Area_km2` |
| `contributing_areas.gpkg` | Layer `contributing_areas`: DCA polygons grouped and clipped by `SubId`, with `Area_km2` |
| `contributing_areas.tif` | Final DCA on the input grid; signed 32-bit `SubId` values, with 0 as NoData |
| `subbasin_metrics.csv` | Areas in m2, `F_num`, `F_den`, and `Flush_frct` in 0..1 |

`WET_ORIG` identifies the parent wetland generated during classification;
it is separate from source IDs such as `OGF_ID`. A value of 0 indicates no
wetland parent, including areas outside mapped wetlands and the optional
lake override.

Rerunning the workflows replaces the generated layers, raster, and CSV.

## Structure and checks

```text
workflows/       two runnable workflows with editable settings
library/         classification, D8 routing, and area calculations
examples/data/   prepared watershed inputs
tests/           checks for classification, routing, geometry, and fractions
```

From the repository root:

```bash
python -m unittest discover -s tests -v
```

The tests cover classification, shared seeds, D8 routing, subbasin clipping,
geometry cleanup, and area fractions. Run the included example to check the
complete workflow and generate the four outputs above.

## Citation and data sources

### Software

Software author: Hongren Shen. Citation metadata for version 1.0.0 is provided
in [CITATION.cff](CITATION.cff). When using GitHub code, record the exact commit.
For an archived software release, cite the DOI of the version used. The
repository citation is:

Shen, H. (2026). *Wetland hydrology tools* (Version 1.0.0) [Computer software].
[GitHub](https://github.com/hongren-shen/wetland-hydrology-tools).

### OWL-Hydro dataset

For the OWL-Hydro gauge boundary, retained lake inventory, or associated
products used with these workflows, please cite:

Shen, H., Tolson, B., Han, M., Craig, J., Metcalfe, R. (2026).
*OWL-Hydro v1.0: An Integrated, Model-Ready Dataset for Semi-Distributed
Hydrologic Modelling in Ontario, Canada*. Federated Research Data Repository.
[https://doi.org/10.20383/103.01878](https://doi.org/10.20383/103.01878)

### Routing and Ontario source data

The subbasin, river, and lake inputs are based on OLRRP v2. Please also cite:

Shen, H., Han, M., Tolson, B., and Metcalfe, R. A. (2024).
*The Ontario Lake and River Routing Product Version 2 (OLRRP V2)* [Data set].
[https://doi.org/10.5281/zenodo.14225103](https://doi.org/10.5281/zenodo.14225103)

Wetland polygons are from the Government of Ontario
[Wetlands dataset](https://data.ontario.ca/dataset/wetlands). Flow direction is
from [Ontario Integrated Hydrology](https://data.ontario.ca/dataset/ontario-integrated-hydrology-data).
See [example data sources](examples/DATA_SOURCES.md) for preparation and data terms.

## License

Code is provided under the [MIT License](LICENSE), copyright 2019-2026
Hongren Shen. Example data retain their source attribution and applicable
data terms, separately from the software license. Preserve the notices in
[example data sources](examples/DATA_SOURCES.md) when redistributing the example.
