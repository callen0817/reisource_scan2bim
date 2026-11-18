# -*- coding: utf-8 -*-
"""
reisource_scan2bim — NavVis Multi-Dataset Unifier
Handles multiple NavVis VLX walks without altering raw filenames on disk.
Applies alignment transformations, microsecond epoch timestamp matching,
and emits a unified spatial pose graph matching merged point clouds.
"""

import os
import glob
import json
import xml.etree.ElementTree as ET
import numpy as np

class NavVisDatasetUnifier:
    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.datasets = []
        self.alignments = {}
        self.unified_poses = []

    def scan_datasets(self):
        """Discovers all child dataset walks and alignment metadata."""
        self.datasets = []
        self.alignments = {}

        # Look for alignment XMLs (NavVis Desktop format) and alignment.json (NavVis IVION web-v4 bundle format)
        align_files = glob.glob(os.path.join(self.project_root, "*alignment*.xml")) + \
                      glob.glob(os.path.join(self.project_root, "dataset_alignment.xml"))

        for af in align_files:
            self._parse_alignment_xml(af)

        for root, dirs, files in os.walk(self.project_root):
            if "alignment.json" in files:
                self._parse_alignment_json(os.path.join(root, "alignment.json"), os.path.basename(root))

        # Scan for dataset directories containing poses.csv or info/*-info.json (web-v4 bundle format)
        for root, dirs, files in os.walk(self.project_root):
            rel_dir = os.path.relpath(root, self.project_root)
            ds_id = os.path.basename(root) if rel_dir != "." else "root_dataset"

            if "poses.csv" in files:
                has_panos = os.path.isdir(os.path.join(root, "pano")) or any(f.endswith((".jpg", ".nvr")) for f in files)
                self.datasets.append({
                    "id": ds_id,
                    "path": root,
                    "rel_path": rel_dir,
                    "poses_csv": os.path.join(root, "poses.csv"),
                    "info_dir": None,
                    "has_panos": has_panos,
                    "transform": self.alignments.get(ds_id, np.identity(4))
                })
            elif "dataset.json" in files and os.path.isdir(os.path.join(root, "info")):
                info_dir = os.path.join(root, "info")
                info_files = sorted(glob.glob(os.path.join(info_dir, "*-info.json")))
                if info_files:
                    has_panos = os.path.isdir(os.path.join(root, "pano"))
                    self.datasets.append({
                        "id": ds_id,
                        "path": root,
                        "rel_path": rel_dir,
                        "poses_csv": None,
                        "info_dir": info_dir,
                        "info_files": info_files,
                        "has_panos": has_panos,
                        "transform": self.alignments.get(ds_id, np.identity(4))
                    })

        return self.datasets

    def _parse_alignment_json(self, json_path, default_ds_id):
        """Parses NavVis IVION web-v4 alignment.json 4x4 transform matrix."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name") or default_ds_id
            tf = data.get("site_transform") or data.get("transform")
            if isinstance(tf, dict) and "r11" in tf:
                mat = np.array([
                    [float(tf["r11"]), float(tf["r12"]), float(tf["r13"]), float(tf["tx"])],
                    [float(tf["r21"]), float(tf["r22"]), float(tf["r23"]), float(tf["ty"])],
                    [float(tf["r31"]), float(tf["r32"]), float(tf["r33"]), float(tf["tz"])],
                    [0.0, 0.0, 0.0, 1.0],
                ], dtype=float)
                self.alignments[name] = mat
                self.alignments[default_ds_id] = mat
        except Exception as e:
            print(f"[Warning] Failed parsing alignment JSON {json_path}: {e}")

    def _parse_alignment_xml(self, xml_path):
        """Parses 4x4 rigid transformation matrices for each dataset walk."""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for ds_elem in root.iter("dataset"):
                name = ds_elem.get("name") or ds_elem.get("id") or os.path.basename(ds_elem.get("path", ""))
                matrix_elem = ds_elem.find("transformation") or ds_elem.find("matrix")
                if matrix_elem is not None and matrix_elem.text:
                    vals = [float(v) for v in matrix_elem.text.strip().split()]
                    if len(vals) == 16:
                        mat = np.array(vals).reshape((4, 4))
                        self.alignments[name] = mat
        except Exception as e:
            print(f"[Warning] Failed parsing alignment XML {xml_path}: {e}")

    def load_and_unify_poses(self):
        """Merges all poses into a unified global coordinate system without file renaming."""
        self.scan_datasets()
        self.unified_poses = []

        for ds in self.datasets:
            ds_id = ds["id"]
            trans = ds["transform"]
            csv_path = ds.get("poses_csv")
            q_align = _rotation_matrix_to_quaternion(trans[:3, :3])

            if csv_path and os.path.isfile(csv_path):
                with open(csv_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]

                if not lines:
                    continue

                data_rows = lines[1:]
                for row_idx, line in enumerate(data_rows):
                    parts = line.split(";") if ";" in line else line.split(",")
                    if len(parts) < 8:
                        continue

                    try:
                        ts = float(parts[0])
                        x_loc, y_loc, z_loc = float(parts[1]), float(parts[2]), float(parts[3])
                        qx_loc, qy_loc, qz_loc, qw_loc = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                    except ValueError:
                        continue

                    img_name = f"pano-{row_idx+1:06d}.jpg"
                    rel_img_path = os.path.join(ds["rel_path"], "pano", img_name)

                    local_pt = np.array([x_loc, y_loc, z_loc, 1.0])
                    global_pt = trans @ local_pt
                    q_global = _quaternion_multiply(q_align, [qw_loc, qx_loc, qy_loc, qz_loc])

                    self.unified_poses.append({
                        "global_id": f"{ds_id}__{img_name}",
                        "dataset_source": ds_id,
                        "timestamp": ts,
                        "local_pose": [x_loc, y_loc, z_loc],
                        "global_pose": [float(global_pt[0]), float(global_pt[1]), float(global_pt[2])],
                        "quaternion": [float(v) for v in q_global],
                        "relative_image_path": rel_img_path
                    })

            elif ds.get("info_files"):
                for info_file in ds["info_files"]:
                    try:
                        with open(info_file, "r", encoding="utf-8") as f:
                            info = json.load(f)
                    except Exception:
                        continue

                    cam = info.get("cam_head") or info.get("footprint") or info.get("cam0")
                    if not isinstance(cam, dict) or "position" not in cam or "quaternion" not in cam:
                        continue

                    pos = cam["position"]
                    quat = cam["quaternion"]  # NavVis info.json quaternion is [w, x, y, z]
                    if len(pos) < 3 or len(quat) < 4:
                        continue

                    x_loc, y_loc, z_loc = float(pos[0]), float(pos[1]), float(pos[2])
                    qw_loc, qx_loc, qy_loc, qz_loc = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
                    ts = float(info.get("timestamp", 0.0))

                    stem = os.path.basename(info_file).replace("-info.json", "")
                    img_name = f"{stem}.nvr"
                    rel_img_path = os.path.join(ds["rel_path"], "pano", img_name)

                    local_pt = np.array([x_loc, y_loc, z_loc, 1.0])
                    global_pt = trans @ local_pt
                    q_global = _quaternion_multiply(q_align, [qw_loc, qx_loc, qy_loc, qz_loc])

                    pose_entry = {
                        "global_id": f"{ds_id}__{img_name}",
                        "dataset_source": ds_id,
                        "timestamp": ts,
                        "local_pose": [x_loc, y_loc, z_loc],
                        "global_pose": [float(global_pt[0]), float(global_pt[1]), float(global_pt[2])],
                        "quaternion": [float(v) for v in q_global],
                        "relative_image_path": rel_img_path
                    }
                    fp = info.get("footprint")
                    if isinstance(fp, dict) and "position" in fp and len(fp["position"]) >= 3:
                        fp_local = np.array([float(fp["position"][0]), float(fp["position"][1]), float(fp["position"][2]), 1.0])
                        fp_global = trans @ fp_local
                        pose_entry["footprint_pose"] = [float(fp_global[0]), float(fp_global[1]), float(fp_global[2])]

                    self.unified_poses.append(pose_entry)

        return self.unified_poses

    def _parse_site_model(self):
        """Extracts floor Z-intervals from NavVis bundle site_model.json if present."""
        floors = []
        for root, dirs, files in os.walk(self.project_root):
            if "site_model.json" in files:
                try:
                    with open(os.path.join(root, "site_model.json"), "r", encoding="utf-8") as f:
                        sm = json.load(f)
                    for bldg in sm if isinstance(sm, list) else [sm]:
                        for child in bldg.get("children", []):
                            if child.get("type") == "FLOOR":
                                floors.append({
                                    "name": str(child.get("name") or len(floors)),
                                    "z_min": child.get("scs_z_min"),
                                    "z_max": child.get("scs_z_max"),
                                })
                except Exception:
                    pass
        return floors

    def export_unified_index(self, out_json_path):
        """Exports the master pose index for downstream Vision & BIM processing."""
        poses = self.load_and_unify_poses()
        data = {
            "project_root": self.project_root,
            "datasets_count": len(self.datasets),
            "datasets": [d["id"] for d in self.datasets],
            "total_panoramas": len(poses),
            "site_floors": self._parse_site_model(),
            "panos": poses
        }
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data


def _rotation_matrix_to_quaternion(R):
    """Converts a 3x3 rotation matrix to unit quaternion [w, x, y, z]."""
    tr = float(np.trace(R))
    if tr > 0.0:
        s = 2.0 * np.sqrt(tr + 1.0)
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z], dtype=float)
    n = float(np.linalg.norm(q))
    return q / n if n > 1e-12 else np.array([1.0, 0.0, 0.0, 0.0])


def _quaternion_multiply(q1, q2):
    """Hamilton product of two [w, x, y, z] quaternions."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    q = np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], dtype=float)
    n = float(np.linalg.norm(q))
    return q / n if n > 1e-12 else np.array([1.0, 0.0, 0.0, 0.0])
