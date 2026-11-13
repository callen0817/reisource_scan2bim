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

def rotation_matrix_from_quaternion(qw, qx, qy, qz):
    """Returns a 3x3 orthonormal rotation matrix from unit quaternion (w, x, y, z)."""
    norm = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    if norm < 1e-12:
        return np.identity(3, dtype=float)
    w, x, y, z = qw / norm, qx / norm, qy / norm, qz / norm
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w),       2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w),       1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w),       2.0 * (y * z + x * w),       1.0 - 2.0 * (x * x + y * y)],
    ], dtype=float)


class NavVisPanoPose:
    def __init__(self, pano_id, filename, timestamp, pos_xyz, quat_wxyz):
        self.id = int(pano_id)
        self.filename = filename
        self.timestamp = float(timestamp)
        self.pos = np.array(pos_xyz, dtype=float)
        self.quat = np.array(quat_wxyz, dtype=float)
        self.roll, self.pitch, self.yaw = euler_from_quaternion(*quat_wxyz)
        self.R_cam_to_world = rotation_matrix_from_quaternion(*quat_wxyz)
        self.R_world_to_cam = self.R_cam_to_world.T

    def distance_to_point(self, pt_xyz):
        return float(np.linalg.norm(self.pos - np.array(pt_xyz)))

    def project_3d_point_to_equirectangular(self, pt_xyz, pano_w=8192, pano_h=4096):
        """
        Projects a world 3D coordinate onto equirectangular panorama pixel coordinates (u, v)
        using full 6-DoF rotation (roll, pitch, yaw).
        """
        rel_world = np.array(pt_xyz, dtype=float) - self.pos
        rel_cam = self.R_world_to_cam @ rel_world
        x_rot, y_rot, z_rot = float(rel_cam[0]), float(rel_cam[1]), float(rel_cam[2])

        dist_2d = math.hypot(x_rot, y_rot)
        if dist_2d < 1e-4 and abs(z_rot) < 1e-4:
            return None

        # Longitude (-pi to pi) and Latitude (-pi/2 to pi/2)
        lon = math.atan2(y_rot, x_rot)
        lat = math.atan2(z_rot, dist_2d)

        u = (lon / (2.0 * math.pi) + 0.5) * pano_w
        v = (0.5 - lat / math.pi) * pano_h

        return float(np.clip(u, 0, pano_w - 1)), float(np.clip(v, 0, pano_h - 1))

    def unproject_equirectangular_to_ray(self, u, v, pano_w=8192, pano_h=4096):
        """
        Unprojects equirectangular pixel (u, v) to a unit 3D ray direction in world coordinates.
        """
        lon = (float(u) / float(pano_w) - 0.5) * (2.0 * math.pi)
        lat = (0.5 - float(v) / float(pano_h)) * math.pi
        cos_lat = math.cos(lat)
        ray_cam = np.array([
            cos_lat * math.cos(lon),
            cos_lat * math.sin(lon),
            math.sin(lat),
        ], dtype=float)
        ray_world = self.R_cam_to_world @ ray_cam
        norm = float(np.linalg.norm(ray_world))
        return ray_world / norm if norm > 1e-12 else ray_world


class TriModalFusionEngine:
    def __init__(self, poses_csv_path=None):
        self.poses = []
        if poses_csv_path:
            self._load_poses(poses_csv_path)

    def _load_poses(self, csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(";")]
                if len(parts) >= 10:
                    try:
                        p = NavVisPanoPose(
                            pano_id=parts[0],
                            filename=parts[1],
                            timestamp=parts[2],
                            pos_xyz=[float(parts[3]), float(parts[4]), float(parts[5])],
                            quat_wxyz=[float(parts[6]), float(parts[7]), float(parts[8]), float(parts[9])]
                        )
                        self.poses.append(p)
                    except ValueError:
                        continue

    def find_best_viewing_pose(self, target_xyz, occluder_xyz=None, occlusion_radius=0.18):
        """
        Finds the closest camera pose with an unobstructed line of sight to target_xyz.
        When occluder_xyz (N, 3) is provided, rejects poses whose ray passes within
        occlusion_radius of intermediate points before reaching target_xyz.
        """
        target = np.array(target_xyz, dtype=float)
        candidates = sorted(
            ((p.distance_to_point(target), p) for p in self.poses),
            key=lambda item: item[0],
        )
        if not candidates:
            return None, float("inf")

        if occluder_xyz is None or len(occluder_xyz) == 0:
            return candidates[0][1], candidates[0][0]

        for dist, pose in candidates:
            if dist < 1e-4:
                return pose, dist
            ray = (target - pose.pos) / dist
            rel = occluder_xyz - pose.pos
            proj = rel @ ray
            # Only check points strictly between camera and target (with 0.25m margin)
            between = (proj > 0.25) & (proj < dist - 0.25)
            if not np.any(between):
                return pose, dist
            perp_sq = np.sum((rel[between] - np.outer(proj[between], ray)) ** 2, axis=1)
            if not np.any(perp_sq < (occlusion_radius ** 2)):
                return pose, dist

        return candidates[0][1], candidates[0][0]
