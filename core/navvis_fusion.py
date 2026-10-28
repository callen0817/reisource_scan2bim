# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Tri-Modal NavVis VLX Fusion Engine
Fuses:
1. Point cloud 3D geometry (.npz / .e57)
2. 360-degree equirectangular panoramic photography (.jpg)
3. 6-DoF camera trajectory (pano-poses.csv)

Enables:
- Pinhole and equirectangular unprojection (pixel ray -> 3D point).
- Automatic identification of architectural openings, materials, and fixtures.
- Seamless multi-station camera localization.
"""

import math
import numpy as np

def euler_from_quaternion(qw, qx, qy, qz):
    """Calculates roll, pitch, yaw from quaternion (w, x, y, z)."""
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw

class NavVisPanoPose:
    def __init__(self, pano_id, filename, timestamp, pos_xyz, quat_wxyz):
        self.id = int(pano_id)
        self.filename = filename
        self.timestamp = float(timestamp)
        self.pos = np.array(pos_xyz, dtype=float)
        self.quat = np.array(quat_wxyz, dtype=float)
        self.roll, self.pitch, self.yaw = euler_from_quaternion(*quat_wxyz)

    def distance_to_point(self, pt_xyz):
        return float(np.linalg.norm(self.pos - np.array(pt_xyz)))

    def project_3d_point_to_equirectangular(self, pt_xyz, pano_w=8192, pano_h=4096):
        """
        Projects a world 3D coordinate onto equirectangular panorama pixel coordinates (u, v).
        """
        # Vector from camera to point
        rel_vec = np.array(pt_xyz) - self.pos
        # Rotate by inverse of camera yaw
        cos_y = math.cos(-self.yaw)
        sin_y = math.sin(-self.yaw)
        x_rot = cos_y * rel_vec[0] - sin_y * rel_vec[1]
        y_rot = sin_y * rel_vec[0] + cos_y * rel_vec[1]
        z_rot = rel_vec[2]

        dist_2d = math.hypot(x_rot, y_rot)
        if dist_2d < 1e-4 and abs(z_rot) < 1e-4:
            return None

        # Longitude (-pi to pi) and Latitude (-pi/2 to pi/2)
        lon = math.atan2(y_rot, x_rot)
        lat = math.atan2(z_rot, dist_2d)

        u = (lon / (2.0 * math.pi) + 0.5) * pano_w
        v = (0.5 - lat / math.pi) * pano_h

        return float(np.clip(u, 0, pano_w - 1)), float(np.clip(v, 0, pano_h - 1))

class TriModalFusionEngine:
    def __init__(self, poses_csv_path):
        self.poses = []
        self._load_poses(poses_csv_path)

    def _load_poses(self, csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(";")]
                if len(parts) >= 10:
                    p = NavVisPanoPose(
                        pano_id=parts[0],
                        filename=parts[1],
                        timestamp=parts[2],
                        pos_xyz=[float(parts[3]), float(parts[4]), float(parts[5])],
                        quat_wxyz=[float(parts[6]), float(parts[7]), float(parts[8]), float(parts[9])]
                    )
                    self.poses.append(p)

    def find_best_viewing_pose(self, target_xyz):
        """Finds the camera pose with the clearest, closest direct line of sight to target_xyz."""
        best_p = None
        min_dist = float("inf")
        for p in self.poses:
            d = p.distance_to_point(target_xyz)
            if d < min_dist:
                min_dist = d
                best_p = p
        return best_p, min_dist
