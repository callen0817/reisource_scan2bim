# -*- coding: utf-8 -*-
"""
reisource_scan2bim — End-to-End Scan & Bundle Ingestion Pipeline
Ingests:
- Raw LiDAR point clouds (.e57, .las, .laz, .ply, .npz)
- NavVis VLX / IVION .bundle archives (ZIP-based or extracted directory with dataset alignment XMLs,
  poses.csv, and 360° panoramas)

Produces:
1. Structured BIM Manifest JSON (<out_dir>/<project_slug>_bim_manifest.json)
2. Unified NavVis Pose Index JSON (<out_dir>/<project_slug>_navvis_index.json) if bundle provided
3. Certified IFC4 Model (<out_dir>/<project_slug>_BIM.ifc)
4. Self-contained Autodesk Revit 2024–2027 Python Generator (<out_dir>/build_<project_slug>_revit.py)
"""

import argparse
import glob
import json
import os
import sys
import tempfile
import time
import zipfile
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.bim_exporter import BIMModelExporter
from core.navvis_unifier import NavVisDatasetUnifier
from core.spatial_extractor import SpatialBIMExtractor


def find_e57_in_directory(search_dir, hint="2525"):
    """Finds a matching .e57/.las/.laz/.ply file in search_dir."""
    if os.path.isfile(search_dir):
        return search_dir
    if not os.path.isdir(search_dir):
        return None
    exts = ("*.e57", "*.E57", "*.las", "*.laz", "*.ply", "*.npz")
    candidates = []
    for ext in exts:
        candidates.extend(glob.glob(os.path.join(search_dir, ext)))
    if not candidates:
        return None
    hint_lower = hint.lower()
    for c in candidates:
        if hint_lower in os.path.basename(c).lower() or "belmont" in os.path.basename(c).lower():
            return c
    return candidates[0]


def load_point_cloud(cloud_path, max_points=5_000_000):
    """
    Loads 3D point cloud coordinates (and optional RGB) from .e57, .las/.laz, .ply, or .npz.
    Automatically subsamples very large clouds to max_points for fast segmentation.
    """
    ext = os.path.splitext(cloud_path)[1].lower()
    xyz = None
    rgb = None

    if ext == ".npz":
        data = np.load(cloud_path)
        key = "xyz" if "xyz" in data else ("points" if "points" in data else list(data.keys())[0])
        xyz = np.asarray(data[key][:, :3], dtype=float)
        if "rgb" in data:
            rgb = np.asarray(data["rgb"], dtype=float)

    elif ext == ".e57":
        # Try pye57 first, then open3d
        try:
            import pye57
            e57 = pye57.E57(cloud_path)
            chunks = []
            n_scans = e57.scan_count
            stride = max(1, n_scans // 20)
            for idx in range(0, n_scans, stride):
                header = e57.get_header(idx)
                n_pts = int(header.point_count)
                if n_pts > 20_000_000:
                    # Stream large scans in 5M-point chunks to avoid multi-GB RAM spikes
                    chunk_size = 5_000_000
                    pt_step = max(1, n_pts // max_points)
                    data, bufs = e57.make_buffers(["cartesianX", "cartesianY", "cartesianZ"], chunk_size)
                    reader = header.points.reader(bufs)
                    scan_chunks = []
                    try:
                        while True:
                            got = reader.read()
                            if got == 0:
                                break
                            pts_chunk = np.column_stack([
                                data["cartesianX"][:got:pt_step],
                                data["cartesianY"][:got:pt_step],
                                data["cartesianZ"][:got:pt_step],
                            ])
                            scan_chunks.append(pts_chunk)
                    finally:
                        reader.close()
                    pts = np.vstack(scan_chunks)
                    if header.has_pose():
                        pts = e57.to_global(pts, header.rotation, header.translation)
                    chunks.append(pts)
                else:
                    raw = e57.read_scan(idx, intensity=False, colors=False, ignore_missing_fields=True)
                    pts = np.column_stack([raw["cartesianX"], raw["cartesianY"], raw["cartesianZ"]])
                    chunks.append(pts)
            xyz = np.vstack(chunks)
        except ImportError:
            try:
                import open3d as o3d
                pcd = o3d.io.read_point_cloud(cloud_path)
                xyz = np.asarray(pcd.points, dtype=float)
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot read .e57 file '{cloud_path}'. Install pye57 (`pip install pye57`) or open3d (`pip install open3d`). Error: {exc}"
                ) from exc

    elif ext in (".las", ".laz"):
        import laspy
        las = laspy.read(cloud_path)
        xyz = np.column_stack([las.x, las.y, las.z]).astype(float)

    elif ext == ".ply":
        import open3d as o3d
        pcd = o3d.io.read_point_cloud(cloud_path)
        xyz = np.asarray(pcd.points, dtype=float)

    else:
        raise ValueError(f"Unsupported point cloud extension: {ext}")

    # Filter NaNs/Infs
    valid = np.isfinite(xyz).all(axis=1)
    xyz = xyz[valid]
    if len(xyz) > max_points:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(xyz), size=max_points, replace=False)
        xyz = xyz[idx]

    return {"xyz": xyz, "rgb": rgb}


def ingest_navvis_bundle(bundle_path, out_index_json):
    """
    Ingests either an extracted NavVis directory or a .bundle (ZIP archive) file,
    unifies all walk trajectories and alignment matrices, and writes out_index_json.
    """
    if not bundle_path or not os.path.exists(bundle_path):
        return None

    if os.path.isdir(bundle_path):
        unifier = NavVisDatasetUnifier(bundle_path)
        return unifier.export_unified_index(out_index_json)

    if zipfile.is_zipfile(bundle_path):
        with tempfile.TemporaryDirectory(prefix="navvis_bundle_") as tmpdir:
            with zipfile.ZipFile(bundle_path, "r") as zf:
                # Extract only alignment XMLs and poses.csv metadata for speed
                members = [
                    m for m in zf.namelist()
                    if m.endswith(".xml") or m.endswith(".csv") or m.endswith(".json")
                ]
                zf.extractall(tmpdir, members=members)
            unifier = NavVisDatasetUnifier(tmpdir)
            return unifier.export_unified_index(out_index_json)

    print(f"[Info] Bundle '{bundle_path}' is not a directory or standard zip archive; skipping pose index.")
    return None


def run_scan_pipeline(e57_path, bundle_path=None, project_name="2525_Belmont", out_dir=None, voxel_size=0.05):
    t0 = time.time()
    if out_dir is None:
        out_dir = os.path.join(REPO_ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    slug = project_name.lower().replace(" ", "_")
    resolved_cloud = find_e57_in_directory(e57_path, hint=project_name)
    if not resolved_cloud or not os.path.isfile(resolved_cloud):
        raise FileNotFoundError(
            f"Could not find point cloud at '{e57_path}'. Pass the exact .e57 path or directory containing it."
        )

    print("================================================================================")
    print(f"  reisource_scan2bim — Automated Scan-to-BIM Pipeline: {project_name}")
    print("================================================================================")
    print(f"[1/4] Loading point cloud: {resolved_cloud}")
    cloud_data = load_point_cloud(resolved_cloud)
    print(f"      Loaded {len(cloud_data['xyz']):,} valid 3D points.")

    print(f"[2/4] Running SpatialBIMExtractor (voxel_size={voxel_size}m)...")
    extractor = SpatialBIMExtractor(target_lod=300, voxel_size=voxel_size)
    manifest = extractor.extract_from_pointcloud(cloud_data, site_name=project_name)
    manifest["source_point_cloud"] = os.path.abspath(resolved_cloud)

    if bundle_path and os.path.exists(bundle_path):
        print(f"[2b/4] Unifying NavVis Bundle: {bundle_path}")
        index_path = os.path.join(out_dir, f"{slug}_navvis_index.json")
        navvis_index = ingest_navvis_bundle(bundle_path, index_path)
        if navvis_index:
            manifest["navvis_bundle"] = {
                "bundle_path": os.path.abspath(bundle_path),
                "datasets_count": navvis_index["datasets_count"],
                "total_panoramas": navvis_index["total_panoramas"],
                "index_json": index_path,
            }
            print(
                f"      Unified {navvis_index['total_panoramas']} panoramas across {navvis_index['datasets_count']} walk(s)."
            )

    manifest_path = os.path.join(out_dir, f"{slug}_bim_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[3/4] Saved BIM Manifest: {manifest_path}")
    print(
        f"      Extracted: {len(manifest['levels'])} levels | {len(manifest['walls'])} mitred walls | "
        f"{len(manifest['doors'])} doors | {len(manifest.get('spaces', []))} rooms"
    )

    revit_script_path = os.path.join(out_dir, f"build_{slug}_revit.py")
    BIMModelExporter(manifest).export_revit_script(revit_script_path)
    print(f"      Saved Native Revit 2024-2027 Generator: {revit_script_path}")

    ifc_path = os.path.join(out_dir, f"{slug}_BIM.ifc")
    try:
        from scripts.export_ifc import export_ifc
        print(f"[4/4] Exporting Native IFC4 Model: {ifc_path}")
        export_ifc(manifest_path=manifest_path, out_ifc_path=ifc_path)
    except ImportError as exc:
        print(f"[4/4] Skipping live .ifc write (ifcopenshell not installed: {exc}).")

    elapsed = time.time() - t0
    print("================================================================================")
    print(f"  Completed {project_name} Scan-to-BIM in {elapsed:.2f}s")
    print("================================================================================")
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description="Run end-to-end Scan2BIM on an E57 cloud and optional NavVis .bundle.")
    parser.add_argument(
        "--e57",
        default=r"C:\Users\ChristopherAllen\Downloads",
        help="Path to .e57/.las/.ply file or directory containing it",
    )
    parser.add_argument(
        "--bundle",
        default=r"C:\Users\ChristopherAllen\Downloads\261113_2525_Belmont_2026-11-18.bundle",
        help="Optional path to NavVis .bundle file or extracted folder",
    )
    parser.add_argument("--project", default="2525_Belmont", help="Project name")
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "data"), help="Output directory")
    parser.add_argument("--voxel-size", type=float, default=0.05, help="Voxel decimation grid size in meters")
    args = parser.parse_args()

    run_scan_pipeline(
        e57_path=args.e57,
        bundle_path=args.bundle,
        project_name=args.project,
        out_dir=args.out_dir,
        voxel_size=args.voxel_size,
    )


if __name__ == "__main__":
    main()
