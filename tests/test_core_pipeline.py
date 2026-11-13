# -*- coding: utf-8 -*-
"""
Unit & integration tests for reisource_scan2bim core modules.
"""

import math
import os
import sys
import tempfile
import time
import unittest

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.bim_exporter import BIMModelExporter
from core.ifc_classification import get_classification
from core.navvis_fusion import NavVisPanoPose, TriModalFusionEngine
from core.navvis_unifier import _quaternion_multiply, _rotation_matrix_to_quaternion
from core.runs_engine import LinearRun, generate_fittings
from core.spatial_extractor import SpatialBIMExtractor
from core.walls_engine import AnalyticalWall, mitre_wall_network


def _sample_wall_box(p1, p2, base_z, height, thickness, density=400, door_gap=None, seed=0):
    rng = np.random.default_rng(seed)
    p1 = np.array(p1, dtype=float)
    p2 = np.array(p2, dtype=float)
    v = p2 - p1
    L = float(np.linalg.norm(v))
    d = v / L
    n = np.array([-d[1], d[0]])
    ht = thickness * 0.5

    n_pts = int(L * height * density)
    u = rng.uniform(0.0, L, size=n_pts)
    z = rng.uniform(base_z, base_z + height, size=n_pts)
    side = rng.choice([-1.0, 1.0], size=n_pts)
    noise = rng.normal(0.0, 0.004, size=n_pts)

    if door_gap is not None:
        g_start, g_end, g_h = door_gap
        keep = ~((u >= g_start) & (u <= g_end) & (z <= base_z + g_h))
        u, z, side, noise = u[keep], z[keep], side[keep], noise[keep]

    xy = p1[None, :] + np.outer(u, d) + np.outer(side * ht + noise, n)
    return np.column_stack([xy, z])


class TestCorePipeline(unittest.TestCase):
    def test_spatial_extractor_multi_room_cloud(self):
        rng = np.random.default_rng(123)
        # 8m x 5m room, floor at z=0.0, ceiling at z=2.74
        floor_xy = rng.uniform([0.0, 0.0], [8.0, 5.0], size=(2500, 2))
        floor_pts = np.column_stack([floor_xy, rng.normal(0.0, 0.003, size=2500)])
        ceil_pts = np.column_stack([floor_xy, rng.normal(2.74, 0.003, size=2500)])

        w_south = _sample_wall_box([0.0, 0.0], [8.0, 0.0], 0.0, 2.74, 0.152, seed=1)
        w_north = _sample_wall_box([0.0, 5.0], [8.0, 5.0], 0.0, 2.74, 0.152, seed=2)
        w_west = _sample_wall_box([0.0, 0.0], [0.0, 5.0], 0.0, 2.74, 0.152, seed=3)
        w_east = _sample_wall_box([8.0, 0.0], [8.0, 5.0], 0.0, 2.74, 0.152, seed=4)
        # Interior partition at X=4.0 with 0.914m door gap
        w_part = _sample_wall_box([4.0, 0.0], [4.0, 5.0], 0.0, 2.74, 0.127, door_gap=(2.0, 2.95, 2.13), seed=5)

        xyz = np.vstack([floor_pts, ceil_pts, w_south, w_north, w_west, w_east, w_part])

        t0 = time.time()
        extractor = SpatialBIMExtractor(target_lod=300, voxel_size=0.05)
        manifest = extractor.extract_from_pointcloud({"xyz": xyz}, site_name="TestClinic")
        elapsed = time.time() - t0

        self.assertLess(elapsed, 3.0)
        self.assertAlmostEqual(manifest["levels"][0]["elevation"], 0.0, delta=0.04)
        self.assertAlmostEqual(manifest["levels"][1]["elevation"], 2.74, delta=0.05)
        self.assertGreaterEqual(len(manifest["walls"]), 5)
        self.assertGreaterEqual(len(manifest["doors"]), 1)
        self.assertGreaterEqual(len(manifest["spaces"]), 1)

    def test_wall_mitring_and_residuals(self):
        w1 = AnalyticalWall("W1", "North", [0.0, 5.0], [8.0, 5.0], 0.0, 2.74, 0.152, "Exterior")
        w2 = AnalyticalWall("W2", "East", [8.0, 5.0], [8.0, 0.0], 0.0, 2.74, 0.152, "Exterior")
        joins = mitre_wall_network([w1, w2])
        self.assertIsNotNone(joins["W1"][1])
        self.assertIsNotNone(joins["W2"][0])

        poly = w1.get_mitred_polygon(join_start=joins["W1"][0], join_end=joins["W1"][1])
        self.assertEqual(len(poly), 4)
        # Outer corner at x=8.076, y=5.076
        xs = [p[0] for p in poly]
        self.assertAlmostEqual(max(xs), 8.076, delta=0.01)

        pts = _sample_wall_box([0.0, 5.0], [8.0, 5.0], 0.0, 2.74, 0.152, seed=9)
        res = w1.compute_point_residuals(pts)
        self.assertGreater(res["count"], 100)
        self.assertLess(res["mean_abs_error_m"], 0.015)

    def test_navvis_6dof_roundtrip_and_occlusion(self):
        # 30 deg yaw, 10 deg pitch, -5 deg roll quaternion
        roll, pitch, yaw = math.radians(-5), math.radians(10), math.radians(30)
        cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
        cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
        cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy

        pose = NavVisPanoPose(1, "pano-000001.jpg", 1000.0, [1.0, 2.0, 1.5], [qw, qx, qy, qz])
        target = np.array([5.0, 3.5, 2.2])
        u, v = pose.project_3d_point_to_equirectangular(target)
        ray = pose.unproject_equirectangular_to_ray(u, v)
        expected_ray = (target - pose.pos) / np.linalg.norm(target - pose.pos)
        self.assertGreater(float(np.dot(ray, expected_ray)), 0.9999)

        # Occlusion check: pose_near is closer but blocked by wall points; pose_clear is unobstructed
        pose_near = NavVisPanoPose(1, "p1.jpg", 1.0, [0.0, 0.0, 1.5], [1, 0, 0, 0])
        pose_clear = NavVisPanoPose(2, "p2.jpg", 2.0, [5.0, 3.0, 1.5], [1, 0, 0, 0])
        engine = TriModalFusionEngine()
        engine.poses = [pose_near, pose_clear]
        occluder = np.array([[2.0, 0.0, 1.5], [2.0, 0.1, 1.5]])
        best_p, _ = engine.find_best_viewing_pose([5.0, 0.0, 1.5], occluder_xyz=occluder)
        self.assertEqual(best_p.id, 2)

    def test_quaternion_alignment(self):
        # 90 deg rotation around Z
        R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        q_align = _rotation_matrix_to_quaternion(R)
        q_out = _quaternion_multiply(q_align, [1.0, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(abs(q_out[0]), math.sqrt(0.5), delta=1e-5)
        self.assertAlmostEqual(abs(q_out[3]), math.sqrt(0.5), delta=1e-5)

    def test_runs_and_fittings(self):
        r1 = LinearRun("D1", "Main Duct 1", "duct", [0.0, 0.0, 3.0], [4.0, 0.0, 3.0], width=0.3, height=0.2)
        r2 = LinearRun("D2", "Branch Duct 2", "duct", [4.0, 0.0, 3.0], [4.0, 3.0, 3.0], width=0.25, height=0.2)
        fittings = generate_fittings([r1, r2])
        self.assertEqual(len(fittings), 1)
        self.assertEqual(fittings[0]["ifc_class"], "IfcDuctFitting")
        self.assertAlmostEqual(fittings[0]["angle_degrees"], 90.0, delta=0.1)

    def test_ifc_classification_and_revit_exporter(self):
        ext_spec = get_classification("Exterior")
        self.assertEqual(ext_spec["ifc_class"], "IfcWall")
        self.assertEqual(ext_spec["predefined_type"], "SOLIDWALL")

        cw_spec = get_classification("CurtainWall")
        self.assertEqual(cw_spec["ifc_class"], "IfcCurtainWall")

        manifest = {
            "project": "UnitTest",
            "levels": [{"name": "01_Ground", "elevation": 0.0}],
            "slabs": [{"id": "S1", "name": "Floor", "x_min": 0, "x_max": 5, "y_min": 0, "y_max": 4, "elevation_top": 0.0, "thickness": 0.15}],
            "walls": [{"id": "W1", "name": "Wall 1", "start": [0, 0], "end": [5, 0], "base_elevation": 0.0, "height": 3.0, "thickness": 0.152}],
            "doors": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_py = os.path.join(tmpdir, "revit_gen.py")
            BIMModelExporter(manifest).export_revit_script(out_py)
            with open(out_py, "r", encoding="utf-8") as f:
                code = f.read()
            compile(code, out_py, "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
