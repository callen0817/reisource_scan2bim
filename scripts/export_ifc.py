# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Native Editable IFC4 Exporter
Implements:
- Standard ifcopenshell.api IFC4 project & multi-storey setup
- Native Revit-editable IfcWall (Axis Curve2D + Body SweptSolid + IfcMaterialLayerSetUsage)
- True wall-relative IfcOpeningElement voids (IfcRelVoidsElement + IfcRelFillsElement)
  so Revit executes real boolean wall cuts with ZERO Generic Model opening artifacts
- First-class Structural Columns (IfcColumn, rectangular & circular)
- First-class Structural Beams (IfcBeam, top-justified)
- Strict BIM taxonomy: IfcCovering (Ceiling), IfcSlab (Floor), IfcDoor, IfcWindow
- Opt-in IfcSpace export (--include-spaces) to prevent Revit Generic Model space clutter
"""

import argparse
import os
import sys
import time
import json
import math
import ifcopenshell
import ifcopenshell.api

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.ifc_classification import (
    assign_wall_material_layers,
    attach_pset_and_classification,
    get_classification,
)

DEFAULT_MANIFEST_PATH = os.path.join(REPO_ROOT, "data", "av_scanar_bim_manifest.json")
DEFAULT_OUT_IFC_PATH = os.path.join(REPO_ROOT, "data", "Output_BIM.ifc")


def make_solid_box(model, dx, dy, dz, ox=0.0, oy=0.0, oz=0.0):
    rect = model.createIfcRectangleProfileDef("AREA", None, None, float(dx), float(dy))
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((float(ox), float(oy), float(oz)))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    return model.createIfcExtrudedAreaSolid(rect, axis2placement, direction, float(dz))


def make_solid_polygon(model, polygon_2d, dz, oz=0.0):
    pts = [model.createIfcCartesianPoint((float(p[0]), float(p[1]))) for p in polygon_2d]
    if pts and (polygon_2d[0][0] != polygon_2d[-1][0] or polygon_2d[0][1] != polygon_2d[-1][1]):
        pts.append(pts[0])
    curve = model.createIfcPolyline(pts)
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, curve)
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((0.0, 0.0, float(oz)))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    return model.createIfcExtrudedAreaSolid(profile, axis2placement, direction, float(dz))


def make_solid_cylinder(model, radius, length, ox=0.0, oy=0.0, oz=0.0):
    circle = model.createIfcCircleProfileDef("AREA", None, None, float(radius))
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((float(ox), float(oy), float(oz)))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    return model.createIfcExtrudedAreaSolid(circle, axis2placement, direction, float(length))


def create_shape(model, body_context, solids, extra_reps=None):
    if not isinstance(solids, list):
        solids = [solids]
    reps = []
    if extra_reps:
        reps.extend(extra_reps)
    reps.append(model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", solids))
    return model.createIfcProductDefinitionShape(None, None, reps)


def create_axis_rep(model, axis_context, length):
    p0 = model.createIfcCartesianPoint((0.0, 0.0))
    p1 = model.createIfcCartesianPoint((float(length), 0.0))
    line = model.createIfcPolyline([p0, p1])
    return model.createIfcShapeRepresentation(axis_context, "Axis", "Curve2D", [line])


def create_local_placement(model, x, y, z, z_axis=(0.0, 0.0, 1.0), x_axis=(1.0, 0.0, 0.0), relative_to=None):
    pt = model.createIfcCartesianPoint((float(x), float(y), float(z)))
    dir_z = model.createIfcDirection([float(v) for v in z_axis])
    dir_x = model.createIfcDirection([float(v) for v in x_axis])
    axis2 = model.createIfcAxis2Placement3D(pt, dir_z, dir_x)
    return model.createIfcLocalPlacement(relative_to, axis2)


def add_surface_style(model, shape_rep_item, name, r, g, b, transparency=0.0, _cache=None):
    if _cache is not None and name in _cache:
        style = _cache[name]
    else:
        col = model.createIfcColourRgb(name, float(r), float(g), float(b))
        rendering = model.createIfcSurfaceStyleRendering(
            col, float(transparency), None, None, None, None, None, None, "NOTDEFINED"
        )
        style = model.createIfcSurfaceStyle(name, "BOTH", [rendering])
        if _cache is not None:
            _cache[name] = style
    model.createIfcStyledItem(shape_rep_item, [style], name)


def export_ifc(manifest_path=DEFAULT_MANIFEST_PATH, out_ifc_path=DEFAULT_OUT_IFC_PATH, include_spaces=False):
    t0 = time.time()
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Project Initialization via ifcopenshell.api
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=manifest.get("project", "Scan2BIM"))
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})

    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context
    )
    axis_ctx = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Axis", target_view="GRAPH_VIEW", parent=context
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name=manifest.get("site_address", "Scan2BIM Site"))
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name=manifest.get("building_name", "Building"))

    levels_spec = manifest.get("levels") or [{"id": "Level_00", "name": "01_Ground_Floor", "elevation": 0.0}]
    storeys = []
    storey_by_key = {}
    storey_elements = {}
    for lv in levels_spec:
        st = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name=lv["name"])
        elev = float(lv.get("elevation", 0.0))
        st.Elevation = elev
        st.ObjectPlacement = create_local_placement(model, 0.0, 0.0, elev)
        storeys.append(st)
        storey_by_key[lv.get("id", lv["name"])] = st
        storey_by_key[lv["name"]] = st
        storey_elements[st] = []
    storey_l1 = storeys[0]

    def _get_storey(item):
        if not item:
            return storey_l1
        k = item.get("level_id") or item.get("level_name")
        return storey_by_key.get(k, storey_l1)

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=storeys)

    omniclass = ifcopenshell.api.run("classification.add_classification", model, classification="OmniClass")
    contained_elements = []
    style_cache = {}
    mat_cache = {}

    def _register_elem(elem, item_dict=None):
        contained_elements.append(elem)
        st = _get_storey(item_dict)
        storey_elements[st].append(elem)

    # 2. Slabs / Floors
    for s in manifest.get("slabs", manifest.get("floors", [])):
        dz = float(s["thickness"])
        is_ramp = "RAMP" in s.get("id", "").upper()
        cat_key = "Ramp" if is_ramp else "InteriorFloor"
        spec = get_classification(cat_key)
        slab = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"], name=s["name"], predefined_type=spec["predefined_type"])
        if "polygon" in s and s["polygon"]:
            elev = float(s.get("elevation_top", s.get("elevation", 0.0)))
            slab.ObjectPlacement = create_local_placement(model, 0.0, 0.0, elev - dz)
            solid = make_solid_polygon(model, s["polygon"], dz)
        else:
            dx = float(s["x_max"] - s["x_min"])
            dy = float(s["y_max"] - s["y_min"])
            cx = 0.5 * (s["x_min"] + s["x_max"])
            cy = 0.5 * (s["y_min"] + s["y_max"])
            cz = float(s.get("elevation_top", s.get("elevation", 0.0))) - dz
            slab.ObjectPlacement = create_local_placement(model, cx, cy, cz)
            solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        slab.Representation = create_shape(model, body, solid)
        add_surface_style(model, solid, "Concrete_Floor_Slab", 0.55, 0.56, 0.58, _cache=style_cache)
        attach_pset_and_classification(model, slab, cat_key, classification_entity=omniclass)
        _register_elem(slab, s)

    # 3. Ceilings (IfcCovering / CEILING)
    for c in manifest.get("ceilings", []):
        dz = float(c["thickness"])
        clg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCovering", name=c["name"], predefined_type="CEILING")
        if "polygon" in c and c["polygon"]:
            clg.ObjectPlacement = create_local_placement(model, 0.0, 0.0, float(c["elevation"]) - dz)
            solid = make_solid_polygon(model, c["polygon"], dz)
        else:
            dx = float(c["x_max"] - c["x_min"])
            dy = float(c["y_max"] - c["y_min"])
            cx = 0.5 * (c["x_min"] + c["x_max"])
            cy = 0.5 * (c["y_min"] + c["y_max"])
            cz = float(c["elevation"]) - dz
            clg.ObjectPlacement = create_local_placement(model, cx, cy, cz)
            solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        clg.Representation = create_shape(model, body, solid)
        add_surface_style(model, solid, "Acoustic_Ceiling_Drywall", 0.94, 0.94, 0.95, _cache=style_cache)
        attach_pset_and_classification(model, clg, "SuspendedCeiling", classification_entity=omniclass)
        _register_elem(clg, c)

    # 4. Architectural Walls (Axis Curve2D + Body SweptSolid + IfcMaterialLayerSetUsage)
    wall_entities = {}
    wall_metadata = {}
    for w in manifest.get("walls", []):
        p1 = w.get("start", w.get("p1"))
        p2 = w.get("end", w.get("p2"))
        x0, y0 = float(p1[0]), float(p1[1])
        x1, y1 = float(p2[0]), float(p2[1])
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1e-4:
            continue
        thick = float(w["thickness"])
        height = float(w["height"])
        cz = float(w.get("base_elevation", w.get("base_z", 0.0)))

        ux = (x1 - x0) / length
        uy = (y1 - y0) / length
        x_axis = (ux, uy, 0.0)

        w_type = w.get("type", "Exterior" if "Exterior" in w.get("name", "") else "Interior")
        spec = get_classification(w_type, fallback="Interior")
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"], name=w["name"], predefined_type=spec["predefined_type"])
        # Place wall origin at start point (x0, y0, cz) so Axis runs (0,0)->(length,0)
        wall.ObjectPlacement = create_local_placement(model, x0, y0, cz, x_axis=x_axis)
        axis_rep = create_axis_rep(model, axis_ctx, length)
        solid = make_solid_box(model, length, thick, height, 0.5 * length, 0.0, 0.0)
        wall.Representation = create_shape(model, body, solid, extra_reps=[axis_rep])

        if w_type.startswith("Exterior"):
            add_surface_style(model, solid, "Wall_Exterior_Concrete", 0.85, 0.85, 0.83, _cache=style_cache)
        else:
            add_surface_style(model, solid, "Wall_Interior_Drywall", 0.92, 0.92, 0.93, _cache=style_cache)

        assign_wall_material_layers(model, wall, thick, w_type, _cache=mat_cache)
        attach_pset_and_classification(model, wall, w_type, classification_entity=omniclass)

        wall_entities[w["id"]] = wall
        wall_metadata[w["id"]] = {
            "ux": ux, "uy": uy,
            "x0": x0, "y0": y0,
            "cz": cz,
            "length": length,
            "thick": thick,
            "level_id": w.get("level_id"),
            "level_name": w.get("level_name"),
        }
        _register_elem(wall, w)

    # 5. Openings (Wall-Relative IfcOpeningElement + IfcDoor / IfcWindow)
    openings_list = list(manifest.get("openings", []))
    if not openings_list:
        for d in manifest.get("doors", []):
            pos = d.get("pos", d.get("location", [0.0, 0.0, 0.0]))
            openings_list.append({
                "id": d["id"],
                "name": d.get("name", d["id"]),
                "host_wall": d.get("host", d.get("host_wall")),
                "location": pos,
                "offset": d.get("offset"),
                "width": d["width"],
                "height": d["height"],
                "sill_z": d.get("sill_z", pos[2] if len(pos) >= 3 else 0.0),
                "type": "Door",
            })
        for wi in manifest.get("windows", []):
            pos = wi.get("pos", wi.get("location", [0.0, 0.0, 0.0]))
            openings_list.append({
                "id": wi["id"],
                "name": wi.get("name", wi["id"]),
                "host_wall": wi.get("host", wi.get("host_wall")),
                "location": pos,
                "offset": wi.get("offset"),
                "width": wi["width"],
                "height": wi["height"],
                "sill_z": wi.get("sill_z", pos[2] if len(pos) >= 3 else 0.9),
                "type": "Window",
            })

    for op in openings_list:
        host_id = op["host_wall"]
        host_wall = wall_entities.get(host_id)
        w_meta = wall_metadata.get(host_id)
        if not host_wall or not w_meta:
            continue

        lx, ly, lz = op["location"]
        ow = float(op["width"])
        oh = float(op["height"])
        sill = float(op.get("sill_z", lz))
        # Compute local u offset along host wall
        if op.get("offset") is not None:
            local_u = float(op["offset"])
        else:
            local_u = (lx - w_meta["x0"]) * w_meta["ux"] + (ly - w_meta["y0"]) * w_meta["uy"]
        local_z = sill - w_meta["cz"]
        thick_void = w_meta["thick"] + 0.08

        # Place Opening RELATIVE TO HOST WALL so Revit executes a real wall cut!
        void_solid = make_solid_box(model, ow, thick_void, oh, 0.0, 0.0, 0.0)
        void_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name=f"Opening_{op['id']}", predefined_type="OPENING")
        void_elem.ObjectPlacement = create_local_placement(
            model, local_u, 0.0, local_z, relative_to=host_wall.ObjectPlacement
        )
        void_elem.Representation = create_shape(model, body, void_solid)

        model.create_entity("IfcRelVoidsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingBuildingElement=host_wall,
            RelatedOpeningElement=void_elem
        )

        is_door = "Door" in op.get("type", "") or "OP_" in op["id"] or "Door" in op["id"]
        if is_door:
            casing_d = float(op.get("casing_depth", w_meta["thick"] + 0.04))
            casing_solid = make_solid_box(model, ow + 0.06, casing_d, oh + 0.03, 0.0, 0.0, 0.0)
            leaf_solid = make_solid_box(model, ow - 0.04, 0.045, oh - 0.03, 0.0, 0.0, 0.0)
            filling_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDoor", name=op["name"], predefined_type="DOOR")
            filling_elem.OverallWidth = ow
            filling_elem.OverallHeight = oh
            filling_elem.ObjectPlacement = create_local_placement(model, 0.0, 0.0, 0.0, relative_to=void_elem.ObjectPlacement)
            filling_elem.Representation = create_shape(model, body, [casing_solid, leaf_solid])
            add_surface_style(model, casing_solid, "Architectural_Wood_Casing", 0.68, 0.48, 0.32, _cache=style_cache)
            attach_pset_and_classification(model, filling_elem, "Door", classification_entity=omniclass)
        else:
            frame_solid = make_solid_box(model, ow, 0.12, oh, 0.0, 0.0, 0.0)
            glass_solid = make_solid_box(model, max(0.1, ow - 0.10), 0.024, max(0.1, oh - 0.10), 0.0, 0.0, 0.05)
            filling_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name=op["name"], predefined_type="WINDOW")
            filling_elem.OverallWidth = ow
            filling_elem.OverallHeight = oh
            filling_elem.ObjectPlacement = create_local_placement(model, 0.0, 0.0, 0.0, relative_to=void_elem.ObjectPlacement)
            filling_elem.Representation = create_shape(model, body, [frame_solid, glass_solid])
            add_surface_style(model, frame_solid, "Window_Anodized_Bronze", 0.22, 0.20, 0.18, _cache=style_cache)
            attach_pset_and_classification(model, filling_elem, "Window", classification_entity=omniclass)

        model.create_entity("IfcRelFillsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingOpeningElement=void_elem,
            RelatedBuildingElement=filling_elem
        )
        _register_elem(filling_elem, w_meta)

    # 6. Structural Columns (IfcColumn)
    for col in manifest.get("columns", []):
        cx, cy = float(col["center"][0]), float(col["center"][1])
        cz = float(col.get("base_z", 0.0))
        ch = float(col.get("height", 3.0))
        rot = math.radians(float(col.get("rotation_deg", 0.0)))
        x_axis = (math.cos(rot), math.sin(rot), 0.0)

        col_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name=col["name"], predefined_type="COLUMN")
        col_elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
        if col.get("shape") == "circular":
            solid = make_solid_cylinder(model, float(col.get("radius", 0.25)), ch, 0.0, 0.0, 0.0)
        else:
            solid = make_solid_box(model, float(col.get("width", 0.40)), float(col.get("depth", 0.40)), ch, 0.0, 0.0, 0.0)
        col_elem.Representation = create_shape(model, body, solid)
        add_surface_style(model, solid, "Structural_Concrete_Column", 0.62, 0.64, 0.67, _cache=style_cache)
        attach_pset_and_classification(model, col_elem, "Column", classification_entity=omniclass)
        _register_elem(col_elem, col)

    # 7. Structural Beams (IfcBeam, top-justified)
    for bm in manifest.get("beams", []):
        sx, sy, sz = float(bm["start"][0]), float(bm["start"][1]), float(bm["start"][2])
        ex, ey, ez = float(bm["end"][0]), float(bm["end"][1]), float(bm["end"][2])
        length = math.hypot(ex - sx, ey - sy)
        if length < 0.1:
            continue
        bw = float(bm.get("width", 0.30))
        bd = float(bm.get("depth", 0.40))
        top_z = float(bm.get("top_z", max(sz, ez)))
        ux, uy = (ex - sx) / length, (ey - sy) / length

        bm_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name=bm["name"], predefined_type="BEAM")
        bm_elem.ObjectPlacement = create_local_placement(model, sx, sy, top_z, x_axis=(ux, uy, 0.0))
        axis_rep = create_axis_rep(model, axis_ctx, length)
        solid = make_solid_box(model, length, bw, bd, 0.5 * length, 0.0, -bd)
        bm_elem.Representation = create_shape(model, body, solid, extra_reps=[axis_rep])
        add_surface_style(model, solid, "Structural_Steel_Beam", 0.40, 0.44, 0.50, _cache=style_cache)
        attach_pset_and_classification(model, bm_elem, "Beam", classification_entity=omniclass)
        _register_elem(bm_elem, bm)

    # 8. Legacy Linear MEP Runs & Framing
    for run in manifest.get("linear_runs", []):
        sx, sy, sz = run["start"]
        ex, ey, ez = run["end"]
        length = math.hypot(ex - sx, ey - sy)
        rw = run.get("width", 0.15)
        rh = run.get("height", 0.10)
        cx, cy, cz = 0.5 * (sx + ex), 0.5 * (sy + ey), 0.5 * (sz + ez)
        ux = (ex - sx) / length if length > 1e-4 else 1.0
        uy = (ey - sy) / length if length > 1e-4 else 0.0
        solid = make_solid_box(model, length, rw, rh, 0.0, 0.0, 0.0)
        if run["category"] == "duct":
            elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDuctSegment", name=run["name"], predefined_type="RIGIDSEGMENT")
            elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=(ux, uy, 0.0))
            elem.Representation = create_shape(model, body, solid)
            add_surface_style(model, solid, "Slot_Diffuser_Matte_White", 0.90, 0.90, 0.92, _cache=style_cache)
        else:
            elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name=run["name"], predefined_type="BEAM")
            elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=(ux, uy, 0.0))
            elem.Representation = create_shape(model, body, solid)
            add_surface_style(model, solid, "Structural_Steel_Primer", 0.45, 0.48, 0.52, _cache=style_cache)
        _register_elem(elem, run)

    # 9. Furniture & Equipment
    for furn in manifest.get("furniture_and_equipment", []):
        lx, ly, lz = furn["location"]
        dx, dy, dz = furn["dimensions"]
        f_spec = get_classification("Furniture")
        f_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=f_spec["ifc_class"], name=furn["name"], predefined_type=f_spec["predefined_type"])
        f_elem.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        f_elem.Representation = create_shape(model, body, solid)
        add_surface_style(model, solid, "Furniture_Generic", 0.78, 0.74, 0.68, _cache=style_cache)
        attach_pset_and_classification(model, f_elem, "Furniture", classification_entity=omniclass)
        _register_elem(f_elem, furn)

    # 10. Lighting & Electrical
    for lt in manifest.get("lighting_and_electrical", []):
        lx, ly, lz = lt["location"]
        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcLightFixture", name=lt["name"], predefined_type="POINTSOURCE")
        elem.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        cyl = make_solid_cylinder(model, 0.09, 0.03, 0.0, 0.0, -0.03)
        elem.Representation = create_shape(model, body, cyl)
        add_surface_style(model, cyl, "Downlight_LED_Diffuser", 0.98, 0.98, 0.95, _cache=style_cache)
        attach_pset_and_classification(model, elem, "LightFixture", classification_entity=omniclass)
        _register_elem(elem, lt)

    # 11. Optional Architectural Spaces (off by default to prevent Revit Generic Model blocks)
    space_entities = []
    if include_spaces:
        storey_spaces = {st: [] for st in storeys}
        for sp in manifest.get("spaces", []):
            sp_ent = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace", name=sp["name"], predefined_type="SPACE")
            sp_ent.ObjectPlacement = create_local_placement(model, 0.0, 0.0, sp.get("elevation", 0.0))
            sp_solid = make_solid_polygon(model, sp["polygon"], sp.get("height", 2.7))
            sp_ent.Representation = create_shape(model, body, sp_solid)
            attach_pset_and_classification(
                model, sp_ent, "Space",
                extra_props={"GrossPlannedArea": sp.get("area_m2", 0.0)},
                classification_entity=omniclass,
            )
            space_entities.append(sp_ent)
            storey_spaces[_get_storey(sp)].append(sp_ent)
        for st, sp_list in storey_spaces.items():
            if sp_list:
                ifcopenshell.api.run("aggregate.assign_object", model, relating_object=st, products=sp_list)

    # 12. Assign each element to its matching IfcBuildingStorey
    for st, elems in storey_elements.items():
        if elems:
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=st, products=elems)

    # 13. Write Model
    out_dir = os.path.dirname(os.path.abspath(out_ifc_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    model.write(out_ifc_path)
    duration = time.time() - t0
    size_kb = os.path.getsize(out_ifc_path) / 1024.0
    print(f"Successfully generated Native Editable IFC4 Model: {out_ifc_path}")
    print(f"  File size: {size_kb:.1f} KB in {duration:.2f}s")
    print(f"  Contained {len(contained_elements)} building elements and {len(space_entities)} spaces.")


def main():
    parser = argparse.ArgumentParser(description="Export Scan2BIM JSON manifest to IFC4.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to input BIM manifest JSON")
    parser.add_argument("--out", default=DEFAULT_OUT_IFC_PATH, help="Path to output .ifc file")
    parser.add_argument("--include-spaces", action="store_true", help="Include IfcSpace volume solids in IFC")
    args = parser.parse_args()
    export_ifc(manifest_path=args.manifest, out_ifc_path=args.out, include_spaces=args.include_spaces)


if __name__ == "__main__":
    main()
