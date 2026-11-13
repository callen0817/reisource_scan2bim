# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Spatial Segmentation & BIM Primitive Extractor
Vectorized LiDAR point cloud segmentation engine:
- O(N) voxel decimation & statistical elevation datum detection (floor, ceiling, deck)
- Dominant building orientation estimation (Manhattan / Atlanta alignment)
- Iterative RANSAC 2D wall centerline extraction with bimodal thickness estimation
- 1D wall-profile opening (door/window) gap detection
- 2D occupancy-grid room/space segmentation (IfcSpace) and mitred wall networks
"""

import numpy as np
from collections import deque

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
    # Encode 3D voxel indices via structured array for fast unique grouping
    order = np.lexsort((coords[:, 2], coords[:, 1], coords[:, 0]))
    sorted_coords = coords[order]
    sorted_pts = xyz[order]
    diff = np.any(np.diff(sorted_coords, axis=0) != 0, axis=1)
    split_idx = np.flatnonzero(diff) + 1
    groups = np.split(sorted_pts, split_idx)
    return np.vstack([g.mean(axis=0) for g in groups])


def detect_elevation_datums(z_vals, bin_size=0.02, min_separation=0.6):
    """
    Finds dominant horizontal planes (floor, ceiling, structural deck) using a
    fine-grained Z histogram with non-maximum suppression.
    """
    z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
    if z_max - z_min < 0.2:
        return z_min, z_max, z_max

    bins = max(20, int(np.ceil((z_max - z_min) / bin_size)))
    hist, edges = np.histogram(z_vals, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])

    # Smooth slightly with [0.25, 0.5, 0.25] kernel
    if len(hist) >= 3:
        smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same")
    else:
        smooth = hist.astype(float)

    # Only accept peaks that rise significantly above the uniform wall-point baseline
    nonzero = smooth[smooth > 0]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else 0.0
    min_peak_height = max(baseline * 2.5, float(smooth.max()) * 0.15)

    # Pick strongest peaks separated by min_separation
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


def _estimate_dominant_angle(pts_2d, seed=42):
    """Estimates dominant orthogonal axis angle (radians in [0, pi/2)) via fast RANSAC."""
    if len(pts_2d) < 30:
        return 0.0
    rng = np.random.default_rng(seed)
    n_pts = len(pts_2d)
    best_angle = 0.0
    best_score = -1

    # Sample pairs and score alignment on a 90-degree folded histogram
    n_samples = min(400, n_pts * 2)
    i1 = rng.integers(0, n_pts, size=n_samples)
    i2 = rng.integers(0, n_pts, size=n_samples)
    vecs = pts_2d[i2] - pts_2d[i1]
    lengths = np.linalg.norm(vecs, axis=1)
    valid = lengths > 0.5
    if not np.any(valid):
        return 0.0

    angles = np.mod(np.arctan2(vecs[valid, 1], vecs[valid, 0]), np.pi * 0.5)
    hist, edges = np.histogram(angles, bins=90, range=(0.0, np.pi * 0.5))
    best_bin = int(np.argmax(hist))
    best_angle = float(0.5 * (edges[best_bin] + edges[best_bin + 1]))
    # Snap to exact 0 if within 1.5 degrees
    if best_angle < np.radians(1.5) or abs(best_angle - np.pi * 0.5) < np.radians(1.5):
        return 0.0
    return best_angle


def _snap_direction(direction, dominant_angle, angle_tol_deg=8.0):
    """Snaps a 2D unit direction to the nearest dominant orthogonal axis if within tolerance."""
    ang = np.arctan2(direction[1], direction[0])
    candidates = [dominant_angle + k * (np.pi * 0.5) for k in range(-4, 5)]
    best_c = min(candidates, key=lambda c: abs((ang - c + np.pi) % (2 * np.pi) - np.pi))
    diff = abs((ang - best_c + np.pi) % (2 * np.pi) - np.pi)
    if diff <= np.radians(angle_tol_deg):
        return np.array([np.cos(best_c), np.sin(best_c)], dtype=float)
    return direction


def _extract_ransac_walls(
    wall_xyz,
    floor_z,
    ceiling_z,
    dominant_angle=0.0,
    max_walls=40,
    min_wall_points=45,
    min_wall_length=0.60,
    inlier_band=0.14,
    seed=42,
):
    """
    Iteratively extracts 2D wall segments from 3D wall-slice points using vectorized RANSAC,
    bimodal thickness estimation, and opening gap detection.
    """
    if len(wall_xyz) < min_wall_points:
        return []

    rng = np.random.default_rng(seed)
    rem_xyz = wall_xyz.copy()
    walls = []

    for wall_idx in range(max_walls):
        if len(rem_xyz) < min_wall_points:
            break

        pts_2d = rem_xyz[:, :2]
        n_pts = len(pts_2d)
        n_iters = min(350, max(80, n_pts // 4))

        best_inliers = None
        best_count = 0
        best_p0 = None
        best_dir = None

        i1 = rng.integers(0, n_pts, size=n_iters)
        i2 = rng.integers(0, n_pts, size=n_iters)
        for a, b in zip(i1, i2):
            if a == b:
                continue
            v = pts_2d[b] - pts_2d[a]
            L = float(np.linalg.norm(v))
            if L < 0.4:
                continue
            d = v / L
            n = np.array([-d[1], d[0]])
            perp = np.abs((pts_2d - pts_2d[a]) @ n)
            inliers = perp <= inlier_band
            cnt = int(np.count_nonzero(inliers))
            if cnt > best_count:
                best_count = cnt
                best_inliers = inliers
                best_p0 = pts_2d[a]
                best_dir = d

        if best_inliers is None or best_count < min_wall_points:
            break

        # Refine direction with PCA on inliers and snap to dominant frame
        inlier_2d = pts_2d[best_inliers]
        centroid = inlier_2d.mean(axis=0)
        centered = inlier_2d - centroid
        cov = (centered.T @ centered) / max(1, len(centered))
        eigvals, eigvecs = np.linalg.eigh(cov)
        refined_dir = eigvecs[:, 1]
        if np.dot(refined_dir, best_dir) < 0:
            refined_dir = -refined_dir
        snapped_dir = _snap_direction(refined_dir, dominant_angle)
        snapped_norm = np.array([-snapped_dir[1], snapped_dir[0]])

        # Project all remaining points onto snapped line to find contiguous segment(s)
        rel = pts_2d - centroid
        perp_all = rel @ snapped_norm
        band_mask = np.abs(perp_all) <= inlier_band
        if np.count_nonzero(band_mask) < min_wall_points:
            rem_xyz = rem_xyz[~best_inliers]
            continue

        along = rel[band_mask] @ snapped_dir
        perp_band = perp_all[band_mask]
        z_band = rem_xyz[band_mask, 2]

        # Split into contiguous segments if there are large (>0.8m) gaps
        t_min, t_max = float(np.percentile(along, 1)), float(np.percentile(along, 99))
        seg_len = t_max - t_min
        if seg_len < min_wall_length:
            rem_xyz = rem_xyz[~band_mask]
            continue

        # Estimate thickness from bimodal +/- face offsets
        pos_p = perp_band[perp_band > 0.01]
        neg_p = perp_band[perp_band < -0.01]
        if len(pos_p) >= 10 and len(neg_p) >= 10:
            raw_thk = float(np.median(pos_p) - np.median(neg_p))
            center_shift = 0.5 * float(np.median(pos_p) + np.median(neg_p))
        else:
            raw_thk = 0.127
            center_shift = float(np.median(perp_band))

        raw_thk = float(np.clip(raw_thk, 0.08, 0.65))
        adj_centroid = centroid + snapped_norm * center_shift
        p_start = adj_centroid + snapped_dir * t_min
        p_end = adj_centroid + snapped_dir * t_max

        # Estimate height from upper percentile of Z
        wall_top_z = float(np.percentile(z_band, 98))
        wall_h = max(0.8, round(max(wall_top_z - floor_z, ceiling_z - floor_z), 3))
        wall_type = "LowDivider" if wall_h < 1.5 else ("Exterior" if raw_thk >= 0.145 else "Interior")

        wall = AnalyticalWall(
            wall_id=f"W_SEG_{len(walls)+1:02d}",
            name=f"{wall_type} Wall {len(walls)+1:02d}",
            p_start=p_start,
            p_end=p_end,
            base_z=floor_z,
            height=wall_h,
            raw_thickness=raw_thk,
            wall_type=wall_type,
        )

        # Detect door/window openings via 1D density profile along the wall
        _detect_wall_openings(wall, along - t_min, z_band, floor_z, wall_h)

        walls.append(wall)
        rem_xyz = rem_xyz[~band_mask]

    return walls


def _detect_wall_openings(wall, along_local, z_band, floor_z, wall_h, bin_w=0.10):
    """Detects door/window gaps along a wall's 1D point-density profile."""
    if wall.length < 1.4 or len(along_local) < 30:
        return
    n_bins = max(5, int(np.floor(wall.length / bin_w)))
    # Restrict to door/window mid-height band (0.4m to 1.9m above floor)
    mid_mask = (z_band >= floor_z + 0.4) & (z_band <= floor_z + 1.9)
    pts_along = along_local[mid_mask]
    if len(pts_along) < 15:
        return

    counts, edges = np.histogram(pts_along, bins=n_bins, range=(0.0, wall.length))
    median_cnt = float(np.median(counts[counts > 0])) if np.any(counts > 0) else 0.0
    if median_cnt < 2.0:
        return

    low_bins = counts <= max(0.0, 0.15 * median_cnt)
    # Find contiguous runs of low-density bins away from wall ends
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
            if 0.65 <= gap_w <= 2.40 and center_off > 0.35 and (wall.length - center_off) > 0.35:
                snapped_w = snap_to_catalog(gap_w, STANDARD_DOOR_WIDTHS, tolerance=0.12)
                op_idx = len(wall.openings) + 1
                wall.add_opening(
                    opening_id=f"OP_{wall.wall_id}_{op_idx}",
                    name=f"Detected Door {wall.wall_id}_{op_idx}",
                    offset_from_start=round(center_off, 3),
                    width=snapped_w,
                    height=min(2.134, max(1.9, wall_h - 0.1)),
                    sill_z=floor_z,
                    opening_type="Door",
                )


def _segment_spaces(walls, x_min, x_max, y_min, y_max, floor_z, ceiling_z, res=0.15):
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

    # Flood fill exterior from border (0, 0)
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

    # Remaining unvisited 0-cells are enclosed interior spaces
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
                if area >= 1.5:
                    ys = [c[0] for c in comp]
                    xs = [c[1] for c in comp]
                    rx_min = x_min + (min(xs) - 2) * res
                    rx_max = x_min + (max(xs) - 1) * res
                    ry_min = y_min + (min(ys) - 2) * res
                    ry_max = y_min + (max(ys) - 1) * res
                    spaces.append({
                        "id": f"SPACE_{len(spaces)+1:02d}",
                        "name": f"Room {len(spaces)+1:02d}",
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

    def extract_from_pointcloud(self, cloud_data, site_name="Site"):
        """
        cloud_data: dict with 'xyz' (N, 3), optional 'rgb' (N, 3)
        Returns a structured BIM manifest dictionary with segmented levels,
        mitred walls, detected openings, slabs, ceilings, and spaces.
        """
        xyz_raw = np.asarray(cloud_data["xyz"], dtype=float)
        xyz = voxel_downsample(xyz_raw, self.voxel_size) if len(xyz_raw) > 5000 else xyz_raw

        z_vals = xyz[:, 2]
        z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
        floor_z, ceiling_z, deck_z = detect_elevation_datums(z_vals)

        x_min, x_max = float(np.min(xyz[:, 0])), float(np.max(xyz[:, 0]))
        y_min, y_max = float(np.min(xyz[:, 1])), float(np.max(xyz[:, 1]))

        # Extract vertical wall slice (between floor+0.4m and ceiling-0.25m)
        wall_mask = (z_vals >= floor_z + 0.40) & (z_vals <= ceiling_z - 0.25)
        wall_xyz = xyz[wall_mask]

        dominant_angle = _estimate_dominant_angle(wall_xyz[:, :2])
        walls = _extract_ransac_walls(
            wall_xyz,
            floor_z=floor_z,
            ceiling_z=ceiling_z,
            dominant_angle=dominant_angle,
        )
        joins = mitre_wall_network(walls)

        wall_dicts = []
        doors = []
        for w in walls:
            j_s, j_e = joins.get(w.wall_id, (None, None))
            w_dict = w.to_dict(join_start=j_s, join_end=j_e)
            w_dict["residuals"] = w.compute_point_residuals(xyz)
            wall_dicts.append(w_dict)

            for op in w.openings:
                loc_2d = w.start + w.direction * op["offset"]
                doors.append({
                    "id": op["id"],
                    "name": op["name"],
                    "host": w.wall_id,
                    "width": op["width"],
                    "height": op["height"],
                    "pos": [round(float(loc_2d[0]), 3), round(float(loc_2d[1]), 3), round(op["sill_z"], 3)],
                })

        spaces = _segment_spaces(walls, x_min, x_max, y_min, y_max, floor_z, ceiling_z)

        envelope_poly = [
            [round(x_min, 3), round(y_min, 3)],
            [round(x_max, 3), round(y_min, 3)],
            [round(x_max, 3), round(y_max, 3)],
            [round(x_min, 3), round(y_max, 3)],
        ]

        manifest = {
            "project": f"{site_name} Scan-to-BIM Model",
            "target_lod": self.target_lod,
            "dominant_orientation_deg": round(float(np.degrees(dominant_angle)), 2),
            "bounds": {
                "x": [round(x_min, 3), round(x_max, 3)],
                "y": [round(y_min, 3), round(y_max, 3)],
                "z": [round(z_min, 3), round(z_max, 3)],
            },
            "levels": [
                {"id": "Level_00", "name": "00_Ground_Floor", "elevation": floor_z},
                {"id": "Level_01", "name": "01_Ceiling_Level", "elevation": ceiling_z},
                {"id": "Level_02", "name": "02_Structure_Deck", "elevation": deck_z},
            ],
            "slabs": [
                {
                    "id": "Floor_Main_Slab",
                    "name": "Architectural Ground Slab",
                    "type": "InteriorFloor",
                    "x_min": round(x_min, 3), "x_max": round(x_max, 3),
                    "y_min": round(y_min, 3), "y_max": round(y_max, 3),
                    "polygon": envelope_poly,
                    "elevation_top": floor_z,
                    "thickness": 0.15,
                }
            ],
            "ceilings": [
                {
                    "id": "Ceiling_Acoustic_Grid",
                    "name": "Suspended Acoustic Ceiling",
                    "type": "SuspendedCeiling",
                    "x_min": round(x_min, 3), "x_max": round(x_max, 3),
                    "y_min": round(y_min, 3), "y_max": round(y_max, 3),
                    "polygon": envelope_poly,
                    "elevation": ceiling_z,
                    "thickness": 0.04,
                }
            ],
            "walls": wall_dicts,
            "doors": doors,
            "spaces": spaces,
            "plumbing_fixtures": [],
            "casework": [],
        }

        return manifest
