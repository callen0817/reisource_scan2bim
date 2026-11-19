# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Per-Level Point-Cloud-to-BIM Visual QA Overlay Generator
Renders crisp 2D orthographic PNG overlays comparing the raw E57 wall-slice points
against extracted BIM Walls, Slabs, Structural Columns, Structural Beams, Doors, and Windows.
"""

import math
import os
import cv2
import numpy as np


def render_level_qa_overlays(cloud_data, manifest, out_dir, project_slug="project", img_size=1600):
    """
    Generates one 2D orthographic QA PNG per building story in `out_dir`.
    Returns a list of saved PNG file paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    xyz = np.asarray(cloud_data["xyz"], dtype=float)
    normals = cloud_data.get("normals")
    if normals is not None:
        normals = np.asarray(normals, dtype=float)

    qa_metrics = manifest.get("qa_metrics", {})
    saved_paths = []

    for lvl in manifest.get("levels", []):
        lvl_id = lvl["id"]
        lvl_name = lvl["name"]
        if lvl_name not in qa_metrics:
            continue

        qm = qa_metrics[lvl_name]
        floor_z = float(qm["floor_z"])
        ceiling_z = float(qm["ceiling_z"])

        # Collect wall-slice points for this story
        mask = (xyz[:, 2] >= floor_z + 0.35) & (xyz[:, 2] <= ceiling_z - 0.15)
        if normals is not None and len(normals) == len(xyz):
            mask &= np.abs(normals[:, 2]) < 0.30
        pts = xyz[mask, :2]

        st_walls = [w for w in manifest.get("walls", []) if w.get("level_id") == lvl_id]
        st_cols = [c for c in manifest.get("columns", []) if c.get("level_id") == lvl_id]
        st_beams = [b for b in manifest.get("beams", []) if b.get("level_id") == lvl_id]
        st_slabs = [s for s in manifest.get("slabs", []) if s.get("level_id") == lvl_id]
        st_doors = [d for d in manifest.get("doors", []) if d.get("level_id") == lvl_id]
        st_wins = [w for w in manifest.get("windows", []) if w.get("level_id") == lvl_id]

        if len(pts) < 20 and not st_walls:
            continue

        # Determine plot bounds (1st–99th percentile of points + BIM elements)
        all_xy = [pts] if len(pts) > 0 else []
        for w in st_walls:
            p1, p2 = w.get("start", w.get("p1")), w.get("end", w.get("p2"))
            all_xy.append(np.array([p1, p2], dtype=float))
        for c in st_cols:
            all_xy.append(np.array([c["center"]], dtype=float))
        merged = np.vstack(all_xy)
        x_min, x_max = float(np.percentile(merged[:, 0], 0.5)) - 1.5, float(np.percentile(merged[:, 0], 99.5)) + 1.5
        y_min, y_max = float(np.percentile(merged[:, 1], 0.5)) - 1.5, float(np.percentile(merged[:, 1], 99.5)) + 1.5

        span = max(x_max - x_min, y_max - y_min, 1.0)
        pad = 70
        draw_area = img_size - 2 * pad
        scale = draw_area / span

        def to_px(x, y):
            px = int(round(pad + (x - x_min) * scale))
            py = int(round(img_size - pad - (y - y_min) * scale))
            return px, py

        # White canvas
        canvas = np.full((img_size, img_size, 3), 255, dtype=np.uint8)

        # 1. Draw Slab polygons (soft green tint outline)
        for s in st_slabs:
            poly = s.get("polygon") or []
            if len(poly) >= 3:
                arr = np.array([to_px(p[0], p[1]) for p in poly], dtype=np.int32)
                cv2.polylines(canvas, [arr], isClosed=True, color=(160, 210, 160), thickness=2, lineType=cv2.LINE_AA)

        # 2. Draw raw E57 wall-slice points (light/mid gray)
        if len(pts) > 0:
            if len(pts) > 250_000:
                rng = np.random.default_rng(42)
                pts = pts[rng.choice(len(pts), 250_000, replace=False)]
            pxs = np.clip(np.round(pad + (pts[:, 0] - x_min) * scale).astype(np.int32), 0, img_size - 1)
            pys = np.clip(np.round(img_size - pad - (pts[:, 1] - y_min) * scale).astype(np.int32), 0, img_size - 1)
            canvas[pys, pxs] = (155, 155, 155)

        # 3. Draw Structural Beams (purple lines)
        for b in st_beams:
            p1 = to_px(b["start"][0], b["start"][1])
            p2 = to_px(b["end"][0], b["end"][1])
            bw = max(2, int(round(b["width"] * scale)))
            cv2.line(canvas, p1, p2, color=(180, 60, 180), thickness=bw, lineType=cv2.LINE_AA)

        # 4. Draw BIM Walls (bold blue)
        for w in st_walls:
            p1 = w.get("start", w.get("p1"))
            p2 = w.get("end", w.get("p2"))
            thk_px = max(2, int(round(float(w.get("thickness", 0.15)) * scale)))
            cv2.line(canvas, to_px(p1[0], p1[1]), to_px(p2[0], p2[1]), color=(210, 80, 20), thickness=thk_px, lineType=cv2.LINE_AA)

        # 5. Draw Doors (orange) & Windows (cyan)
        for d in st_doors:
            pos = d.get("pos")
            if pos:
                cv2.circle(canvas, to_px(pos[0], pos[1]), max(4, int(round(0.35 * scale))), (0, 140, 255), -1, lineType=cv2.LINE_AA)
        for wi in st_wins:
            pos = wi.get("pos")
            if pos:
                cv2.circle(canvas, to_px(pos[0], pos[1]), max(4, int(round(0.30 * scale))), (230, 200, 0), -1, lineType=cv2.LINE_AA)

        # 6. Draw Structural Columns (solid red)
        for c in st_cols:
            cx, cy = c["center"]
            if c.get("shape") == "circular":
                r_px = max(4, int(round(c.get("radius", 0.25) * scale)))
                cv2.circle(canvas, to_px(cx, cy), r_px, (20, 20, 220), -1, lineType=cv2.LINE_AA)
            else:
                rad = math.radians(c.get("rotation_deg", 0.0))
                hw, hd = 0.5 * c.get("width", 0.4), 0.5 * c.get("depth", 0.4)
                corners = np.array([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]], dtype=float)
                cs, sn = math.cos(rad), math.sin(rad)
                rot = np.column_stack([corners[:, 0] * cs - corners[:, 1] * sn + cx, corners[:, 0] * sn + corners[:, 1] * cs + cy])
                arr = np.array([to_px(p[0], p[1]) for p in rot], dtype=np.int32)
                cv2.fillPoly(canvas, [arr], color=(20, 20, 220), lineType=cv2.LINE_AA)

        # Header & Legend
        title = (
            f"{project_slug} | {lvl_name} (Z={floor_z:.2f}..{ceiling_z:.2f}m) | "
            f"Walls:{qm['walls']} Cols:{qm['columns']} Beams:{qm['beams']} Doors:{qm['doors']} Wins:{qm['windows']} | "
            f"Recall@10cm:{qm['wall_cloud_recall_10cm']*100:.1f}%"
        )
        cv2.putText(canvas, title, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 20, 20), 2, cv2.LINE_AA)
        legend = "Gray=E57 Cloud | Blue=Walls | Red=Columns | Purple=Beams | Green=Slab | Orange=Doors | Cyan=Windows"
        cv2.putText(canvas, legend, (20, img_size - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 60, 60), 1, cv2.LINE_AA)

        safe_lvl = lvl_name.replace(" ", "_").replace("/", "_")
        out_path = os.path.join(out_dir, f"{project_slug}_{safe_lvl}_qa.png")
        cv2.imwrite(out_path, canvas)
        saved_paths.append(out_path)

    return saved_paths
