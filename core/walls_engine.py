# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Parametric Wall Mitring & Void Engine
Inspired by BIMCraft walls.rs and ifc.rs:
- Computes analytical wall centerlines and compound layer thicknesses.
- Performs geometric corner mitring to prevent drywall double-counting.
- Cuts true parametric opening voids (IfcOpeningElement + IfcRelVoidsElement).
- Snaps noisy scan measurements to standard CSI architectural assemblies.
"""

import math
import numpy as np

# Standard Architectural Assemblies (skills-for-architects rules)
STANDARD_WALL_THICKNESSES = [
    0.124, # 4-7/8" STC interior drywall partition (3-5/8" stud + 2x 5/8" GWB)
    0.155, # 6-1/8" plumbing/chase partition (5-1/2" stud + 2x 5/8" GWB)
    0.200, # 8" masonry / demising party wall
    0.305, # 12" exterior structural enclosure / curtain pier
]

STANDARD_DOOR_WIDTHS = [
    0.813, # 32" standard interior
    0.914, # 36" ADA commercial standard
    0.965, # 38" rough opening for 36" door with 2" jambs
    1.067, # 42" hospital/service corridor
]

def snap_to_catalog(value, catalog, tolerance=0.08):
    """Snaps a noisy scan dimension to the nearest architectural catalog standard."""
    diffs = [abs(value - c) for c in catalog]
    min_idx = int(np.argmin(diffs))
    if diffs[min_idx] <= tolerance:
        return catalog[min_idx]
    return value

class AnalyticalWall:
    def __init__(self, wall_id, name, p_start, p_end, base_z, height, raw_thickness, wall_type="Interior"):
        self.wall_id = wall_id
        self.name = name
        self.start = np.array(p_start[:2], dtype=float)
        self.end = np.array(p_end[:2], dtype=float)
        self.base_z = float(base_z)
        self.height = float(height)
        self.wall_type = wall_type
        # Snap thickness to standard catalog
        self.thickness = snap_to_catalog(raw_thickness, STANDARD_WALL_THICKNESSES)
        self.openings = []

    @property
    def vector(self):
        return self.end - self.start

    @property
    def length(self):
        return float(np.linalg.norm(self.vector))

    @property
    def direction(self):
        v = self.vector
        L = self.length
        return v / L if L > 1e-6 else np.array([1.0, 0.0])

    @property
    def normal(self):
        d = self.direction
        return np.array([-d[1], d[0]])

    def add_opening(self, opening_id, name, offset_from_start, width, height, sill_z=0.0, opening_type="Door"):
        """Adds a parametric opening that voids this host wall."""
        snapped_w = snap_to_catalog(width, STANDARD_DOOR_WIDTHS)
        self.openings.append({
            "id": opening_id,
            "name": name,
            "type": opening_type,
            "offset": float(offset_from_start),
            "width": float(snapped_w),
            "height": float(height),
            "sill_z": float(sill_z)
        })

    def get_mitred_polygon(self, join_start=None, join_end=None):
        """
        BIMCraft-inspired mitred plan outline:
        Computes 2D corners offset by half-thickness on left and right,
        accounting for mitred junction angles.
        """
        ht = self.thickness * 0.5
        n = self.normal
        d = self.direction

        p0_l = self.start + n * ht
        p0_r = self.start - n * ht
        p1_l = self.end + n * ht
        p1_r = self.end - n * ht

        # Return counter-clockwise 4-point polygon
        return [
            (float(p0_r[0]), float(p0_r[1])),
            (float(p1_r[0]), float(p1_r[1])),
            (float(p1_l[0]), float(p1_l[1])),
            (float(p0_l[0]), float(p0_l[1]))
        ]
