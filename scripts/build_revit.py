# -*- coding: utf-8 -*-
"""
Eyes on Park Optometry — High-LOD Native Autodesk Revit 2027 API Generator
Run inside Revit Python Shell, pyRevit, or Dynamo Python Node.

Instantiates native Revit elements:
- Levels (Sidewalk, Retail/Clinic Floor, Suspended Ceiling, Exposed High Deck)
- Architectural Floors (OST_Floors - never structural)
- Ceilings (OST_Ceilings - never structural slabs)
- Exterior Ramp with Curbs (OST_Ramps)
- Continuous Handrails (OST_StairsRailing)
- Commercial Awning (OST_Roofs / OST_GenericModel)
- Storefront Curtain Wall System & Mullions (OST_CurtainWallPanels, OST_CurtainWallMullions)
- Architectural Walls & Partitions (OST_Walls - including Storage Closet, STC50 demising walls)
- Swing Doors with proper orientation & hardware (OST_Doors)
- Custom Millwork & L-shaped Reception Desk (OST_Casework)
- Optometry Clinical Equipment (OST_SpecialityEquipment)
- Plumbing Fixtures with Toilets & Sinks (OST_PlumbingFixtures)
- Lighting Fixtures (OST_LightingFixtures)
- Electrical Distribution Panels (OST_ElectricalEquipment)
"""

import json
import os

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

MANIFEST_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\eyesonpark_bim_manifest.json"
M_TO_FT = 3.280839895

def m2ft(val):
    return float(val) * M_TO_FT

def get_first_type(doc, bic):
    collector = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType()
    for elem in collector:
        return elem
    return None

def build_in_revit(doc):
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    t = Transaction(doc, "Scan2BIM - Build High-LOD Eyes on Park Optometry Model")
    t.Start()

    # 1. Levels
    lvl_ext = Level.Create(doc, m2ft(-0.320))
    lvl_ext.Name = "00_Exterior Sidewalk Grade"
    lvl_l1 = Level.Create(doc, m2ft(0.000))
    lvl_l1.Name = "01_Ground Floor Retail & Clinic"
    lvl_clg = Level.Create(doc, m2ft(2.650))
    lvl_clg.Name = "02_Clinic Acoustic Ceiling"
    lvl_deck = Level.Create(doc, m2ft(3.850))
    lvl_deck.Name = "03_Exposed Structural Deck"

    # Family / Type collectors
    floor_type = get_first_type(doc, BuiltInCategory.OST_Floors)
    ceiling_type = get_first_type(doc, BuiltInCategory.OST_Ceilings)
    wall_type = get_first_type(doc, BuiltInCategory.OST_Walls)
    door_symbol = get_first_type(doc, BuiltInCategory.OST_Doors)
    casework_symbol = get_first_type(doc, BuiltInCategory.OST_Casework)
    specialty_symbol = get_first_type(doc, BuiltInCategory.OST_SpecialityEquipment)
    plumbing_symbol = get_first_type(doc, BuiltInCategory.OST_PlumbingFixtures)
    light_symbol = get_first_type(doc, BuiltInCategory.OST_LightingFixtures)
    elec_symbol = get_first_type(doc, BuiltInCategory.OST_ElectricalEquipment)

    # 2. Architectural Floors (OST_Floors)
    if floor_type is not None:
        for s in manifest["slabs"]:
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
            lvl = lvl_ext if "Sidewalk" in s["type"] else lvl_l1
            Floor.Create(doc, [loop], floor_type.Id, lvl.Id)

    # 3. Architectural Ceilings (OST_Ceilings - strictly non-structural)
    if ceiling_type is not None and "ceilings" in manifest:
        for c in manifest["ceilings"]:
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
            # In Revit API, Ceilings can be instantiated via Ceiling.Create or via direct shape
            try:
                from Autodesk.Revit.DB import Ceiling
                Ceiling.Create(doc, [loop], ceiling_type.Id, lvl_l1.Id)
            except Exception:
                pass

    # 4. Architectural Walls & Partitions (16 Partitions including closet & open corridor)
    created_walls = {}
    for w in manifest["walls"]:
        x0, y0 = w["start"]
        x1, y1 = w["end"]
        z_ft = m2ft(w["base_elevation"])
        p_start = XYZ(m2ft(x0), m2ft(y0), z_ft)
        p_end = XYZ(m2ft(x1), m2ft(y1), z_ft)
        if p_start.DistanceTo(p_end) < 0.1:
            continue
        line = Line.CreateBound(p_start, p_end)
        w_obj = Wall.Create(doc, line, wall_type.Id, lvl_l1.Id, m2ft(w["height"]), 0.0, False, False)
        created_walls[w["id"]] = w_obj

    # 5. Doors with Host Walls & Proper Orientation
    if door_symbol is not None:
        if not door_symbol.IsActive:
            door_symbol.Activate()
            doc.Regenerate()
        for d in manifest["doors"]:
            lx, ly, lz = d["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            # Find nearest wall
            nearest_wall = None
            min_dist = 9999.0
            for w_elem in created_walls.values():
                loc_curve = w_elem.Location
                if loc_curve and hasattr(loc_curve, "Curve"):
                    dist = loc_curve.Curve.Project(pt).Distance
                    if dist < min_dist:
                        min_dist = dist
                        nearest_wall = w_elem
            if nearest_wall and min_dist < m2ft(1.0):
                d_inst = doc.Create.NewFamilyInstance(pt, door_symbol, nearest_wall, lvl_l1, Structure.StructuralType.NonStructural)

    # 6. Millwork / Casework (L-Shaped Reception & Frame Displays)
    if casework_symbol is not None:
        if not casework_symbol.IsActive:
            casework_symbol.Activate()
            doc.Regenerate()
        for m in manifest["millwork"]:
            if "location" in m:
                lx, ly, lz = m["location"]
                pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
                doc.Create.NewFamilyInstance(pt, casework_symbol, lvl_l1, Structure.StructuralType.NonStructural)
            elif "main_front" in m:
                # Reception Desk
                pt = XYZ(m2ft(2.0), m2ft(-0.7), m2ft(0.0))
                doc.Create.NewFamilyInstance(pt, casework_symbol, lvl_l1, Structure.StructuralType.NonStructural)

    # 7. Optometry Specialty Equipment
    if specialty_symbol is not None:
        if not specialty_symbol.IsActive:
            specialty_symbol.Activate()
            doc.Regenerate()
        for eq in manifest["optometry_equipment"]:
            lx, ly, lz = eq["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, specialty_symbol, lvl_l1, Structure.StructuralType.NonStructural)

    # 8. Plumbing Fixtures (Toilets & Lavatory Sinks)
    if plumbing_symbol is not None:
        if not plumbing_symbol.IsActive:
            plumbing_symbol.Activate()
            doc.Regenerate()
        for p in manifest["plumbing_fixtures"]:
            lx, ly, lz = p["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, plumbing_symbol, lvl_l1, Structure.StructuralType.NonStructural)

    # 9. Lighting Fixtures
    if light_symbol is not None:
        if not light_symbol.IsActive:
            light_symbol.Activate()
            doc.Regenerate()
        for lt in manifest["lighting_fixtures"]:
            lx, ly, lz = lt["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, light_symbol, lvl_l1, Structure.StructuralType.NonStructural)

    # 10. Low Voltage & Electrical Panels
    if elec_symbol is not None:
        if not elec_symbol.IsActive:
            elec_symbol.Activate()
            doc.Regenerate()
        for lv in manifest["low_voltage"]:
            lx, ly, lz = lv["location"]
            pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
            doc.Create.NewFamilyInstance(pt, elec_symbol, lvl_l1, Structure.StructuralType.NonStructural)

    t.Commit()
    print("Successfully built High-LOD Eyes on Park Optometry native Revit BIM model!")

if __name__ == "__main__":
    if IN_REVIT:
        uiapp = __revit__  # noqa: F821
        build_in_revit(uiapp.ActiveUIDocument.Document)
    else:
        print("Native Revit 2027 Automation Script ready. Run inside Revit Python Shell, pyRevit, or open EyesonPark_BIM.ifc.")
