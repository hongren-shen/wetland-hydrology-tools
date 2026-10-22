"""First-depression D8 drainage with exact seed overlap and owner clipping."""

from collections import defaultdict, deque
from math import ceil, floor

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
import shapely
from shapely.geometry import shape


# ESRI D8 values mapped to north-origin row and column offsets.
D8 = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1),
      16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}


def _polygon_parts(geometry):
    """Yield positive polygon parts, including generated overlay collections."""
    if geometry.geom_type == 'Polygon':
        if not geometry.is_empty and geometry.area > 0:
            yield geometry
    elif geometry.geom_type in ('MultiPolygon', 'GeometryCollection'):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def _check_grid(transform):
    if (transform.b != 0 or transform.d != 0 or transform.a <= 0
            or transform.e >= 0 or not np.isfinite(tuple(transform)).all()
            or not np.isclose(transform.a, -transform.e, rtol=1e-9, atol=1e-9)):
        raise ValueError('FDR requires an unrotated north-up grid with square cells.')


def build_seed_groups(parts, valid_mask, transform):
    """Return seed labels, exact group memberships, and coverage diagnostics.

    ``parts`` maps positive part IDs to valid polygons. A valid cell is a seed
    only when the polygon overlaps it by positive area. Shared cells retain the
    full membership tuple, so a small wetland cannot be overwritten by another.
    Every part must overlap at least one valid cell; boundary contact is ignored.
    """
    _check_grid(transform)
    if valid_mask.ndim != 2 or valid_mask.dtype != np.bool_:
        raise ValueError('The valid-data mask must be a two-dimensional Boolean array.')
    if not parts:
        raise ValueError('At least one depression part is required to build seeds.')
    nrows, ncols = valid_mask.shape
    size, xmin, ymax = transform.a, transform.c, transform.f
    cell_members = defaultdict(list)
    missing = []
    for pid, geometry in sorted(parts.items()):
        if (isinstance(pid, bool) or not isinstance(pid, (int, np.integer)) or pid <= 0
                or geometry is None or geometry.is_empty or not geometry.is_valid
                or geometry.geom_type not in ('Polygon', 'MultiPolygon')):
            raise ValueError('Seed parts require positive integer IDs and valid polygon geometries.')
        minx, miny, maxx, maxy = geometry.bounds
        c0, c1 = max(0, floor((minx - xmin) / size)), min(ncols, ceil((maxx - xmin) / size))
        r0, r1 = max(0, floor((ymax - maxy) / size)), min(nrows, ceil((ymax - miny) / size))
        width, height = max(0, c1 - c0), max(0, r1 - r0)
        covered = 0
        for start in range(0, width * height, 65536):
            local = np.arange(start, min(start + 65536, width * height))
            rows, cols = r0 + local // width, c0 + local % width
            selected = valid_mask[rows, cols]
            rows, cols = rows[selected], cols[selected]
            left, top = xmin + cols * size, ymax - rows * size
            cells = shapely.box(left, top - size, left + size, top)
            positive = shapely.area(shapely.intersection(geometry, cells)) > 0
            ids = rows[positive] * ncols + cols[positive]
            for cell in ids:
                cell_members[int(cell)].append(int(pid))
            covered += len(ids)
        if covered == 0:
            missing.append(int(pid))
    if missing:
        raise ValueError('Depression parts have no positive-area overlap with valid FDR cells: '
                         + str(missing[:20]))
    signatures = {tuple(members) for members in cell_members.values()}
    groups = {number: members for number, members in enumerate(sorted(signatures), 1)}
    if len(groups) > np.iinfo(np.int32).max:
        raise ValueError('Too many seed groups for an int32 raster.')
    signature_ids = {members: number for number, members in groups.items()}
    seeds = np.zeros(valid_mask.shape, dtype=np.int32)
    for cell, members in cell_members.items():
        seeds.flat[cell] = signature_ids[tuple(members)]
    return seeds, groups, {'depression_parts': len(parts), 'seed_groups': len(groups),
                           'seed_cells': len(cell_members),
                           'shared_seed_cells': sum(len(pids) > 1 for pids in cell_members.values())}


def trace_d8(flow_direction, seeds, valid_mask):
    """Assign cells to the first seed reached downstream using ESRI D8 codes.

    All seeds are fixed before upstream propagation. Integer values 0..255 are
    accepted; the eight D8 powers route, and other values are terminal sinks.
    NoData cells, paths without a seed, and seed-free cycles remain zero.
    """
    if (flow_direction.ndim != 2 or flow_direction.shape != seeds.shape
            or seeds.shape != valid_mask.shape or valid_mask.dtype != np.bool_
            or flow_direction.dtype.kind not in 'iu' or seeds.dtype.kind not in 'iu'):
        raise ValueError('FDR, integer seeds, and Boolean mask must have the same two-dimensional shape.')
    values = flow_direction[valid_mask]
    if np.any((values < 0) | (values > 255)):
        raise ValueError('Valid FDR values must be ESRI D8 integers in the range 0..255.')
    if np.any(seeds < 0) or np.any(seeds > np.iinfo(np.int32).max) or np.any(seeds[~valid_mask] != 0):
        raise ValueError('Seeds must be nonnegative int32 labels on valid FDR cells.')
    labels = seeds.astype(np.int32, copy=True)
    nrows, ncols = labels.shape
    queue = deque(np.flatnonzero(labels).tolist())
    while queue:
        cell = queue.popleft()
        row, col = divmod(cell, ncols)
        label = labels[row, col]
        for code, (dr, dc) in D8.items():
            nr, nc = row - dr, col - dc
            if (0 <= nr < nrows and 0 <= nc < ncols and valid_mask[nr, nc]
                    and labels[nr, nc] == 0 and flow_direction[nr, nc] == code):
                labels[nr, nc] = label
                queue.append(nr * ncols + nc)
    return labels


def _ids(values, label):
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{label} must contain positive integer IDs.') from exc
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(number) or number <= 0 or not number.is_integer():
            raise ValueError(f'{label} must contain positive integer IDs.')
        result.append(int(number))
    return result


def _check_polygons(frame, label):
    if frame.crs is None or 'SubId' not in frame:
        raise ValueError(f'{label} requires a CRS and SubId field.')
    if (frame.geometry.isna().any() or frame.geometry.is_empty.any()
            or not frame.geometry.is_valid.all()
            or not frame.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all()):
        raise ValueError(f'{label} requires nonempty valid polygon geometries.')


def delineate_depressions(depressions, subbasins, flow_direction_path):
    """Return owner DCA polygons, first-hit labels, raster profile, and diagnostics.

    Output polygons contain ``SubId`` and ``Area_km2`` in the FDR CRS. Labels are
    int32 seed-group IDs with zero meaning unassigned; they are process products,
    not owner IDs. The returned profile uses zero as NoData. Depressions are
    clipped to their explicit owners before every polygon part is seed-checked.
    The final union includes all owned bodies and is clipped to each owner.

    ``crop_edge_labels`` identifies catchments reaching the rectangular raster
    edge. A nonempty list requires a larger-context comparison before the crop
    is treated as complete. A polygon mask must not truncate the input FDR.
    """
    _check_polygons(subbasins, 'Subbasins')
    _check_polygons(depressions, 'Depressions')
    if subbasins.empty or not subbasins.crs.is_projected or any(
            not np.isclose(axis.unit_conversion_factor, 1.0) for axis in subbasins.crs.axis_info[:2]):
        raise ValueError('Subbasins require a projected CRS with metre units.')
    owner_ids = _ids(subbasins.SubId, 'Subbasin SubId')
    if len(set(owner_ids)) != len(owner_ids):
        raise ValueError('Subbasin SubId must be unique.')
    depression_owners = _ids(depressions.SubId, 'Depression SubId')
    if not set(depression_owners).issubset(owner_ids):
        raise ValueError('Every depression SubId must have a matching owner subbasin.')
    with rasterio.open(flow_direction_path) as source:
        if source.count != 1 or source.crs is None or not source.crs.is_projected:
            raise ValueError('FDR requires one band and a projected CRS.')
        if not np.isclose(source.crs.linear_units_factor[1], 1.0):
            raise ValueError('FDR requires metre units.')
        _check_grid(source.transform)
        flow = source.read(1)
        valid = source.read_masks(1) > 0
        profile = source.profile.copy()
    transform, crs = profile['transform'], profile['crs']
    profile.update(dtype='int32', nodata=0, count=1, compress='deflate')
    owners = dict(zip(owner_ids, subbasins.to_crs(crs).geometry))
    if sum(geometry.area for geometry in owners.values()) - shapely.union_all(list(owners.values())).area > 1.0:
        raise ValueError('Subbasins overlap; each location must have one owner.')
    parts, part_owners = {}, {}
    for owner, geometry in zip(depression_owners, depressions.to_crs(crs).geometry):
        owned = list(_polygon_parts(geometry.intersection(owners[owner])))
        if not owned:
            raise ValueError(f'Depression has no area inside its owner SubId {owner}.')
        for part in owned:
            pid = len(parts) + 1
            parts[pid], part_owners[pid] = part, owner
    if parts:
        seeds, groups, diagnostics = build_seed_groups(parts, valid, transform)
    else:
        seeds = np.zeros(flow.shape, dtype=np.int32)
        groups = {}
        diagnostics = {'depression_parts': 0, 'seed_groups': 0, 'seed_cells': 0, 'shared_seed_cells': 0}
    labels = trace_d8(flow, seeds, valid)
    observed = set(np.unique(labels)) - {0}
    if observed != set(groups):
        raise RuntimeError('Delineation lost a seed group.')
    raw_by_owner, bodies = defaultdict(list), defaultdict(list)
    group_areas = defaultdict(float)
    group_owners = {group: {part_owners[pid] for pid in members} for group, members in groups.items()}
    for geometry, value in shapes(labels, mask=labels > 0, transform=transform):
        polygon = shape(geometry)
        polygon = polygon if polygon.is_valid else shapely.make_valid(polygon)
        polygon = shapely.union_all(list(_polygon_parts(polygon)))
        group_areas[int(value)] += polygon.area
        for owner in group_owners[int(value)]:
            raw_by_owner[owner].append(polygon)
    counts = np.bincount(labels.ravel(), minlength=len(groups) + 1)
    for group in groups:
        if abs(group_areas[group] - counts[group] * transform.a ** 2) > 1.0:
            raise RuntimeError(f'Polygonized area differs from raster cells for seed group {group}.')
    for pid, part in parts.items():
        bodies[part_owners[pid]].append(part)
    records = []
    for owner in sorted(bodies):
        body = shapely.union_all(bodies[owner])
        combined = shapely.union_all(raw_by_owner[owner] + [body]).intersection(owners[owner])
        geometry = shapely.union_all(list(_polygon_parts(combined)))
        if (geometry.is_empty or not geometry.is_valid
                or body.difference(geometry).area > 1.0
                or geometry.difference(owners[owner]).area > 1.0):
            raise RuntimeError(f'DCA failed body coverage or owner containment for SubId {owner}.')
        records.append({'SubId': owner, 'Area_km2': geometry.area / 1e6, 'geometry': geometry})
    output = gpd.GeoDataFrame(records, columns=['SubId', 'Area_km2', 'geometry'], geometry='geometry', crs=crs)
    edge_mask = np.zeros(labels.shape, dtype=bool)
    edge_mask[[0, -1], :] = True
    edge_mask[:, [0, -1]] = True
    edges = labels[edge_mask]
    diagnostics.update({'labelled_cells': int(np.count_nonzero(labels)),
                        'terminal_cells': int(np.count_nonzero(valid & ~np.isin(flow, list(D8)))),
                        'crop_edge_cells': int(np.count_nonzero(edges)),
                        'crop_edge_labels': [int(label) for label in np.unique(edges) if label > 0],
                        'owner_count': len(output)})
    return output, labels, profile, diagnostics
