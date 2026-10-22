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

        # Look for alignment XMLs (NavVis Desktop / IVION format)
        align_files = glob.glob(os.path.join(self.project_root, "*alignment*.xml")) + \
                      glob.glob(os.path.join(self.project_root, "dataset_alignment.xml"))
        
        for af in align_files:
            self._parse_alignment_xml(af)

        # Scan for dataset directories containing poses.csv
        for root, dirs, files in os.walk(self.project_root):
            if "poses.csv" in files:
                rel_dir = os.path.relpath(root, self.project_root)
                # Avoid root itself if poses.csv is at root
                ds_id = os.path.basename(root) if rel_dir != "." else "root_dataset"
                has_panos = os.path.isdir(os.path.join(root, "pano")) or any(f.endswith(".jpg") for f in files)
                
                self.datasets.append({
                    "id": ds_id,
                    "path": root,
                    "rel_path": rel_dir,
                    "poses_csv": os.path.join(root, "poses.csv"),
                    "has_panos": has_panos,
                    "transform": self.alignments.get(ds_id, np.identity(4))
                })

        return self.datasets

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
            csv_path = ds["poses_csv"]

            with open(csv_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]

            if not lines:
                continue

            # Check header
            header = lines[0].split(";") if ";" in lines[0] else lines[0].split(",")
            data_rows = lines[1:]

            for row_idx, line in enumerate(data_rows):
                parts = line.split(";") if ";" in line else line.split(",")
                if len(parts) < 8:
                    continue

                try:
                    # Typical NavVis format: timestamp, x, y, z, qx, qy, qz, qw (or with image_name)
                    ts = float(parts[0])
                    x_loc, y_loc, z_loc = float(parts[1]), float(parts[2]), float(parts[3])
                    qx_loc, qy_loc, qz_loc, qw_loc = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                except ValueError:
                    continue

                # Relative image path preservation
                # Usually pano_index corresponds to row_idx + 1: pano-000001.jpg
                img_name = f"pano-{row_idx+1:06d}.jpg"
                rel_img_path = os.path.join(ds["rel_path"], "pano", img_name)

                # Apply 4x4 rigid transformation: P_global = T * P_local
                local_pt = np.array([x_loc, y_loc, z_loc, 1.0])
                global_pt = trans @ local_pt

                self.unified_poses.append({
                    "global_id": f"{ds_id}__{img_name}",
                    "dataset_source": ds_id,
                    "timestamp": ts,
                    "local_pose": [x_loc, y_loc, z_loc],
                    "global_pose": [float(global_pt[0]), float(global_pt[1]), float(global_pt[2])],
                    "quaternion": [qw_loc, qx_loc, qy_loc, qz_loc],
                    "relative_image_path": rel_img_path
                })

        return self.unified_poses

    def export_unified_index(self, out_json_path):
        """Exports the master pose index for downstream Vision & BIM processing."""
        poses = self.load_and_unify_poses()
        data = {
            "project_root": self.project_root,
            "datasets_count": len(self.datasets),
            "datasets": [d["id"] for d in self.datasets],
            "total_panoramas": len(poses),
            "panos": poses
        }
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data
