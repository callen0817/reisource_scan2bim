# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Linear MEPF & Structural Framing "Run" Engine
Inspired by BIMCraft runs.rs:
- Unified 3D representation of linear building elements:
  Beams, ducts, pipes, conduits, cable trays, and structural columns.
- Applies professional justification:
  * Structural framing & beams: Justified to TOP (flush to underside of slab).
  * MEP pipes, ducts & conduit: Justified to CENTER.
- Computes 3D tube (24 sides) or extruded prism profiles with accurate slope/pitch.
- Maps directly to standard IFC4 product entities.
"""

import math
import numpy as np

RUN_IFC_MAPPING = {
    "beam": ("IfcBeam", "BEAM"),
    "column": ("IfcColumn", "COLUMN"),
    "duct": ("IfcDuctSegment", "RIGIDSEGMENT"),
    "pipe": ("IfcPipeSegment", "RIGIDSEGMENT"),
    "conduit": ("IfcCableCarrierSegment", "CONDUITSEGMENT"),
    "cabletray": ("IfcCableCarrierSegment", "CABLETRAYSEGMENT"),
}

class LinearRun:
    def __init__(self, run_id, name, category, pt_start, pt_end, profile_type="round", 
                 radius=0.05, width=0.20, height=0.20, justification=None):
        self.run_id = run_id
        self.name = name
        self.category = category.lower()
        self.start = np.array(pt_start, dtype=float)
        self.end = np.array(pt_end, dtype=float)
        self.profile_type = profile_type # "round" or "rectangular"
        self.radius = float(radius)
        self.width = float(width)
        self.height = float(height)

        # BIMCraft justification rules:
        # Beams default to Top, MEP defaults to Center
        if justification:
            self.justification = justification.lower()
        else:
            self.justification = "top" if self.category in ("beam", "stripfooting") else "center"

    @property
    def vector_3d(self):
        return self.end - self.start

    @property
    def length_3d(self):
        return float(np.linalg.norm(self.vector_3d))

    @property
    def plan_length(self):
        return float(np.linalg.norm(self.vector_3d[:2]))

    @property
    def slope_degrees(self):
        L_plan = self.plan_length
        dz = abs(self.end[2] - self.start[2])
        return math.degrees(math.atan2(dz, L_plan)) if L_plan > 1e-6 else 90.0

    @property
    def ifc_class_and_type(self):
        return RUN_IFC_MAPPING.get(self.category, ("IfcBuildingElementProxy", "USERDEFINED"))

    def get_adjusted_centerline(self):
        """
        Adjusts 3D centerline based on justification:
        If 'top', drops centerline by half-height so upper boundary flushes with start[2].
        """
        if self.justification == "top":
            drop = self.height * 0.5
            adj_start = self.start - np.array([0, 0, drop])
            adj_end = self.end - np.array([0, 0, drop])
            return adj_start, adj_end
        return self.start, self.end

    def to_dict(self):
        adj_s, adj_e = self.get_adjusted_centerline()
        ifc_cls, predef = self.ifc_class_and_type
        return {
            "id": self.run_id,
            "name": self.name,
            "category": self.category,
            "ifc_class": ifc_cls,
            "predefined_type": predef,
            "profile_type": self.profile_type,
            "radius": round(self.radius, 4),
            "width": round(self.width, 4),
            "height": round(self.height, 4),
            "justification": self.justification,
            "start": [round(float(v), 4) for v in adj_s],
            "end": [round(float(v), 4) for v in adj_e],
            "slope_degrees": round(self.slope_degrees, 3),
        }


FITTING_IFC_MAPPING = {
    "duct": ("IfcDuctFitting", "BEND"),
    "pipe": ("IfcPipeFitting", "BEND"),
    "conduit": ("IfcCableCarrierFitting", "BEND"),
    "cabletray": ("IfcCableCarrierFitting", "BEND"),
}


def generate_fittings(runs, join_tolerance=0.15, min_angle_deg=5.0):
    """
    Detects connected MEP linear runs sharing an endpoint within join_tolerance
    and emits parametric elbow/transition fitting descriptors.
    """
    fittings = []
    seen_pairs = set()
    for i, r1 in enumerate(runs):
        if r1.category not in FITTING_IFC_MAPPING:
            continue
        for j in range(i + 1, len(runs)):
            r2 = runs[j]
            if r1.category != r2.category:
                continue
            endpoints_1 = (r1.start, r1.end)
            endpoints_2 = (r2.start, r2.end)
            for p1 in endpoints_1:
                for p2 in endpoints_2:
                    if float(np.linalg.norm(p1 - p2)) <= join_tolerance:
                        pair_key = (r1.run_id, r2.run_id)
                        if pair_key in seen_pairs:
                            continue
                        v1 = r1.vector_3d
                        v2 = r2.vector_3d
                        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                        if n1 < 1e-6 or n2 < 1e-6:
                            continue
                        cos_a = float(np.clip(abs(np.dot(v1, v2) / (n1 * n2)), -1.0, 1.0))
                        angle = math.degrees(math.acos(cos_a))
                        if angle >= min_angle_deg:
                            seen_pairs.add(pair_key)
                            ifc_cls, predef = FITTING_IFC_MAPPING[r1.category]
                            mid = 0.5 * (p1 + p2)
                            fittings.append({
                                "id": f"FIT_{r1.run_id}_{r2.run_id}",
                                "name": f"{r1.category.title()} Fitting ({angle:.0f} deg)",
                                "category": r1.category,
                                "ifc_class": ifc_cls,
                                "predefined_type": predef,
                                "location": [round(float(v), 4) for v in mid],
                                "width": round(max(r1.width, r2.width), 4),
                                "height": round(max(r1.height, r2.height), 4),
                                "angle_degrees": round(angle, 2),
                                "connected_runs": [r1.run_id, r2.run_id],
                            })
    return fittings
