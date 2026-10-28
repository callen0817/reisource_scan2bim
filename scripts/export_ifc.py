# -*- coding: utf-8 -*-
"""
Reisource Scan2BIM — Native IFC4 Exporter Engine
Implements Quartz & BIMCraft parametric principles:
- True parametric wall opening voids:
  * IfcOpeningElement
  * IfcRelVoidsElement (physical opening void cutting host IfcWall)
  * IfcRelFillsElement (IfcDoor / IfcWindow filling the void)
- Accurate orientation matching wall directional vector
- Linear MEP runs: IfcDuctSegment with Top/Center justification
- Structural framing: IfcBeam
- Strict BIM taxonomy: IfcCovering (Ceiling), IfcSlab (Floor)
"""

import os
import sys
import time
import json
import math
import argparse
import ifcopenshell
import ifcopenshell.api

def make_solid_box(model, dx, dy, dz, ox=0.0, oy=0.0, oz=0.0):
    rect = model.createIfcRectangleProfileDef("AREA", None, None, float(dx), float(dy))
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((float(ox), float(oy), float(oz)))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    return model.createIfcExtrudedAreaSolid(rect, axis2placement, direction, float(dz))

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

def export_ifc_from_manifest(manifest_path, output_path):
    t0 = time.time()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # 1. Project Initialization via ifcopenshell.api
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=manifest.get("project", "Scan2BIM Project"))
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})

    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name=manifest.get("site_address", "Project Site"))
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Main Facility")
    storey_l1 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="01_Ground_Floor")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey_l1])

    contained_elements = []

    # 2. Slabs (Floors)
    for s in manifest.get("slabs", []):
        dx = s["x_max"] - s["x_min"]
        dy = s["y_max"] - s["y_min"]
        dz = s["thickness"]
        cx = 0.5 * (s["x_min"] + s["x_max"])
        cy = 0.5 * (s["y_min"] + s["y_max"])
        cz = s["elevation_top"] - dz
        slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name=s["name"], predefined_type="FLOOR")
        slab.ObjectPlacement = create_local_placement(model, cx, cy, cz)
        solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        slab.Representation = create_shape(model, body, solid)
        s_item = slab.Representation.Representations[0].Items[0]
        add_surface_style(model, s_item, "Floor_Finish", 0.28, 0.29, 0.31)
        contained_elements.append(slab)

    # 3. Ceilings (IfcCovering / CEILING)
    for c in manifest.get("ceilings", []):
        dx = c["x_max"] - c["x_min"]
        dy = c["y_max"] - c["y_min"]
        dz = c["thickness"]
        cx = 0.5 * (c["x_min"] + c["x_max"])
        cy = 0.5 * (c["y_min"] + c["y_max"])
        cz = c["elevation"] - dz
        clg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCovering", name=c["name"], predefined_type="CEILING")
        clg.ObjectPlacement = create_local_placement(model, cx, cy, cz)
        solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        clg.Representation = create_shape(model, body, solid)
        c_item = clg.Representation.Representations[0].Items[0]
        add_surface_style(model, c_item, "Ceiling_Finish", 0.94, 0.94, 0.95)
        contained_elements.append(clg)

    # 4. Architectural Walls
    wall_entities = {}
    wall_metadata = {}
    for w in manifest.get("walls", []):
        x0, y0 = w["start"]
        x1, y1 = w["end"]
        length = math.hypot(x1 - x0, y1 - y0)
        thick = float(w["thickness"])
        height = float(w["height"])
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        cz = w["base_elevation"]

        ux = (x1 - x0) / length if length > 1e-4 else 1.0
        uy = (y1 - y0) / length if length > 1e-4 else 0.0
        x_axis = (ux, uy, 0.0)

        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=w["name"], predefined_type="SOLIDWALL")
        wall.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
        solid = make_solid_box(model, length, thick, height, 0.0, 0.0, 0.0)
        wall.Representation = create_shape(model, body, solid)
        w_item = wall.Representation.Representations[0].Items[0]
        if "Exterior" in w["name"]:
            add_surface_style(model, w_item, "Wall_Exterior_Concrete", 0.88, 0.88, 0.86)
        else:
            add_surface_style(model, w_item, "Wall_Interior_Drywall", 0.92, 0.92, 0.93)

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

        # Void Solid
        void_solid = make_solid_box(model, ow, thick_void, oh, 0.0, 0.0, 0.0)
        void_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name=f"Opening_{op['id']}", predefined_type="OPENING")
        void_elem.ObjectPlacement = create_local_placement(model, lx, ly, sill, x_axis=x_axis)
        void_elem.Representation = create_shape(model, body, void_solid)

        # Relate void to host wall via IfcRelVoidsElement
        model.create_entity("IfcRelVoidsElement",
            GlobalId=ifcopenshell.guid.new(),
            RelatingBuildingElement=host_wall,
            RelatedOpeningElement=void_elem
        )

        # Filling Door or Window
        if "Door" in op.get("type", "") or "Door" in op["id"]:
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
        else:
            frame_solid = make_solid_box(model, ow, 0.12, oh, 0.0, 0.0, 0.0)
            glass_solid = make_solid_box(model, ow - 0.10, 0.024, oh - 0.10, 0.0, 0.0, 0.0)
            filling_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name=op["name"], predefined_type="WINDOW")
            filling_elem.OverallWidth = float(ow)
            filling_elem.OverallHeight = float(oh)
            filling_elem.ObjectPlacement = create_local_placement(model, lx, ly, sill, x_axis=x_axis)
            filling_elem.Representation = create_shape(model, body, [frame_solid, glass_solid])
            f_item = filling_elem.Representation.Representations[0].Items[0]
            add_surface_style(model, f_item, "Window_Frame_Metal", 0.22, 0.20, 0.18)

        # Relate filling element to opening void via IfcRelFillsElement
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
            add_surface_style(model, r_item, "MEP_Ductwork", 0.90, 0.90, 0.92)
        else:
            elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name=run["name"], predefined_type="BEAM")
            elem.ObjectPlacement = create_local_placement(model, cx, cy, cz, x_axis=x_axis)
            elem.Representation = create_shape(model, body, solid)
            r_item = elem.Representation.Representations[0].Items[0]
            add_surface_style(model, r_item, "Structural_Framing", 0.45, 0.48, 0.52)
        contained_elements.append(elem)

    # 7. Furniture & Equipment (IfcFurnishingElement)
    for furn in manifest.get("furniture_and_equipment", []):
        lx, ly, lz = furn["location"]
        dx, dy, dz = furn["dimensions"]
        f_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFurnishingElement", name=furn["name"])
        f_elem.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
        f_elem.Representation = create_shape(model, body, solid)
        f_item = f_elem.Representation.Representations[0].Items[0]
        add_surface_style(model, f_item, "Furniture_Finish", 0.35, 0.36, 0.38)
        contained_elements.append(f_elem)

    # 8. Lighting and Electrical (IfcLightFixture)
    for lt in manifest.get("lighting_and_electrical", []):
        lx, ly, lz = lt["location"]
        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcLightFixture", name=lt["name"])
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
        contained_elements.append(elem)

    # 9. Spatial Structure Assignment
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey_l1, products=contained_elements)

    # 10. Write File
    model.write(output_path)
    duration = time.time() - t0
    size_kb = os.path.getsize(output_path) / 1024.0
    print(f"Generated High-LOD Native IFC4 Model: {output_path}")
    print(f"  Size: {size_kb:.1f} KB in {duration:.2f}s | Elements: {len(contained_elements)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export BIM Manifest to Native IFC4")
    parser.add_argument("--manifest", default=r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar\av_scanar_bim_manifest.json")
    parser.add_argument("--out", default=r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar\AV_scanAR_BIM.ifc")
    args = parser.parse_args()

    if os.path.exists(args.manifest):
        export_ifc_from_manifest(args.manifest, args.out)
    else:
        print(f"Manifest not found: {args.manifest}")
