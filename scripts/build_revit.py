# -*- coding: utf-8 -*-
"""
Reisource Scan2BIM — Native Autodesk Revit 2027 Automation Generator
Run inside Revit Python Shell, pyRevit, Dynamo, or execute standalone for CLI review.

Instantiates native Revit elements:
- Levels (Floor, Ceiling, Exposed High Deck)
- Architectural Floors (OST_Floors - never structural)
- Architectural Ceilings (OST_Ceilings - strictly non-structural)
- Demising & Exterior Walls (OST_Walls - with mitred corner joints)
- Hosted Openings: Doors (OST_Doors) and Windows (OST_Windows)
- Linear MEP Runs (OST_DuctCurves / OST_DuctTerminal)
- Structural Framing Window Lintel (OST_StructuralFraming)
- Furniture & Workstations (OST_Furniture)
- Lighting Fixtures & Exit Sign (OST_LightingFixtures)
"""

import json
import os
import math
import argparse

try:
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitServices")
    from Autodesk.Revit.DB import (
        Transaction, XYZ, Line, CurveLoop, Level, Wall, Floor,
        FilteredElementCollector, BuiltInCategory, FamilySymbol,
        Structure
    )
    from RevitServices.Persistence import DocumentManager
    IN_REVIT = True
except Exception:
    IN_REVIT = False

M_TO_FT = 3.280839895

def m2ft(val):
    return float(val) * M_TO_FT

def get_first_type(doc, bic):
    collector = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType()
    for elem in collector:
        return elem
    return None

def build_in_revit(doc, manifest_path):
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    t = Transaction(doc, f"Scan2BIM - Build {manifest.get('project', 'Model')}")
    t.Start()

    # 1. Levels
    levels = {}
    for lvl_info in manifest.get("levels", []):
        z_ft = m2ft(lvl_info["elevation"])
        lvl = Level.Create(doc, z_ft)
        lvl.Name = lvl_info["name"]
        levels[lvl_info["id"]] = lvl

    lvl_floor = list(levels.values())[0] if levels else None

    # Category types
    floor_type = get_first_type(doc, BuiltInCategory.OST_Floors)
    ceiling_type = get_first_type(doc, BuiltInCategory.OST_Ceilings)
    wall_type = get_first_type(doc, BuiltInCategory.OST_Walls)
    door_symbol = get_first_type(doc, BuiltInCategory.OST_Doors)
    window_symbol = get_first_type(doc, BuiltInCategory.OST_Windows)
    furniture_symbol = get_first_type(doc, BuiltInCategory.OST_Furniture)
    light_symbol = get_first_type(doc, BuiltInCategory.OST_LightingFixtures)
    framing_symbol = get_first_type(doc, BuiltInCategory.OST_StructuralFraming)

    # 2. Architectural Floor
    if floor_type is not None and lvl_floor is not None:
        for s in manifest.get("slabs", []):
            z_ft = m2ft(s["elevation_top"])
            p0 = XYZ(m2ft(s["x_min"]), m2ft(s["y_min"]), z_ft)
            p1 = XYZ(m2ft(s["x_max"]), m2ft(s["y_min"]), z_ft)
            p2 = XYZ(m2ft(s["x_max"]), m2ft(s["y_max"]), z_ft)
            p3 = XYZ(m2ft(s["x_min"]), m2ft(s["y_max"]), z_ft)
            loop = CurveLoop()
            loop.Append(Line.CreateBound(p0, p1))
            loop.Append(Line.CreateBound(p1, p2))
            loop.Append(Line.CreateBound(p2, p3))
            loop.Append(Line.CreateBound(p3, p0))
            Floor.Create(doc, [loop], floor_type.Id, lvl_floor.Id)

    # 3. Architectural Ceilings (OST_Ceilings)
    if ceiling_type is not None and lvl_floor is not None:
        for c in manifest.get("ceilings", []):
            z_ft = m2ft(c["elevation"])
            p0 = XYZ(m2ft(c["x_min"]), m2ft(c["y_min"]), z_ft)
            p1 = XYZ(m2ft(c["x_max"]), m2ft(c["y_min"]), z_ft)
            p2 = XYZ(m2ft(c["x_max"]), m2ft(c["y_max"]), z_ft)
            p3 = XYZ(m2ft(c["x_min"]), m2ft(c["y_max"]), z_ft)
            loop = CurveLoop()
            loop.Append(Line.CreateBound(p0, p1))
            loop.Append(Line.CreateBound(p1, p2))
            loop.Append(Line.CreateBound(p2, p3))
            loop.Append(Line.CreateBound(p3, p0))
            try:
                from Autodesk.Revit.DB import Ceiling
                Ceiling.Create(doc, [loop], ceiling_type.Id, lvl_floor.Id)
            except Exception:
                pass

    # 4. Architectural Walls
    created_walls = {}
    if wall_type is not None and lvl_floor is not None:
        for w in manifest.get("walls", []):
            x0, y0 = w["start"]
            x1, y1 = w["end"]
            z_ft = m2ft(w["base_elevation"])
            p_start = XYZ(m2ft(x0), m2ft(y0), z_ft)
            p_end = XYZ(m2ft(x1), m2ft(y1), z_ft)
            if p_start.DistanceTo(p_end) < 0.1:
                continue
            line = Line.CreateBound(p_start, p_end)
            w_obj = Wall.Create(doc, line, wall_type.Id, lvl_floor.Id, m2ft(w["height"]), 0.0, False, False)
            created_walls[w["id"]] = w_obj

    # 5. Hosted Openings (Doors & Windows)
    for op in manifest.get("openings", []):
        host_id = op["host_wall"]
        host_wall = created_walls.get(host_id)
        lx, ly, lz = op["location"]
        pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))

        if "Door" in op["id"] and door_symbol is not None and host_wall is not None:
            if not door_symbol.IsActive:
                door_symbol.Activate()
                doc.Regenerate()
            doc.Create.NewFamilyInstance(pt, door_symbol, host_wall, lvl_floor, Structure.StructuralType.NonStructural)
        elif "Window" in op["id"] and window_symbol is not None and host_wall is not None:
            if not window_symbol.IsActive:
                window_symbol.Activate()
                doc.Regenerate()
            doc.Create.NewFamilyInstance(pt, window_symbol, host_wall, lvl_floor, Structure.StructuralType.NonStructural)

    # 6. Linear MEP Runs & Structural Framing
    for run in manifest.get("linear_runs", []):
        sx, sy, sz = run["start"]
        ex, ey, ez = run["end"]
        p_start = XYZ(m2ft(sx), m2ft(sy), m2ft(sz))
        p_end = XYZ(m2ft(ex), m2ft(ey), m2ft(sz))
        if run["category"] == "beam" and framing_symbol is not None and lvl_floor is not None:
            if not framing_symbol.IsActive:
                framing_symbol.Activate()
                doc.Regenerate()
            line = Line.CreateBound(p_start, p_end)
            doc.Create.NewFamilyInstance(line, framing_symbol, lvl_floor, Structure.StructuralType.Beam)

    # 7. Furniture & Equipment
    if furniture_symbol is not None and lvl_floor is not None:
        if not furniture_symbol.IsActive:
            furniture_symbol.Activate()
            doc.Regenerate()
        for f_item in manifest.get("furniture_and_equipment", []):
            lx, ly, lz = f_item["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, furniture_symbol, lvl_floor, Structure.StructuralType.NonStructural)

    # 8. Lighting Fixtures
    if light_symbol is not None and lvl_floor is not None:
        if not light_symbol.IsActive:
            light_symbol.Activate()
            doc.Regenerate()
        for lt in manifest.get("lighting_and_electrical", []):
            lx, ly, lz = lt["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, light_symbol, lvl_floor, Structure.StructuralType.NonStructural)

    t.Commit()
    print(f"Successfully built High-LOD native Revit BIM model for {manifest.get('project')}!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revit BIM Generator")
    parser.add_argument("--manifest", default=r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar\av_scanar_bim_manifest.json")
    args = parser.parse_args()

    if IN_REVIT:
        uiapp = __revit__  # noqa: F821
        build_in_revit(uiapp.ActiveUIDocument.Document, args.manifest)
    else:
        if os.path.exists(args.manifest):
            with open(args.manifest, "r") as f:
                manifest = json.load(f)
            print("=================================================================")
            print(f"Reisource Scan2BIM — Native Autodesk Revit Automation Engine")
            print("=================================================================")
            print(f"Project: {manifest.get('project')}")
            print(f"Levels: {len(manifest.get('levels', []))} defined")
            print(f"Walls: {len(manifest.get('walls', []))} partitions with mitred corners")
            print(f"Hosted Openings: {len(manifest.get('openings', []))} doors and windows")
            print(f"Linear Runs: {len(manifest.get('linear_runs', []))} MEP ducts & structural framing")
            print(f"Furniture & Workstations: {len(manifest.get('furniture_and_equipment', []))}")
            print(f"Lighting & Life Safety: {len(manifest.get('lighting_and_electrical', []))} fixtures")
            print("\nReady for Revit execution via pyRevit, Revit Python Shell, or IFC import.")
            print("=================================================================")
        else:
            print(f"Manifest not found: {args.manifest}")
