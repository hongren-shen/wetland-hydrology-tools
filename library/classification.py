"""Classify wetlands using whole-polygon connections and full-resolution catchments."""

import math

import geopandas as gpd
import pandas as pd
import shapely


CLASS_NAMES = {1: "WETLAND_DEP", 2: "WETLAND_RIVER", 3: "WETLAND_LAKE", 4: "NO_WETLAND"}


def _check_layer(frame, name, crs, kinds):
    if not isinstance(frame, gpd.GeoDataFrame) or frame.crs != crs:
        raise ValueError(f"{name} must be a GeoDataFrame with the same projected CRS.")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"{name} contains missing or empty geometry.")
    if not frame.geometry.is_valid.all():
        raise ValueError(f"{name} contains invalid geometry; repair and verify it before processing.")
    if not frame.geom_type.isin(kinds).all():
        raise ValueError(f"{name} must contain only {', '.join(kinds)} geometry.")


def _polygon_parts(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def identify_depression_lakes(full_subbasins, full_lakes, retained_lake_ids):
    """Select omitted headwater lakes using the complete, uncropped routing graph.

    ``retained_lake_ids`` is the lake-ID inventory retained by the model's
    simplified routing network. Geometry always comes from ``full_lakes``.
    """
    required = {"SubId", "DowSubId", "HyLakeId"}
    if not required.issubset(full_subbasins.columns) or "Hylak_id" not in full_lakes:
        raise ValueError("Headwater selection needs SubId, DowSubId, HyLakeId, and Hylak_id.")
    ids = full_subbasins[list(required)].apply(pd.to_numeric, errors="raise")
    downstream = set(ids.loc[ids.DowSubId > 0, "DowSubId"])
    headwaters = ids.loc[~ids.SubId.isin(downstream) & (ids.HyLakeId > 0), "HyLakeId"]
    lake_ids = pd.to_numeric(full_lakes.Hylak_id, errors="raise")
    retained = set(pd.to_numeric(pd.Series(list(retained_lake_ids)), errors="raise"))
    return full_lakes.loc[lake_ids.isin(headwaters) & ~lake_ids.isin(retained)].copy()


def classify_wetlands(wetlands, rivers, lakes, subbasins, river_buffer_m=60.0,
                      lake_buffer_m=0.0, depression_lakes=None):
    """Return a nonoverlapping classification covering the supplied subbasins.

    Inputs must share a projected metre CRS. Wetlands are dissolved into whole
    singlepart parents before connection tests and clipping. Preserve complete
    parents and their river/lake context when preparing a basin example.

    Lake connection takes precedence. A lake-connected parent's portion in a
    non-lake subbasin becomes river wetland. Optional depression lake polygons
    override every class after classification. Distances are planar and include
    touching boundaries; they use exact distance tests rather than buffer arcs.
    """
    crs = subbasins.crs
    if crs is None or not crs.is_projected or not crs.axis_info or any(
            not math.isclose(axis.unit_conversion_factor, 1.0) for axis in crs.axis_info[:2]):
        raise ValueError("Inputs require a projected CRS with metre units.")
    polygons = ("Polygon", "MultiPolygon")
    for frame, name, kinds in (
            (wetlands, "wetlands", polygons), (rivers, "rivers", ("LineString", "MultiLineString")),
            (lakes, "lakes", polygons), (subbasins, "subbasins", polygons)):
        _check_layer(frame, name, crs, kinds)
    if depression_lakes is not None:
        _check_layer(depression_lakes, "depression_lakes", crs, polygons)
    for name, distance in (("river_buffer_m", river_buffer_m), ("lake_buffer_m", lake_buffer_m)):
        if not math.isfinite(distance) or distance < 0:
            raise ValueError(f"{name} must be a finite, nonnegative distance.")
    if subbasins.empty or not {"SubId", "Lake_Cat"}.issubset(subbasins.columns):
        raise ValueError("Nonempty subbasins with SubId and Lake_Cat are required.")
    owner_ids = pd.to_numeric(subbasins.SubId, errors="raise")
    if (owner_ids.isna().any() or owner_ids.duplicated().any()
            or (owner_ids <= 0).any() or (owner_ids % 1 != 0).any()):
        raise ValueError("SubId must contain unique positive integer identifiers.")
    lake_categories = pd.to_numeric(subbasins.Lake_Cat, errors="raise").fillna(0)
    owners = subbasins.assign(SubId=owner_ids.astype("int64"), Lake_Cat=lake_categories)
    extent = shapely.union_all(owners.geometry.array)
    if owners.geometry.area.sum() - extent.area > max(1e-6, extent.area * 1e-12):
        raise ValueError("Subbasin polygons overlap; each location must have one owner.")

    wetland_union = shapely.union_all(wetlands.geometry.array)
    river_union = shapely.union_all(rivers.geometry.array)
    lake_union = shapely.union_all(lakes.geometry.array)
    rows = []

    def append(geometry, owner, parent_id, class_id, river=0, lake=0):
        for part in _polygon_parts(geometry):
            rows.append({"SubId": int(owner), "WET_ORIG": int(parent_id), "wetld_ID": class_id,
                         "wetld_name": CLASS_NAMES[class_id], "cnnct_s": int(river),
                         "cnnct_l": int(lake), "geometry": part})

    for parent_id, parent in enumerate(_polygon_parts(wetland_union), start=1):
        river = bool(shapely.dwithin(parent, river_union, river_buffer_m))
        lake = bool(shapely.dwithin(parent, lake_union, lake_buffer_m))
        for position in owners.sindex.query(parent, predicate="intersects"):
            owner = owners.iloc[position]
            part = parent.intersection(owner.geometry)
            if lake and owner.Lake_Cat > 0:
                append(part, owner.SubId, parent_id, 3, river, True)
            elif river or lake:
                append(part, owner.SubId, parent_id, 2, True, False)
            else:
                append(part, owner.SubId, parent_id, 1)
    for owner in owners.itertuples():
        append(owner.geometry.difference(wetland_union), owner.SubId, 0, 4)

    if depression_lakes is not None and not depression_lakes.empty:
        depression = shapely.union_all(depression_lakes.geometry.array)
        previous, rows = rows, []
        for row in previous:
            append(row["geometry"].difference(depression), row["SubId"], row["WET_ORIG"],
                   row["wetld_ID"], row["cnnct_s"], row["cnnct_l"])
        for owner in owners.itertuples():
            append(owner.geometry.intersection(depression), owner.SubId, 0, 1)

    result = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
    result["Area_km2"] = result.geometry.area / 1e6
    return result[["SubId", "WET_ORIG", "wetld_ID", "wetld_name", "cnnct_s", "cnnct_l",
                   "Area_km2", "geometry"]].reset_index(drop=True)
