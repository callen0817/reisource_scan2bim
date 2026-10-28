# -*- coding: utf-8 -*-
"""
AV scanAR Executive Studio & Survey Lab — Procedural Blender BIM Builder & Renderer
Calibrated directly against ASTM E57 point cloud geometry and 360° panoramas:
- Accurate floor datum: Z = -0.570m
- Accurate ceiling datum: Z = 2.246m (clear height: 2.816m = 9' 3")
- True room boundary: West X=-2.52m, East X=+1.52m (4.04m), South Y=-1.08m, North Y=2.64m (3.72m)
- Cabinet on the WEST WALL (X=-2.68m, Y=1.45m, Z=-0.57m, height 1.92m, width 0.80m)
- Continuous engineering desk counter parallel to the North wall (length 3.15m, depth 0.55m)
- 2 collaborative peninsula tables extending perpendicular to the North wall along Y (X=-1.35m and X=+0.65m)
- Properly oriented monitors on desks (facing South) and peninsula tables (facing East/West)
- High-rise punched windows on South wall (Y=-1.08m) and cased portal entry on East wall (X=+1.52m)
- Recessed slot diffuser along North ceiling (drop Z=2.185m)
- 8 NavVis VLX-3 trajectory poses
- 1:1 reference point cloud overlay
"""

import os
import sys
import json
import math
import csv
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler, Quaternion
import numpy as np

WORKSPACE_DIR = r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar"
MANIFEST_PATH = os.path.join(WORKSPACE_DIR, "av_scanar_bim_manifest.json")
NPZ_PATH = os.path.join(WORKSPACE_DIR, "av_scanar_cloud.npz")
POSES_PATH = os.path.join(WORKSPACE_DIR, "panorama_test", "pano-poses.csv")
OUT_BLEND = os.path.join(WORKSPACE_DIR, "AV_scanAR_BIM.blend")
ARTIFACTS_DIR = r"C:\Users\calle\.gemini\antigravity\brain\aaea3624-ea7d-4e9e-9586-ba31bb2668f4"

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
            mat.blend_method = 'BLEND'
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

def build_scene():
    clear_scene()

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    # 1. Collections Setup
    col_slabs = get_or_create_collection("01_Floors_And_Ceilings")
    col_walls = get_or_create_collection("02_Walls_Architecture")
    col_openings = get_or_create_collection("03_Openings_Doors_Windows")
    col_runs = get_or_create_collection("04_Linear_MEP_And_Structure")
    col_furn = get_or_create_collection("05_Furniture_And_Equipment")
    col_light = get_or_create_collection("06_Lighting_And_Electrical")
    col_traj = get_or_create_collection("07_NavVis_Scanner_Trajectory")
    col_pc = get_or_create_collection("08_Reference_Point_Cloud")

    # 2. Materials
    mat_carpet = create_pbr_material("Carpet_Tile_Charcoal", (0.24, 0.25, 0.27, 1.0), roughness=0.88)
    mat_ceiling = create_pbr_material("Ceiling_Matte_White", (0.94, 0.94, 0.95, 1.0), roughness=0.65)
    mat_wall_int = create_pbr_material("Wall_Warm_Grey_Paint", (0.91, 0.91, 0.92, 1.0), roughness=0.55)
    mat_wall_ext = create_pbr_material("Wall_Architectural_Concrete", (0.86, 0.86, 0.84, 1.0), roughness=0.7)
    mat_wood = create_pbr_material("Wood_Oak_Casing", (0.64, 0.44, 0.26, 1.0), roughness=0.38)
    mat_black_steel = create_pbr_material("Metal_Black_Steel", (0.10, 0.10, 0.11, 1.0), metallic=0.85, roughness=0.32)
    mat_glass = create_pbr_material("Glass_LowE_Clear", (0.85, 0.92, 0.95, 0.18), transmission=0.92, roughness=0.08)
    mat_shade = create_pbr_material("Fabric_Roller_Shade", (0.82, 0.82, 0.80, 1.0), roughness=0.75)
    mat_exit = create_pbr_material("Exit_Sign_LED", (1.0, 0.1, 0.1, 1.0), emission_color=(1.0, 0.05, 0.05, 1.0), emission_strength=7.0)
    mat_downlight = create_pbr_material("Downlight_Diffuser", (0.98, 0.98, 0.95, 1.0), emission_color=(1.0, 0.96, 0.90, 1.0), emission_strength=4.0)
    mat_diffuser = create_pbr_material("Diffuser_Matte_White", (0.88, 0.88, 0.90, 1.0), roughness=0.45)
    mat_beam = create_pbr_material("Steel_Window_Lintel", (0.38, 0.42, 0.46, 1.0), metallic=0.75, roughness=0.4)
    mat_cabinet = create_pbr_material("Cabinet_Dark_Powdercoat", (0.18, 0.19, 0.21, 1.0), metallic=0.6, roughness=0.42)
    mat_desk_top = create_pbr_material("Desk_White_Oak", (0.80, 0.70, 0.54, 1.0), roughness=0.35)
    mat_desk_frame = create_pbr_material("Desk_White_Frame", (0.92, 0.92, 0.93, 1.0), roughness=0.4)
    mat_monitor = create_pbr_material("Monitor_Display_Sleek", (0.08, 0.08, 0.09, 1.0), metallic=0.5, roughness=0.25)
    mat_marker = create_pbr_material("NavVis_Trajectory_Cyan", (0.05, 0.75, 0.95, 1.0), emission_color=(0.0, 0.8, 1.0, 1.0), emission_strength=3.5)

    floor_z = -0.570
    clg_z = 2.246

    # 3. Floors & Ceilings
    for s in manifest.get("slabs", []):
        dx = s["x_max"] - s["x_min"]
        dy = s["y_max"] - s["y_min"]
        dz = s["thickness"]
        cx = 0.5 * (s["x_min"] + s["x_max"])
        cy = 0.5 * (s["y_min"] + s["y_max"])
        cz = s["elevation_top"] - dz
        add_box_object(s["id"], col_slabs, mat_carpet, cx, cy, cz, dx, dy, dz)

    for c in manifest.get("ceilings", []):
        dx = c["x_max"] - c["x_min"]
        dy = c["y_max"] - c["y_min"]
        dz = c["thickness"]
        cx = 0.5 * (c["x_min"] + c["x_max"])
        cy = 0.5 * (c["y_min"] + c["y_max"])
        cz = c["elevation"] - dz
        add_box_object(c["id"], col_slabs, mat_ceiling, cx, cy, cz, dx, dy, dz)

    # 4. Architectural Walls (Mitred corners matching point cloud)
    wall_objs = {}
    wall_meta = {}
    for w in manifest.get("walls", []):
        x0, y0 = w["start"]
        x1, y1 = w["end"]
        length = math.hypot(x1 - x0, y1 - y0)
        thick = float(w["thickness"])
        height = float(w["height"])
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        cz = w["base_elevation"]
        rot_z = math.atan2(y1 - y0, x1 - x0)

        mat_w = mat_wall_ext if "Exterior" in w["name"] else mat_wall_int
        w_obj = add_box_object(w["id"], col_walls, mat_w, cx, cy, cz, length, thick, height, rot_z=rot_z)
        wall_objs[w["id"]] = w_obj
        wall_meta[w["id"]] = {
            "rot_z": rot_z, "thick": thick, "cx": cx, "cy": cy,
            "ux": (x1 - x0) / length, "uy": (y1 - y0) / length
        }

    # 5. Openings (Doors & Windows with Boolean Cuts)
    for op in manifest.get("openings", []):
        host_id = op["host_wall"]
        host_wall = wall_objs.get(host_id)
        w_info = wall_meta.get(host_id)
        if not host_wall or not w_info:
            continue

        lx, ly, lz = op["location"]
        ow = op["width"]
        oh = op["height"]
        sill = op.get("sill_z", 0.0)
        rot_z = w_info["rot_z"]

        # Boolean Void Cutter
        cutter = add_box_object(f"Void_{op['id']}", col_openings, None, lx, ly, sill, ow, w_info["thick"] + 0.15, oh, rot_z=rot_z)
        cutter.hide_render = True
        cutter.display_type = 'WIRE'

        mod = host_wall.modifiers.new(name=f"Void_{op['id']}", type='BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = cutter

        if "Door" in op["id"]:
            # Wood Casing Portal
            casing_depth = op.get("casing_depth", 0.32)
            add_box_object(f"{op['id']}_Casing_Head", col_openings, mat_wood, lx, ly, sill + oh, ow + 0.16, casing_depth, 0.08, rot_z=rot_z)
            dx_j = math.cos(rot_z) * (ow * 0.5 + 0.04)
            dy_j = math.sin(rot_z) * (ow * 0.5 + 0.04)
            add_box_object(f"{op['id']}_Casing_Jamb_L", col_openings, mat_wood, lx - dx_j, ly - dy_j, sill, 0.08, casing_depth, oh + 0.08, rot_z=rot_z)
            add_box_object(f"{op['id']}_Casing_Jamb_R", col_openings, mat_wood, lx + dx_j, ly + dy_j, sill, 0.08, casing_depth, oh + 0.08, rot_z=rot_z)

            # Black Steel Frame
            add_box_object(f"{op['id']}_Steel_Frame_H", col_openings, mat_black_steel, lx, ly, sill + oh - 0.04, ow, 0.05, 0.04, rot_z=rot_z)
            add_box_object(f"{op['id']}_Steel_Frame_L", col_openings, mat_black_steel, lx - dx_j + 0.02, ly - dy_j, sill, 0.04, 0.05, oh, rot_z=rot_z)
            add_box_object(f"{op['id']}_Steel_Frame_R", col_openings, mat_black_steel, lx + dx_j - 0.02, ly + dy_j, sill, 0.04, 0.05, oh, rot_z=rot_z)

            # Glazed Pivot Leaf (slightly swung open 15 degrees)
            add_box_object(f"{op['id']}_Glass_Leaf", col_openings, mat_glass, lx, ly, sill + 0.02, ow - 0.08, 0.015, oh - 0.06, rot_z=rot_z + math.radians(15))
            add_cylinder_object(f"{op['id']}_Pull_Handle", col_openings, mat_black_steel, lx + 0.25, ly - 0.06, sill + 0.90, 0.015, 0.35)
        else:
            # Punched Window Assembly
            add_box_object(f"{op['id']}_Frame_Outer", col_openings, mat_black_steel, lx, ly, sill, ow, 0.12, oh, rot_z=rot_z)
            add_box_object(f"{op['id']}_Glazing", col_openings, mat_glass, lx, ly, sill + 0.05, ow - 0.10, 0.024, oh - 0.10, rot_z=rot_z)
            add_box_object(f"{op['id']}_Sill_Stool", col_openings, mat_wood, lx, ly, sill - 0.03, ow + 0.08, 0.22, 0.03, rot_z=rot_z)
            add_box_object(f"{op['id']}_Shade_Cassette", col_openings, mat_diffuser, lx, ly, sill + oh - 0.10, ow - 0.04, 0.09, 0.09, rot_z=rot_z)
            add_box_object(f"{op['id']}_Shade_Fabric", col_openings, mat_shade, lx, ly - 0.02, sill + oh * 0.55, ow - 0.06, 0.005, oh * 0.45, rot_z=rot_z)

    # 6. Linear MEP Runs & Structural Framing
    for run in manifest.get("linear_runs", []):
        sx, sy, sz = run["start"]
        ex, ey, ez = run["end"]
        length = math.hypot(ex - sx, ey - sy)
        rw = run.get("width", 0.15)
        rh = run.get("height", 0.10)
        cx = 0.5 * (sx + ex)
        cy = 0.5 * (sy + ey)
        cz = 0.5 * (sz + ez) - rh
        rot_z = math.atan2(ey - sy, ex - sx)

        if run["category"] == "duct":
            add_box_object(run["id"], col_runs, mat_diffuser, cx, cy, cz, length, rw, rh, rot_z=rot_z)
            add_box_object(f"{run['id']}_SlotVane", col_runs, mat_black_steel, cx, cy, cz + 0.01, length - 0.04, rw * 0.4, 0.02, rot_z=rot_z)
        else:
            add_box_object(run["id"], col_runs, mat_beam, cx, cy, cz, length, rw, rh, rot_z=rot_z)

    # 7. Furniture & Workstations (Exact Layout Calibrated to Point Cloud)
    for furn in manifest.get("furniture_and_equipment", []):
        lx, ly, lz = furn["location"]
        dx, dy, dz = furn["dimensions"]

        if "Cabinet" in furn["id"]:
            # CABINET ON WEST WALL
            add_box_object(furn["id"], col_furn, mat_cabinet, lx, ly, lz, dx, dy, dz)
            add_box_object(f"{furn['id']}_Seam", col_furn, mat_black_steel, lx + dx*0.5 + 0.005, ly, lz + 0.05, 0.005, 0.01, dz - 0.10)
            add_cylinder_object(f"{furn['id']}_Handle_L", col_furn, mat_black_steel, lx + dx*0.5 + 0.02, ly - 0.06, lz + 0.95, 0.012, 0.22)
            add_cylinder_object(f"{furn['id']}_Handle_R", col_furn, mat_black_steel, lx + dx*0.5 + 0.02, ly + 0.06, lz + 0.95, 0.012, 0.22)

        elif "Counter" in furn.get("category", "") or "Desk_North" in furn["id"]:
            # DESKS PARALLEL TO NORTH WALL
            # Oak top surface
            add_box_object(f"{furn['id']}_Top", col_furn, mat_desk_top, lx, ly, lz + dz - 0.035, dx, dy, 0.035)
            # Support frame / modesty panel along North wall
            add_box_object(f"{furn['id']}_Modesty", col_furn, mat_desk_frame, lx, ly + dy*0.5 - 0.02, lz, dx - 0.10, 0.025, dz - 0.035)
            # End legs
            add_box_object(f"{furn['id']}_Leg_L", col_furn, mat_desk_frame, lx - dx*0.5 + 0.05, ly, lz, 0.05, dy - 0.06, dz - 0.035)
            add_box_object(f"{furn['id']}_Leg_R", col_furn, mat_desk_frame, lx + dx*0.5 - 0.05, ly, lz, 0.05, dy - 0.06, dz - 0.035)
            # Intermediate support pedestals
            add_box_object(f"{furn['id']}_Pedestal", col_furn, mat_desk_frame, lx, ly, lz, 0.05, dy - 0.06, dz - 0.035)

        elif "Peninsula" in furn.get("category", "") or "Table_Peninsula" in furn["id"]:
            # 2 TABLES PERPENDICULAR TO NORTH WALL (Along Y)
            add_box_object(f"{furn['id']}_Top", col_furn, mat_desk_top, lx, ly, lz + dz - 0.035, dx, dy, 0.035)
            # Dual trestle legs at south and north ends
            add_box_object(f"{furn['id']}_Leg_South", col_furn, mat_desk_frame, lx, ly - dy*0.5 + 0.08, lz, dx - 0.10, 0.045, dz - 0.035)
            add_box_object(f"{furn['id']}_Leg_North", col_furn, mat_desk_frame, lx, ly + dy*0.5 - 0.08, lz, dx - 0.10, 0.045, dz - 0.035)
            # Center stretcher beam
            add_box_object(f"{furn['id']}_Stretcher", col_furn, mat_desk_frame, lx, ly, lz + 0.15, 0.04, dy - 0.30, 0.04)

        elif "Display" in furn.get("category", "") or "Monitor" in furn["id"]:
            # MONITORS WITH EXACT ORIENTATIONS
            facing = furn.get("facing", "South")
            rot_mon = 0.0
            if facing == "East":
                rot_mon = math.pi * 0.5
            elif facing == "West":
                rot_mon = -math.pi * 0.5
            elif facing == "North":
                rot_mon = math.pi

            # Display Screen
            add_box_object(furn["id"], col_furn, mat_monitor, lx, ly, lz, dx, dy, dz, rot_z=rot_mon)
            # Stand column and base
            add_box_object(f"{furn['id']}_StandCol", col_furn, mat_black_steel, lx, ly, lz - 0.08, 0.04, 0.04, 0.08, rot_z=rot_mon)
            add_box_object(f"{furn['id']}_StandBase", col_furn, mat_black_steel, lx, ly, lz - 0.08, 0.22, 0.18, 0.015, rot_z=rot_mon)

    # 8. Lighting & Life Safety
    for lt in manifest.get("lighting_and_electrical", []):
        lx, ly, lz = lt["location"]
        if "Exit" in lt["id"]:
            dx, dy, dz = lt.get("dimensions", [0.32, 0.06, 0.18])
            add_box_object(lt["id"], col_light, mat_exit, lx, ly, lz, dx, dy, dz)
            l_data = bpy.data.lights.new(name=f"{lt['id']}_Glow", type='POINT')
            l_data.color = (1.0, 0.05, 0.05)
            l_data.energy = 25.0
            l_obj = bpy.data.objects.new(name=f"{lt['id']}_Glow", object_data=l_data)
            col_light.objects.link(l_obj)
            l_obj.location = (lx, ly, lz - 0.05)
        else:
            add_cylinder_object(lt["id"], col_light, mat_downlight, lx, ly, lz - 0.03, 0.09, 0.03)
            l_data = bpy.data.lights.new(name=f"{lt['id']}_Spot", type='SPOT')
            l_data.color = (1.0, 0.96, 0.90)
            l_data.energy = 450.0
            l_data.spot_size = math.radians(75)
            l_data.spot_blend = 0.35
            l_obj = bpy.data.objects.new(name=f"{lt['id']}_Spot", object_data=l_data)
            col_light.objects.link(l_obj)
            l_obj.location = (lx, ly, lz - 0.05)
            l_obj.rotation_euler = (math.pi, 0, 0)

    # 9. NavVis Scanner Trajectory Poses (Visualized as cyan sensor markers)
    if os.path.exists(POSES_PATH):
        with open(POSES_PATH, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            pose_idx = 0
            for row in reader:
                if not row or len(row) < 8:
                    continue
                tx, ty, tz = float(row[1]), float(row[2]), float(row[3])
                add_cylinder_object(f"NavVis_Pano_{pose_idx:02d}", col_traj, mat_marker, tx, ty, tz - 0.05, 0.08, 0.10)
                add_cylinder_object(f"NavVis_Mast_{pose_idx:02d}", col_traj, mat_black_steel, tx, ty, floor_z, 0.015, tz - floor_z)
                pose_idx += 1

    # 10. Reference Point Cloud Overlay (QC validation)
    if os.path.exists(NPZ_PATH):
        data_pc = np.load(NPZ_PATH)
        xyz_pc = data_pc["xyz"]
        # Filter to room bounds
        mask_pc = (xyz_pc[:, 0] >= -3.0) & (xyz_pc[:, 0] <= 1.8) & \
                  (xyz_pc[:, 1] >= -1.3) & (xyz_pc[:, 1] <= 2.8) & \
                  (xyz_pc[:, 2] >= floor_z - 0.1) & (xyz_pc[:, 2] <= clg_z + 0.1)
        sub_xyz = xyz_pc[mask_pc][::8]
        pc_mesh = bpy.data.meshes.new("PointCloud_Reference_Mesh")
        pc_mesh.from_pydata(sub_xyz.tolist(), [], [])
        pc_mesh.update()
        pc_obj = bpy.data.objects.new("PointCloud_Reference", pc_mesh)
        col_pc.objects.link(pc_obj)
        pc_obj.hide_render = True

    # 11. Environment & Lighting
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in dir(bpy.types.RenderSettings) or hasattr(scene.render, "engine") and "BLENDER_EEVEE_NEXT" in [e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items] else "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False

    # Exterior Daylight Sun through South Windows
    sun_data = bpy.data.lights.new(name="Sun_Exterior_Daylight", type='SUN')
    sun_data.color = (0.95, 0.98, 1.0)
    sun_data.energy = 5.5
    sun_obj = bpy.data.objects.new(name="Sun_Exterior_Daylight", object_data=sun_data)
    col_light.objects.link(sun_obj)
    sun_obj.location = (-0.5, -6.0, 4.0)
    sun_obj.rotation_euler = (math.radians(60), math.radians(12), math.radians(8))

    # Ambient Room Fill Light
    fill_data = bpy.data.lights.new(name="Fill_Interior", type='POINT')
    fill_data.color = (0.95, 0.96, 0.98)
    fill_data.energy = 400.0
    fill_obj = bpy.data.objects.new(name="Fill_Interior", object_data=fill_data)
    col_light.objects.link(fill_obj)
    fill_obj.location = (-0.5, 0.8, 1.5)

    # 12. Cinematic Camera Viewpoints (Targeting Exact Layout)
    cameras = [
        {
            "name": "Cam_01_Room_Overview_Desks_Peninsulas",
            "loc": (-0.50, -0.65, 1.40),
            "rot": (math.radians(78), 0.0, math.radians(0)),
            "out": os.path.join(WORKSPACE_DIR, "av_scanar_render_01_interior_overview.png"),
            "art": os.path.join(ARTIFACTS_DIR, "av_scanar_render_01_interior_overview.png")
        },
        {
            "name": "Cam_02_West_Wall_Cabinet_Closeup",
            "loc": (-1.10, 1.45, 1.35),
            "rot": (math.radians(85), 0.0, math.radians(90)),
            "out": os.path.join(WORKSPACE_DIR, "av_scanar_render_02_entry_portal_exit_sign.png"),
            "art": os.path.join(ARTIFACTS_DIR, "av_scanar_render_02_entry_portal_exit_sign.png")
        },
        {
            "name": "Cam_03_South_Windows_And_Facade",
            "loc": (-0.50, 2.00, 1.35),
            "rot": (math.radians(82), 0.0, math.radians(180)),
            "out": os.path.join(WORKSPACE_DIR, "av_scanar_render_03_punched_windows_workstations.png"),
            "art": os.path.join(ARTIFACTS_DIR, "av_scanar_render_03_punched_windows_workstations.png")
        },
        {
            "name": "Cam_04_Axonometric_Cutaway_Point_Cloud_Match",
            "loc": (-4.50, -3.50, 4.80),
            "rot": (math.radians(52), 0.0, math.radians(-50)),
            "out": os.path.join(WORKSPACE_DIR, "av_scanar_render_04_axonometric_cutaway.png"),
            "art": os.path.join(ARTIFACTS_DIR, "av_scanar_render_04_axonometric_cutaway.png")
        }
    ]

    for c in cameras:
        cam_data = bpy.data.cameras.new(c["name"])
        cam_data.lens = 20.0  # Wide architectural lens
        cam_obj = bpy.data.objects.new(c["name"], cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
        cam_obj.location = c["loc"]
        cam_obj.rotation_euler = c["rot"]
        scene.camera = cam_obj
        scene.render.filepath = c["out"]
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {c['out']}")

        if os.path.exists(c["out"]):
            import shutil
            shutil.copy2(c["out"], c["art"])
            print(f"  Copied to artifact: {c['art']}")

    # 13. Save Blend File
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    print(f"Successfully saved high-LOD Blender BIM model to {OUT_BLEND}")

if __name__ == "__main__":
    build_scene()
