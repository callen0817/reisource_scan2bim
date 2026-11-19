# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Normal-Driven Multi-Story 3D Scan-to-BIM Engine
Industry-grade point-cloud-to-BIM segmentation pipeline:
1. Pre-oriented E57 surface normals (or Open3D normals oriented toward NavVis camera poses)
2. Building-Aligned Coordinate (BAC) frame from vertical-wall normal histogram
3. Upward/downward normal-separated multi-story floor & ceiling datum detection
4. BAC-aligned rectilinear Slab & Ceiling footprint polygonization
5. 3D normal-clustered planar wall face extraction, opposing-face pairing, & support QA filtering
6. Structural Column extraction (DBSCAN vertical shaft clustering, rectangular/circular fit)
7. Structural Beam extraction (ceiling-soffit / plenum elongated 3D cluster fitting)
8. 2D (u, z) elevation void detection for Doors & Windows + automated QA recall metrics
"""

from collections import deque
import math
import numpy as np

from .walls_engine import (
    AnalyticalWall,
    STANDARD_DOOR_WIDTHS,
    mitre_wall_network,
    snap_to_catalog,
)


def voxel_downsample(xyz, voxel_size=0.05, normals=None):
    """Fast vectorized O(N) voxel grid centroid downsampling (preserving normals if given)."""
    if len(xyz) == 0 or voxel_size <= 0:
        return (xyz, normals) if normals is not None else xyz
    coords = np.floor(xyz / float(voxel_size)).astype(np.int64)
    order = np.lexsort((coords[:, 2], coords[:, 1], coords[:, 0]))
    sorted_coords = coords[order]
    sorted_pts = xyz[order]
    diff = np.any(np.diff(sorted_coords, axis=0) != 0, axis=1)
    split_idx = np.flatnonzero(diff) + 1
    starts = np.concatenate([[0], split_idx])
    counts = np.diff(np.concatenate([starts, [len(sorted_pts)]]))

    # Vectorized reduceat is 10x faster than Python list comprehension over np.split
    sum_pts = np.add.reduceat(sorted_pts, starts, axis=0)
    down_xyz = sum_pts / counts[:, None]

    if normals is None:
        return down_xyz

    sorted_n = normals[order]
    sum_n = np.add.reduceat(sorted_n, starts, axis=0)
    norms = np.linalg.norm(sum_n, axis=1, keepdims=True)
    down_n = np.divide(sum_n, np.maximum(norms, 1e-9))
    return down_xyz, down_n


def ensure_oriented_normals(xyz, normals=None, navvis_index=None):
    """
    Returns unit-length oriented 3D surface normals (N, 3).
    - If pre-oriented normals are provided (e.g. from E57 nor:normalX/Y/Z), normalizes them.
    - Otherwise estimates normals via Open3D and orients them toward the nearest NavVis
      camera pose (or interior centroid when no trajectory is available).
    """
    if normals is not None and len(normals) == len(xyz):
        n = np.asarray(normals, dtype=float)
        lens = np.linalg.norm(n, axis=1, keepdims=True)
        valid = (lens[:, 0] > 1e-6) & np.isfinite(n).all(axis=1)
        if np.mean(valid) > 0.85:
            out = np.zeros_like(n)
            out[valid] = n[valid] / lens[valid]
            return out

    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.13, max_nn=18))
    n = np.asarray(pcd.normals, dtype=float)

    # Orient normals consistently toward scanner camera positions (or room centroid)
    cam_pts = []
    if navvis_index and navvis_index.get("panos"):
        for p in navvis_index["panos"]:
            gp = p.get("global_pose")
            if gp and len(gp) >= 3:
                cam_pts.append(gp)

    if cam_pts:
        from scipy.spatial import cKDTree
        cam_arr = np.asarray(cam_pts, dtype=float)
        tree = cKDTree(cam_arr)
        _, nearest_idx = tree.query(xyz, k=1)
        view_vecs = cam_arr[nearest_idx] - xyz
        flip = np.sum(n * view_vecs, axis=1) < 0.0
        n[flip] *= -1.0
    else:
        center = np.mean(xyz, axis=0)
        view_vecs = center[None, :] - xyz
        flip = np.sum(n * view_vecs, axis=1) < 0.0
        n[flip] *= -1.0

    return n


def estimate_dominant_axis_from_normals(normals):
    """
    Estimates the building's dominant orthogonal axis angle in [0, pi/2) directly from
    the histogram of vertical-surface horizontal normals (|nz| < 0.20).
    """
    vert = np.abs(normals[:, 2]) < 0.20
    if np.count_nonzero(vert) < 50:
        return 0.0
    vn = normals[vert]
    angles = np.mod(np.arctan2(vn[:, 1], vn[:, 0]), np.pi * 0.5)
    hist, edges = np.histogram(angles, bins=180, range=(0.0, np.pi * 0.5))
    # Circular smoothing with [0.25, 0.5, 0.25]
    padded = np.concatenate([[hist[-1]], hist, [hist[0]]]).astype(float)
    smooth = 0.25 * padded[:-2] + 0.5 * padded[1:-1] + 0.25 * padded[2:]
    best_bin = int(np.argmax(smooth))
    peak_angle = float(0.5 * (edges[best_bin] + edges[best_bin + 1]))
    # Refine peak with mean of angles within +/- 2.5 deg (folded mod pi/2)
    diff = np.abs((angles - peak_angle + np.pi * 0.25) % (np.pi * 0.5) - np.pi * 0.25)
    near = angles[diff <= np.radians(2.5)]
    if len(near) > 10:
        # Circular mean in 4x angle space (period pi/2)
        best_angle = float((np.arctan2(np.mean(np.sin(4.0 * near)), np.mean(np.cos(4.0 * near))) / 4.0) % (np.pi * 0.5))
    else:
        best_angle = peak_angle
    if best_angle < np.radians(2.0) or abs(best_angle - np.pi * 0.5) < np.radians(2.0):
        return 0.0
    return best_angle


def _rot2d(xy, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.column_stack([xy[:, 0] * c - xy[:, 1] * s, xy[:, 0] * s + xy[:, 1] * c])


def detect_elevation_datums(z_vals, bin_size=0.02, min_separation=0.6):
    """Single-story Z-histogram elevation datum detector (kept for API compatibility)."""
    z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
    if z_max - z_min < 0.2:
        return z_min, z_max, z_max
    bins = max(20, int(np.ceil((z_max - z_min) / bin_size)))
    hist, edges = np.histogram(z_vals, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same") if len(hist) >= 3 else hist.astype(float)
    nonzero = smooth[smooth > 0]
    baseline = float(np.median(nonzero)) if len(nonzero) > 0 else 0.0
    min_peak_height = max(baseline * 2.5, float(smooth.max()) * 0.15)
    peaks = []
    for idx in np.argsort(smooth)[::-1]:
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
    if len(sub) < 25:
        return None
    bins = max(8, int(np.ceil((z_hi - z_lo) / bin_size)))
    hist, edges = np.histogram(sub, bins=bins, range=(z_lo, z_hi))
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same") if len(hist) >= 3 else hist.astype(float)
    best = int(np.argmax(smooth))
    if smooth[best] < 8:
        return None
    return round(float(centers[best]), 3)


def detect_building_stories(xyz, normals=None, navvis_index=None):
    """
    Detects all building stories using upward-normal floor points (nz > 0.80) and
    downward-normal ceiling points (nz < -0.80), cross-checked with NavVis site_model.json
    and footprint poses when available.
    """
    z_vals = xyz[:, 2]
    z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
    if normals is not None and len(normals) == len(xyz):
        floor_z_pts = z_vals[normals[:, 2] > 0.80]
        ceil_z_pts = z_vals[normals[:, 2] < -0.80]
        if len(floor_z_pts) < 100:
            floor_z_pts = z_vals[np.abs(normals[:, 2]) > 0.80]
        if len(ceil_z_pts) < 100:
            ceil_z_pts = z_vals[np.abs(normals[:, 2]) > 0.80]
    else:
        floor_z_pts = z_vals
        ceil_z_pts = z_vals

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
            # Search lower 55% of site_model floor interval (never clip below z_lo so deep basements are found)
            f_search_lo, f_search_hi = z_lo - 0.25, z_lo + 0.55 * (z_hi - z_lo)
            if len(fp_pts) > 0:
                in_f = fp_pts[(fp_pts[:, 2] >= z_lo - 0.3) & (fp_pts[:, 2] <= z_hi)]
                if len(in_f) >= 5:
                    p15_fp_z = float(np.percentile(in_f[:, 2], 15))
                    p85_fp_z = float(np.percentile(in_f[:, 2], 85))
                    f_search_lo = max(z_lo - 0.3, p15_fp_z - 1.2)
                    f_search_hi = min(z_hi - 1.5, p85_fp_z + 0.6)

            floor_z = _find_strongest_z_peak(floor_z_pts, f_search_lo, f_search_hi)
            if floor_z is None:
                floor_z = _find_strongest_z_peak(z_vals, z_lo - 0.25, z_lo + 0.55 * (z_hi - z_lo))
            if floor_z is None:
                floor_z = round(z_lo + 0.5, 3)

            next_z_hi = float(sorted_sf[idx + 1]["z_min"]) if idx + 1 < len(sorted_sf) else z_hi
            c_lo = floor_z + 2.15
            c_hi = min(next_z_hi + 0.15, floor_z + 4.40)
            ceil_z = _find_strongest_z_peak(ceil_z_pts, c_lo, c_hi) if c_hi > c_lo + 0.2 else None
            if ceil_z is None and c_hi > c_lo + 0.2:
                ceil_z = _find_strongest_z_peak(z_vals, c_lo, c_hi)
            if ceil_z is None:
                ceil_z = round(min(z_hi - 0.15, floor_z + 3.0), 3)

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
            hist, edges = np.histogram(floor_z_pts, bins=bins, range=(z_min, z_max))
            centers = 0.5 * (edges[:-1] + edges[1:])
            smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same")
            nonzero = smooth[smooth > 0]
            baseline = float(np.median(nonzero)) if len(nonzero) > 0 else 0.0
            min_pk = max(baseline * 3.0, float(smooth.max()) * 0.16)
            slab_peaks = []
            for i in np.argsort(smooth)[::-1]:
                if smooth[i] < min_pk:
                    break
                zc = float(centers[i])
                if all(abs(zc - p) >= 2.4 for p in slab_peaks):
                    slab_peaks.append(zc)
            slab_peaks.sort()

            if len(slab_peaks) < 2:
                f_z, c_z, _ = detect_elevation_datums(z_vals)
                stories.append({"id": "Level_00", "name": "00_Ground_Floor", "floor_z": float(f_z), "ceiling_z": float(c_z)})
            else:
                for idx in range(len(slab_peaks)):
                    f_z = round(slab_peaks[idx], 3)
                    if idx + 1 < len(slab_peaks):
                        next_f = slab_peaks[idx + 1]
                        c_hi = min(next_f - 0.15, f_z + 4.4)
                        c_z = _find_strongest_z_peak(ceil_z_pts, f_z + 2.15, c_hi) or round(min(next_f - 0.30, f_z + 3.0), 3)
                    else:
                        c_z = _find_strongest_z_peak(ceil_z_pts, f_z + 2.15, min(z_max, f_z + 4.2))
                        if c_z is None:
                            continue
                    stories.append({"id": f"Level_{idx:02d}", "name": f"Level_{idx:02d}", "floor_z": float(f_z), "ceiling_z": float(c_z)})

    # Populate next_floor_z for structural beam plenum detection
    for idx, st in enumerate(stories):
        if idx + 1 < len(stories):
            st["next_floor_z"] = stories[idx + 1]["floor_z"]
        else:
            st["next_floor_z"] = st["ceiling_z"] + 0.45

    return stories


def _douglas_peucker(pts, tol=0.25):
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


def extract_horizontal_polygons_bac(pts_2d_world, dominant_angle, cell_size=0.35, min_area_m2=8.0, navvis_xy_world=None):
    """
    Rotates horizontal floor/ceiling points into Building-Aligned Coordinates (BAC),
    extracts clean rectilinear footprint polygon(s), and transforms them back to world XY.
    """
    if len(pts_2d_world) < 30:
        return []

    pts_bac = _rot2d(pts_2d_world, -dominant_angle)
    nv_bac = _rot2d(navvis_xy_world, -dominant_angle) if (navvis_xy_world is not None and len(navvis_xy_world) > 0) else None

    x_min, y_min = float(np.min(pts_bac[:, 0])), float(np.min(pts_bac[:, 1]))
    x_max, y_max = float(np.max(pts_bac[:, 0])), float(np.max(pts_bac[:, 1]))
    nx = int(np.ceil((x_max - x_min) / cell_size)) + 4
    ny = int(np.ceil((y_max - y_min) / cell_size)) + 4
    if nx * ny > 400_000 or nx < 4 or ny < 4:
        return []

    gx = np.clip(((pts_bac[:, 0] - x_min) / cell_size).astype(int) + 2, 1, nx - 2)
    gy = np.clip(((pts_bac[:, 1] - y_min) / cell_size).astype(int) + 2, 1, ny - 2)
    counts = np.zeros((ny, nx), dtype=np.int32)
    np.add.at(counts, (gy, gx), 1)
    grid = (counts >= 2).astype(np.uint8)

    # 2-pass morphological closing to produce a single clean architectural footprint per wing
    closed = grid.copy()
    for _ in range(2):
        dil = closed.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                dil |= np.roll(np.roll(closed, dy, axis=0), dx, axis=1)
        closed = dil
    for _ in range(2):
        ero = closed.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ero &= np.roll(np.roll(closed, dy, axis=0), dx, axis=1)
        closed = ero

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
                if nv_bac is not None and len(nv_bac) > 0:
                    comp_pts = np.array([[x_min + (cx - 1.5) * cell_size, y_min + (cy - 1.5) * cell_size] for cy, cx in comp])
                    d_min = float(np.min(np.linalg.norm(comp_pts[:, None, :] - nv_bac[None, :, :], axis=2)))
                    if d_min > 5.0:
                        continue

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
                    bac_pts = np.array(
                        [[x_min + (vx - 2) * cell_size, y_min + (vy - 2) * cell_size] for vx, vy in best_loop],
                        dtype=float,
                    )
                    simp_bac = _douglas_peucker(np.vstack([bac_pts, bac_pts[0]]), tol=cell_size * 0.85)[:-1]
                    if len(simp_bac) >= 3:
                        world_pts = _rot2d(simp_bac, dominant_angle)
                        polygons.append([[round(float(p[0]), 3), round(float(p[1]), 3)] for p in world_pts])

    return polygons


def _split_contiguous_runs(along_vals, max_gap=0.65, min_length=0.65, min_points=30):
    """Splits 1D coordinates along a planar wall face into contiguous [u0, u1] segments."""
    if len(along_vals) < min_points:
        return []
    s = np.sort(along_vals)
    gaps = np.diff(s)
    split_pts = np.flatnonzero(gaps > max_gap) + 1
    runs = []
    for g in np.split(s, split_pts):
        if len(g) < min_points:
            continue
        u0 = float(np.percentile(g, 1))
        u1 = float(np.percentile(g, 99))
        if (u1 - u0) >= min_length:
            runs.append((u0, u1, len(g)))
    return runs


def _compute_surface_support(u_vals, z_vals, u0, u1, floor_z, ceiling_z, cell=0.22):
    """Computes fraction of (u, z) wall face cells backed by actual scan points."""
    nu = max(1, int(math.ceil((u1 - u0) / cell)))
    nz = max(1, int(math.ceil((ceiling_z - floor_z) / cell)))
    iu = np.clip(((u_vals - u0) / cell).astype(int), 0, nu - 1)
    iz = np.clip(((z_vals - floor_z) / cell).astype(int), 0, nz - 1)
    occ = len(set(zip(iu.tolist(), iz.tolist())))
    return occ / float(nu * nz)


def extract_planar_walls(
    story_xyz,
    story_normals,
    floor_z,
    ceiling_z,
    dominant_angle=0.0,
    level_id="Level_00",
    level_name="00_Ground_Floor",
    wall_id_offset=0,
):
    """
    Normal-clustered 3D planar wall face segmentation + opposing-face wall pairing.
    Eliminates phantom RANSAC walls across empty space and measures true wall thickness.
    """
    story_h = ceiling_z - floor_z
    if story_h < 1.2 or len(story_xyz) < 100:
        return []

    # 1. Select vertical-surface points
    vmask = (
        (np.abs(story_normals[:, 2]) < 0.22)
        & (story_xyz[:, 2] >= floor_z + 0.25)
        & (story_xyz[:, 2] <= ceiling_z - 0.15)
    )
    if np.count_nonzero(vmask) < 80:
        return []

    v_xyz = story_xyz[vmask]
    v_nor = story_normals[vmask]

    # Rotate XY and horizontal normals into Building-Aligned Coordinates (BAC)
    xy_bac = _rot2d(v_xyz[:, :2], -dominant_angle)
    nxy_bac = _rot2d(v_nor[:, :2], -dominant_angle)
    n_lens = np.linalg.norm(nxy_bac, axis=1, keepdims=True)
    nxy_bac = np.divide(nxy_bac, np.maximum(n_lens, 1e-9))
    angles_deg = np.degrees(np.arctan2(nxy_bac[:, 1], nxy_bac[:, 0])) % 360.0

    # 2. Extract planar face patches per directional bucket (primary orthogonal + strong diagonal)
    bucket_centers = [0.0, 90.0, 180.0, 270.0]
    # Also check 15-deg diagonal buckets for angled walls
    for ang in range(15, 360, 15):
        if any(min(abs(ang - c), 360.0 - abs(ang - c)) < 10.0 for c in bucket_centers):
            continue
        diff = np.minimum(np.abs(angles_deg - ang), 360.0 - np.abs(angles_deg - ang))
        if np.count_nonzero(diff <= 7.5) >= 600:
            bucket_centers.append(float(ang))

    faces = []
    for ang_deg in bucket_centers:
        diff = np.minimum(np.abs(angles_deg - ang_deg), 360.0 - np.abs(angles_deg - ang_deg))
        bmask = diff <= 8.0
        if np.count_nonzero(bmask) < 40:
            continue

        b_xy = xy_bac[bmask]
        b_z = v_xyz[bmask, 2]
        # Refine non-orthogonal bucket normal to exact mean normal of its points
        if ang_deg not in (0.0, 90.0, 180.0, 270.0):
            mean_n = np.mean(nxy_bac[bmask], axis=0)
            n_len = float(np.linalg.norm(mean_n))
            n_vec = mean_n / n_len if n_len > 1e-6 else np.array([math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))], dtype=float)
        else:
            rad = math.radians(ang_deg)
            n_vec = np.array([math.cos(rad), math.sin(rad)], dtype=float)
        t_vec = np.array([-n_vec[1], n_vec[0]], dtype=float)

        d_vals = b_xy @ n_vec
        u_vals = b_xy @ t_vec

        d_min, d_max = float(np.min(d_vals)), float(np.max(d_vals))
        if d_max - d_min < 0.02:
            d_peaks = [0.5 * (d_min + d_max)]
        else:
            bins = max(10, int(math.ceil((d_max - d_min) / 0.025)))
            hist, edges = np.histogram(d_vals, bins=bins, range=(d_min, d_max))
            centers = 0.5 * (edges[:-1] + edges[1:])
            smooth = np.convolve(hist.astype(float), [0.25, 0.5, 0.25], mode="same") if len(hist) >= 3 else hist.astype(float)
            d_peaks = []
            for idx in np.argsort(smooth)[::-1]:
                if smooth[idx] < 25:
                    break
                dc = float(centers[idx])
                if all(abs(dc - p) >= 0.065 for p in d_peaks):
                    d_peaks.append(dc)

        for d0 in d_peaks:
            pmask = np.abs(d_vals - d0) <= 0.045
            if np.count_nonzero(pmask) < 35:
                continue
            p_u = u_vals[pmask]
            p_d = d_vals[pmask]
            p_z = b_z[pmask]

            runs = _split_contiguous_runs(p_u, max_gap=0.70, min_length=0.65, min_points=35)
            for u0, u1, _ in runs:
                rmask = (p_u >= u0 - 0.04) & (p_u <= u1 + 0.04)
                ru = p_u[rmask]
                rd = p_d[rmask]
                rz = p_z[rmask]
                if len(ru) < 35:
                    continue
                z_span = float(np.percentile(rz, 97) - np.percentile(rz, 3))
                if z_span < min(1.25, 0.50 * story_h):
                    continue
                support = _compute_surface_support(ru, rz, u0, u1, floor_z, ceiling_z)
                if support < 0.30:
                    continue

                faces.append({
                    "ang_deg": ang_deg,
                    "n": n_vec,
                    "t": t_vec,
                    "d": float(np.median(rd)),
                    "u0": u0,
                    "u1": u1,
                    "support": support,
                    "count": len(ru),
                    "used": False,
                })

    # 3. Pair opposite-facing parallel faces into double-sided walls
    walls_bac = []
    faces.sort(key=lambda f: f["count"], reverse=True)
    for i, f1 in enumerate(faces):
        if f1["used"]:
            continue
        best_j = None
        best_score = -1.0
        for j in range(i + 1, len(faces)):
            f2 = faces[j]
            if f2["used"]:
                continue
            # Opposite normals: n1 . n2 < -0.95
            if float(np.dot(f1["n"], f2["n"])) > -0.95:
                continue
            # Signed thickness: f1 faces +n1, f2 faces -n1, so wall body lies behind both faces
            # Point on f1 has p . n1 = d1; point on f2 has p . (-n1) = d2 => p . n1 = -d2
            sep = f1["d"] - (-f2["d"])
            # Accept either outward-facing or inward-facing pair (depending on normal sign)
            abs_sep = abs(f1["d"] + f2["d"])
            if not (0.07 <= abs_sep <= 0.55):
                continue
            # Note: since t2 = -t1 for opposite normals, f2's u range in f1's tangent frame is [-f2.u1, -f2.u0]
            f2_u0_in_f1 = -f2["u1"]
            f2_u1_in_f1 = -f2["u0"]
            ov = min(f1["u1"], f2_u1_in_f1) - max(f1["u0"], f2_u0_in_f1)
            if ov < 0.35:
                continue
            score = ov / (abs_sep + 0.1)
            if score > best_score:
                best_score = score
                best_j = j

        if best_j is not None:
            f2 = faces[best_j]
            f1["used"] = True
            f2["used"] = True
            d_mid = 0.5 * (f1["d"] - f2["d"])
            thk = float(np.clip(abs(f1["d"] + f2["d"]), 0.09, 0.50))
            u0 = min(f1["u0"], -f2["u1"])
            u1 = max(f1["u1"], -f2["u0"])
            p_start_bac = f1["n"] * d_mid + f1["t"] * u0
            p_end_bac = f1["n"] * d_mid + f1["t"] * u1
            walls_bac.append({
                "p_start": p_start_bac,
                "p_end": p_end_bac,
                "thickness": thk,
                "support": round(0.5 * (f1["support"] + f2["support"]), 3),
                "double_sided": True,
                "wall_type": "Exterior" if thk >= 0.17 else "Interior",
            })
        elif (f1["u1"] - f1["u0"]) >= 1.15 and f1["support"] >= 0.42:
            # Single-sided perimeter/exterior wall: offset behind the face by half thickness
            f1["used"] = True
            thk = 0.152
            d_mid = f1["d"] - 0.5 * thk
            p_start_bac = f1["n"] * d_mid + f1["t"] * f1["u0"]
            p_end_bac = f1["n"] * d_mid + f1["t"] * f1["u1"]
            walls_bac.append({
                "p_start": p_start_bac,
                "p_end": p_end_bac,
                "thickness": thk,
                "support": round(f1["support"], 3),
                "double_sided": False,
                "wall_type": "Exterior",
            })

    # 4. Deduplicate overlapping collinear walls in BAC
    deduped = []
    walls_bac.sort(key=lambda w: float(np.linalg.norm(w["p_end"] - w["p_start"])), reverse=True)
    for wb in walls_bac:
        v = wb["p_end"] - wb["p_start"]
        L = float(np.linalg.norm(v))
        if L < 0.65:
            continue
        d = v / L
        is_dup = False
        for prev in deduped:
            pv = prev["p_end"] - prev["p_start"]
            pL = float(np.linalg.norm(pv))
            pd = pv / pL
            if abs(float(np.dot(d, pd))) > 0.99:
                mid = 0.5 * (wb["p_start"] + wb["p_end"])
                perp = abs(float(np.dot(mid - prev["p_start"], np.array([-pd[1], pd[0]]))))
                if perp < 0.24:
                    u0 = float(np.dot(wb["p_start"] - prev["p_start"], pd))
                    u1 = float(np.dot(wb["p_end"] - prev["p_start"], pd))
                    ov = min(max(u0, u1), pL) - max(min(u0, u1), 0.0)
                    if ov > 0.55 * min(L, pL):
                        is_dup = True
                        break
        if not is_dup:
            deduped.append(wb)

    # 5. Snap nearby orthogonal/angled wall endpoints (L-corners & T-junctions) for watertight joins
    _snap_wall_endpoints(deduped, tol=0.35)

    # 6. Transform back to world coordinates, instantiate AnalyticalWalls, & detect Doors/Windows
    walls = []
    for idx, wb in enumerate(deduped):
        pts_w = _rot2d(np.vstack([wb["p_start"], wb["p_end"]]), dominant_angle)
        w_idx = wall_id_offset + len(walls) + 1
        wall = AnalyticalWall(
            wall_id=f"W_{level_id}_{len(walls)+1:02d}",
            name=f"{wb['wall_type']} Wall {w_idx:02d}",
            p_start=pts_w[0],
            p_end=pts_w[1],
            base_z=floor_z,
            height=round(story_h, 3),
            raw_thickness=wb["thickness"],
            wall_type=wb["wall_type"],
        )
        wall.level_id = level_id
        wall.level_name = level_name
        wall.surface_support = wb["support"]
        wall.double_sided = wb["double_sided"]

        _detect_wall_openings_2d(wall, story_xyz, floor_z, ceiling_z)
        walls.append(wall)

    return walls


def _snap_wall_endpoints(walls_bac, tol=0.35):
    """Snaps wall endpoints to nearby perpendicular/angled wall intersections (L-corners & T-junctions)."""
    for i, w1 in enumerate(walls_bac):
        p1, p2 = w1["p_start"], w1["p_end"]
        v1 = p2 - p1
        L1 = float(np.linalg.norm(v1))
        if L1 < 1e-4:
            continue
        d1 = v1 / L1
        for ep_key in ("p_start", "p_end"):
            ep = w1[ep_key]
            best_pt = None
            best_dist = tol
            for j, w2 in enumerate(walls_bac):
                if i == j:
                    continue
                q1, q2 = w2["p_start"], w2["p_end"]
                v2 = q2 - q1
                L2 = float(np.linalg.norm(v2))
                if L2 < 1e-4:
                    continue
                d2 = v2 / L2
                if abs(float(np.dot(d1, d2))) > 0.85:
                    continue
                # Line-line intersection of infinite lines (p1 + t*d1 = q1 + s*d2)
                det = d1[0] * (-d2[1]) - d1[1] * (-d2[0])
                if abs(det) < 1e-6:
                    continue
                rhs = q1 - p1
                t = (rhs[0] * (-d2[1]) - rhs[1] * (-d2[0])) / det
                s = (d1[0] * rhs[1] - d1[1] * rhs[0]) / det
                ix_pt = p1 + t * d1
                dist_ep = float(np.linalg.norm(ix_pt - ep))
                if dist_ep < best_dist and (-tol <= s <= L2 + tol):
                    best_dist = dist_ep
                    best_pt = ix_pt
            if best_pt is not None:
                w1[ep_key] = best_pt


def _detect_wall_openings_2d(wall, story_xyz, floor_z, ceiling_z, bin_w=0.10):
    """
    Projects points near the wall onto its 2D (u, z) elevation plane to detect both
    Doors (void down to floor with header above) and Windows (void with sill below + header above).
    """
    story_h = ceiling_z - floor_z
    if wall.length < 1.5 or story_h < 2.1:
        return

    rel = story_xyz[:, :2] - wall.start[None, :]
    u = rel @ wall.direction
    perp = np.abs(rel @ wall.normal)
    z = story_xyz[:, 2]
    mask = (u >= 0.0) & (u <= wall.length) & (perp <= wall.thickness * 0.5 + 0.12) & (z >= floor_z + 0.10) & (z <= ceiling_z - 0.05)
    if np.count_nonzero(mask) < 40:
        return

    u_l = u[mask]
    z_l = z[mask]
    n_bins = max(6, int(math.floor(wall.length / bin_w)))

    sill_mask = (z_l >= floor_z + 0.15) & (z_l <= floor_z + 0.85)
    mid_mask = (z_l >= floor_z + 0.90) & (z_l <= floor_z + 1.90)
    hdr_mask = (z_l >= floor_z + 2.00) & (z_l <= ceiling_z - 0.05)

    sill_cnt, _ = np.histogram(u_l[sill_mask], bins=n_bins, range=(0.0, wall.length))
    mid_cnt, _ = np.histogram(u_l[mid_mask], bins=n_bins, range=(0.0, wall.length))
    hdr_cnt, _ = np.histogram(u_l[hdr_mask], bins=n_bins, range=(0.0, wall.length))

    nz_mid = mid_cnt[mid_cnt > 0]
    med_mid = float(np.median(nz_mid)) if len(nz_mid) > 0 else 0.0
    if med_mid < 2.0:
        return

    low_mid = mid_cnt <= max(0.0, 0.15 * med_mid)
    in_gap = False
    gap_start = 0
    for i, is_low in enumerate(low_mid):
        if is_low and not in_gap:
            in_gap = True
            gap_start = i
        elif (not is_low or i == n_bins - 1) and in_gap:
            end_i = i if not is_low else i + 1
            in_gap = False
            gap_w = (end_i - gap_start) * bin_w
            center_off = 0.5 * (gap_start + end_i) * bin_w
            if center_off <= 0.35 or (wall.length - center_off) <= 0.35:
                continue

            has_header = int(np.sum(hdr_cnt[gap_start:end_i])) >= 1 or np.count_nonzero(hdr_mask) < 10
            sill_pts = int(np.sum(sill_cnt[gap_start:end_i]))
            if not has_header:
                continue

            if sill_pts <= max(1, int(0.15 * med_mid * (end_i - gap_start))) and 0.70 <= gap_w <= 2.15:
                snapped_w = snap_to_catalog(gap_w, STANDARD_DOOR_WIDTHS, tolerance=0.12)
                op_idx = len(wall.openings) + 1
                wall.add_opening(
                    opening_id=f"OP_{wall.wall_id}_{op_idx}",
                    name=f"Detected Door {wall.wall_id}_{op_idx}",
                    offset_from_start=round(center_off, 3),
                    width=snapped_w,
                    height=min(2.134, max(1.95, story_h - 0.10)),
                    sill_z=floor_z,
                    opening_type="Door",
                )
            elif sill_pts >= max(3, int(0.35 * med_mid * (end_i - gap_start))) and 0.60 <= gap_w <= 3.20:
                op_idx = len(wall.openings) + 1
                wall.add_opening(
                    opening_id=f"WIN_{wall.wall_id}_{op_idx}",
                    name=f"Detected Window {wall.wall_id}_{op_idx}",
                    offset_from_start=round(center_off, 3),
                    width=round(gap_w, 3),
                    height=min(1.35, max(0.80, story_h - 1.15)),
                    sill_z=round(floor_z + 0.90, 3),
                    opening_type="Window",
                )


def extract_structural_columns(
    story_xyz,
    story_normals,
    walls,
    floor_z,
    ceiling_z,
    dominant_angle=0.0,
    level_id="Level_00",
    level_name="00_Ground_Floor",
    col_id_offset=0,
):
    """
    Extracts Structural Columns (IfcColumn) from remaining vertical-normal points
    not belonging to walls via Open3D DBSCAN clustering + vertical shaft validation.
    """
    story_h = ceiling_z - floor_z
    if story_h < 1.5 or len(story_xyz) < 100:
        return []

    vmask = (
        (np.abs(story_normals[:, 2]) < 0.28)
        & (story_xyz[:, 2] >= floor_z + 0.25)
        & (story_xyz[:, 2] <= ceiling_z - 0.15)
    )
    cand_xyz = story_xyz[vmask]
    if len(cand_xyz) < 40:
        return []

    # Remove points belonging to any extracted wall
    keep = np.ones(len(cand_xyz), dtype=bool)
    xy = cand_xyz[:, :2]
    for w in walls:
        rel = xy - w.start[None, :]
        u = rel @ w.direction
        perp = np.abs(rel @ w.normal)
        in_w = (u >= -0.10) & (u <= w.length + 0.10) & (perp <= w.thickness * 0.5 + 0.14)
        keep &= ~in_w

    rem_xyz = cand_xyz[keep]
    if len(rem_xyz) < 35:
        return []

    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(rem_xyz)
    labels = np.asarray(pcd.cluster_dbscan(eps=0.16, min_points=25, print_progress=False))
    max_lbl = int(labels.max()) if len(labels) > 0 else -1
    if max_lbl < 0:
        return []

    columns = []
    for lbl in range(max_lbl + 1):
        pts = rem_xyz[labels == lbl]
        if len(pts) < 35:
            continue

        z_lo, z_hi = float(np.percentile(pts[:, 2], 2)), float(np.percentile(pts[:, 2], 98))
        z_span = z_hi - z_lo
        if z_span < 0.62 * story_h:
            continue

        # Check continuous vertical shaft occupancy (rejects isolated clutter)
        n_zbins = max(4, int(story_h / 0.25))
        iz = np.clip(((pts[:, 2] - floor_z) / 0.25).astype(int), 0, n_zbins - 1)
        if len(np.unique(iz)) / float(n_zbins) < 0.55:
            continue

        xy_bac = _rot2d(pts[:, :2], -dominant_angle)
        x0, x1 = float(np.percentile(xy_bac[:, 0], 3)), float(np.percentile(xy_bac[:, 0], 97))
        y0, y1 = float(np.percentile(xy_bac[:, 1], 3)), float(np.percentile(xy_bac[:, 1], 97))
        dx, dy = x1 - x0, y1 - y0
        if not (0.15 <= dx <= 1.25 and 0.15 <= dy <= 1.25):
            continue
        if max(dx, dy) / max(min(dx, dy), 1e-6) > 2.8:
            continue

        c_bac = np.array([[0.5 * (x0 + x1), 0.5 * (y0 + y1)]], dtype=float)
        c_world = _rot2d(c_bac, dominant_angle)[0]

        # Circular vs rectangular heuristic from radial distance variance
        r_dists = np.linalg.norm(xy_bac - c_bac, axis=1)
        r_med = float(np.median(r_dists))
        r_cv = float(np.std(r_dists) / max(r_med, 1e-6))
        is_circular = (abs(dx - dy) / max(dx, dy) < 0.20) and (r_cv < 0.14)

        c_idx = col_id_offset + len(columns) + 1
        columns.append({
            "id": f"COL_{level_id}_{len(columns)+1:02d}",
            "name": f"Structural Column {c_idx:02d}",
            "level_id": level_id,
            "level_name": level_name,
            "shape": "circular" if is_circular else "rectangular",
            "center": [round(float(c_world[0]), 3), round(float(c_world[1]), 3)],
            "width": round(dx, 3),
            "depth": round(dy, 3),
            "radius": round(0.25 * (dx + dy), 3),
            "base_z": round(floor_z, 3),
            "height": round(story_h, 3),
            "rotation_deg": round(float(np.degrees(dominant_angle)), 2),
            "point_count": int(len(pts)),
        })

    return columns


def extract_structural_beams(
    story_xyz,
    story_normals,
    walls,
    columns,
    floor_z,
    ceiling_z,
    next_floor_z,
    dominant_angle=0.0,
    level_id="Level_00",
    level_name="00_Ground_Floor",
    beam_id_offset=0,
):
    """
    Extracts Structural Beams (IfcBeam) from drop-beam soffits below the ceiling
    and exposed linear structural framing in the ceiling plenum via 3D DBSCAN clustering.
    """
    story_h = ceiling_z - floor_z
    if story_h < 1.8 or len(story_xyz) < 100:
        return []

    z = story_xyz[:, 2]
    # Drop-beam zone below ceiling + plenum structural zone above ceiling
    drop_mask = (z >= ceiling_z - 0.65) & (z <= ceiling_z - 0.08)
    plenum_mask = (z >= ceiling_z + 0.08) & (z <= min(next_floor_z - 0.08, ceiling_z + 0.75))
    bmask = drop_mask | plenum_mask
    cand_xyz = story_xyz[bmask]
    if len(cand_xyz) < 40:
        return []

    # Exclude points inside walls or columns
    keep = np.ones(len(cand_xyz), dtype=bool)
    xy = cand_xyz[:, :2]
    for w in walls:
        rel = xy - w.start[None, :]
        u = rel @ w.direction
        perp = np.abs(rel @ w.normal)
        keep &= ~((u >= -0.10) & (u <= w.length + 0.10) & (perp <= w.thickness * 0.5 + 0.15))
    for col in columns:
        c = np.array(col["center"], dtype=float)
        r = 0.5 * max(col["width"], col["depth"]) + 0.15
        keep &= np.linalg.norm(xy - c[None, :], axis=1) > r

    rem_xyz = cand_xyz[keep]
    if len(rem_xyz) < 35:
        return []

    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(rem_xyz)
    labels = np.asarray(pcd.cluster_dbscan(eps=0.13, min_points=22, print_progress=False))
    max_lbl = int(labels.max()) if len(labels) > 0 else -1
    if max_lbl < 0:
        return []

    beams = []
    for lbl in range(max_lbl + 1):
        pts = rem_xyz[labels == lbl]
        if len(pts) < 28:
            continue

        xy_bac = _rot2d(pts[:, :2], -dominant_angle)
        centroid = xy_bac.mean(axis=0)
        centered = xy_bac - centroid
        cov = (centered.T @ centered) / max(1, len(centered))
        _, eigvecs = np.linalg.eigh(cov)
        axis_bac = eigvecs[:, 1]
        # Snap beam direction to BAC X or Y if within 8 degrees
        ang = math.atan2(axis_bac[1], axis_bac[0])
        for k in range(-4, 5):
            target = k * (math.pi * 0.5)
            if abs((ang - target + math.pi) % (2 * math.pi) - math.pi) <= math.radians(8.0):
                axis_bac = np.array([math.cos(target), math.sin(target)], dtype=float)
                break
        norm_bac = np.array([-axis_bac[1], axis_bac[0]], dtype=float)

        u = centered @ axis_bac
        v = centered @ norm_bac
        u0, u1 = float(np.percentile(u, 2)), float(np.percentile(u, 98))
        v0, v1 = float(np.percentile(v, 3)), float(np.percentile(v, 97))
        z0, z1 = float(np.percentile(pts[:, 2], 3)), float(np.percentile(pts[:, 2], 97))

        length = u1 - u0
        width = v1 - v0
        depth = max(0.10, z1 - z0)

        if length < 1.20 or not (0.07 <= width <= 0.75) or not (0.08 <= depth <= 0.80):
            continue
        if length / max(width, 1e-6) < 2.6:
            continue

        # Verify linear continuity along beam length
        n_ubins = max(4, int(length / 0.25))
        iu = np.clip(((u - u0) / 0.25).astype(int), 0, n_ubins - 1)
        if len(np.unique(iu)) / float(n_ubins) < 0.55:
            continue

        v_mid = 0.5 * (v0 + v1)
        p_s_bac = centroid + axis_bac * u0 + norm_bac * v_mid
        p_e_bac = centroid + axis_bac * u1 + norm_bac * v_mid
        pts_w = _rot2d(np.vstack([p_s_bac, p_e_bac]), dominant_angle)

        b_idx = beam_id_offset + len(beams) + 1
        top_z = round(min(z1, ceiling_z) if z1 <= ceiling_z + 0.05 else z1, 3)
        beams.append({
            "id": f"BEAM_{level_id}_{len(beams)+1:02d}",
            "name": f"Structural Beam {b_idx:02d}",
            "level_id": level_id,
            "level_name": level_name,
            "start": [round(float(pts_w[0][0]), 3), round(float(pts_w[0][1]), 3), top_z],
            "end": [round(float(pts_w[1][0]), 3), round(float(pts_w[1][1]), 3), top_z],
            "width": round(width, 3),
            "depth": round(depth, 3),
            "length": round(length, 3),
            "top_z": top_z,
            "bottom_z": round(top_z - depth, 3),
            "justification": "top",
            "point_count": int(len(pts)),
        })

    return beams


def _segment_spaces(walls, x_min, x_max, y_min, y_max, floor_z, ceiling_z, level_id="Level_00", level_name="00_Ground_Floor", res=0.18):
    """Segments enclosed architectural rooms (IfcSpace) via 2D occupancy-grid flood fill."""
    if not walls:
        return []
    nx = max(10, int(math.ceil((x_max - x_min) / res)) + 4)
    ny = max(10, int(math.ceil((y_max - y_min) / res)) + 4)
    if nx * ny > 250000:
        return []

    grid = np.zeros((ny, nx), dtype=np.uint8)
    for w in walls:
        steps = max(2, int(math.ceil(w.length / (res * 0.5))))
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


def _compute_story_wall_recall(story_xyz, story_normals, walls, columns, floor_z, ceiling_z, tol=0.10):
    """Computes fraction of vertical wall/column scan points explained within `tol` meters of BIM geometry."""
    vmask = (
        (np.abs(story_normals[:, 2]) < 0.22)
        & (story_xyz[:, 2] >= floor_z + 0.35)
        & (story_xyz[:, 2] <= ceiling_z - 0.20)
    )
    pts = story_xyz[vmask, :2]
    if len(pts) == 0:
        return 0.0
    explained = np.zeros(len(pts), dtype=bool)
    for w in walls:
        rel = pts - w.start[None, :]
        u = rel @ w.direction
        perp = np.abs(rel @ w.normal)
        explained |= (u >= -0.05) & (u <= w.length + 0.05) & (perp <= w.thickness * 0.5 + tol)
    for col in columns:
        c = np.array(col["center"], dtype=float)
        r = 0.5 * max(col["width"], col["depth"]) + tol
        explained |= np.linalg.norm(pts - c[None, :], axis=1) <= r
    return round(float(np.mean(explained)), 4)


class SpatialBIMExtractor:
    def __init__(self, target_lod=300, voxel_size=0.05):
        self.target_lod = target_lod
        self.voxel_size = float(voxel_size)

    def extract_from_pointcloud(self, cloud_data, site_name="Site", navvis_index=None):
        """
        cloud_data: dict with 'xyz' (N, 3), optional 'normals' (N, 3), optional 'rgb' (N, 3)
        navvis_index: optional unified NavVis index dict (site_floors + 6-DoF/footprint poses)
        Returns a structured multi-story BIM manifest with Levels, Slabs, Ceilings, Walls,
        Structural Columns, Structural Beams, Doors, Windows, Spaces, and QA metrics.
        """
        xyz_raw = np.asarray(cloud_data["xyz"], dtype=float)
        nor_raw = cloud_data.get("normals")
        if nor_raw is not None:
            nor_raw = np.asarray(nor_raw, dtype=float)

        if len(xyz_raw) > 5000:
            if nor_raw is not None and len(nor_raw) == len(xyz_raw):
                xyz, normals = voxel_downsample(xyz_raw, self.voxel_size, normals=nor_raw)
            else:
                xyz = voxel_downsample(xyz_raw, self.voxel_size)
                normals = None
        else:
            xyz, normals = xyz_raw, nor_raw

        normals = ensure_oriented_normals(xyz, normals=normals, navvis_index=navvis_index)
        dominant_angle = estimate_dominant_axis_from_normals(normals)
        stories = detect_building_stories(xyz, normals=normals, navvis_index=navvis_index)

        z_vals = xyz[:, 2]
        z_min, z_max = float(np.min(z_vals)), float(np.max(z_vals))
        x_min, x_max = float(np.min(xyz[:, 0])), float(np.max(xyz[:, 0]))
        y_min, y_max = float(np.min(xyz[:, 1])), float(np.max(xyz[:, 1]))

        nv_pts = []
        if navvis_index and navvis_index.get("panos"):
            for p in navvis_index["panos"]:
                fp = p.get("footprint_pose") or p.get("global_pose")
                if fp and len(fp) >= 3:
                    nv_pts.append(fp)
        nv_pts = np.array(nv_pts, dtype=float) if nv_pts else np.empty((0, 3), dtype=float)

        levels = []
        slabs = []
        ceilings = []
        wall_dicts = []
        columns = []
        beams = []
        doors = []
        windows = []
        spaces = []
        qa_metrics = {}

        for st in stories:
            lvl_id = st["id"]
            lvl_name = st["name"]
            floor_z = st["floor_z"]
            ceiling_z = st["ceiling_z"]
            next_floor_z = st["next_floor_z"]
            levels.append({"id": lvl_id, "name": lvl_name, "elevation": floor_z})

            story_nv_xy = None
            if len(nv_pts) > 0:
                in_st = nv_pts[(nv_pts[:, 2] >= floor_z - 0.5) & (nv_pts[:, 2] <= ceiling_z + 0.5)]
                if len(in_st) > 0:
                    story_nv_xy = in_st[:, :2]

            # 1. Floor Slab polygons from upward-facing horizontal normals
            f_mask = (z_vals >= floor_z - 0.14) & (z_vals <= floor_z + 0.14) & (normals[:, 2] > 0.75)
            if np.count_nonzero(f_mask) < 30:
                f_mask = (z_vals >= floor_z - 0.14) & (z_vals <= floor_z + 0.14)
            floor_slice = xyz[f_mask]
            floor_polys = extract_horizontal_polygons_bac(
                floor_slice[:, :2], dominant_angle, cell_size=0.35, min_area_m2=8.0, navvis_xy_world=story_nv_xy
            )
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

            # 2. Ceiling polygons from downward-facing horizontal normals
            c_mask = (z_vals >= ceiling_z - 0.15) & (z_vals <= ceiling_z + 0.15) & (normals[:, 2] < -0.75)
            if np.count_nonzero(c_mask) < 30:
                c_mask = (z_vals >= ceiling_z - 0.15) & (z_vals <= ceiling_z + 0.15)
            ceil_slice = xyz[c_mask]
            ceil_polys = extract_horizontal_polygons_bac(
                ceil_slice[:, :2], dominant_angle, cell_size=0.35, min_area_m2=8.0, navvis_xy_world=story_nv_xy
            )
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

            # Slice points belonging to this story (floor to next floor plenum)
            st_mask = (z_vals >= floor_z - 0.05) & (z_vals <= next_floor_z + 0.05)
            st_xyz = xyz[st_mask]
            st_nor = normals[st_mask]

            # 3. 3D Planar Patch Wall Extraction + Opposing-Face Pairing
            walls = extract_planar_walls(
                st_xyz, st_nor,
                floor_z=floor_z,
                ceiling_z=ceiling_z,
                dominant_angle=dominant_angle,
                level_id=lvl_id,
                level_name=lvl_name,
                wall_id_offset=len(wall_dicts),
            )
            joins = mitre_wall_network(walls)

            for w in walls:
                j_s, j_e = joins.get(w.wall_id, (None, None))
                w_dict = w.to_dict(join_start=j_s, join_end=j_e)
                w_dict["level_id"] = lvl_id
                w_dict["level_name"] = lvl_name
                w_dict["surface_support"] = getattr(w, "surface_support", 1.0)
                w_dict["double_sided"] = getattr(w, "double_sided", True)
                w_dict["residuals"] = w.compute_point_residuals(st_xyz)
                wall_dicts.append(w_dict)

                for op in w.openings:
                    loc_2d = w.start + w.direction * op["offset"]
                    op_entry = {
                        "id": op["id"],
                        "name": op["name"],
                        "host": w.wall_id,
                        "level_id": lvl_id,
                        "level_name": lvl_name,
                        "type": op["type"],
                        "offset": op["offset"],
                        "width": op["width"],
                        "height": op["height"],
                        "sill_z": op["sill_z"],
                        "pos": [round(float(loc_2d[0]), 3), round(float(loc_2d[1]), 3), round(op["sill_z"], 3)],
                    }
                    if op["type"] == "Window":
                        windows.append(op_entry)
                    else:
                        doors.append(op_entry)

            # 4. PRIORITY: Structural Columns (IfcColumn)
            st_cols = extract_structural_columns(
                st_xyz, st_nor, walls,
                floor_z=floor_z,
                ceiling_z=ceiling_z,
                dominant_angle=dominant_angle,
                level_id=lvl_id,
                level_name=lvl_name,
                col_id_offset=len(columns),
            )
            columns.extend(st_cols)

            # 5. PRIORITY: Structural Beams (IfcBeam)
            st_beams = extract_structural_beams(
                st_xyz, st_nor, walls, st_cols,
                floor_z=floor_z,
                ceiling_z=ceiling_z,
                next_floor_z=next_floor_z,
                dominant_angle=dominant_angle,
                level_id=lvl_id,
                level_name=lvl_name,
                beam_id_offset=len(beams),
            )
            beams.extend(st_beams)

            # 6. Enclosed Room Segmentation
            if walls:
                wx_min = min(min(w.start[0], w.end[0]) for w in walls)
                wx_max = max(max(w.start[0], w.end[0]) for w in walls)
                wy_min = min(min(w.start[1], w.end[1]) for w in walls)
                wy_max = max(max(w.start[1], w.end[1]) for w in walls)
                spaces.extend(_segment_spaces(walls, wx_min, wx_max, wy_min, wy_max, floor_z, ceiling_z, level_id=lvl_id, level_name=lvl_name))

            # 7. Per-story QA recall
            recall = _compute_story_wall_recall(st_xyz, st_nor, walls, st_cols, floor_z, ceiling_z)
            qa_metrics[lvl_name] = {
                "floor_z": floor_z,
                "ceiling_z": ceiling_z,
                "walls": len(walls),
                "columns": len(st_cols),
                "beams": len(st_beams),
                "doors": sum(1 for d in doors if d["level_id"] == lvl_id),
                "windows": sum(1 for wi in windows if wi["level_id"] == lvl_id),
                "wall_cloud_recall_10cm": recall,
                "mean_surface_support": round(float(np.mean([getattr(w, "surface_support", 1.0) for w in walls])), 3) if walls else 0.0,
            }

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
            "columns": columns,
            "beams": beams,
            "doors": doors,
            "windows": windows,
            "spaces": spaces,
            "qa_metrics": qa_metrics,
            "plumbing_fixtures": [],
            "casework": [],
        }

        return manifest
