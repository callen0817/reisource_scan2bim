# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Native IFC4 & Revit Exporter
Translates geometric manifests into strict IFC4 standards and Revit 2027 API scripts.
"""

import os
import json
import uuid
import datetime

class BIMModelExporter:
    def __init__(self, manifest):
        self.manifest = manifest

    def export_revit_script(self, out_script_path):
        """Generates a self-contained pyRevit / Revit Python Shell automation script."""
        manifest_json = json.dumps(self.manifest, indent=2)
        script_content = f'''# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Native Autodesk Revit 2024–2027 Automation Generator
Generated: {datetime.datetime.now().isoformat()}
Project: {self.manifest.get("project", "Scan2BIM")}
"""

import json
import math
try:
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitServices")
    from Autodesk.Revit.DB import (
        Transaction, XYZ, Line, CurveLoop, Level, Wall, Floor,
        FilteredElementCollector, BuiltInCategory, BuiltInParameter, Structure
    )
    IN_REVIT = True
except Exception:
    IN_REVIT = False

M_TO_FT = 3.280839895
MANIFEST_DATA = json.loads(r\'\'\'{manifest_json}\'\'\')

def m2ft(val):
    return float(val) * M_TO_FT

def _match_wall_type(doc, target_thickness_m):
    target_ft = m2ft(target_thickness_m)
    best, best_diff = None, float("inf")
    for wt in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsElementType():
        try:
            diff = abs(float(wt.Width) - target_ft)
            if diff < best_diff:
                best_diff, best = diff, wt
        except Exception:
            continue
    return best

def build_model(doc):
    t = Transaction(doc, "reisource_scan2bim — Build Model")
    t.Start()

    existing_lvls = {{l.Name: l for l in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType()}}
    base_level = None
    for lvl_info in MANIFEST_DATA.get("levels", []):
        lvl = existing_lvls.get(lvl_info["name"])
        if not lvl:
            lvl = Level.Create(doc, m2ft(lvl_info["elevation"]))
            lvl.Name = lvl_info["name"]
        if base_level is None:
            base_level = lvl
    if not base_level:
        base_level = Level.Create(doc, 0.0)
        base_level.Name = "01_Ground Floor"

    floor_type = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Floors).WhereElementIsElementType().FirstElement()
    if floor_type is not None:
        for s in MANIFEST_DATA.get("slabs", MANIFEST_DATA.get("floors", [])):
            elev = m2ft(s.get("elevation_top", s.get("elevation", 0.0)))
            poly = s.get("polygon") or [
                [s["x_min"], s["y_min"]], [s["x_max"], s["y_min"]],
                [s["x_max"], s["y_max"]], [s["x_min"], s["y_max"]]
            ]
            loop = CurveLoop()
            for i in range(len(poly)):
                pa, pb = poly[i], poly[(i + 1) % len(poly)]
                loop.Append(Line.CreateBound(XYZ(m2ft(pa[0]), m2ft(pa[1]), elev), XYZ(m2ft(pb[0]), m2ft(pb[1]), elev)))
            Floor.Create(doc, [loop], floor_type.Id, base_level.Id)

    created_walls = {{}}
    for w in MANIFEST_DATA.get("walls", []):
        p1 = w.get("start", w.get("p1"))
        p2 = w.get("end", w.get("p2"))
        z_ft = m2ft(w.get("base_elevation", w.get("base_z", 0.0)))
        pa, pb = XYZ(m2ft(p1[0]), m2ft(p1[1]), z_ft), XYZ(m2ft(p2[0]), m2ft(p2[1]), z_ft)
        if pa.DistanceTo(pb) < 0.1:
            continue
        wt = _match_wall_type(doc, w.get("thickness", 0.127))
        if wt is not None:
            created_walls[w["id"]] = Wall.Create(doc, Line.CreateBound(pa, pb), wt.Id, base_level.Id, m2ft(w["height"]), 0.0, False, False)

    door_sym = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Doors).WhereElementIsElementType().FirstElement()
    if door_sym is not None:
        if not door_sym.IsActive:
            door_sym.Activate()
            doc.Regenerate()
        for d in MANIFEST_DATA.get("doors", MANIFEST_DATA.get("openings", [])):
            host = created_walls.get(d.get("host", d.get("host_wall")))
            pos = d.get("pos", d.get("location"))
            if host and pos:
                doc.Create.NewFamilyInstance(XYZ(m2ft(pos[0]), m2ft(pos[1]), m2ft(pos[2])), door_sym, host, base_level, Structure.StructuralType.NonStructural)

    print("Revit elements instantiated successfully.")
    t.Commit()

if __name__ == "__main__":
    if IN_REVIT:
        uiapp = __revit__  # noqa: F821
        build_model(uiapp.ActiveUIDocument.Document)
    else:
        print(f"Loaded manifest: {{MANIFEST_DATA.get('project')}} ({{len(MANIFEST_DATA.get('walls', []))}} walls)")
'''
        with open(out_script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        return out_script_path
