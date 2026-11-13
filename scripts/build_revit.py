# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Native Autodesk Revit 2024–2027 API Generator
Run inside Revit Python Shell, pyRevit, or Dynamo Python Node.

Instantiates native Revit elements with intelligent type/family matching:
- Levels (matched by elevation or created)
- Architectural Floors & Ceilings (supports arbitrary closed polygons)
- Demising & Interior Walls (matched to closest WallType by thickness & function)
- Hosted Doors & Windows (matched by opening width & category)
- Linear MEP Ducts (OST_DuctCurves) & Structural Framing (OST_StructuralFraming)
- Casework (OST_Casework), Furniture (OST_Furniture), Plumbing (OST_PlumbingFixtures),
  and Lighting Fixtures (OST_LightingFixtures) with rotation & OmniClass/CSI comments.
"""

import json
import os
import sys
import math

try:
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitServices")
    from Autodesk.Revit.DB import (
        Transaction, XYZ, Line, CurveLoop, Level, Wall, Floor, Ceiling,
        FilteredElementCollector, BuiltInCategory, BuiltInParameter,
        FamilySymbol, Structure, ElementTransformUtils
    )
    IN_REVIT = True
except Exception:
    IN_REVIT = False

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "data", "av_scanar_bim_manifest.json")
MANIFEST_PATH = os.environ.get("SCAN2BIM_MANIFEST", DEFAULT_MANIFEST)
M_TO_FT = 3.280839895


def m2ft(val):
    return float(val) * M_TO_FT


def get_first_type(doc, bic):
    collector = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType()
    for elem in collector:
        return elem
    return None


def match_wall_type(doc, target_thickness_m, wall_type_hint="Interior"):
    """Selects the Revit WallType whose Width is closest to target_thickness_m."""
    target_ft = m2ft(target_thickness_m)
    is_ext = "Exterior" in wall_type_hint
    best = None
    best_score = float("inf")
    for wt in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsElementType():
        try:
            w_ft = float(wt.Width)
        except Exception:
            continue
        score = abs(w_ft - target_ft)
        # Small preference bonus if family/type name matches Exterior vs Interior
        t_name = (wt.Name or "") if hasattr(wt, "Name") else ""
        if is_ext and "Exterior" in t_name:
            score -= 0.02
        elif not is_ext and "Interior" in t_name:
            score -= 0.02
        if score < best_score:
            best_score = score
            best = wt
    return best if best is not None else get_first_type(doc, BuiltInCategory.OST_Walls)


def match_family_symbol(doc, bic, name_hint="", target_width_m=None):
    """Selects the best matching FamilySymbol in a Revit BuiltInCategory."""
    symbols = list(FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType())
    if not symbols:
        return None
    hint_tokens = [t.lower() for t in name_hint.replace("_", " ").split() if len(t) > 2]
    best = symbols[0]
    best_score = -1.0
    for sym in symbols:
        score = 0.0
        s_name = (sym.Name or "").lower() if hasattr(sym, "Name") else ""
        f_name = (sym.FamilyName or "").lower() if hasattr(sym, "FamilyName") else ""
        combined = f"{f_name} {s_name}"
        for tok in hint_tokens:
            if tok in combined:
                score += 1.0
        if target_width_m is not None:
            w_param = sym.get_Parameter(BuiltInParameter.DOOR_WIDTH) or sym.get_Parameter(BuiltInParameter.WINDOW_WIDTH)
            if w_param and w_param.HasValue:
                diff = abs(w_param.AsDouble() - m2ft(target_width_m))
                score += max(0.0, 2.0 - diff)
        if score > best_score:
            best_score = score
            best = sym
    return best


def _set_identity_params(elem, elem_id="", comment=""):
    try:
        if elem_id:
            p_mark = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark and not p_mark.IsReadOnly:
                p_mark.Set(str(elem_id))
        if comment:
            p_comm = elem.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p_comm and not p_comm.IsReadOnly:
                p_comm.Set(str(comment))
    except Exception:
        pass


def _make_curve_loop(poly_2d, z_ft):
    loop = CurveLoop()
    n = len(poly_2d)
    for i in range(n):
        p_a = poly_2d[i]
        p_b = poly_2d[(i + 1) % n]
        xa, ya = m2ft(p_a[0]), m2ft(p_a[1])
        xb, yb = m2ft(p_b[0]), m2ft(p_b[1])
        if math.hypot(xb - xa, yb - ya) > 1e-4:
            loop.Append(Line.CreateBound(XYZ(xa, ya, z_ft), XYZ(xb, yb, z_ft)))
    return loop


def build_in_revit(doc, manifest_path=MANIFEST_PATH):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    t = Transaction(doc, "reisource_scan2bim — Build Native Revit Model")
    t.Start()

    # 1. Levels
    levels = {}
    existing_lvls = {l.Name: l for l in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType()}
    for lvl_info in manifest.get("levels", []):
        l_name = lvl_info["name"]
        if l_name in existing_lvls:
            lvl = existing_lvls[l_name]
        else:
            lvl = Level.Create(doc, m2ft(lvl_info["elevation"]))
            lvl.Name = l_name
        levels[lvl_info.get("id", l_name)] = lvl

    lvl_floor = next(iter(levels.values()), None)
    if lvl_floor is None:
        lvl_floor = Level.Create(doc, 0.0)
        lvl_floor.Name = "01_Ground Floor"

    floor_type = get_first_type(doc, BuiltInCategory.OST_Floors)
    ceiling_type = get_first_type(doc, BuiltInCategory.OST_Ceilings)
    framing_symbol = get_first_type(doc, BuiltInCategory.OST_StructuralFraming)

    # 2. Architectural Floors (polygon or bounding box)
    if floor_type is not None:
        for s in manifest.get("slabs", manifest.get("floors", [])):
            elev = s.get("elevation_top", s.get("elevation", 0.0))
            z_ft = m2ft(elev)
            poly = s.get("polygon") or [
                [s["x_min"], s["y_min"]],
                [s["x_max"], s["y_min"]],
                [s["x_max"], s["y_max"]],
                [s["x_min"], s["y_max"]],
            ]
            loop = _make_curve_loop(poly, z_ft)
            flr = Floor.Create(doc, [loop], floor_type.Id, lvl_floor.Id)
            _set_identity_params(flr, s.get("id", ""), s.get("name", ""))

    # 3. Architectural Ceilings (OST_Ceilings)
    if ceiling_type is not None:
        for c in manifest.get("ceilings", []):
            z_ft = m2ft(c["elevation"])
            poly = c.get("polygon") or [
                [c["x_min"], c["y_min"]],
                [c["x_max"], c["y_min"]],
                [c["x_max"], c["y_max"]],
                [c["x_min"], c["y_max"]],
            ]
            loop = _make_curve_loop(poly, z_ft)
            try:
                clg = Ceiling.Create(doc, [loop], ceiling_type.Id, lvl_floor.Id)
                _set_identity_params(clg, c.get("id", ""), c.get("name", ""))
            except Exception:
                pass

    # 4. Architectural Walls (matched by thickness & Exterior/Interior)
    created_walls = {}
    for w in manifest.get("walls", []):
        p1 = w.get("start", w.get("p1"))
        p2 = w.get("end", w.get("p2"))
        z_ft = m2ft(w.get("base_elevation", w.get("base_z", 0.0)))
        p_start = XYZ(m2ft(p1[0]), m2ft(p1[1]), z_ft)
        p_end = XYZ(m2ft(p2[0]), m2ft(p2[1]), z_ft)
        if p_start.DistanceTo(p_end) < 0.1:
            continue
        w_type = match_wall_type(doc, w.get("thickness", 0.127), w.get("type", "Interior"))
        if w_type is None:
            continue
        line = Line.CreateBound(p_start, p_end)
        w_obj = Wall.Create(doc, line, w_type.Id, lvl_floor.Id, m2ft(w["height"]), 0.0, False, False)
        _set_identity_params(w_obj, w.get("id", ""), f"{w.get('name', '')} | T={w.get('thickness')}m")
        created_walls[w["id"]] = w_obj

    # 5. Hosted Openings (Doors & Windows)
    for op in manifest.get("openings", manifest.get("doors", [])):
        host_id = op.get("host_wall", op.get("host"))
        host_wall = created_walls.get(host_id)
        if host_wall is None:
            continue
        lx, ly, lz = op.get("location", op.get("pos", [0.0, 0.0, 0.0]))
        pt = XYZ(m2ft(lx), m2ft(ly), m2ft(lz))
        is_door = "Door" in op.get("type", "") or "Door" in op.get("id", "") or "DR_" in op.get("id", "")
        bic = BuiltInCategory.OST_Doors if is_door else BuiltInCategory.OST_Windows
        sym = match_family_symbol(doc, bic, op.get("name", ""), target_width_m=op.get("width"))
        if sym is not None:
            if not sym.IsActive:
                sym.Activate()
                doc.Regenerate()
            inst = doc.Create.NewFamilyInstance(pt, sym, host_wall, lvl_floor, Structure.StructuralType.NonStructural)
            _set_identity_params(inst, op.get("id", ""), op.get("name", ""))

    # 6. Linear MEP Runs (Ducts) & Structural Framing (Beams)
    duct_type = get_first_type(doc, BuiltInCategory.OST_DuctCurves)
    mep_sys = get_first_type(doc, BuiltInCategory.OST_DuctSystem)
    for run in manifest.get("linear_runs", []):
        sx, sy, sz = run["start"]
        ex, ey, ez = run["end"]
        p_start = XYZ(m2ft(sx), m2ft(sy), m2ft(sz))
        p_end = XYZ(m2ft(ex), m2ft(ey), m2ft(ez))
        if p_start.DistanceTo(p_end) < 0.05:
            continue
        if run.get("category") == "beam" and framing_symbol is not None:
            if not framing_symbol.IsActive:
                framing_symbol.Activate()
                doc.Regenerate()
            line = Line.CreateBound(p_start, p_end)
            inst = doc.Create.NewFamilyInstance(line, framing_symbol, lvl_floor, Structure.StructuralType.Beam)
            _set_identity_params(inst, run.get("id", ""), run.get("name", ""))
        elif run.get("category") == "duct" and duct_type is not None and mep_sys is not None:
            try:
                from Autodesk.Revit.DB.Mechanical import Duct
                d_obj = Duct.Create(doc, mep_sys.Id, duct_type.Id, lvl_floor.Id, p_start, p_end)
                _set_identity_params(d_obj, run.get("id", ""), run.get("name", ""))
            except Exception:
                pass

    # 7. Casework, Furniture, Plumbing & Lighting
    category_groups = [
        ("casework", BuiltInCategory.OST_Casework),
        ("furniture_and_equipment", BuiltInCategory.OST_Furniture),
        ("plumbing", BuiltInCategory.OST_PlumbingFixtures),
        ("lighting_and_electrical", BuiltInCategory.OST_LightingFixtures),
    ]
    for key, bic in category_groups:
        for item in manifest.get(key, []):
            pos = item.get("location", item.get("pos", item.get("center")))
            if not pos:
                continue
            sym = match_family_symbol(doc, bic, item.get("name", ""))
            if sym is None:
                continue
            if not sym.IsActive:
                sym.Activate()
                doc.Regenerate()
            pt = XYZ(m2ft(pos[0]), m2ft(pos[1]), m2ft(pos[2]))
            inst = doc.Create.NewFamilyInstance(pt, sym, lvl_floor, Structure.StructuralType.NonStructural)
            rot_deg = item.get("rotation_deg")
            if rot_deg:
                axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, math.radians(float(rot_deg)))
            _set_identity_params(inst, item.get("id", ""), item.get("name", ""))

    t.Commit()
    print("Successfully built High-LOD native Revit BIM model!")


if __name__ == "__main__":
    m_path = sys.argv[1] if len(sys.argv) > 1 else MANIFEST_PATH
    if IN_REVIT:
        uiapp = __revit__  # noqa: F821
        build_in_revit(uiapp.ActiveUIDocument.Document, manifest_path=m_path)
    else:
        with open(m_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        print("=================================================================")
        print("reisource_scan2bim — Native Autodesk Revit 2024-2027 Generator")
        print("=================================================================")
        print(f"Project: {manifest.get('project')}")
        print(f"Levels: {len(manifest.get('levels', []))} | Walls: {len(manifest.get('walls', []))}")
        print(f"Openings/Doors: {len(manifest.get('openings', manifest.get('doors', [])))}")
        print(f"Linear Runs: {len(manifest.get('linear_runs', []))} | Spaces: {len(manifest.get('spaces', []))}")
        print("Run inside pyRevit, Revit Python Shell, or Dynamo Python Node.")
        print("=================================================================")
