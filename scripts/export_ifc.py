# -*- coding: utf-8 -*-
"""
AV scanAR Data Sync — Native IFC4 Exporter
Implements:
- Standard ifcopenshell.api project setup
- Parametric wall opening voids:
  * IfcOpeningElement
  * IfcRelVoidsElement (physical opening void cutting host IfcWall)
  * IfcRelFillsElement (IfcDoor / IfcWindow filling the void)
- Accurate orientation matching wall directional vector
- Linear MEP runs: IfcDuctSegment with Top/Center justification
- Structural framing: IfcBeam
- Strict BIM taxonomy: IfcCovering (Ceiling), IfcSlab (Floor)
"""

import argparse
import os
import sys
import time
import json
import math
import numpy as np
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

def create_shape(model, body_context, solids):
    if not isinstance(solids, list):
        solids = [solids]
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", solids)
    return model.createIfcProductDefinitionShape(None, None, [shape])

def create_local_placement(model, x, y, z, z_axis=(0.0, 0.0, 1.0), x_axis=(1.0, 0.0, 0.0), relative_to=None):
    pt = model.createIfcCartesianPoint((float(x), float(y), float(z)))
    dir_z = model.createIfcDirection([float(v) for v in z_axis])
    dir_x = model.createIfcDirection([float(v) for v in x_axis])
    axis2 = model.createIfcAxis2Placement3D(pt, dir_z, dir_x)
    return model.createIfcLocalPlacement(relative_to, axis2)

def add_surface_style(model, shape_rep_item, name, r, g, b, transparency=0.0):
    col = model.createIfcColourRgb(name, float(r), float(g), float(b))
    rendering = model.createIfcSurfaceStyleRendering(
        col, float(transparency), None, None, None, None, None, None, "NOTDEFINED"
    )
    style = model.createIfcSurfaceStyle(name, "BOTH", [rendering])
    model.createIfcStyledItem(shape_rep_item, [style], name)

def export_ifc(manifest_path=DEFAULT_MANIFEST_PATH, out_ifc_path=DEFAULT_OUT_IFC_PATH):
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

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name=manifest.get("site_address", "Scan2BIM Site"))
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name=manifest.get("building_name", "Building"))
    storey_l1 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="01_Ground_Floor")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey_l1])

    omniclass = ifcopenshell.api.run("classification.add_classification", model, classification="OmniClass")
    contained_elements = []

    # 2. Slabs / Floors (supports both bounding-box and polygon schemas)
    for s in manifest.get("slabs", manifest.get("floors", [])):
        dz = s["thickness"]
        is_ramp = "RAMP" in s.get("id", "").upper()
        cat_key = "Ramp" if is_ramp else "InteriorFloor"
        spec = get_classification(cat_key)
        slab = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"], name=s["name"], predefined_type=spec["predefined_type"])
        if "polygon" in s and s["polygon"]:
            elev = s.get("elevation_top", s.get("elevation", 0.0))
            slab.ObjectPlacement = create_local_placement(model, 0.0, 0.0, elev - dz)
            solid = make_solid_polygon(model, s["polygon"], dz)
        else:
            dx = s["x_max"] - s["x_min"]
            dy = s["y_max"] - s["y_min"]
            cx = 0.5 * (s["x_min"] + s["x_max"])
            cy = 0.5 * (s["y_min"] + s["y_max"])
            cz = s.get("elevation_top", s.get("elevation", 0.0)) - dz
            slab.ObjectPlacement = create_local_placement(model, cx, cy, cz)
            solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        slab.Representation = create_shape(model, body, solid)
        s_item = slab.Representation.Representations[0].Items[0]
        add_surface_style(model, s_item, "Carpet_Tile_Charcoal", 0.28, 0.29, 0.31)
        attach_pset_and_classification(model, slab, cat_key, classification_entity=omniclass)
        contained_elements.append(slab)

    # 3. Ceilings (IfcCovering / CEILING)
    for c in manifest.get("ceilings", []):
        dz = c["thickness"]
        clg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCovering", name=c["name"], predefined_type="CEILING")
        if "polygon" in c and c["polygon"]:
            clg.ObjectPlacement = create_local_placement(model, 0.0, 0.0, c["elevation"] - dz)
            solid = make_solid_polygon(model, c["polygon"], dz)
        else:
            dx = c["x_max"] - c["x_min"]
            dy = c["y_max"] - c["y_min"]
            cx = 0.5 * (c["x_min"] + c["x_max"])
            cy = 0.5 * (c["y_min"] + c["y_max"])
            cz = c["elevation"] - dz
            clg.ObjectPlacement = create_local_placement(model, cx, cy, cz)
            solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        clg.Representation = create_shape(model, body, solid)
        c_item = clg.Representation.Representations[0].Items[0]
        add_surface_style(model, c_item, "Acoustic_Ceiling_Drywall", 0.94, 0.94, 0.95)
        attach_pset_and_classification(model, clg, "SuspendedCeiling", classification_entity=omniclass)
        contained_elements.append(clg)

    # 4. Architectural Walls
    wall_entities = {}
    wall_metadata = {}
    for w in manifest.get("walls", []):
        p1 = w.get("start", w.get("p1"))
        p2 = w.get("end", w.get("p2"))
        x0, y0 = p1[0], p1[1]
        x1, y1 = p2[0], p2[1]
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1e-4:
            continue
        thick = float(w["thickness"])
        height = float(w["height"])
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        cz = float(w.get("base_elevation", w.get("base_z", 0.0)))

        ux = (x1 - x0) / length
        uy = (y1 - y0) / length
        x_axis = (ux, uy, 0.0)

        w_type = w.get("type", "Exterior" if "Exterior" in w.get("name", "") else "Interior")
        spec = get_classification(w_type, fallback="Interior")
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"], name=w["name"], predefined_type=spec["predefined_type"])
        wall.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
        solid = make_solid_box(model, length, thick, height, 0.0, 0.0, 0.0)
        wall.Representation = create_shape(model, body, solid)
        w_item = wall.Representation.Representations[0].Items[0]
        if w_type.startswith("Exterior"):
            add_surface_style(model, w_item, "Wall_Exterior_Concrete", 0.88, 0.88, 0.86)
        else:
            add_surface_style(model, w_item, "Wall_Interior_Drywall", 0.92, 0.92, 0.93)

        assign_wall_material_layers(model, wall, thick, w_type)
        attach_pset_and_classification(model, wall, w_type, classification_entity=omniclass)

        wall_entities[w["id"]] = wall
        wall_metadata[w["id"]] = {
            "ux": ux, "uy": uy,
            "x0": x0, "y0": y0,
            "cx": cx, "cy": cy,
            "thick": thick
        }
        contained_elements.append(wall)

    # 5. Openings (Parametric Voids + Door/Window Elements)
    for op in manifest.get("openings", []):
        host_id = op["host_wall"]
        host_wall = wall_entities.get(host_id)
        w_meta = wall_metadata.get(host_id)
        if not host_wall or not w_meta:
            continue

        lx, ly, lz = op["location"]
        ow = op["width"]
        oh = op["height"]
        sill = op.get("sill_z", 0.0)
        thick_void = w_meta["thick"] + 0.10
        x_axis = (w_meta["ux"], w_meta["uy"], 0.0)

        void_solid = make_solid_box(model, ow, thick_void, oh, 0.0, 0.0, 0.0)
        void_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name=f"Opening_{op['id']}", predefined_type="OPENING")
        void_elem.ObjectPlacement = create_local_placement(model, lx, ly, sill, x_axis=x_axis)
        void_elem.Representation = create_shape(model, body, void_solid)

        model.create_entity("IfcRelVoidsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingBuildingElement=host_wall,
            RelatedOpeningElement=void_elem
        )

        is_door = "Door" in op.get("type", "") or "Door" in op["id"]
        if is_door:
            casing_d = op.get("casing_depth", 0.32)
            casing_solid = make_solid_box(model, ow + 0.08, casing_d, oh + 0.04, 0.0, 0.0, 0.0)
            leaf_solid = make_solid_box(model, ow - 0.04, 0.05, oh - 0.03, 0.0, 0.0, 0.0)
            filling_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDoor", name=op["name"], predefined_type="DOOR")
            filling_elem.OverallWidth = float(ow)
            filling_elem.OverallHeight = float(oh)
            filling_elem.ObjectPlacement = create_local_placement(model, lx, ly, sill, x_axis=x_axis)
            filling_elem.Representation = create_shape(model, body, [casing_solid, leaf_solid])
            f_item = filling_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Architectural_Wood_Casing", 0.68, 0.48, 0.32)
            attach_pset_and_classification(model, filling_elem, "Door", classification_entity=omniclass)
        else:
            frame_solid = make_solid_box(model, ow, 0.12, oh, 0.0, 0.0, 0.0)
            glass_solid = make_solid_box(model, ow - 0.10, 0.024, oh - 0.10, 0.0, 0.0, 0.0)
            shade_box = make_solid_box(model, ow, 0.10, 0.12, 0.0, 0.0, oh * 0.5 - 0.06)
            filling_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name=op["name"], predefined_type="WINDOW")
            filling_elem.OverallWidth = float(ow)
            filling_elem.OverallHeight = float(oh)
            filling_elem.ObjectPlacement = create_local_placement(model, lx, ly, sill, x_axis=x_axis)
            filling_elem.Representation = create_shape(model, body, [frame_solid, glass_solid, shade_box])
            f_item = filling_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Window_Anodized_Bronze", 0.22, 0.20, 0.18)
            attach_pset_and_classification(model, filling_elem, "Window", classification_entity=omniclass)

        model.create_entity("IfcRelFillsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingOpeningElement=void_elem,
            RelatedBuildingElement=filling_elem
        )
        contained_elements.append(filling_elem)

    # 6. Linear MEP Runs & Structural Framing (IfcDuctSegment, IfcBeam)
    for run in manifest.get("linear_runs", []):
        sx, sy, sz = run["start"]
        ex, ey, ez = run["end"]
        length = math.hypot(ex - sx, ey - sy)
        rw = run.get("width", 0.15)
        rh = run.get("height", 0.10)
        cx = 0.5 * (sx + ex)
        cy = 0.5 * (sy + ey)
        cz = 0.5 * (sz + ez)

        ux = (ex - sx) / length if length > 1e-4 else 1.0
        uy = (ey - sy) / length if length > 1e-4 else 0.0
        x_axis = (ux, uy, 0.0)

        solid = make_solid_box(model, length, rw, rh, 0.0, 0.0, 0.0)
        if run["category"] == "duct":
            elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDuctSegment", name=run["name"], predefined_type="RIGIDSEGMENT")
            elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
            elem.Representation = create_shape(model, body, solid)
            r_item = elem.Representation.Representations[0].Items[0]
            add_surface_style(model, r_item, "Slot_Diffuser_Matte_White", 0.90, 0.90, 0.92)
        else:
            elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name=run["name"], predefined_type="BEAM")
            elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
            elem.Representation = create_shape(model, body, solid)
            r_item = elem.Representation.Representations[0].Items[0]
            add_surface_style(model, r_item, "Structural_Steel_Primer", 0.45, 0.48, 0.52)
        contained_elements.append(elem)

    # 7. Furniture & Equipment (IfcFurniture in IFC4)
    for furn in manifest.get("furniture_and_equipment", []):
        lx, ly, lz = furn["location"]
        dx, dy, dz = furn["dimensions"]
        f_spec = get_classification("Furniture")
        f_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=f_spec["ifc_class"], name=furn["name"], predefined_type=f_spec["predefined_type"])
        f_elem.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        if "Cabinet" in furn["id"]:
            body_solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
            handle1 = make_solid_cylinder(model, 0.012, 0.15, -dx * 0.5 + 0.02, -0.06, 0.9)
            handle2 = make_solid_cylinder(model, 0.012, 0.15, -dx * 0.5 + 0.02, 0.06, 0.9)
            f_elem.Representation = create_shape(model, body, [body_solid, handle1, handle2])
            f_item = f_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Cabinet_Charcoal_Steel", 0.22, 0.23, 0.25)
        elif "Workstation" in furn["id"]:
            top = make_solid_box(model, dx, dy, 0.035, 0.0, 0.0, dz - 0.035)
            leg_l = make_solid_box(model, dx - 0.10, 0.05, dz - 0.035, 0.0, -dy * 0.5 + 0.08, 0.0)
            leg_r = make_solid_box(model, dx - 0.10, 0.05, dz - 0.035, 0.0, dy * 0.5 - 0.08, 0.0)
            monitor = make_solid_box(model, 0.04, 0.85, 0.38, 0.15, 0.0, dz + 0.12)
            stand = make_solid_box(model, 0.18, 0.22, 0.12, 0.15, 0.0, dz)
            f_elem.Representation = create_shape(model, body, [top, leg_l, leg_r, monitor, stand])
            f_item = f_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Desk_White_Oak", 0.82, 0.72, 0.55)
        else:
            solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
            f_elem.Representation = create_shape(model, body, solid)
            f_item = f_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Linen_Drape_Sheer", 0.85, 0.84, 0.82, transparency=0.4)
        attach_pset_and_classification(model, f_elem, "Furniture", classification_entity=omniclass)
        contained_elements.append(f_elem)

    # 8. Lighting and Electrical (IfcLightFixture)
    for lt in manifest.get("lighting_and_electrical", []):
        lx, ly, lz = lt["location"]
        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcLightFixture", name=lt["name"], predefined_type="POINTSOURCE")
        elem.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        if "Exit" in lt["id"]:
            dx, dy, dz = lt.get("dimensions", [0.32, 0.06, 0.18])
            box = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
            elem.Representation = create_shape(model, body, box)
            l_item = elem.Representation.Representations[0].Items[0]
            add_surface_style(model, l_item, "Exit_Sign_Illuminated_Red", 0.95, 0.15, 0.15)
        else:
            cyl = make_solid_cylinder(model, 0.09, 0.03, 0.0, 0.0, -0.03)
            elem.Representation = create_shape(model, body, cyl)
            l_item = elem.Representation.Representations[0].Items[0]
            add_surface_style(model, l_item, "Downlight_LED_Diffuser", 0.98, 0.98, 0.95)
        attach_pset_and_classification(model, elem, "LightFixture", classification_entity=omniclass)
        contained_elements.append(elem)

    # 9. Architectural Spaces / Rooms (IfcSpace)
    space_entities = []
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
    if space_entities:
        ifcopenshell.api.run("aggregate.assign_object", model, relating_object=storey_l1, products=space_entities)

    # 10. Aggregate all elements into Storey Level 1
    if contained_elements:
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey_l1, products=contained_elements)

    # 11. Write Model
    out_dir = os.path.dirname(os.path.abspath(out_ifc_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    model.write(out_ifc_path)
    duration = time.time() - t0
    size_kb = os.path.getsize(out_ifc_path) / 1024.0
    print(f"Successfully generated High-LOD Native IFC4 Model: {out_ifc_path}")
    print(f"  File size: {size_kb:.1f} KB in {duration:.2f}s")
    print(f"  Contained {len(contained_elements)} building elements and {len(space_entities)} spaces.")


def main():
    parser = argparse.ArgumentParser(description="Export Scan2BIM JSON manifest to IFC4.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to input BIM manifest JSON")
    parser.add_argument("--out", default=DEFAULT_OUT_IFC_PATH, help="Path to output .ifc file")
    args = parser.parse_args()
    export_ifc(manifest_path=args.manifest, out_ifc_path=args.out)


if __name__ == "__main__":
    main()
