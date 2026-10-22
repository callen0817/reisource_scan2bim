import os
import sys
import json
import math
import bpy
import bmesh
from mathutils import Vector, Matrix
import numpy as np

MANIFEST_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\eyesonpark_bim_manifest.json"
NPZ_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\eyesonpark_cloud.npz"
OUT_BLEND = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark\EyesonPark_Scan2BIM.blend"
RENDER_DIR = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark"

def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for cam in list(bpy.data.cameras):
        bpy.data.cameras.remove(cam)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)

def get_or_create_collection(name, parent=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(col)
    else:
        parent.children.link(col)
    return col

def tag_bim_properties(obj, ifc_class, predefined_type, category, name=None):
    obj["IFC_Class"] = ifc_class
    obj["PredefinedType"] = predefined_type
    obj["BIM_Category"] = category
    if name:
        obj["BIM_Name"] = name

def create_pbr_material(name, rgba, metallic=0.0, roughness=0.5, transmission=0.0, emission_color=None, emission_strength=0.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.diffuse_color = rgba
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = rgba
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = transmission
        if emission_color and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_color
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
        if rgba[3] < 1.0 and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = rgba[3]
    return mat

def add_box_object(name, collection, mat, cx, cy, cz_bottom, dx, dy, dz, rot_z=0.0):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dx
        v.co.y *= dy
        v.co.z = (v.co.z + 0.5) * dz
    bm.to_mesh(mesh)
    bm.free()

    obj.location = (cx, cy, cz_bottom)
    obj.rotation_euler = (0, 0, rot_z)
    if mat:
        obj.data.materials.append(mat)
    return obj

def add_cylinder_object(name, collection, mat, cx, cy, cz_bottom, radius, height, rot_x=0.0, rot_y=0.0, rot_z=0.0):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)

    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=radius, radius2=radius, depth=height)
    for v in bm.verts:
        v.co.z += height * 0.5
    bm.to_mesh(mesh)
    bm.free()

    obj.location = (cx, cy, cz_bottom)
    obj.rotation_euler = (rot_x, rot_y, rot_z)
    if mat:
        obj.data.materials.append(mat)
    return obj

# ----------------- HIGH-LOD GEOMETRIC BUILDERS -----------------

def build_contoured_toilet(p_id, collection, mat_ceramic, mat_chrome, mat_seat, lx, ly, lz):
    # Vitreous china elongated bowl
    bowl_mesh = bpy.data.meshes.new(f"{p_id}_Bowl_Mesh")
    bowl_obj = bpy.data.objects.new(f"{p_id}_Elongated_Bowl", bowl_mesh)
    collection.objects.link(bowl_obj)
    tag_bim_properties(bowl_obj, "IfcSanitaryTerminal", "WC_SEAT", "Plumbing Fixtures", "ADA Flushometer Water Closet")

    bm = bmesh.new()
    # Pedestal foot
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.18, radius2=0.15, depth=0.25)
    for v in bm.verts:
        v.co.z += 0.125
        v.co.x += 0.05
    # Upper bowl flare
    bm_bowl = bmesh.new()
    bmesh.ops.create_cone(bm_bowl, cap_ends=True, cap_tris=False, segments=20, radius1=0.22, radius2=0.18, depth=0.22)
    for v in bm_bowl.verts:
        v.co.z += 0.35
        v.co.x += 0.12
    # Rim ring
    bmesh.ops.create_cone(bm_bowl, cap_ends=True, cap_tris=False, segments=20, radius1=0.23, radius2=0.23, depth=0.05)
    for v in bm_bowl.verts:
        if v.co.z < 0.20:
            v.co.z += 0.44
            v.co.x += 0.12
    bm_bowl.to_mesh(bowl_mesh)
    bm_bowl.free()
    bm.free()
    bowl_obj.location = (lx, ly, lz)
    bowl_obj.data.materials.append(mat_ceramic)

    # Seat ring & lid
    add_box_object(f"{p_id}_Seat_Ring", collection, mat_seat, lx + 0.12, ly, lz + 0.46, 0.46, 0.38, 0.03)
    add_box_object(f"{p_id}_Seat_Lid", collection, mat_seat, lx - 0.10, ly, lz + 0.48, 0.04, 0.38, 0.42)

    # Commercial chrome flushometer valve & piping
    add_cylinder_object(f"{p_id}_Flush_Pipe_Vertical", collection, mat_chrome, lx - 0.16, ly, lz + 0.48, 0.02, 0.42)
    add_cylinder_object(f"{p_id}_Flush_Pipe_WallSupply", collection, mat_chrome, lx - 0.26, ly, lz + 0.85, 0.02, 0.20, rot_y=math.pi*0.5)
    add_cylinder_object(f"{p_id}_Flush_Valve_Body", collection, mat_chrome, lx - 0.16, ly, lz + 0.82, 0.045, 0.08)
    add_box_object(f"{p_id}_Flush_Handle", collection, mat_chrome, lx - 0.16, ly - 0.12, lz + 0.84, 0.02, 0.12, 0.02)

    # ADA Stainless Steel Wall Grab Bars
    # Rear 36" grab bar
    add_cylinder_object(f"{p_id}_GrabBar_Rear", collection, mat_chrome, lx - 0.35, ly, lz + 0.86, 0.02, 0.91, rot_x=math.pi*0.5)
    # Side 42" grab bar along wall (North wall of restroom)
    add_cylinder_object(f"{p_id}_GrabBar_Side", collection, mat_chrome, lx + 0.10, ly + 0.65, lz + 0.86, 0.02, 1.06, rot_y=math.pi*0.5)

def build_lavatory_sink(p_id, collection, mat_ceramic, mat_chrome, mat_glass, lx, ly, lz, is_restroom=False):
    # Vitreous china wall-hung basin
    basin_obj = add_box_object(f"{p_id}_Basin", collection, mat_ceramic, lx, ly, lz, 0.50, 0.45, 0.20)
    tag_bim_properties(basin_obj, "IfcSanitaryTerminal", "WASHHANDBASIN", "Plumbing Fixtures", "Wall-Hung Lavatory Sink")

    # Front curved apron cutout effect (inner basin recess)
    inner_basin = add_box_object(f"{p_id}_Inner_Recess", collection, mat_ceramic, lx, ly, lz + 0.06, 0.42, 0.36, 0.14)

    # Chrome gooseneck sensor faucet
    add_cylinder_object(f"{p_id}_Faucet_Base", collection, mat_chrome, lx, ly + 0.14, lz + 0.20, 0.025, 0.06)
    add_cylinder_object(f"{p_id}_Faucet_Spout", collection, mat_chrome, lx, ly + 0.06, lz + 0.25, 0.015, 0.14, rot_x=math.radians(35))

    # P-trap chrome waste pipe underneath
    add_cylinder_object(f"{p_id}_PTrap_Vert", collection, mat_chrome, lx, ly, lz - 0.16, 0.02, 0.16)
    add_cylinder_object(f"{p_id}_PTrap_Horiz", collection, mat_chrome, lx, ly + 0.12, lz - 0.16, 0.02, 0.24, rot_x=math.pi*0.5)

    if is_restroom:
        # Commercial Restroom Mirror with Stainless Frame above sink
        mirror_obj = add_box_object(f"{p_id}_Wall_Mirror", collection, mat_glass, lx, ly + 0.22, lz + 0.50, 0.60, 0.02, 0.90)
        tag_bim_properties(mirror_obj, "IfcFurnishingElement", "USERDEFINED", "Specialties", "Restroom ADA Mirror")
        # Soap dispenser
        add_box_object(f"{p_id}_Soap_Dispenser", collection, mat_chrome, lx - 0.35, ly + 0.20, lz + 0.40, 0.12, 0.10, 0.22)

def build_exam_chair(eq_id, collection, mat_chair, mat_chrome, lx, ly, lz, rot_z=0.0):
    # Base Pedestal Disc
    base_obj = add_cylinder_object(f"{eq_id}_Base_Plate", collection, mat_chrome, lx, ly, lz, 0.38, 0.06)
    tag_bim_properties(base_obj, "IfcMedicalDevice", "USERDEFINED", "Specialty Equipment", "Motorized Optometry Exam Chair")

    # Hydraulic Lift Cylinder Column
    add_cylinder_object(f"{eq_id}_Hydraulic_Column", collection, mat_chrome, lx, ly, lz + 0.06, 0.12, 0.38)

    # Metal Footrest Assembly
    add_box_object(f"{eq_id}_Footrest", collection, mat_chrome, lx - 0.35, ly, lz + 0.15, 0.32, 0.36, 0.04)
    add_box_object(f"{eq_id}_Footrest_Bracket", collection, mat_chrome, lx - 0.15, ly, lz + 0.22, 0.25, 0.08, 0.04)

    # Ergonomic Contoured Seat Cushion
    add_box_object(f"{eq_id}_Seat_Cushion", collection, mat_chair, lx, ly, lz + 0.44, 0.55, 0.52, 0.12)

    # Lumbar Support Backrest with Bolsters
    add_box_object(f"{eq_id}_Backrest", collection, mat_chair, lx + 0.25, ly, lz + 0.56, 0.12, 0.48, 0.68)

    # Articulated Headrest on dual chrome poles
    add_cylinder_object(f"{eq_id}_Headrest_Poles", collection, mat_chrome, lx + 0.25, ly, lz + 1.22, 0.015, 0.15)
    add_box_object(f"{eq_id}_Headrest_Pillow", collection, mat_chair, lx + 0.24, ly, lz + 1.30, 0.09, 0.24, 0.16)

    # Dual Padded Armrests
    for s_y in [-0.29, 0.29]:
        add_box_object(f"{eq_id}_Armrest_{s_y}", collection, mat_chair, lx, ly + s_y, lz + 0.68, 0.40, 0.08, 0.06)
        add_cylinder_object(f"{eq_id}_Arm_Support_{s_y}", collection, mat_chrome, lx + 0.15, ly + s_y, lz + 0.48, 0.02, 0.22)

def build_phoropter_stand(eq_id, collection, mat_instrument, mat_chrome, lx, ly, lz):
    # Heavy Cast Base
    base_obj = add_cylinder_object(f"{eq_id}_Cast_Base", collection, mat_instrument, lx, ly, lz, 0.28, 0.08)
    tag_bim_properties(base_obj, "IfcMedicalDevice", "USERDEFINED", "Specialty Equipment", "Articulated Phoropter Stand")

    # Tall Vertical Column
    add_cylinder_object(f"{eq_id}_Main_Column", collection, mat_instrument, lx, ly, lz + 0.08, 0.07, 1.65)

    # Counterbalanced Horizontal Articulated Arm
    add_box_object(f"{eq_id}_Articulated_Arm", collection, mat_chrome, lx - 0.26, ly + 0.12, lz + 1.45, 0.55, 0.07, 0.08)

    # Phoropter Dual Ocular Refractor Head
    # Main ocular body housing
    head_obj = add_box_object(f"{eq_id}_Refractor_Body", collection, mat_instrument, lx - 0.48, ly + 0.28, lz + 1.32, 0.32, 0.14, 0.24)
    # Left and Right Ocular Apertures
    for eye_y in [-0.07, 0.07]:
        add_cylinder_object(f"{eq_id}_Ocular_{eye_y}", collection, mat_chrome, lx - 0.50, ly + 0.28 + eye_y, lz + 1.30, 0.035, 0.08, rot_y=math.pi*0.5)
    # Rotary Dials & Forehead Rest
    add_cylinder_object(f"{eq_id}_Knob_Left", collection, mat_chrome, lx - 0.48, ly + 0.44, lz + 1.40, 0.03, 0.04, rot_x=math.pi*0.5)
    add_cylinder_object(f"{eq_id}_Knob_Right", collection, mat_chrome, lx - 0.48, ly + 0.12, lz + 1.40, 0.03, 0.04, rot_x=math.pi*0.5)
    add_box_object(f"{eq_id}_Forehead_Rest", collection, mat_instrument, lx - 0.42, ly + 0.28, lz + 1.42, 0.04, 0.18, 0.03)

    # Overhead Exam Light on Flexible Neck
    add_cylinder_object(f"{eq_id}_Lamp_Pole", collection, mat_chrome, lx, ly, lz + 1.73, 0.02, 0.35)
    add_box_object(f"{eq_id}_Lamp_Shade", collection, mat_instrument, lx - 0.15, ly + 0.10, lz + 2.05, 0.22, 0.12, 0.10)

def build_slit_lamp_station(eq_id, collection, mat_instrument, mat_chrome, mat_table, lx, ly, lz):
    # Motorized Table Column & Base
    base_obj = add_box_object(f"{eq_id}_Table_Base", collection, mat_instrument, lx, ly, lz, 0.65, 0.50, 0.08)
    tag_bim_properties(base_obj, "IfcMedicalDevice", "USERDEFINED", "Specialty Equipment", "Slit Lamp Biomicroscope Station")
    add_cylinder_object(f"{eq_id}_Lift_Column", collection, mat_chrome, lx, ly, lz + 0.08, 0.08, 0.64)

    # Rounded Workstation Tabletop
    add_box_object(f"{eq_id}_Tabletop", collection, mat_table, lx, ly, lz + 0.72, 0.90, 0.60, 0.04)

    # Chin Rest Assembly (Dual Vertical Chrome Rods + Chin Cup + Forehead Strap)
    add_cylinder_object(f"{eq_id}_Chin_Post_Left", collection, mat_chrome, lx - 0.18, ly - 0.12, lz + 0.76, 0.012, 0.35)
    add_cylinder_object(f"{eq_id}_Chin_Post_Right", collection, mat_chrome, lx - 0.18, ly + 0.12, lz + 0.76, 0.012, 0.35)
    add_box_object(f"{eq_id}_Chin_Cup", collection, mat_instrument, lx - 0.18, ly, lz + 0.92, 0.06, 0.10, 0.03)
    add_box_object(f"{eq_id}_Forehead_Bar", collection, mat_instrument, lx - 0.18, ly, lz + 1.08, 0.04, 0.26, 0.03)

    # Biomicroscope Optics & Slit Tower
    add_box_object(f"{eq_id}_Glide_Plate", collection, mat_chrome, lx + 0.10, ly, lz + 0.76, 0.28, 0.24, 0.03)
    add_cylinder_object(f"{eq_id}_Joystick", collection, mat_chrome, lx + 0.20, ly, lz + 0.79, 0.012, 0.12)
    # Stereo Eyepieces
    add_box_object(f"{eq_id}_Microscope_Body", collection, mat_instrument, lx + 0.06, ly, lz + 0.92, 0.16, 0.18, 0.15)
    add_cylinder_object(f"{eq_id}_Eyepiece_L", collection, mat_chrome, lx + 0.16, ly - 0.04, lz + 0.98, 0.02, 0.08, rot_y=math.radians(60))
    add_cylinder_object(f"{eq_id}_Eyepiece_R", collection, mat_chrome, lx + 0.16, ly + 0.04, lz + 0.98, 0.02, 0.08, rot_y=math.radians(60))
    # Vertical Illumination Slit Tower
    add_cylinder_object(f"{eq_id}_Illum_Tower", collection, mat_instrument, lx - 0.04, ly, lz + 0.90, 0.035, 0.30)

def build_visual_field_perimeter(eq_id, collection, mat_instrument, mat_table, lx, ly, lz):
    # Console Cart
    cart_obj = add_box_object(f"{eq_id}_Cart", collection, mat_table, lx, ly, lz, 0.85, 0.65, 0.75)
    tag_bim_properties(cart_obj, "IfcMedicalDevice", "USERDEFINED", "Specialty Equipment", "Automated Visual Field Perimeter")

    # Perimeter Testing Bowl / Enclosure
    dome_mesh = bpy.data.meshes.new(f"{eq_id}_Bowl_Mesh")
    dome_obj = bpy.data.objects.new(f"{eq_id}_Hemispherical_Bowl", dome_mesh)
    collection.objects.link(dome_obj)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=24, radius1=0.28, radius2=0.28, depth=0.45)
    bm.to_mesh(dome_mesh)
    bm.free()
    dome_obj.location = (lx, ly, lz + 0.98)
    dome_obj.rotation_euler = (0, math.pi*0.5, 0)
    dome_obj.data.materials.append(mat_instrument)

    # Patient Viewport & Chin rest
    add_box_object(f"{eq_id}_Patient_Visor", collection, mat_instrument, lx - 0.28, ly, lz + 0.98, 0.12, 0.26, 0.22)

def build_autorefractor_station(eq_id, collection, mat_instrument, mat_table, lx, ly, lz):
    # Dual instrument table
    table_obj = add_box_object(f"{eq_id}_Dual_Table", collection, mat_table, lx, ly, lz, 1.35, 0.70, 0.76)
    tag_bim_properties(table_obj, "IfcMedicalDevice", "USERDEFINED", "Specialty Equipment", "Autorefractor & Keratometer Station")

    # Instrument 1: Autorefractor with LCD Screen
    add_box_object(f"{eq_id}_Autorefractor_Body", collection, mat_instrument, lx - 0.35, ly, lz + 0.76, 0.45, 0.36, 0.38)
    add_box_object(f"{eq_id}_LCD_Screen", collection, mat_instrument, lx - 0.20, ly, lz + 0.95, 0.03, 0.22, 0.18)

    # Instrument 2: Non-Contact Tonometer
    add_box_object(f"{eq_id}_Tonometer_Body", collection, mat_instrument, lx + 0.35, ly, lz + 0.76, 0.42, 0.34, 0.36)

def build_reception_desk(col_mill, mat_oak, mat_quartz, mat_laminate, r_info):
    # Custom L-Shaped Reception & Cashier Desk matching the scan footprint exactly
    # Main front section (X=2.00, Y in [-1.6, 0.2])
    mf = r_info.get("main_front", {})
    sr = r_info.get("side_return", {})
    ada = r_info.get("ada_section", {})

    # 1. Main High Transaction Counter (Y in [-1.6, -0.3])
    # Fluted Oak Front Base
    base_high = add_box_object("Millwork_Reception_Front_High_Base", col_mill, mat_oak, 2.00, -0.95, 0.0, 0.70, 1.30, 1.05)
    tag_bim_properties(base_high, "IfcFurnishingElement", "USERDEFINED", "Casework", "Reception Transaction Counter")
    # Calacatta Quartz Transaction Top
    add_box_object("Millwork_Reception_Front_High_Countertop", col_mill, mat_quartz, 1.95, -0.95, 1.05, 0.40, 1.35, 0.05)

    # 2. ADA Lowered Transaction Counter (Y in [-0.3, 0.2])
    base_ada = add_box_object("Millwork_Reception_Front_ADA_Base", col_mill, mat_oak, 2.00, -0.05, 0.0, 0.70, 0.50, 0.82)
    tag_bim_properties(base_ada, "IfcFurnishingElement", "USERDEFINED", "Casework", "Reception ADA Lowered Counter")
    add_box_object("Millwork_Reception_Front_ADA_Countertop", col_mill, mat_quartz, 1.95, -0.05, 0.82, 0.40, 0.55, 0.05)

    # 3. Interior Worksurface behind front desk (Z=0.76)
    add_box_object("Millwork_Reception_Worksurface", col_mill, mat_laminate, 2.22, -0.70, 0.72, 0.55, 1.70, 0.04)

    # 4. Side Return Counter (Y = -1.60, X in [2.00, 3.20])
    base_ret = add_box_object("Millwork_Reception_Return_Base", col_mill, mat_oak, 2.60, -1.60, 0.0, 1.20, 0.65, 0.72)
    tag_bim_properties(base_ret, "IfcFurnishingElement", "USERDEFINED", "Casework", "Reception Side Return Counter")
    add_box_object("Millwork_Reception_Return_Top", col_mill, mat_quartz, 2.60, -1.60, 0.72, 1.25, 0.70, 0.04)

    # Under-counter drawer pedestal
    add_box_object("Millwork_Reception_Drawer_Pedestal", col_mill, mat_laminate, 3.00, -1.55, 0.08, 0.42, 0.52, 0.60)

def build_optical_display_wall(m_id, col_mill, mat_cabinet, mat_glass, mat_led, lx, ly, lz, dx, dy, dz, shelves_count=5):
    # Main casework backboard & enclosure
    body = add_box_object(f"{m_id}_Casework", col_mill, mat_cabinet, lx, ly, lz, dx, dy, dz)
    tag_bim_properties(body, "IfcFurnishingElement", "USERDEFINED", "Casework", "Illuminated Optical Frame Display")

    # Plinth base
    add_box_object(f"{m_id}_Plinth", col_mill, mat_cabinet, lx, ly, lz, dx, dy, 0.12)

    # Vertical LED reveal channels along the rear of display
    led_y = ly - 0.14 if ly > 0 else ly + 0.14
    add_box_object(f"{m_id}_LED_Channel_Left", col_mill, mat_led, lx - dx*0.42, led_y, lz + 0.20, 0.04, 0.02, dz - 0.35)
    add_box_object(f"{m_id}_LED_Channel_Right", col_mill, mat_led, lx + dx*0.42, led_y, lz + 0.20, 0.04, 0.02, dz - 0.35)
    add_box_object(f"{m_id}_LED_Channel_Center", col_mill, mat_led, lx, led_y, lz + 0.20, 0.04, 0.02, dz - 0.35)

    # Cantilevered Tempered Glass Shelves
    glass_y = ly - 0.08 if ly > 0 else ly + 0.08
    for i in range(1, shelves_count + 1):
        sh_z = lz + 0.25 + (dz - 0.40) * (i / (shelves_count + 1))
        # Glass shelf pane
        add_box_object(f"{m_id}_Shelf_{i}", col_mill, mat_glass, lx, glass_y, sh_z, dx * 0.94, dy * 0.70, 0.015)

def build_door_leaf_and_frame(d_info, col_arch, mat_door, mat_frame, mat_hardware, mat_glass):
    d_id = d_info["id"]
    lx, ly, lz = d_info["location"]
    w = d_info["width"]
    h = d_info["height"]
    t = d_info.get("thickness", 0.05)
    swing = d_info.get("swing_direction", "")

    # Door Frame (3-sided perimeter jamb)
    # Left jamb
    jamb_l = add_box_object(f"{d_id}_Jamb_L", col_arch, mat_frame, lx, ly - w*0.5, lz, 0.12, 0.05, h)
    tag_bim_properties(jamb_l, "IfcDoor", "DOOR", "Doors", d_info.get("name", "Door"))
    # Right jamb
    add_box_object(f"{d_id}_Jamb_R", col_arch, mat_frame, lx, ly + w*0.5, lz, 0.12, 0.05, h)
    # Header
    add_box_object(f"{d_id}_Header", col_arch, mat_frame, lx, ly, lz + h, 0.12, w + 0.10, 0.06)

    # Determine Door Leaf Angle & Hinge Position
    # Render door leaf slightly open (25 degrees) to show realistic swing
    if "Storefront" in d_id:
        # Commercial storefront glass door swinging inward
        rot = math.radians(25)
        leaf = add_box_object(f"{d_id}_Leaf_Frame", col_arch, mat_frame, lx + math.sin(rot)*w*0.5, ly - w*0.5 + math.cos(rot)*w*0.5, lz, 0.06, w - 0.08, h - 0.04, rot_z=rot)
        add_box_object(f"{d_id}_Glass_Panel", col_arch, mat_glass, lx + math.sin(rot)*w*0.5, ly - w*0.5 + math.cos(rot)*w*0.5, lz + 0.15, 0.015, w - 0.22, h - 0.30, rot_z=rot)
        # Horizontal panic push bar
        add_box_object(f"{d_id}_Panic_Bar", col_arch, mat_hardware, lx + math.sin(rot)*w*0.5 + 0.03, ly - w*0.5 + math.cos(rot)*w*0.5, lz + 1.05, 0.04, w * 0.75, 0.04, rot_z=rot)
    elif "Closet" in d_id:
        # Storage closet door at X=8.00 swinging outward into hallway
        rot = math.radians(-35)
        add_box_object(f"{d_id}_Leaf", col_arch, mat_door, lx + math.sin(rot)*w*0.5, ly - w*0.5 + math.cos(rot)*w*0.5, lz, t, w - 0.04, h - 0.02, rot_z=rot)
        # Lever handle
        add_cylinder_object(f"{d_id}_Lever", col_arch, mat_hardware, lx + math.sin(rot)*w*0.85, ly - w*0.5 + math.cos(rot)*w*0.85, lz + 1.0, 0.015, 0.12, rot_x=math.pi*0.5)
    elif "Restroom" in d_id:
        # Commercial ADA Restroom door swinging outward into corridor
        rot = math.radians(30)
        add_box_object(f"{d_id}_Leaf", col_arch, mat_door, lx - math.sin(rot)*w*0.5, ly - w*0.5 + math.cos(rot)*w*0.5, lz, t, w - 0.04, h - 0.02, rot_z=-rot)
        # ADA lever handle & privacy indicator
        add_cylinder_object(f"{d_id}_Lever", col_arch, mat_hardware, lx - math.sin(rot)*w*0.85, ly - w*0.5 + math.cos(rot)*w*0.85, lz + 1.0, 0.015, 0.12, rot_x=math.pi*0.5)
        add_box_object(f"{d_id}_Privacy_Indicator", col_arch, mat_hardware, lx - 0.03, ly, lz + 1.10, 0.02, 0.08, 0.08)
    else:
        # Exam Room doors swinging inward against partitions
        rot = math.radians(25) if "Exam_Room_1" in d_id else math.radians(-25)
        add_box_object(f"{d_id}_Leaf", col_arch, mat_door, lx + math.sin(rot)*w*0.5, ly - w*0.5 + math.cos(rot)*w*0.5, lz, t, w - 0.04, h - 0.02, rot_z=rot)
        add_cylinder_object(f"{d_id}_Lever", col_arch, mat_hardware, lx + math.sin(rot)*w*0.85, ly - w*0.5 + math.cos(rot)*w*0.85, lz + 1.0, 0.015, 0.12, rot_x=math.pi*0.5)

# ----------------- MAIN SCENE BUILDER -----------------

def build_eyesonpark_scene():
    clear_scene()

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    # Root and semantic BIM collections
    col_root = get_or_create_collection("EyesonPark_BIM")
    col_pc = get_or_create_collection("00_PointCloud_Reference", col_root)
    col_ext = get_or_create_collection("01_Exterior_Sidewalk_Ramp_Awning", col_root)
    col_sf = get_or_create_collection("02_Storefront_Glazing_And_Mullions", col_root)
    col_walls = get_or_create_collection("03_Architectural_Walls_And_Partitions", col_root)
    col_floors = get_or_create_collection("04_Architectural_Floors", col_root)
    col_ceil = get_or_create_collection("05_Suspended_And_Exposed_Ceilings", col_root)
    col_doors = get_or_create_collection("06_Doors_And_Hardware", col_root)
    col_mill = get_or_create_collection("07_Optical_Millwork_And_Displays", col_root)
    col_equip = get_or_create_collection("08_Optometry_Clinical_Equipment", col_root)
    col_plumb = get_or_create_collection("09_Plumbing_Fixtures", col_root)
    col_light = get_or_create_collection("10_Lighting_And_Ceiling_Fixtures", col_root)
    col_lv = get_or_create_collection("11_Electrical_And_LowVoltage", col_root)

    # Materials
    mat_sidewalk = create_pbr_material("MAT_Sidewalk_Concrete", (0.62, 0.63, 0.65, 1.0), roughness=0.7)
    mat_ramp = create_pbr_material("MAT_Ramp_Concrete", (0.68, 0.69, 0.72, 1.0), roughness=0.6)
    mat_railing = create_pbr_material("MAT_Stainless_Steel", (0.85, 0.86, 0.88, 1.0), metallic=0.9, roughness=0.2)
    mat_awning_fab = create_pbr_material("MAT_Awning_Fabric_Navy", (0.08, 0.16, 0.35, 1.0), roughness=0.85)
    mat_awning_frm = create_pbr_material("MAT_Awning_Frame_Black", (0.15, 0.15, 0.16, 1.0), metallic=0.8, roughness=0.3)
    mat_sf_glass = create_pbr_material("MAT_Storefront_Glass", (0.85, 0.92, 0.98, 0.30), roughness=0.08, transmission=0.88)
    mat_sf_mullion = create_pbr_material("MAT_Storefront_Mullion_Black", (0.12, 0.12, 0.14, 1.0), metallic=0.85, roughness=0.25)
    mat_floor_retail = create_pbr_material("MAT_Floor_Retail_Terrazzo", (0.84, 0.80, 0.74, 1.0), metallic=0.05, roughness=0.35)
    mat_floor_clinic = create_pbr_material("MAT_Floor_Clinic_SheetVinyl", (0.88, 0.89, 0.90, 1.0), metallic=0.0, roughness=0.45)
    mat_wall = create_pbr_material("MAT_Wall_Paint_OffWhite", (0.92, 0.93, 0.94, 1.0), roughness=0.55)
    mat_door = create_pbr_material("MAT_Door_Natural_Oak", (0.75, 0.55, 0.35, 1.0), roughness=0.45)
    mat_frame = create_pbr_material("MAT_Frame_Anodized_Bronze", (0.28, 0.25, 0.22, 1.0), metallic=0.7, roughness=0.3)
    mat_disp_white = create_pbr_material("MAT_Optical_Display_Lacquer_White", (0.96, 0.96, 0.97, 1.0), roughness=0.2)
    mat_disp_oak = create_pbr_material("MAT_Wood_Fluted_Oak", (0.78, 0.58, 0.36, 1.0), roughness=0.4)
    mat_quartz = create_pbr_material("MAT_Countertop_Calacatta_Quartz", (0.94, 0.94, 0.95, 1.0), roughness=0.15)
    mat_chair = create_pbr_material("MAT_Medical_Leather_Charcoal", (0.18, 0.20, 0.24, 1.0), roughness=0.5)
    mat_chair_seat = create_pbr_material("MAT_Toilet_Seat_Polypropylene", (0.92, 0.93, 0.95, 1.0), roughness=0.25)
    mat_instrument = create_pbr_material("MAT_Medical_Instrument_White", (0.90, 0.91, 0.92, 1.0), metallic=0.2, roughness=0.25)
    mat_chrome = create_pbr_material("MAT_Chrome_Plated_Steel", (0.92, 0.93, 0.94, 1.0), metallic=0.95, roughness=0.15)
    mat_ceramic = create_pbr_material("MAT_Vitreous_China_White", (0.95, 0.96, 0.98, 1.0), roughness=0.15)
    mat_light_led = create_pbr_material("MAT_LED_Emitter_Luminance", (1.0, 0.96, 0.88, 1.0), roughness=0.2, emission_color=(1.0, 0.96, 0.88, 1.0), emission_strength=5.0)
    mat_ceiling_ac = create_pbr_material("MAT_Acoustic_Ceiling_Tile", (0.93, 0.94, 0.95, 0.4), roughness=0.6)
    mat_elec = create_pbr_material("MAT_Electrical_Panel_Grey", (0.35, 0.38, 0.42, 1.0), metallic=0.6, roughness=0.35)

    # 1. FLOORS & SLABS (Correct Classification: IfcSlab / FLOOR)
    for s in manifest["slabs"]:
        dx = s["x_max"] - s["x_min"]
        dy = s["y_max"] - s["y_min"]
        dz = s["thickness"]
        cx = 0.5 * (s["x_min"] + s["x_max"])
        cy = 0.5 * (s["y_min"] + s["y_max"])
        cz = s["elevation_top"] - dz
        if "Sidewalk" in s["type"]:
            obj = add_box_object(s["id"], col_ext, mat_sidewalk, cx, cy, cz, dx, dy, dz)
            tag_bim_properties(obj, "IfcSlab", "BASESLAB", "Floors", s["name"])
        elif "Clinical" in s["name"]:
            obj = add_box_object(s["id"], col_floors, mat_floor_clinic, cx, cy, cz, dx, dy, dz)
            tag_bim_properties(obj, "IfcSlab", "FLOOR", "Floors", s["name"])
        else:
            obj = add_box_object(s["id"], col_floors, mat_floor_retail, cx, cy, cz, dx, dy, dz)
            tag_bim_properties(obj, "IfcSlab", "FLOOR", "Floors", s["name"])

    # 2. CEILINGS (Correct Classification: IfcCovering / CEILING - Never Structural)
    for c in manifest.get("ceilings", []):
        dx = c["x_max"] - c["x_min"]
        dy = c["y_max"] - c["y_min"]
        dz = c["thickness"]
        cx = 0.5 * (c["x_min"] + c["x_max"])
        cy = 0.5 * (c["y_min"] + c["y_max"])
        cz = c["elevation"]
        c_obj = add_box_object(c["id"], col_ceil, mat_ceiling_ac, cx, cy, cz, dx, dy, dz)
        tag_bim_properties(c_obj, "IfcCovering", "CEILING", "Ceilings", c["name"])
        c_obj.hide_viewport = True
        c_obj.hide_render = True

    # 3. EXTERIOR ADA RAMP, CURBS & LANDINGS
    rmp = manifest["ramp"]
    sx, sy, sz = rmp["start_point"]
    ex, ey, ez = rmp["end_point"]
    r_dy = rmp["width"]
    hw = r_dy * 0.5
    curb_w = 0.10
    curb_h = rmp.get("curb_height", 0.10)

    # Sloped Ramp Run
    mesh_ramp = bpy.data.meshes.new("Ramp_ADA_Run_Mesh")
    obj_ramp = bpy.data.objects.new("Ramp_ADA_Run", mesh_ramp)
    col_ext.objects.link(obj_ramp)
    tag_bim_properties(obj_ramp, "IfcRampFlight", "STRAIGHT", "Ramps", "ADA Accessibility Ramp Run")
    bm_r = bmesh.new()
    v0 = bm_r.verts.new((sx, sy - hw, sz))
    v1 = bm_r.verts.new((sx, sy + hw, sz))
    v2 = bm_r.verts.new((ex, sy + hw, ez))
    v3 = bm_r.verts.new((ex, sy - hw, ez))
    v4 = bm_r.verts.new((sx, sy - hw, sz - 0.15))
    v5 = bm_r.verts.new((sx, sy + hw, sz - 0.15))
    v6 = bm_r.verts.new((ex, sy + hw, ez - 0.15))
    v7 = bm_r.verts.new((ex, sy - hw, ez - 0.15))
    bm_r.faces.new((v3, v2, v1, v0))
    bm_r.faces.new((v4, v5, v6, v7))
    bm_r.faces.new((v0, v1, v5, v4))
    bm_r.faces.new((v1, v2, v6, v5))
    bm_r.faces.new((v2, v3, v7, v6))
    bm_r.faces.new((v3, v0, v4, v7))
    bmesh.ops.recalc_face_normals(bm_r, faces=bm_r.faces)
    bm_r.to_mesh(mesh_ramp)
    bm_r.free()
    obj_ramp.data.materials.append(mat_ramp)

    # Ramp Side Curbs (North and South)
    for c_sign, c_name in [(-1, "South"), (1, "North")]:
        cy_pos = sy + c_sign * (hw + curb_w*0.5)
        # Curb run
        curb_mesh = bpy.data.meshes.new(f"Ramp_Curb_{c_name}_Mesh")
        curb_obj = bpy.data.objects.new(f"Ramp_Curb_{c_name}", curb_mesh)
        col_ext.objects.link(curb_obj)
        tag_bim_properties(curb_obj, "IfcRamp", "USERDEFINED", "Ramps", f"ADA Edge Protection Curb {c_name}")
        bm_c = bmesh.new()
        cv0 = bm_c.verts.new((sx, cy_pos - curb_w*0.5, sz))
        cv1 = bm_c.verts.new((sx, cy_pos + curb_w*0.5, sz))
        cv2 = bm_c.verts.new((ex, cy_pos + curb_w*0.5, ez))
        cv3 = bm_c.verts.new((ex, cy_pos - curb_w*0.5, ez))
        cv4 = bm_c.verts.new((sx, cy_pos - curb_w*0.5, sz + curb_h))
        cv5 = bm_c.verts.new((sx, cy_pos + curb_w*0.5, sz + curb_h))
        cv6 = bm_c.verts.new((ex, cy_pos + curb_w*0.5, ez + curb_h))
        cv7 = bm_c.verts.new((ex, cy_pos - curb_w*0.5, ez + curb_h))
        bm_c.faces.new((cv3, cv2, cv1, cv0))
        bm_c.faces.new((cv4, cv5, cv6, cv7))
        bm_c.faces.new((cv0, cv1, cv5, cv4))
        bm_c.faces.new((cv1, cv2, cv6, cv5))
        bm_c.faces.new((cv2, cv3, cv7, cv6))
        bm_c.faces.new((cv3, cv0, cv4, cv7))
        bmesh.ops.recalc_face_normals(bm_c, faces=bm_c.faces)
        bm_c.to_mesh(curb_mesh)
        bm_c.free()
        curb_obj.data.materials.append(mat_ramp)

    # Threshold Landing at Top
    land_top = add_box_object("Ramp_Threshold_Landing", col_ext, mat_ramp, 0.12 - 0.35, sy, ez - 0.15, 0.70, r_dy + curb_w*2, 0.15)
    tag_bim_properties(land_top, "IfcSlab", "LANDING", "Ramps", "ADA Door Threshold Landing")

    # 4. ADA DUAL CONTINUOUS HANDRAILS (Upper 0.95m & Lower 0.45m)
    for rl in manifest["railings"]:
        rx0, ry0, rz0 = rl["start"]
        rx1, ry1, rz1 = rl["end"]
        n_posts = rl["posts_count"]
        h_upper = rl.get("height_upper", 0.95)
        h_lower = rl.get("height_lower", 0.45)

        # Stanchion Posts
        for pi in range(n_posts):
            frac = pi / (n_posts - 1)
            px = rx0 + (rx1 - rx0) * frac
            pz = rz0 + (rz1 - rz0) * frac
            post_obj = add_cylinder_object(f"{rl['id']}_Post_{pi+1}", col_ext, mat_railing, px, ry0, pz, 0.022, h_upper)
            tag_bim_properties(post_obj, "IfcRailing", "GUARDRAIL", "Railings", "Handrail Stanchion Post")

        # Upper Continuous Handrail
        rl_len = math.hypot(rx1 - rx0, rz1 - rz0)
        rl_angle = math.atan2(rz1 - rz0, rx1 - rx0)
        for h_rail, r_label in [(h_upper, "Upper"), (h_lower, "Lower")]:
            rail_mesh = bpy.data.meshes.new(f"{rl['id']}_{r_label}_Mesh")
            rail_obj = bpy.data.objects.new(f"{rl['id']}_Rail_{r_label}", rail_mesh)
            col_ext.objects.link(rail_obj)
            tag_bim_properties(rail_obj, "IfcRailing", "HANDRAIL", "Railings", f"ADA Continuous Handrail ({r_label})")
            bm_rail = bmesh.new()
            bmesh.ops.create_cone(bm_rail, cap_ends=True, cap_tris=False, segments=12, radius1=0.022, radius2=0.022, depth=rl_len)
            for v in bm_rail.verts:
                v.co.z += rl_len * 0.5
            bm_rail.to_mesh(rail_mesh)
            bm_rail.free()
            rail_obj.location = (rx0, ry0, rz0 + h_rail)
            rail_obj.rotation_euler = (math.pi * 0.5, rl_angle + math.pi * 0.5, 0.0)
            rail_obj.data.materials.append(mat_railing)

    # 5. EXTERIOR AWNING CANOPY (Classification: IfcShadingDevice / AWNING)
    aw = manifest["awning"]
    aw_x0, aw_x1 = aw["x_front"], aw["x_back"]
    aw_y0, aw_y1 = aw["y_min"], aw["y_max"]
    aw_z0, aw_z1 = aw["z_front"], aw["z_back"]
    v_drop = aw.get("valance_drop", 0.30)

    aw_mesh = bpy.data.meshes.new("Awning_Canopy_Mesh")
    aw_obj = bpy.data.objects.new("Awning_Commercial_Canopy", aw_mesh)
    col_ext.objects.link(aw_obj)
    tag_bim_properties(aw_obj, "IfcShadingDevice", "AWNING", "Awnings", aw["name"])
    bm_aw = bmesh.new()
    # 4 roof corners
    av0 = bm_aw.verts.new((aw_x0, aw_y0, aw_z0))
    av1 = bm_aw.verts.new((aw_x0, aw_y1, aw_z0))
    av2 = bm_aw.verts.new((aw_x1, aw_y1, aw_z1))
    av3 = bm_aw.verts.new((aw_x1, aw_y0, aw_z1))
    # Front valance drop
    av4 = bm_aw.verts.new((aw_x0, aw_y0, aw_z0 - v_drop))
    av5 = bm_aw.verts.new((aw_x0, aw_y1, aw_z0 - v_drop))
    # Side triangular endcaps
    bm_aw.faces.new((av3, av2, av1, av0)) # Sloped roof
    bm_aw.faces.new((av0, av1, av5, av4)) # Front valance
    bm_aw.faces.new((av3, av0, av4))       # South triangle
    bm_aw.faces.new((av1, av2, av5))       # North triangle
    bmesh.ops.recalc_face_normals(bm_aw, faces=bm_aw.faces)
    bm_aw.to_mesh(aw_mesh)
    bm_aw.free()
    aw_obj.data.materials.append(mat_awning_fab)

    # Awning support metal outrigger trusses
    for aw_y in aw.get("outriggers_y", [-3.7, -1.65, 0.4, 2.4]):
        outr = add_box_object(f"Awning_Outrigger_{aw_y:.1f}", col_ext, mat_awning_frm, 0.5 * (aw_x0 + aw_x1), aw_y, aw_z0, abs(aw_x1 - aw_x0), 0.05, 0.05)
        tag_bim_properties(outr, "IfcMember", "USERDEFINED", "Awnings", "Awning Structural Outrigger Arm")

    # 6. STOREFRONT CURTAIN WALL & MULLIONS (Classification: IfcCurtainWall, IfcMember, IfcPlate)
    sf = manifest["storefront"]
    sf_x = sf["x_coord"]
    sf_y0, sf_y1 = sf["y_start"], sf["y_end"]
    sf_w = sf["width"]
    sf_h = sf["height"]
    m_prof = sf.get("mullion_profile", [0.05, 0.12])
    v_mulls = sf.get("vertical_mullions_y", [-3.95, -1.85, 0.12, 1.15, 2.05, 3.75])
    t_elev = sf.get("transom_elevation", 2.20)

    # Perimeter Storefront Curtain Wall
    sf_cw = add_box_object("Storefront_Glazing_System", col_sf, mat_sf_glass, sf_x, 0.5 * (sf_y0 + sf_y1), 0.35, 0.02, sf_w, sf_h - 0.35)
    tag_bim_properties(sf_cw, "IfcCurtainWall", "USERDEFINED", "Curtain Walls", "Storefront Aluminum Glazing System")

    # Vertical Mullions
    for my in v_mulls:
        m_obj = add_box_object(f"Storefront_Mullion_Y_{my:.2f}", col_sf, mat_sf_mullion, sf_x, my, 0.0, m_prof[1], m_prof[0], sf_h)
        tag_bim_properties(m_obj, "IfcMember", "MULLION", "Curtain Wall Mullions", "Storefront Vertical Mullion")

    # Horizontal Transom Bar
    trans_obj = add_box_object("Storefront_Transom_Bar", col_sf, mat_sf_mullion, sf_x, 0.5 * (sf_y0 + sf_y1), t_elev, m_prof[1], sf_w, m_prof[0])
    tag_bim_properties(trans_obj, "IfcMember", "TRANSOM", "Curtain Wall Mullions", "Storefront Horizontal Transom")

    # 7. ARCHITECTURAL WALLS (16 Clean Scan-Calibrated Partitions)
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
        w_obj = add_box_object(w["id"], col_walls, mat_wall, cx, cy, cz, dx, dy, height)
        tag_bim_properties(w_obj, "IfcWall", "SOLIDWALL", "Walls", w["name"])

    # 8. DOORS (All 5 Doors with Correct Swings, Hinges & Hardware)
    for d in manifest["doors"]:
        build_door_leaf_and_frame(d, col_doors, mat_door, mat_frame, mat_railing, mat_sf_glass)

    # 9. OPTICAL MILLWORK & CUSTOM RECEPTION
    for m in manifest["millwork"]:
        if "Reception" in m["id"]:
            build_reception_desk(col_mill, mat_disp_oak, mat_quartz, mat_disp_white, m)
        elif "Display" in m["id"]:
            lx, ly, lz = m["location"]
            dx, dy, dz = m["dimensions"]
            build_optical_display_wall(m["id"], col_mill, mat_disp_white, mat_sf_glass, mat_light_led, lx, ly, lz, dx, dy, dz, m.get("shelves_count", 5))
        elif "Dispensing" in m["id"]:
            lx, ly, lz = m["location"]
            dx, dy, dz = m["dimensions"]
            dt_top = add_box_object(m["id"] + "_Top", col_mill, mat_disp_oak, lx, ly, lz + 0.72, dx, dy, 0.04)
            tag_bim_properties(dt_top, "IfcFurnishingElement", "USERDEFINED", "Furniture", m["name"])
            for lx_leg in [-dx * 0.45, dx * 0.45]:
                for ly_leg in [-dy * 0.40, dy * 0.40]:
                    add_cylinder_object(f"{m['id']}_Leg_{lx_leg}_{ly_leg}", col_mill, mat_awning_frm, lx + lx_leg, ly + ly_leg, lz, 0.025, 0.72)

    # 10. OPTOMETRY CLINICAL EQUIPMENT
    for eq in manifest["optometry_equipment"]:
        eq_id = eq["id"]
        lx, ly, lz = eq["location"]
        if "Chair" in eq_id:
            build_exam_chair(eq_id, col_equip, mat_chair, mat_chrome, lx, ly, lz)
        elif "Phoropter" in eq_id:
            build_phoropter_stand(eq_id, col_equip, mat_instrument, mat_chrome, lx, ly, lz)
        elif "Slit_Lamp" in eq_id:
            build_slit_lamp_station(eq_id, col_equip, mat_instrument, mat_chrome, mat_disp_white, lx, ly, lz)
        elif "Visual_Field" in eq_id:
            build_visual_field_perimeter(eq_id, col_equip, mat_instrument, mat_disp_white, lx, ly, lz)
        elif "Autorefractor" in eq_id:
            build_autorefractor_station(eq_id, col_equip, mat_instrument, mat_disp_white, lx, ly, lz)
        elif "Doctor_Desk" in eq_id:
            dx, dy, dz = eq["dimensions"]
            dd_top = add_box_object(eq_id + "_DeskTop", col_equip, mat_disp_oak, lx, ly, lz + 0.72, dx, dy, 0.04)
            tag_bim_properties(dd_top, "IfcFurnishingElement", "USERDEFINED", "Furniture", eq["name"])
            add_box_object(eq_id + "_Drawers", col_equip, mat_disp_white, lx + dx*0.35, ly, lz, dx*0.30, dy*0.85, 0.72)
            # Acuity Monitor
            add_box_object(eq_id + "_Monitor", col_equip, mat_awning_frm, lx, ly, lz + 0.76, 0.06, 0.55, 0.35)

    # 11. PLUMBING FIXTURES (Toilets, Sinks & ADA Trim)
    for p in manifest["plumbing_fixtures"]:
        p_id = p["id"]
        lx, ly, lz = p["location"]
        if "Toilet" in p_id:
            build_contoured_toilet(p_id, col_plumb, mat_ceramic, mat_chrome, mat_chair_seat, lx, ly, lz)
        else:
            is_rr = "Restroom" in p_id
            build_lavatory_sink(p_id, col_plumb, mat_ceramic, mat_chrome, mat_sf_glass, lx, ly, lz, is_restroom=is_rr)

    # 12. LIGHTING FIXTURES
    for lt in manifest["lighting_fixtures"]:
        lx, ly, lz = lt["location"]
        lt_id = lt["id"]
        if "Track" in lt_id:
            obj = add_cylinder_object(lt_id, col_light, mat_awning_frm, lx, ly, lz, 0.045, 0.12)
            add_cylinder_object(lt_id + "_Spot", col_light, mat_light_led, lx, ly, lz - 0.04, 0.035, 0.02)
            tag_bim_properties(obj, "IfcLightFixture", "DIRECTIONAL", "Lighting Fixtures", lt.get("name", lt_id))
        elif "Downlight" in lt_id:
            obj = add_cylinder_object(lt_id, col_light, mat_light_led, lx, ly, lz, 0.075, 0.03)
            tag_bim_properties(obj, "IfcLightFixture", "POINT", "Lighting Fixtures", lt.get("name", lt_id))
        elif "Pendant" in lt_id:
            add_cylinder_object(lt_id + "_Cord", col_light, mat_awning_frm, lx, ly, lz, 0.005, 1.15)
            obj = add_cylinder_object(lt_id + "_Shade", col_light, mat_awning_frm, lx, ly, lz, 0.11, 0.22)
            add_cylinder_object(lt_id + "_Bulb", col_light, mat_light_led, lx, ly, lz - 0.05, 0.06, 0.05)
            tag_bim_properties(obj, "IfcLightFixture", "USERDEFINED", "Lighting Fixtures", lt.get("name", lt_id))
        else:
            dx, dy, dz = lt.get("dimensions", [0.60, 0.60, 0.05])
            obj = add_box_object(lt_id, col_light, mat_light_led, lx, ly, lz, dx, dy, dz)
            tag_bim_properties(obj, "IfcLightFixture", "USERDEFINED", "Lighting Fixtures", lt.get("name", lt_id))

    # 13. ELECTRICAL & LOW VOLTAGE
    for lv in manifest["low_voltage"]:
        lx, ly, lz = lv["location"]
        dx, dy, dz = lv.get("dimensions", [0.40, 0.30, 0.40])
        obj = add_box_object(lv["id"], col_lv, mat_elec, lx, ly, lz, dx, dy, dz)
        tag_bim_properties(obj, "IfcElectricDistributionBoard", "USERDEFINED", "Electrical Equipment", lv.get("name", lv["id"]))

    # 14. POINT CLOUD REFERENCE MESH (1:1 QC overlay)
    if os.path.exists(NPZ_PATH):
        print("Linking colorized reference point cloud...")
        data_pc = np.load(NPZ_PATH)
        xyz_pc = data_pc["xyz"][::20]
        pc_mesh = bpy.data.meshes.new("PointCloud_EyesOnPark_Ref_Mesh")
        pc_mesh.from_pydata(xyz_pc.tolist(), [], [])
        pc_mesh.update()
        pc_obj = bpy.data.objects.new("PointCloud_EyesOnPark_Reference", pc_mesh)
        col_pc.objects.link(pc_obj)
        pc_obj.hide_render = True

    # 15. CAMERAS & CINEMATIC RENDERING SETUP
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False

    # Sun / Environment Light
    sun_data = bpy.data.lights.new(name="Sun_Exterior", type='SUN')
    sun_data.energy = 4.0
    sun_obj = bpy.data.objects.new(name="Sun_Exterior", object_data=sun_data)
    col_ext.objects.link(sun_obj)
    sun_obj.location = (-10.0, 5.0, 12.0)
    sun_obj.rotation_euler = (math.radians(45), math.radians(25), math.radians(-50))

    # Interior Multi-Room Lighting (Even, Professional Architectural Illumination)
    room_lights = [
        ("Light_Showroom", (3.5, 0.0, 2.8), 2000.0),
        ("Light_Reception", (2.2, -0.7, 2.6), 1200.0),
        ("Light_Corridor", (8.5, 0.5, 2.4), 1000.0),
        ("Light_Exam1", (13.2, -2.6, 2.4), 1500.0),
        ("Light_Exam2", (13.2, 2.5, 2.4), 1500.0),
        ("Light_Restroom", (14.8, -0.3, 2.4), 1000.0),
    ]
    for l_name, l_pos, l_energy in room_lights:
        l_data = bpy.data.lights.new(name=l_name, type='POINT')
        l_data.energy = l_energy
        l_data.shadow_soft_size = 0.3
        l_obj = bpy.data.objects.new(name=l_name, object_data=l_data)
        col_light.objects.link(l_obj)
        l_obj.location = l_pos

    # Viewpoints
    cameras = [
        {
            "name": "Cam_01_Exterior_Storefront_Ramp",
            "loc": (-5.80, -3.20, 1.70),
            "rot": (math.radians(78), 0.0, math.radians(-57)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_01_exterior_storefront_awning_ramp.png"),
        },
        {
            "name": "Cam_02_Retail_Showroom_Millwork",
            "loc": (0.60, 0.50, 1.55),
            "rot": (math.radians(86), 0.0, math.radians(-90)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_02_retail_showroom_displays_reception.png"),
        },
        {
            "name": "Cam_03_Clinical_Exam_Rooms_Cutaway",
            "loc": (10.50, 5.80, 5.20),
            "rot": (math.radians(52), 0.0, math.radians(-145)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_03_clinical_exam_rooms_equipment.png"),
        },
        {
            "name": "Cam_04_Corridor_Restroom_Closet",
            "loc": (7.00, 0.50, 1.55),
            "rot": (math.radians(86), 0.0, math.radians(-90)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_04_corridor_restroom_closet.png"),
        },
        {
            "name": "Cam_05_Restroom_Plumbing_Fixtures",
            "loc": (14.05, 0.15, 1.35),
            "rot": (math.radians(68), 0.0, math.radians(-145)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_05_restroom_plumbing_fixtures.png"),
        },
        {
            "name": "Cam_06_Exam1_Clinical_Instruments",
            "loc": (11.80, -1.60, 1.50),
            "rot": (math.radians(75), 0.0, math.radians(-140)),
            "out": os.path.join(RENDER_DIR, "eyesonpark_render_06_exam1_clinical_instruments.png"),
        },
    ]

    for c_info in cameras:
        cam_data = bpy.data.cameras.new(c_info["name"])
        cam_data.lens = 24.0 # Wide angle for interior architectural space
        cam_obj = bpy.data.objects.new(c_info["name"], cam_data)
        col_root.objects.link(cam_obj)
        cam_obj.location = c_info["loc"]
        cam_obj.rotation_euler = c_info["rot"]
        scene.camera = cam_obj
        scene.render.filepath = c_info["out"]
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {c_info['out']}")

    # Save Blend file
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    print(f"Saved complete High-LOD Eyes on Park Scan2BIM Blender model to {OUT_BLEND}")

if __name__ == "__main__":
    build_eyesonpark_scene()
