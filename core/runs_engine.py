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
