# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Multi-Story Spatial Segmentation & BIM Primitive Extractor
Vectorized LiDAR point cloud segmentation engine:
- O(N) voxel decimation
- Multi-story elevation datum detection (E57 Z-histogram + optional NavVis site_model/footprint fusion)
- Per-story 2D occupancy-grid footprint polygonization for Slabs & Ceilings (no bounding-box artifacts)
- Vertical-column density filtering to separate architectural walls from furniture/clutter
- Iterative RANSAC 2D wall extraction with mandatory contiguous-segment splitting & deduplication
- Header-verified door/window opening detection & 2D room/space segmentation
"""

from collections import deque
import numpy as np

from .walls_engine import (
    AnalyticalWall,
    STANDARD_DOOR_WIDTHS,
    mitre_wall_network,
    snap_to_catalog,
)


def voxel_downsample(xyz, voxel_size=0.05):
    """Fast vectorized O(N) voxel grid centroid downsampling."""
    if len(xyz) == 0 or voxel_size <= 0:
        return xyz
    coords = np.floor(xyz / float(voxel_size)).astype(np.int64)
    order = np.lexsort((coords[:, 2], coords[:, 1], coords[:, 0]))
    sorted_coords = coords[order]
    sorted_pts = xyz[order]
    diff = np.any(np.diff(sorted_coords, axis=0) != 0, axis=1)
    split_idx = np.flatnonzero(diff) + 1
    groups = np.split(sorted_pts, split_idx)
    return np.vstack([g.mean(axis=0) for g in groups])


def detect_elevation_datums(z_vals, bin_size=0.02, min_separation=0.6):
    """
    Finds dominant horizontal planes (floor, ceiling, structural deck) for a single-story
    Z-slice using a fine-grained Z histogram with non-maximum suppression.
    """
    z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
    if z_max - z_min < 0.2:
        return z_min, z_max, z_max

    bins = max(20, int(np.ceil((z_max - z_min) / bin_size)))
    hist, edges = np.histogram(z_vals, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])

    if len(hist) >= 3:
        smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same")
    else:
        smooth = hist.astype(float)

    nonzero = smooth[smooth > 0]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else 0.0
    min_peak_height = max(baseline * 2.5, float(smooth.max()) * 0.15)

    ranked = np.argsort(smooth)[::-1]
    peaks = []
    for idx in ranked:
        if smooth[idx] < min_peak_height:
            break
        z_c = float(centers[idx])
        if all(abs(z_c - p) >= min_separation for p in peaks):
            peaks.append(z_c)
        if len(peaks) >= 4:
            break

    peaks.sort()
    floor_z = peaks[0] if peaks else z_min
    ceiling_z = peaks[1] if len(peaks) > 1 else max(floor_z + 2.4, z_max - 0.3)
    deck_z = peaks[-1] if len(peaks) > 2 else ceiling_z
    return round(floor_z, 3), round(ceiling_z, 3), round(deck_z, 3)


def _find_strongest_z_peak(z_vals, z_lo, z_hi, bin_size=0.03):
    """Finds the densest horizontal Z-plane within [z_lo, z_hi]."""
    mask = (z_vals >= z_lo) & (z_vals <= z_hi)
    sub = z_vals[mask]
    if len(sub) < 30:
        return None
    bins = max(8, int(np.ceil((z_hi - z_lo) / bin_size)))
    hist, edges = np.histogram(sub, bins=bins, range=(z_lo, z_hi))
    centers = 0.5 * (edges[:-1] + edges[1:])
    if len(hist) >= 3:
        smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same")
    else:
        smooth = hist.astype(float)
    best = int(np.argmax(smooth))
    if smooth[best] < 10:
        return None
    return round(float(centers[best]), 3)


def detect_building_stories(xyz, navvis_index=None):
    """
    Detects all building stories (floor_z, ceiling_z, name, id).
    Uses NavVis site_model.json + footprint poses when available, refined against E57 Z-peaks.
    Falls back to pure E57 multi-story Z-histogram peak detection when no bundle is provided.
    """
    z_vals = xyz[:, 2]
    z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
    stories = []

    site_floors = (navvis_index or {}).get("site_floors") or []
    fp_pts = []
    if navvis_index and navvis_index.get("panos"):
        for p in navvis_index["panos"]:
            fp = p.get("footprint_pose") or p.get("global_pose")
            if fp and len(fp) >= 3:
                fp_pts.append(fp)
    fp_pts = np.array(fp_pts, dtype=float) if fp_pts else np.empty((0, 3), dtype=float)

    if site_floors:
        sorted_sf = sorted(
            [sf for sf in site_floors if sf.get("z_min") is not None and sf.get("z_max") is not None],
            key=lambda s: float(s["z_min"]),
        )
        for idx, sf in enumerate(sorted_sf):
            z_lo, z_hi = float(sf["z_min"]), float(sf["z_max"])
            # Find floor peak in lower 45% of story interval
            mid_z = z_lo + 0.45 * (z_hi - z_lo)
            floor_z = _find_strongest_z_peak(z_vals, z_lo - 0.3, mid_z)
            if floor_z is None:
                # Fallback to NavVis footprint Z in this interval
                if len(fp_pts) > 0:
                    in_f = fp_pts[(fp_pts[:, 2] >= z_lo - 0.3) & (fp_pts[:, 2] <= z_hi)]
                    floor_z = round(float(np.median(in_f[:, 2])), 3) if len(in_f) > 0 else round(z_lo + 0.5, 3)
                else:
                    floor_z = round(z_lo + 0.5, 3)

            # Find ceiling peak between floor_z + 2.1m and min(z_hi, floor_z + 4.8m)
            c_lo = floor_z + 2.1
            c_hi = min(z_hi + 0.2, floor_z + 4.8)
            ceil_z = _find_strongest_z_peak(z_vals, c_lo, c_hi) if c_hi > c_lo + 0.2 else None
            if ceil_z is None:
                ceil_z = round(min(z_hi - 0.2, floor_z + 3.0), 3)

            # Only keep stories that actually have sufficient E57 points
            in_story = np.count_nonzero((z_vals >= floor_z - 0.2) & (z_vals <= ceil_z + 0.2))
            if in_story >= 500:
                fname = str(sf.get("name", f"{idx:02d}")).strip()
                stories.append({
                    "id": f"Level_{idx:02d}",
                    "name": f"Level_{fname}",
                    "floor_z": float(floor_z),
                    "ceiling_z": float(ceil_z),
                })

    if not stories:
        # Pure E57 multi-story detection via Z-histogram
        span = z_max - z_min
        if span <= 4.8:
            f_z, c_z, _ = detect_elevation_datums(z_vals)
            stories.append({
                "id": "Level_00",
                "name": "00_Ground_Floor",
                "floor_z": float(f_z),
                "ceiling_z": float(c_z),
            })
        else:
            bins = max(40, int(np.ceil(span / 0.04)))
            hist, edges = np.histogram(z_vals, bins=bins)
            centers = 0.5 * (edges[:-1] + edges[1:])
            smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same")
            nonzero = smooth[smooth > 0]
            baseline = float(np.median(nonzero)) if len(nonzero) > 0 else 0.0
            min_pk = max(baseline * 3.0, float(smooth.max()) * 0.18)

            ranked = np.argsort(smooth)[::-1]
            slab_peaks = []
            for i in ranked:
                if smooth[i] < min_pk:
                    break
                zc = float(centers[i])
                if all(abs(zc - p) >= 2.4 for p in slab_peaks):
                    slab_peaks.append(zc)
            slab_peaks.sort()

            if len(slab_peaks) < 2:
                f_z, c_z, _ = detect_elevation_datums(z_vals)
                stories.append({
                    "id": "Level_00",
                    "name": "00_Ground_Floor",
                    "floor_z": float(f_z),
                    "ceiling_z": float(c_z),
                })
            else:
                for idx in range(len(slab_peaks)):
                    f_z = round(slab_peaks[idx], 3)
                    if idx + 1 < len(slab_peaks):
                        next_f = slab_peaks[idx + 1]
                        if next_f - f_z > 5.5:
                            c_z = _find_strongest_z_peak(z_vals, f_z + 2.2, f_z + 4.5) or round(f_z + 3.0, 3)
                        else:
                            c_z = _find_strongest_z_peak(z_vals, f_z + 2.1, next_f - 0.15) or round(next_f - 0.30, 3)
                    else:
                        c_z = _find_strongest_z_peak(z_vals, f_z + 2.1, min(z_max, f_z + 4.2))
                        if c_z is None:
                            continue
                    stories.append({
                        "id": f"Level_{idx:02d}",
                        "name": f"Level_{idx:02d}",
                        "floor_z": float(f_z),
                        "ceiling_z": float(c_z),
                    })

    return stories


def _douglas_peucker(pts, tol=0.20):
    """Simplifies a 2D polyline/polygon using Douglas-Peucker."""
    if len(pts) <= 3:
        return pts
    p0, p1 = pts[0], pts[-1]
    v = p1 - p0
    L = float(np.linalg.norm(v))
    if L < 1e-9:
        dists = np.linalg.norm(pts - p0, axis=1)
    else:
        rel = pts - p0
        dists = np.abs(v[0] * rel[:, 1] - v[1] * rel[:, 0]) / L
    idx = int(np.argmax(dists))
    if dists[idx] > tol:
        left = _douglas_peucker(pts[: idx + 1], tol)
        right = _douglas_peucker(pts[idx:], tol)
        return np.vstack([left[:-1], right])
    return np.vstack([p0, p1])


def extract_horizontal_polygons(pts_2d, cell_size=0.35, min_area_m2=6.0, navvis_xy=None):
    """
    Extracts accurate 2D footprint polygon(s) from horizontal slab/ceiling points
    using a morphological occupancy grid + outer boundary tracing.
    Eliminates giant bounding-box rectangle artifacts.
    """
    if len(pts_2d) < 30:
        return []

    x_min, y_min = float(np.min(pts_2d[:, 0])), float(np.min(pts_2d[:, 1]))
    x_max, y_max = float(np.max(pts_2d[:, 0])), float(np.max(pts_2d[:, 1]))
    nx = int(np.ceil((x_max - x_min) / cell_size)) + 4
    ny = int(np.ceil((y_max - y_min) / cell_size)) + 4
    if nx * ny > 400_000 or nx < 4 or ny < 4:
        return []

    gx = np.clip(((pts_2d[:, 0] - x_min) / cell_size).astype(int) + 2, 1, nx - 2)
    gy = np.clip(((pts_2d[:, 1] - y_min) / cell_size).astype(int) + 2, 1, ny - 2)
    counts = np.zeros((ny, nx), dtype=np.int32)
    np.add.at(counts, (gy, gx), 1)
    grid = (counts >= 2).astype(np.uint8)

    # Morphological closing (dilate then erode) to bridge small furniture/column gaps
    dilated = grid.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            dilated |= np.roll(np.roll(grid, dy, axis=0), dx, axis=1)
    closed = dilated.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            closed &= np.roll(np.roll(dilated, dy, axis=0), dx, axis=1)

    # Connected components on occupied cells
    visited = np.zeros_like(closed, dtype=bool)
    polygons = []
    min_cells = max(4, int(min_area_m2 / (cell_size ** 2)))

    for y0 in range(1, ny - 1):
        for x0 in range(1, nx - 1):
            if closed[y0, x0] == 1 and not visited[y0, x0]:
                comp = []
                q = deque([(y0, x0)])
                visited[y0, x0] = True
                while q:
                    cy, cx = q.popleft()
                    comp.append((cy, cx))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny_i, nx_i = cy + dy, cx + dx
                        if 0 <= ny_i < ny and 0 <= nx_i < nx and not visited[ny_i, nx_i] and closed[ny_i, nx_i] == 1:
                            visited[ny_i, nx_i] = True
                            q.append((ny_i, nx_i))

                if len(comp) < min_cells:
                    continue

                comp_set = set(comp)
                # Filter out disconnected outdoor components if NavVis poses are known
                if navvis_xy is not None and len(navvis_xy) > 0:
                    comp_pts = np.array(
                        [[x_min + (cx - 2 + 0.5) * cell_size, y_min + (cy - 2 + 0.5) * cell_size] for cy, cx in comp]
                    )
                    # Check if any NavVis pose is within 6m of this component
                    d_min = float(np.min(np.linalg.norm(comp_pts[:, None, :] - navvis_xy[None, :, :], axis=2)))
                    if d_min > 6.0:
                        continue

                # Trace outer boundary edges of the grid component
                edges = {}
                for cy, cx in comp:
                    if (cy - 1, cx) not in comp_set:
                        edges.setdefault((cx, cy), []).append((cx + 1, cy))
                    if (cy + 1, cx) not in comp_set:
                        edges.setdefault((cx + 1, cy + 1), []).append((cx, cy + 1))
                    if (cy, cx - 1) not in comp_set:
                        edges.setdefault((cx, cy + 1), []).append((cx, cy))
                    if (cy, cx + 1) not in comp_set:
                        edges.setdefault((cx + 1, cy), []).append((cx + 1, cy + 1))

                # Walk the longest closed boundary loop
                best_loop = []
                used_starts = set()
                for start_v in list(edges.keys()):
                    if start_v in used_starts:
                        continue
                    loop = [start_v]
                    curr = start_v
                    for _ in range(len(edges) + 2):
                        nxts = edges.get(curr)
                        if not nxts:
                            break
                        nxt = nxts.pop(0)
                        used_starts.add(curr)
                        if nxt == start_v:
                            break
                        loop.append(nxt)
                        curr = nxt
                    if len(loop) > len(best_loop):
                        best_loop = loop

                if len(best_loop) >= 4:
                    world_pts = np.array(
                        [[x_min + (vx - 2) * cell_size, y_min + (vy - 2) * cell_size] for vx, vy in best_loop],
                        dtype=float,
                    )
                    simp = _douglas_peucker(np.vstack([world_pts, world_pts[0]]), tol=cell_size * 0.6)[:-1]
                    if len(simp) >= 3:
                        polygons.append([[round(float(p[0]), 3), round(float(p[1]), 3)] for p in simp])

    return polygons


def _filter_vertical_wall_points(wall_xyz, floor_z, ceiling_z, cell_xy=0.08, z_bin=0.18, min_z_bins=4):
    """
    Filters a story's mid-height point slice to retain only points belonging to
    vertically continuous surfaces (walls/columns), stripping furniture and clutter.
    """
    if len(wall_xyz) < 100:
        return wall_xyz
    story_h = ceiling_z - floor_z
    req_bins = min(min_z_bins, max(2, int(story_h * 0.45 / z_bin)))

    ix = np.floor(wall_xyz[:, 0] / cell_xy).astype(np.int64)
    iy = np.floor(wall_xyz[:, 1] / cell_xy).astype(np.int64)
    iz = np.floor((wall_xyz[:, 2] - floor_z) / z_bin).astype(np.int64)

    # Unique (ix, iy, iz) voxels, then count distinct iz per (ix, iy)
    vox = np.column_stack([ix, iy, iz])
    order = np.lexsort((vox[:, 2], vox[:, 1], vox[:, 0]))
    sorted_vox = vox[order]
    uniq_mask = np.ones(len(sorted_vox), dtype=bool)
    uniq_mask[1:] = np.any(np.diff(sorted_vox, axis=0) != 0, axis=1)
    uniq_vox = sorted_vox[uniq_mask]

    xy_only = uniq_vox[:, :2]
    diff_xy = np.any(np.diff(xy_only, axis=0) != 0, axis=1)
    split_idx = np.flatnonzero(diff_xy) + 1
    starts = np.concatenate([[0], split_idx])
    ends = np.concatenate([split_idx, [len(xy_only)]])
    counts = ends - starts

    valid_cells = xy_only[starts[counts >= req_bins]]
    if len(valid_cells) == 0:
        return wall_xyz

    # Map valid (ix, iy) back to original points via structured 1D hash
    valid_keys = (valid_cells[:, 0].astype(np.int64) << 32) ^ (valid_cells[:, 1].astype(np.int64) & 0xFFFFFFFF)
    pt_keys = (ix << 32) ^ (iy & 0xFFFFFFFF)
    keep = np.isin(pt_keys, valid_keys)
    filtered = wall_xyz[keep]
    return filtered if len(filtered) >= 60 else wall_xyz


def _estimate_dominant_angle(pts_2d, seed=42):
    """Estimates dominant orthogonal axis angle (radians in [0, pi/2)) via fast RANSAC."""
    if len(pts_2d) < 30:
        return 0.0
    rng = np.random.default_rng(seed)
    n_pts = len(pts_2d)
    n_samples = min(600, n_pts * 2)
    i1 = rng.integers(0, n_pts, size=n_samples)
    i2 = rng.integers(0, n_pts, size=n_samples)
    vecs = pts_2d[i2] - pts_2d[i1]
    lengths = np.linalg.norm(vecs, axis=1)
    valid = (lengths > 0.5) & (lengths < 15.0)
    if not np.any(valid):
        return 0.0

    angles = np.mod(np.arctan2(vecs[valid, 1], vecs[valid, 0]), np.pi * 0.5)
    hist, edges = np.histogram(angles, bins=90, range=(0.0, np.pi * 0.5))
    best_bin = int(np.argmax(hist))
    best_angle = float(0.5 * (edges[best_bin] + edges[best_bin + 1]))
    if best_angle < np.radians(1.5) or abs(best_angle - np.pi * 0.5) < np.radians(1.5):
        return 0.0
    return best_angle


def _snap_direction(direction, dominant_angle, angle_tol_deg=6.0):
    """Snaps a 2D unit direction to the nearest dominant orthogonal axis if within tolerance."""
    ang = np.arctan2(direction[1], direction[0])
    candidates = [dominant_angle + k * (np.pi * 0.5) for k in range(-4, 5)]
    best_c = min(candidates, key=lambda c: abs((ang - c + np.pi) % (2 * np.pi) - np.pi))
    diff = abs((ang - best_c + np.pi) % (2 * np.pi) - np.pi)
    if diff <= np.radians(angle_tol_deg):
        return np.array([np.cos(best_c), np.sin(best_c)], dtype=float)
    return direction


def _split_contiguous_runs(along_vals, max_gap=0.75, min_length=0.60, min_points=35):
    """
    Splits 1D projected coordinates into contiguous [t_start, t_end] intervals
    wherever there is a gap > max_gap. Prevents phantom walls spanning empty space.
    """
    if len(along_vals) < min_points:
        return []
    order = np.argsort(along_vals)
    s = along_vals[order]
    gaps = np.diff(s)
    split_pts = np.flatnonzero(gaps > max_gap) + 1
    groups = np.split(s, split_pts)
    runs = []
    for g in groups:
        if len(g) < min_points:
            continue
        t0 = float(np.percentile(g, 1))
        t1 = float(np.percentile(g, 99))
        if (t1 - t0) >= min_length:
            runs.append((t0, t1, len(g)))
    return runs


def _extract_ransac_walls(
    wall_xyz,
    floor_z,
    ceiling_z,
    dominant_angle=0.0,
    level_id="Level_00",
    level_name="00_Ground_Floor",
    wall_id_offset=0,
    max_walls=60,
    min_wall_points=40,
    min_wall_length=0.65,
    inlier_band=0.085,
    seed=42,
    full_slice_xyz=None,
):
    """
    Iteratively extracts 2D wall segments from filtered vertical wall points using
    vectorized RANSAC, mandatory contiguous-segment splitting, bimodal thickness estimation,
    and header-verified opening detection.
    """
    if len(wall_xyz) < min_wall_points:
        return []

    rng = np.random.default_rng(seed)
    rem_xyz = wall_xyz.copy()
    walls = []
    seen_segments = []

    for _ in range(max_walls * 2):
        if len(rem_xyz) < min_wall_points or len(walls) >= max_walls:
            break

        pts_2d = rem_xyz[:, :2]
        n_pts = len(pts_2d)
        n_iters = min(350, max(90, n_pts // 5))

        best_inliers = None
        best_count = 0
        best_dir = None

        i1 = rng.integers(0, n_pts, size=n_iters)
        i2 = rng.integers(0, n_pts, size=n_iters)
        for a, b in zip(i1, i2):
            if a == b:
                continue
            v = pts_2d[b] - pts_2d[a]
            L = float(np.linalg.norm(v))
            if L < 0.45 or L > 18.0:
                continue
            d = v / L
            n = np.array([-d[1], d[0]])
            perp = np.abs((pts_2d - pts_2d[a]) @ n)
            inliers = perp <= inlier_band
            cnt = int(np.count_nonzero(inliers))
            if cnt > best_count:
                best_count = cnt
                best_inliers = inliers
                best_dir = d

        if best_inliers is None or best_count < min_wall_points:
            break

        # Refine direction with PCA on inliers and snap to dominant orthogonal frame
        inlier_2d = pts_2d[best_inliers]
        centroid = inlier_2d.mean(axis=0)
        centered = inlier_2d - centroid
        cov = (centered.T @ centered) / max(1, len(centered))
        _, eigvecs = np.linalg.eigh(cov)
        refined_dir = eigvecs[:, 1]
        if np.dot(refined_dir, best_dir) < 0:
            refined_dir = -refined_dir
        snapped_dir = _snap_direction(refined_dir, dominant_angle)
        snapped_norm = np.array([-snapped_dir[1], snapped_dir[0]])

        rel = pts_2d - centroid
        perp_all = rel @ snapped_norm
        band_mask = np.abs(perp_all) <= inlier_band
        if np.count_nonzero(band_mask) < min_wall_points:
            rem_xyz = rem_xyz[~best_inliers]
            continue

        # Use full_slice_xyz (includes doorway headers) for contiguous run splitting & opening detection
        if full_slice_xyz is not None and len(full_slice_xyz) > 0:
            fs_rel = full_slice_xyz[:, :2] - centroid
            fs_perp = fs_rel @ snapped_norm
            fs_band = np.abs(fs_perp) <= inlier_band
            fs_along = fs_rel[fs_band] @ snapped_dir
            fs_perp_band = fs_perp[fs_band]
            fs_z = full_slice_xyz[fs_band, 2]
        else:
            fs_along = rel[band_mask] @ snapped_dir
            fs_perp_band = perp_all[band_mask]
            fs_z = rem_xyz[band_mask, 2]

        along_band = rel[band_mask] @ snapped_dir
        runs = _split_contiguous_runs(fs_along, max_gap=0.75, min_length=min_wall_length, min_points=min_wall_points)
        if not runs:
            rem_xyz = rem_xyz[~band_mask]
            continue

        consumed_mask = np.zeros(len(rem_xyz), dtype=bool)
        band_indices = np.flatnonzero(band_mask)

        for t_min, t_max, _ in runs:
            seg_mask_local = (along_band >= t_min - 0.05) & (along_band <= t_max + 0.05)
            consumed_mask[band_indices[seg_mask_local]] = True

            fs_seg_mask = (fs_along >= t_min - 0.05) & (fs_along <= t_max + 0.05)
            seg_along = fs_along[fs_seg_mask]
            seg_perp = fs_perp_band[fs_seg_mask]
            seg_z = fs_z[fs_seg_mask]

            # Require minimum linear point density (prevents sparse noise lines)
            seg_len = t_max - t_min
            if len(seg_along) < max(min_wall_points, int(seg_len * 18)):
                continue

            # Estimate thickness from bimodal +/- face offsets
            pos_p = seg_perp[seg_perp > 0.012]
            neg_p = seg_perp[seg_perp < -0.012]
            if len(pos_p) >= 10 and len(neg_p) >= 10:
                raw_thk = float(np.median(pos_p) - np.median(neg_p))
                center_shift = 0.5 * float(np.median(pos_p) + np.median(neg_p))
            else:
                raw_thk = 0.127
                center_shift = float(np.median(seg_perp))

            raw_thk = float(np.clip(raw_thk, 0.09, 0.45))
            adj_centroid = centroid + snapped_norm * center_shift
            p_start = adj_centroid + snapped_dir * t_min
            p_end = adj_centroid + snapped_dir * t_max

            # Deduplicate overlapping collinear walls
            is_dup = False
            for prev_s, prev_e, prev_d in seen_segments:
                if abs(float(np.dot(snapped_dir, prev_d))) > 0.995:
                    p_mid = 0.5 * (p_start + p_end)
                    perp_d = abs(float(np.dot(p_mid - prev_s, np.array([-prev_d[1], prev_d[0]]))))
                    if perp_d < 0.22:
                        # Check 1D overlap
                        p_len = float(np.linalg.norm(prev_e - prev_s))
                        u0 = float(np.dot(p_start - prev_s, prev_d))
                        u1 = float(np.dot(p_end - prev_s, prev_d))
                        ov = min(max(u0, u1), p_len) - max(min(u0, u1), 0.0)
                        if ov > 0.5 * min(seg_len, p_len):
                            is_dup = True
                            break
            if is_dup:
                continue

            wall_h = max(0.8, round(ceiling_z - floor_z, 3))
            wall_type = "LowDivider" if wall_h < 1.5 else ("Exterior" if raw_thk >= 0.145 else "Interior")
            w_idx = wall_id_offset + len(walls) + 1

            wall = AnalyticalWall(
                wall_id=f"W_{level_id}_{len(walls)+1:02d}",
                name=f"{wall_type} Wall {w_idx:02d}",
                p_start=p_start,
                p_end=p_end,
                base_z=floor_z,
                height=wall_h,
                raw_thickness=raw_thk,
                wall_type=wall_type,
            )
            wall.level_id = level_id
            wall.level_name = level_name

            _detect_wall_openings(wall, seg_along - t_min, seg_z, floor_z, wall_h)
            walls.append(wall)
            seen_segments.append((p_start, p_end, snapped_dir))
            if len(walls) >= max_walls:
                break

        rem_xyz = rem_xyz[~consumed_mask]

    return walls


def _detect_wall_openings(wall, along_local, z_band, floor_z, wall_h, bin_w=0.10):
    """Detects door openings along a wall's 1D point-density profile with header verification."""
    if wall.length < 1.5 or wall_h < 2.2 or len(along_local) < 40:
        return
    n_bins = max(5, int(np.floor(wall.length / bin_w)))
    mid_mask = (z_band >= floor_z + 0.40) & (z_band <= floor_z + 1.90)
    hdr_mask = (z_band >= floor_z + 2.05) & (z_band <= floor_z + wall_h - 0.05)
    pts_along = along_local[mid_mask]
    hdr_along = along_local[hdr_mask]
    if len(pts_along) < 20:
        return

    counts, _ = np.histogram(pts_along, bins=n_bins, range=(0.0, wall.length))
    hdr_counts, _ = np.histogram(hdr_along, bins=n_bins, range=(0.0, wall.length))
    median_cnt = float(np.median(counts[counts > 0])) if np.any(counts > 0) else 0.0
    if median_cnt < 2.0:
        return

    low_bins = counts <= max(0.0, 0.15 * median_cnt)
    in_gap = False
    gap_start = 0
    for i, is_low in enumerate(low_bins):
        if is_low and not in_gap:
            in_gap = True
            gap_start = i
        elif not is_low and in_gap:
            in_gap = False
            gap_w = (i - gap_start) * bin_w
            center_off = 0.5 * (gap_start + i) * bin_w
            has_header = int(np.sum(hdr_counts[gap_start:i])) >= 1 or len(hdr_along) < 10
            if has_header and 0.70 <= gap_w <= 2.10 and center_off > 0.40 and (wall.length - center_off) > 0.40:
                snapped_w = snap_to_catalog(gap_w, STANDARD_DOOR_WIDTHS, tolerance=0.12)
                op_idx = len(wall.openings) + 1
                wall.add_opening(
                    opening_id=f"OP_{wall.wall_id}_{op_idx}",
                    name=f"Detected Door {wall.wall_id}_{op_idx}",
                    offset_from_start=round(center_off, 3),
                    width=snapped_w,
                    height=min(2.134, max(1.95, wall_h - 0.10)),
                    sill_z=floor_z,
                    opening_type="Door",
                )


def _segment_spaces(walls, x_min, x_max, y_min, y_max, floor_z, ceiling_z, level_id="Level_00", level_name="00_Ground_Floor", res=0.18):
    """
    Segments enclosed architectural rooms (IfcSpace) using a 2D occupancy grid
    rasterized from extracted walls + connected-component flood fill.
    """
    if not walls:
        return []
    nx = max(10, int(np.ceil((x_max - x_min) / res)) + 4)
    ny = max(10, int(np.ceil((y_max - y_min) / res)) + 4)
    if nx * ny > 250000:
        return []

    grid = np.zeros((ny, nx), dtype=np.uint8)
    for w in walls:
        steps = max(2, int(np.ceil(w.length / (res * 0.5))))
        ts = np.linspace(0.0, 1.0, steps)
        pts = w.start[None, :] + ts[:, None] * (w.end - w.start)[None, :]
        gx = np.clip(((pts[:, 0] - x_min) / res).astype(int) + 2, 0, nx - 1)
        gy = np.clip(((pts[:, 1] - y_min) / res).astype(int) + 2, 0, ny - 1)
        grid[gy, gx] = 1

    visited = np.zeros_like(grid, dtype=bool)
    q = deque([(0, 0)])
    visited[0, 0] = True
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny_i, nx_i = cy + dy, cx + dx
            if 0 <= ny_i < ny and 0 <= nx_i < nx and not visited[ny_i, nx_i] and grid[ny_i, nx_i] == 0:
                visited[ny_i, nx_i] = True
                q.append((ny_i, nx_i))

    spaces = []
    for y0 in range(ny):
        for x0 in range(nx):
            if grid[y0, x0] == 0 and not visited[y0, x0]:
                comp = []
                cq = deque([(y0, x0)])
                visited[y0, x0] = True
                while cq:
                    cy, cx = cq.popleft()
                    comp.append((cy, cx))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny_i, nx_i = cy + dy, cx + dx
                        if 0 <= ny_i < ny and 0 <= nx_i < nx and not visited[ny_i, nx_i] and grid[ny_i, nx_i] == 0:
                            visited[ny_i, nx_i] = True
                            cq.append((ny_i, nx_i))
                area = len(comp) * (res ** 2)
                if 2.0 <= area <= 500.0:
                    ys = [c[0] for c in comp]
                    xs = [c[1] for c in comp]
                    rx_min = x_min + (min(xs) - 2) * res
                    rx_max = x_min + (max(xs) - 1) * res
                    ry_min = y_min + (min(ys) - 2) * res
                    ry_max = y_min + (max(ys) - 1) * res
                    spaces.append({
                        "id": f"SPACE_{level_id}_{len(spaces)+1:02d}",
                        "name": f"Room {level_id}_{len(spaces)+1:02d}",
                        "level_id": level_id,
                        "level_name": level_name,
                        "area_m2": round(area, 2),
                        "elevation": floor_z,
                        "height": round(ceiling_z - floor_z, 3),
                        "polygon": [
                            [round(rx_min, 3), round(ry_min, 3)],
                            [round(rx_max, 3), round(ry_min, 3)],
                            [round(rx_max, 3), round(ry_max, 3)],
                            [round(rx_min, 3), round(ry_max, 3)],
                        ],
                    })
    return spaces


class SpatialBIMExtractor:
    def __init__(self, target_lod=300, voxel_size=0.05):
        self.target_lod = target_lod
        self.voxel_size = float(voxel_size)

    def extract_from_pointcloud(self, cloud_data, site_name="Site", navvis_index=None):
        """
        cloud_data: dict with 'xyz' (N, 3), optional 'rgb' (N, 3)
        navvis_index: optional unified NavVis index dict (site_floors + 6-DoF/footprint poses)
        Returns a multi-story BIM manifest with accurate per-story slabs, ceilings,
        mitred walls, openings, and rooms.
        """
        xyz_raw = np.asarray(cloud_data["xyz"], dtype=float)
        xyz = voxel_downsample(xyz_raw, self.voxel_size) if len(xyz_raw) > 5000 else xyz_raw

        z_vals = xyz[:, 2]
        z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
        x_min, x_max = float(np.min(xyz[:, 0])), float(np.max(xyz[:, 0]))
        y_min, y_max = float(np.min(xyz[:, 1])), float(np.max(xyz[:, 1]))

        stories = detect_building_stories(xyz, navvis_index=navvis_index)

        # Collect NavVis 2D XY poses per story for noise rejection
        nv_pts = []
        if navvis_index and navvis_index.get("panos"):
            for p in navvis_index["panos"]:
                fp = p.get("footprint_pose") or p.get("global_pose")
                if fp and len(fp) >= 3:
                    nv_pts.append(fp)
        nv_pts = np.array(nv_pts, dtype=float) if nv_pts else np.empty((0, 3), dtype=float)

        # Estimate global dominant orientation across mid-story wall slices
        all_wall_pts = []
        for st in stories:
            m = (z_vals >= st["floor_z"] + 0.45) & (z_vals <= st["ceiling_z"] - 0.30)
            if np.any(m):
                all_wall_pts.append(xyz[m, :2])
        dominant_angle = _estimate_dominant_angle(np.vstack(all_wall_pts)) if all_wall_pts else 0.0

        levels = []
        slabs = []
        ceilings = []
        wall_dicts = []
        doors = []
        spaces = []

        for st in stories:
            lvl_id = st["id"]
            lvl_name = st["name"]
            floor_z = st["floor_z"]
            ceiling_z = st["ceiling_z"]
            levels.append({"id": lvl_id, "name": lvl_name, "elevation": floor_z})

            story_nv_xy = None
            if len(nv_pts) > 0:
                in_st = nv_pts[(nv_pts[:, 2] >= floor_z - 0.5) & (nv_pts[:, 2] <= ceiling_z + 0.5)]
                if len(in_st) > 0:
                    story_nv_xy = in_st[:, :2]

            # 1. Per-story Floor Slab footprint polygon(s)
            floor_slice = xyz[(z_vals >= floor_z - 0.14) & (z_vals <= floor_z + 0.14)]
            floor_polys = extract_horizontal_polygons(floor_slice[:, :2], cell_size=0.35, min_area_m2=6.0, navvis_xy=story_nv_xy)
            if not floor_polys and len(floor_slice) >= 20:
                fx0, fx1 = float(np.percentile(floor_slice[:, 0], 1)), float(np.percentile(floor_slice[:, 0], 99))
                fy0, fy1 = float(np.percentile(floor_slice[:, 1], 1)), float(np.percentile(floor_slice[:, 1], 99))
                floor_polys = [[[round(fx0, 3), round(fy0, 3)], [round(fx1, 3), round(fy0, 3)], [round(fx1, 3), round(fy1, 3)], [round(fx0, 3), round(fy1, 3)]]]

            for p_idx, poly in enumerate(floor_polys):
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                slabs.append({
                    "id": f"Floor_{lvl_id}_{p_idx+1:02d}",
                    "name": f"Floor Slab {lvl_name} ({p_idx+1})",
                    "type": "InteriorFloor",
                    "level_id": lvl_id,
                    "level_name": lvl_name,
                    "x_min": min(xs), "x_max": max(xs),
                    "y_min": min(ys), "y_max": max(ys),
                    "polygon": poly,
                    "elevation_top": floor_z,
                    "thickness": 0.15,
                })

            # 2. Per-story Ceiling footprint polygon(s)
            ceil_slice = xyz[(z_vals >= ceiling_z - 0.14) & (z_vals <= ceiling_z + 0.14)]
            ceil_polys = extract_horizontal_polygons(ceil_slice[:, :2], cell_size=0.35, min_area_m2=6.0, navvis_xy=story_nv_xy)
            if not ceil_polys and len(ceil_slice) >= 20:
                cx0, cx1 = float(np.percentile(ceil_slice[:, 0], 1)), float(np.percentile(ceil_slice[:, 0], 99))
                cy0, cy1 = float(np.percentile(ceil_slice[:, 1], 1)), float(np.percentile(ceil_slice[:, 1], 99))
                ceil_polys = [[[round(cx0, 3), round(cy0, 3)], [round(cx1, 3), round(cy0, 3)], [round(cx1, 3), round(cy1, 3)], [round(cx0, 3), round(cy1, 3)]]]

            for p_idx, poly in enumerate(ceil_polys):
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                ceilings.append({
                    "id": f"Ceiling_{lvl_id}_{p_idx+1:02d}",
                    "name": f"Ceiling {lvl_name} ({p_idx+1})",
                    "type": "SuspendedCeiling",
                    "level_id": lvl_id,
                    "level_name": lvl_name,
                    "x_min": min(xs), "x_max": max(xs),
                    "y_min": min(ys), "y_max": max(ys),
                    "polygon": poly,
                    "elevation": ceiling_z,
                    "thickness": 0.04,
                })

            # 3. Per-story Vertical Wall Extraction + Mitring
            wall_slice = xyz[(z_vals >= floor_z + 0.40) & (z_vals <= ceiling_z - 0.25)]
            vert_walls_xyz = _filter_vertical_wall_points(wall_slice, floor_z, ceiling_z)
            walls = _extract_ransac_walls(
                vert_walls_xyz,
                floor_z=floor_z,
                ceiling_z=ceiling_z,
                dominant_angle=dominant_angle,
                level_id=lvl_id,
                level_name=lvl_name,
                wall_id_offset=len(wall_dicts),
                full_slice_xyz=wall_slice,
            )
            joins = mitre_wall_network(walls)

            for w in walls:
                j_s, j_e = joins.get(w.wall_id, (None, None))
                w_dict = w.to_dict(join_start=j_s, join_end=j_e)
                w_dict["level_id"] = lvl_id
                w_dict["level_name"] = lvl_name
                w_dict["residuals"] = w.compute_point_residuals(vert_walls_xyz)
                wall_dicts.append(w_dict)

                for op in w.openings:
                    loc_2d = w.start + w.direction * op["offset"]
                    doors.append({
                        "id": op["id"],
                        "name": op["name"],
                        "host": w.wall_id,
                        "level_id": lvl_id,
                        "level_name": lvl_name,
                        "width": op["width"],
                        "height": op["height"],
                        "pos": [round(float(loc_2d[0]), 3), round(float(loc_2d[1]), 3), round(op["sill_z"], 3)],
                    })

            if walls:
                wx_min = min(min(w.start[0], w.end[0]) for w in walls)
                wx_max = max(max(w.start[0], w.end[0]) for w in walls)
                wy_min = min(min(w.start[1], w.end[1]) for w in walls)
                wy_max = max(max(w.start[1], w.end[1]) for w in walls)
                spaces.extend(_segment_spaces(walls, wx_min, wx_max, wy_min, wy_max, floor_z, ceiling_z, level_id=lvl_id, level_name=lvl_name))

        if len(stories) == 1:
            levels.append({"id": "Level_01", "name": "01_Ceiling_Level", "elevation": stories[0]["ceiling_z"]})
        elif len(stories) > 1:
            levels.append({"id": f"Level_{len(stories):02d}", "name": "Roof_Ceiling_Level", "elevation": stories[-1]["ceiling_z"]})

        manifest = {
            "project": f"{site_name} Scan-to-BIM Model",
            "target_lod": self.target_lod,
            "dominant_orientation_deg": round(float(np.degrees(dominant_angle)), 2),
            "bounds": {
                "x": [round(x_min, 3), round(x_max, 3)],
                "y": [round(y_min, 3), round(y_max, 3)],
                "z": [round(z_min, 3), round(z_max, 3)],
            },
            "levels": levels,
            "slabs": slabs,
            "ceilings": ceilings,
            "walls": wall_dicts,
            "doors": doors,
            "spaces": spaces,
            "plumbing_fixtures": [],
            "casework": [],
        }

        return manifest
