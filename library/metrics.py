"""Measure the fraction of eligible land draining to depressions."""

import pandas as pd
from shapely import union_all


def subbasin_metrics(subbasins, classes, lakes, contributing_areas):
    """Return one row per SubId; all areas are m2 and Flush_frct is 0..1.

    Eligible land excludes retained routing lakes and all three wetland classes. The
    numerator is the union of the owner's DCA intersected with eligible land.
    Supply the model's retained lake polygons, rather than all connectivity
    lakes. Background WATER is not inferred from the NO_WETLAND class.
    """
    if subbasins.crs is None or not subbasins.crs.is_projected:
        raise ValueError('A projected CRS in metres is required.')
    if any(axis.unit_conversion_factor != 1 for axis in subbasins.crs.axis_info[:2]):
        raise ValueError('Area calculations require metre coordinates.')
    if any(frame.crs != subbasins.crs for frame in (classes, lakes, contributing_areas)):
        raise ValueError('All layers must use the same CRS.')
    if subbasins.SubId.duplicated().any():
        raise ValueError('SubId must be unique in subbasins.')
    owners = set(subbasins.SubId)
    if set(contributing_areas.SubId) - owners or set(classes.SubId) - owners:
        raise ValueError('A feature refers to an unknown SubId.')
    lake_union = union_all(lakes.geometry.to_numpy())
    rows = []
    for owner in subbasins.itertuples():
        wet = classes[(classes.SubId == owner.SubId) & (classes.wetld_name != 'NO_WETLAND')]
        bodies = wet[wet.wetld_name == 'WETLAND_DEP']
        drainage = union_all(contributing_areas.loc[
            contributing_areas.SubId == owner.SubId, 'geometry'].to_numpy())
        if drainage.difference(owner.geometry).area > 1.0:
            raise ValueError('A contributing area exceeds its owner boundary.')
        excluded = union_all([lake_union, *wet.geometry])
        eligible = owner.geometry.difference(excluded)
        denominator = eligible.area
        numerator = drainage.intersection(eligible).area
        rows.append({
            'SubId': int(owner.SubId), 'Sub_area': owner.geometry.area,
            'Depression_m2': union_all(bodies.geometry.to_numpy()).area,
            'DCA_m2': drainage.area, 'F_num': numerator, 'F_den': denominator,
            'Flush_frct': numerator / denominator if denominator else 0.0,
        })
    return pd.DataFrame(rows)
