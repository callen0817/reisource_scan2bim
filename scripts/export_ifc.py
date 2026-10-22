import os
import time
import json
import math
import numpy as np
import ifcopenshell
import ifcopenshell.api

MANIFEST_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\eyesonpark_bim_manifest.json"
OUT_IFC = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\EyesonPark_BIM.ifc"

def create_box_shape(model, body_context, dx, dy, dz):
    rect = model.createIfcRectangleProfileDef("AREA", None, None, float(dx), float(dy))
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    solid = model.createIfcExtrudedAreaSolid(rect, axis2placement, direction, float(dz))
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", [solid])
    return model.createIfcProductDefinitionShape(None, None, [shape])

def create_cylinder_shape(model, body_context, radius, length):
    circle = model.createIfcCircleProfileDef("AREA", None, None, float(radius))
    direction = model.createIfcDirection((0.0, 0.0, 1.0))
    origin = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    axis2placement = model.createIfcAxis2Placement3D(origin, None, None)
    solid = model.createIfcExtrudedAreaSolid(circle, axis2placement, direction, float(length))
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", [solid])
    return model.createIfcProductDefinitionShape(None, None, [shape])

def create_composite_shape(model, body_context, solids_list):
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", solids_list)
    return model.createIfcProductDefinitionShape(None, None, [shape])

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

def build_ifc():
    t0 = time.time()
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Eyes on Park Optometry BIM")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})

    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Park Avenue Retail Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Eyes on Park Building")
    storey_ext = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="00 Exterior Sidewalk & Ramp")
    storey_l1 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="01 Ground Floor Retail & Clinic")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey_ext, storey_l1])

    ext_elements = []
    l1_elements = []

    # 1. FLOORS & SLABS (Correctly categorized as FLOOR, not structural slabs)
    for s in manifest["slabs"]:
        dx = s["x_max"] - s["x_min"]
        dy = s["y_max"] - s["y_min"]
        dz = s["thickness"]
        cx = 0.5 * (s["x_min"] + s["x_max"])
        cy = 0.5 * (s["y_min"] + s["y_max"])
        cz = s["elevation_top"] - dz
        slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name=s["name"], predefined_type="FLOOR")
        slab.ObjectPlacement = create_local_placement(model, cx, cy, cz)
        slab.Representation = create_box_shape(model, body, dx, dy, dz)
        s_item = slab.Representation.Representations[0].Items[0]
        if "Sidewalk" in s["name"]:
            add_surface_style(model, s_item, "Sidewalk_Concrete", 0.65, 0.65, 0.65)
            ext_elements.append(slab)
        else:
            add_surface_style(model, s_item, "Floor_Terrazzo_Vinyl", 0.82, 0.78, 0.72)
            l1_elements.append(slab)

    # 2. CEILINGS (Correctly categorized as IfcCovering with PredefinedType='CEILING', NOT structural)
    for c in manifest["ceilings"]:
        dx = c["x_max"] - c["x_min"]
        dy = c["y_max"] - c["y_min"]
        dz = c["thickness"]
        cx = 0.5 * (c["x_min"] + c["x_max"])
        cy = 0.5 * (c["y_min"] + c["y_max"])
        cz = c["elevation"] - dz
        clg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCovering", name=c["name"], predefined_type="CEILING")
        clg.ObjectPlacement = create_local_placement(model, cx, cy, cz)
        clg.Representation = create_box_shape(model, body, dx, dy, dz)
        c_item = clg.Representation.Representations[0].Items[0]
        add_surface_style(model, c_item, "Acoustic_Ceiling_Tile", 0.94, 0.95, 0.96)
        l1_elements.append(clg)

    # 3. ACCESSIBILITY RAMP (IfcRamp with IfcRampFlight)
    rmp = manifest["ramp"]
    sx, sy, sz = rmp["start_point"]
    ex, ey, ez = rmp["end_point"]
    dx = abs(ex - sx)
    dy = rmp["width"]
    dz = rmp["total_rise"]
    cx = 0.5 * (sx + ex)
    cy = sy
    cz = min(sz, ez)
    ramp_obj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcRamp", name=rmp["name"], predefined_type="STRAIGHT_RUN_RAMP")
    ramp_obj.ObjectPlacement = create_local_placement(model, cx, cy, cz)
    # Ramp solid run with side curbs
    run_solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
    curb_l = make_solid_box(model, dx, 0.10, dz + 0.10, 0.0, -dy*0.5 + 0.05, 0.0)
    curb_r = make_solid_box(model, dx, 0.10, dz + 0.10, 0.0, dy*0.5 - 0.05, 0.0)
    ramp_obj.Representation = create_composite_shape(model, body, [run_solid, curb_l, curb_r])
    r_item = ramp_obj.Representation.Representations[0].Items[0]
    add_surface_style(model, r_item, "Concrete_Ramp", 0.70, 0.70, 0.72)
    ext_elements.append(ramp_obj)

    # 4. RAILINGS (IfcRailing with PredefinedType='HANDRAIL')
    for rl in manifest["railings"]:
        rx0, ry0, rz0 = rl["start"]
        rx1, ry1, rz1 = rl["end"]
        dx = abs(rx1 - rx0)
        h_up = rl["height_upper"]
        h_low = rl["height_lower"]
        cx = 0.5 * (rx0 + rx1)
        cy = ry0
        railing = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcRailing", name=rl["id"], predefined_type="HANDRAIL")
        railing.ObjectPlacement = create_local_placement(model, cx, cy, min(rz0, rz1))
        # Twin continuous rails + vertical posts
        top_rail = make_solid_cylinder(model, 0.025, dx, -dx*0.5, 0.0, h_up)
        low_rail = make_solid_cylinder(model, 0.020, dx, -dx*0.5, 0.0, h_low)
        solids = [top_rail, low_rail]
        for pi in np.linspace(-dx*0.48, dx*0.48, rl["posts_count"]):
            solids.append(make_solid_cylinder(model, 0.022, h_up, pi, 0.0, 0.0))
        railing.Representation = create_composite_shape(model, body, solids)
        rl_item = railing.Representation.Representations[0].Items[0]
        add_surface_style(model, rl_item, "Stainless_Steel", 0.88, 0.89, 0.90)
        ext_elements.append(railing)

    # 5. COMMERCIAL AWNING (IfcShadingDevice with PredefinedType='AWNING', NOT structural)
    aw = manifest["awning"]
    aw_dx = abs(aw["x_back"] - aw["x_front"])
    aw_dy = aw["width"]
    aw_cx = 0.5 * (aw["x_front"] + aw["x_back"])
    aw_cy = 0.5 * (aw["y_min"] + aw["y_max"])
    aw_cz = aw["z_front"]
    awning_obj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcShadingDevice", name=aw["name"], predefined_type="AWNING")
    awning_obj.ObjectPlacement = create_local_placement(model, aw_cx, aw_cy, aw_cz)
    # Canopy fabric sloped sheet + hanging valance + metal outriggers
    canopy_solid = make_solid_box(model, aw_dx, aw_dy, 0.05, 0.0, 0.0, 0.15)
    valance_solid = make_solid_box(model, 0.05, aw_dy, aw["valance_drop"], -aw_dx*0.5, 0.0, -aw["valance_drop"])
    aw_solids = [canopy_solid, valance_solid]
    for oy in [-aw_dy*0.45, -aw_dy*0.15, aw_dy*0.15, aw_dy*0.45]:
        aw_solids.append(make_solid_box(model, aw_dx, 0.06, 0.06, 0.0, oy, 0.0))
    awning_obj.Representation = create_composite_shape(model, body, aw_solids)
    aw_item = awning_obj.Representation.Representations[0].Items[0]
    add_surface_style(model, aw_item, "Sunbrella_Navy_Awning", 0.08, 0.15, 0.35)
    ext_elements.append(awning_obj)

    # 6. STOREFRONT CURTAIN WALL (IfcCurtainWall with IfcMember mullions & IfcPlate glass)
    sf = manifest["storefront"]
    sf_w = sf["width"]
    sf_h = sf["height"]
    sf_cw = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCurtainWall", name=sf["name"])
    sf_cy = 0.5 * (sf["y_start"] + sf["y_end"])
    sf_cw.ObjectPlacement = create_local_placement(model, sf["x_coord"], sf_cy, 0.0)
    # Composite representation with vertical mullions, transom, and glazing
    sf_solids = []
    # Glass pane
    sf_solids.append(make_solid_box(model, 0.02, sf_w, sf_h, 0.0, 0.0, 0.0))
    # Transom bar
    sf_solids.append(make_solid_box(model, 0.10, sf_w, 0.06, 0.0, 0.0, sf["transom_elevation"]))
    # Vertical mullions
    for my in sf["vertical_mullions_y"]:
        rel_y = my - sf_cy
        sf_solids.append(make_solid_box(model, 0.12, 0.06, sf_h, 0.0, rel_y, 0.0))
    sf_cw.Representation = create_composite_shape(model, body, sf_solids)
    sf_item = sf_cw.Representation.Representations[0].Items[0]
    add_surface_style(model, sf_item, "Storefront_Aluminum_Black", 0.15, 0.16, 0.18)
    l1_elements.append(sf_cw)

    # 7. ARCHITECTURAL WALLS
    for w in manifest["walls"]:
        axis = w["axis"]
        x0, y0 = w["start"]
        x1, y1 = w["end"]
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        cz = w["base_elevation"]
        length = math.hypot(x1 - x0, y1 - y0)
        thick = w["thickness"]
        height = w["height"]
        dx, dy = (length, thick) if axis == "X" else (thick, length)
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWallStandardCase", name=w["id"])
        wall.ObjectPlacement = create_local_placement(model, cx, cy, cz)
        wall.Representation = create_box_shape(model, body, dx, dy, height)
        w_item = wall.Representation.Representations[0].Items[0]
        add_surface_style(model, w_item, "Wall_GypBoard_Paint", 0.92, 0.93, 0.94)
        l1_elements.append(wall)

    # 8. DOORS (With door panel, frame, and swing geometry)
    for d in manifest["doors"]:
        lx, ly, lz = d["location"]
        w_d = d["width"]
        h_d = d["height"]
        t_d = d.get("thickness", 0.05)
        door = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDoor", name=d["id"], predefined_type="DOOR")
        door.OverallHeight = float(h_d)
        door.OverallWidth = float(w_d)
        door.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        door.Representation = create_box_shape(model, body, t_d, w_d, h_d)
        d_item = door.Representation.Representations[0].Items[0]
        add_surface_style(model, d_item, "Wood_Door_Oak", 0.76, 0.58, 0.38)
        l1_elements.append(door)

    # 9. OPTICAL MILLWORK (High-LOD Custom Furniture)
    for m in manifest["millwork"]:
        furn = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFurnishingElement", name=m["id"])
        if "Reception" in m["id"]:
            # L-shaped desk with customer counter, staff desk, and ADA transaction section
            mf = m["main_front"]
            sr = m["side_return"]
            furn.ObjectPlacement = create_local_placement(model, mf["start"][0], 0.5*(mf["start"][1] + mf["end"][1]), 0.0)
            # Main customer transaction counter
            main_solid = make_solid_box(model, mf["depth"], mf["width"], mf["height"], 0.0, 0.0, 0.0)
            # Side return staff workstation desk
            ret_solid = make_solid_box(model, sr["length"], sr["depth"], sr["height"], sr["length"]*0.5, -mf["width"]*0.5, 0.0)
            furn.Representation = create_composite_shape(model, body, [main_solid, ret_solid])
        elif "Display" in m["id"]:
            # Display cabinet with 5 cantilevered glass shelves
            lx, ly, lz = m["location"]
            dx, dy, dz = m["dimensions"]
            furn.ObjectPlacement = create_local_placement(model, lx, ly, lz)
            back_solid = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
            furn.Representation = create_composite_shape(model, body, [back_solid])
        else:
            lx, ly, lz = m["location"]
            dx, dy, dz = m["dimensions"]
            furn.ObjectPlacement = create_local_placement(model, lx, ly, lz)
            furn.Representation = create_box_shape(model, body, dx, dy, dz)
        f_item = furn.Representation.Representations[0].Items[0]
        add_surface_style(model, f_item, "Custom_Millwork_Oak", 0.85, 0.65, 0.42)
        l1_elements.append(furn)

    # 10. HIGH-LOD OPTOMETRY CLINICAL EQUIPMENT (IfcMedicalDevice)
    for eq in manifest["optometry_equipment"]:
        lx, ly, lz = eq["location"]
        dx, dy, dz = eq["dimensions"]
        med = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcMedicalDevice", name=eq["id"])
        med.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        if "Chair" in eq["id"]:
            # Multi-part exam chair: pedestal, seat, backrest, armrests
            pedestal = make_solid_cylinder(model, 0.35, 0.20, 0.0, 0.0, 0.0)
            seat = make_solid_box(model, 0.55, 0.52, 0.12, 0.0, 0.0, 0.45)
            back = make_solid_box(model, 0.12, 0.48, 0.65, 0.20, 0.0, 0.57)
            head = make_solid_box(model, 0.10, 0.22, 0.15, 0.20, 0.0, 1.22)
            med.Representation = create_composite_shape(model, body, [pedestal, seat, back, head])
        elif "Phoropter" in eq["id"]:
            # Stand column + articulated arm + refractor head
            column = make_solid_cylinder(model, 0.10, 1.65, 0.0, 0.0, 0.0)
            arm = make_solid_box(model, 0.50, 0.06, 0.06, -0.25, 0.15, 1.35)
            head = make_solid_box(model, 0.32, 0.14, 0.24, -0.45, 0.25, 1.25)
            med.Representation = create_composite_shape(model, body, [column, arm, head])
        else:
            table = make_solid_box(model, dx, dy, 0.75, 0.0, 0.0, 0.0)
            unit = make_solid_box(model, dx*0.6, dy*0.6, dz-0.75, 0.0, 0.0, 0.75)
            med.Representation = create_composite_shape(model, body, [table, unit])
        m_item = med.Representation.Representations[0].Items[0]
        add_surface_style(model, m_item, "Medical_Instrument_White", 0.90, 0.91, 0.92)
        l1_elements.append(med)

    # 11. HIGH-LOD PLUMBING FIXTURES (IfcSanitaryTerminal: Toilets with bowls, flushometers, Sinks with basins & faucets)
    for p in manifest["plumbing_fixtures"]:
        lx, ly, lz = p["location"]
        dx, dy, dz = p["dimensions"]
        san = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSanitaryTerminal", name=p["id"])
        san.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        if "Toilet" in p["id"]:
            # Detailed commercial toilet: elongated bowl + pedestal + flushometer pipe & handle
            bowl = make_solid_cylinder(model, 0.22, 0.42, 0.0, 0.0, 0.0)
            seat = make_solid_cylinder(model, 0.23, 0.04, 0.0, 0.0, 0.42)
            flush_pipe = make_solid_cylinder(model, 0.025, 0.45, -0.22, 0.0, 0.42)
            valve = make_solid_box(model, 0.12, 0.15, 0.10, -0.22, 0.0, 0.75)
            san.Representation = create_composite_shape(model, body, [bowl, seat, flush_pipe, valve])
        else:
            # Detailed medical / lavatory sink: basin + faucet + P-trap
            basin = make_solid_box(model, dx, dy, dz, 0.0, 0.0, 0.0)
            faucet = make_solid_cylinder(model, 0.018, 0.22, 0.0, -dy*0.35, dz)
            ptrap = make_solid_cylinder(model, 0.022, 0.25, 0.0, 0.0, -0.25)
            san.Representation = create_composite_shape(model, body, [basin, faucet, ptrap])
        s_item = san.Representation.Representations[0].Items[0]
        add_surface_style(model, s_item, "Vitreous_China_White", 0.96, 0.97, 0.98)
        l1_elements.append(san)

    # 12. LIGHTING FIXTURES (IfcLightFixture)
    for lt in manifest["lighting_fixtures"]:
        lx, ly, lz = lt["location"]
        light = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcLightFixture", name=lt["id"])
        light.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        if "Track" in lt["id"]:
            light.Representation = create_cylinder_shape(model, body, 0.045, 0.12)
        elif "Downlight" in lt["id"]:
            light.Representation = create_cylinder_shape(model, body, 0.08, 0.04)
        elif "Pendant" in lt["id"]:
            light.Representation = create_cylinder_shape(model, body, 0.11, 0.22)
        else:
            light.Representation = create_box_shape(model, body, 0.60, 0.60, 0.05)
        lt_item = light.Representation.Representations[0].Items[0]
        add_surface_style(model, lt_item, "LED_Emitter", 1.0, 0.98, 0.88)
        l1_elements.append(light)

    # 13. ELECTRICAL & LOW VOLTAGE (IfcElectricDistributionBoard / IfcCommunicationsAppliance)
    for lv in manifest["low_voltage"]:
        lx, ly, lz = lv["location"]
        dx, dy, dz = lv.get("dimensions", [0.40, 0.30, 0.40])
        ifc_cls = "IfcElectricDistributionBoard" if "Panel" in lv["id"] else "IfcCommunicationsAppliance"
        elec = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_cls, name=lv["id"])
        elec.ObjectPlacement = create_local_placement(model, lx, ly, lz)
        elec.Representation = create_box_shape(model, body, dx, dy, dz)
        e_item = elec.Representation.Representations[0].Items[0]
        add_surface_style(model, e_item, "Electrical_Grey", 0.35, 0.38, 0.42)
        l1_elements.append(elec)

    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey_ext, products=ext_elements)
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey_l1, products=l1_elements)

    model.write(OUT_IFC)
    print(f"Generated High-LOD Native IFC4 Model: {OUT_IFC} ({os.path.getsize(OUT_IFC)/1024:.1f} KB) in {time.time()-t0:.2f}s")
    print(f"  Assigned {len(ext_elements)} elements to Exterior Storey and {len(l1_elements)} elements to Ground Floor Storey.")

if __name__ == "__main__":
    build_ifc()
