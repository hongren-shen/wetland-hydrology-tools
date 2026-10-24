# Example data sources

The example inputs for **02HB033, Mountsberg Creek near Carlisle**, Ontario,
Canada, were prepared on **2026-10-22**.

| Input | Source | Preparation |
| --- | --- | --- |
| Watershed outline | [OWL-Hydro v1.0](https://doi.org/10.20383/103.01878), gauge hydrofabric for 02HB033 | Selected the gauge boundary |
| Subbasins, rivers, and lakes | [OLRRP v2](https://doi.org/10.5281/zenodo.14225103) | Selected features at their original resolution, clipped subbasins to the watershed, and retained nearby river and lake context |
| Wetland polygons | Government of Ontario, Ministry of Natural Resources / Land Information Ontario, [Wetlands dataset](https://data.ontario.ca/dataset/wetlands); source copy accessed 2025-03-05 | Retained complete wetland components intersecting the watershed, including connected portions outside it; kept `OGF_ID` and `WETLAND_TYPE` |
| Flow direction | Government of Ontario, [Ontario Integrated Hydrology](https://data.ontario.ca/dataset/ontario-integrated-hydrology-data); source documentation dated November 2020 | Cropped the original 30 m grid without resampling or polygon masking |
| Retained lake inventory | OLRRP v2.0.1 from OWL-Hydro v1.0 | Identified omitted headwater lakes and supplied the retained lake mask used in area calculations |

Vector preparation included geometry repairs, clipping, and field selection.
All vector layers use **EPSG:3161**. The flow direction crop extends
**1,000 m** beyond the watershed's bounding box and preserves the original
grid alignment. The `depression_lakes` layer contains one headwater lake
omitted from the retained model lake inventory.

The repository includes these prepared inputs. Regional data extraction is
separate from the two processing workflows. Run instructions and dataset
citations are in the [main README](../README.md).

## Data terms

Contains information licensed under the
[Open Government Licence - Ontario](https://www.ontario.ca/page/open-government-licence-ontario).
This applies to the Ontario wetland and OIH source information, separately
from the repository's MIT software license.

OWL-Hydro data and compilation are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) to the extent that the
OWL-Hydro licensors hold the relevant rights. OLRRP and other source material
retain their source terms and attribution. Preserve these notices when
redistributing the example. Inclusion does not imply endorsement by the
data providers.
