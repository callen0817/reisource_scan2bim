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


def load_point_cloud(cloud_path, max_points=6_000_000, voxel_size=0.04):
    """
    Loads 3D point cloud coordinates and pre-oriented surface normals (if present)
    from .e57, .las/.laz, .ply, or .npz.
    For multi-hundred-million-point E57 scans, streams chunks via libe57 and preserves
    scanner-oriented nor:normalX/Y/Z vectors without multi-GB RAM spikes.
    """
    ext = os.path.splitext(cloud_path)[1].lower()
    xyz = None
    normals = None
    rgb = None

    if ext == ".npz":
        data = np.load(cloud_path)
        key = "xyz" if "xyz" in data else ("points" if "points" in data else list(data.keys())[0])
        xyz = np.asarray(data[key][:, :3], dtype=float)
        if "normals" in data:
            normals = np.asarray(data["normals"][:, :3], dtype=float)
        if "rgb" in data:
            rgb = np.asarray(data["rgb"], dtype=float)

    elif ext == ".e57":
        try:
            import pye57
            e57 = pye57.E57(cloud_path)
            chunks = []
            norm_chunks = []
            n_scans = e57.scan_count
            stride = max(1, n_scans // 20)
            for idx in range(0, n_scans, stride):
                header = e57.get_header(idx)
                n_pts = int(header.point_count)
                fields = set(header.point_fields)
                has_normals = all(f in fields for f in ("nor:normalX", "nor:normalY", "nor:normalZ"))

                if n_pts > 5_000_000 or has_normals:
                    chunk_size = min(n_pts, 5_000_000)
                    pt_step = max(1, n_pts // max_points)
                    bx = np.zeros(chunk_size, dtype=np.float64)
                    by = np.zeros(chunk_size, dtype=np.float64)
                    bz = np.zeros(chunk_size, dtype=np.float64)
                    vbuf = pye57.libe57.VectorSourceDestBuffer()
                    for fname, arr in (("cartesianX", bx), ("cartesianY", by), ("cartesianZ", bz)):
                        vbuf.append(pye57.libe57.SourceDestBuffer(e57.image_file, fname, arr, chunk_size, True, True))
                    if has_normals:
                        bnx = np.zeros(chunk_size, dtype=np.float64)
                        bny = np.zeros(chunk_size, dtype=np.float64)
                        bnz = np.zeros(chunk_size, dtype=np.float64)
                        for fname, arr in (("nor:normalX", bnx), ("nor:normalY", bny), ("nor:normalZ", bnz)):
                            vbuf.append(pye57.libe57.SourceDestBuffer(e57.image_file, fname, arr, chunk_size, True, True))

                    reader = header.points.reader(vbuf)
                    scan_pts = []
                    scan_nors = []
                    try:
                        while True:
                            got = reader.read()
                            if got == 0:
                                break
                            scan_pts.append(np.column_stack([bx[:got:pt_step], by[:got:pt_step], bz[:got:pt_step]]))
                            if has_normals:
                                scan_nors.append(np.column_stack([bnx[:got:pt_step], bny[:got:pt_step], bnz[:got:pt_step]]))
                    finally:
                        reader.close()

                    pts = np.vstack(scan_pts)
                    if header.has_pose():
                        pts = e57.to_global(pts, header.rotation, header.translation)
                    chunks.append(pts)
                    if has_normals and scan_nors:
                        nors = np.vstack(scan_nors)
                        if header.has_pose():
                            nors = e57.to_global(nors, header.rotation, np.zeros(3))
                        norm_chunks.append(nors)
                else:
                    raw = e57.read_scan(idx, intensity=False, colors=False, ignore_missing_fields=True)
                    pts = np.column_stack([raw["cartesianX"], raw["cartesianY"], raw["cartesianZ"]])
                    chunks.append(pts)
            xyz = np.vstack(chunks)
            if norm_chunks and len(norm_chunks) == len(chunks):
                normals = np.vstack(norm_chunks)
        except ImportError:
            try:
                import open3d as o3d
                pcd = o3d.io.read_point_cloud(cloud_path)
                xyz = np.asarray(pcd.points, dtype=float)
                if pcd.has_normals():
                    normals = np.asarray(pcd.normals, dtype=float)
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
        if pcd.has_normals():
            normals = np.asarray(pcd.normals, dtype=float)

    else:
        raise ValueError(f"Unsupported point cloud extension: {ext}")

    # Filter NaNs/Infs
    valid = np.isfinite(xyz).all(axis=1)
    if normals is not None and len(normals) == len(xyz):
        valid &= np.isfinite(normals).all(axis=1)
        normals = normals[valid]
    else:
        normals = None
    xyz = xyz[valid]

    if len(xyz) > max_points:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(xyz), size=max_points, replace=False)
        xyz = xyz[idx]
        if normals is not None:
            normals = normals[idx]

    return {"xyz": xyz, "normals": normals, "rgb": rgb}


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

    navvis_index = None
    index_path = None
    if bundle_path and os.path.exists(bundle_path):
        print(f"[2/4] Unifying NavVis Bundle: {bundle_path}")
        index_path = os.path.join(out_dir, f"{slug}_navvis_index.json")
        navvis_index = ingest_navvis_bundle(bundle_path, index_path)
        if navvis_index:
            print(
                f"      Unified {navvis_index['total_panoramas']} panoramas across {navvis_index['datasets_count']} walk(s)."
            )

    print(f"[2b/4] Running SpatialBIMExtractor (voxel_size={voxel_size}m)...")
    extractor = SpatialBIMExtractor(target_lod=300, voxel_size=voxel_size)
    manifest = extractor.extract_from_pointcloud(cloud_data, site_name=project_name, navvis_index=navvis_index)
    manifest["source_point_cloud"] = os.path.abspath(resolved_cloud)

    if navvis_index:
        manifest["navvis_bundle"] = {
            "bundle_path": os.path.abspath(bundle_path),
            "datasets_count": navvis_index["datasets_count"],
            "total_panoramas": navvis_index["total_panoramas"],
            "index_json": index_path,
        }

    manifest_path = os.path.join(out_dir, f"{slug}_bim_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[3/4] Saved BIM Manifest: {manifest_path}")
    print(
        f"      Extracted: {len(manifest['levels'])} levels | {len(manifest['walls'])} walls | "
        f"{len(manifest.get('columns', []))} columns | {len(manifest.get('beams', []))} beams | "
        f"{len(manifest['doors'])} doors | {len(manifest.get('windows', []))} windows | {len(manifest.get('spaces', []))} rooms"
    )
    for lname, qm in manifest.get("qa_metrics", {}).items():
        print(
            f"      QA [{lname}]: Z=[{qm['floor_z']:.2f}, {qm['ceiling_z']:.2f}]m | "
            f"W:{qm['walls']} C:{qm['columns']} B:{qm['beams']} | Recall@10cm={qm['wall_cloud_recall_10cm']*100:.1f}%"
        )

    try:
        from core.qa_visualizer import render_level_qa_overlays
        qa_dir = os.path.join(out_dir, "qa")
        qa_imgs = render_level_qa_overlays(cloud_data, manifest, qa_dir, project_slug=slug)
        if qa_imgs:
            print(f"      Saved {len(qa_imgs)} Per-Level QA Overlay PNG(s) in: {qa_dir}")
    except Exception as exc:
        print(f"      [Info] QA overlay rendering skipped: {exc}")

    revit_script_path = os.path.join(out_dir, f"build_{slug}_revit.py")
    BIMModelExporter(manifest).export_revit_script(revit_script_path)
    print(f"      Saved Native Revit 2024-2027 Generator: {revit_script_path}")

    ifc_path = os.path.join(out_dir, f"{slug}_BIM.ifc")
    try:
        from scripts.export_ifc import export_ifc
        print(f"[4/4] Exporting Native Editable IFC4 Model: {ifc_path}")
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
