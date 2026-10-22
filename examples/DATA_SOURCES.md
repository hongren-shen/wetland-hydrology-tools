# Example data sources

Example: **02HB033, Mountsberg Creek near Carlisle**, Ontario, Canada.
Prepared on **2026-10-22** from the local project source copies identified in
[`data/manifest.json`](data/manifest.json). Source identifiers are retained.

| Input | Source and attribution | Changes in this example |
| --- | --- | --- |
| Watershed outline | OWL-Hydro v1.0, Hongren Shen and coauthors; gauge hydrofabric for 02HB033 | Selected one gauge boundary |
| Subbasins, rivers, lakes | Ontario Lake and River Routing Product version 2 (OLRRP v2). [OLRRP v2 dataset](https://doi.org/10.5281/zenodo.14225103) | Selected full-resolution regional-root features, clipped owner subbasins, and retained only needed fields |
| Wetland polygons | Government of Ontario, Ministry of Natural Resources / Land Information Ontario. [Wetlands catalogue](https://data.ontario.ca/dataset/wetlands). Project source accessed 2025-03-05 | Selected whole wetland components touching the watershed, including connected portions outside it; retained source OGF_ID and WETLAND_TYPE |
| Flow direction | Government of Ontario, Ontario Integrated Hydrology. [OIH catalogue](https://data.ontario.ca/dataset/ontario-integrated-hydrology-data). Project source documented as November 2020 | Cropped the project FDRfinal.tif on its original 30 m grid, without resampling or polygon masking |
| Retained lake inventory | OLRRP v2.0.1 from OWL-Hydro v1.0 | Used only to identify omitted headwater lakes and the retained lake mask for metrics; classification geometry remains full resolution |

Contains information licensed under the
[Open Government Licence - Ontario](https://www.ontario.ca/page/open-government-licence-ontario).
This applies to the Ontario wetland and OIH source information. These sources
are independent of the repository's MIT software license.

Original OWL-Hydro data and compilation are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) to the extent that the
OWL-Hydro licensors hold the relevant rights. OLRRP and other source material
retain their source-release terms and attribution. Preserve these notices when
redistributing this modified subset. The example does not imply endorsement by
the data providers.

The prepared data use EPSG:3161. Geometry repairs, clipping, field selection,
and raster cropping are described in the manifest and preparation script.
The example reproduces a small workflow demonstration, not an OWL-Hydro release.
