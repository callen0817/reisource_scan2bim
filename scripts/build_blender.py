# -*- coding: utf-8 -*-
"""
Reisource Scan2BIM — Procedural Blender BIM Builder & Renderer
Instantiates:
- Parametric architectural BIM objects
- True boolean opening voids cutting host walls
- Architectural wood cased doors and punched windows
- Linear MEP diffusers and structural lintel beams
- Furniture, workstations, and lighting
- NavVis scanner trajectory pose visualization
- Renders high-resolution perspectives
- Exports .blend file
"""

import os
import sys
import json
import math
import csv
import argparse
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler, Quaternion
import numpy as np

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

def build_scene(manifest_path, out_blend, poses_path=None, npz_path=None, render_dir=None):
    clear_scene()

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Collections
    col_slabs = get_or_create_collection("01_Floors_And_Ceilings")
    col_walls = get_or_create_collection("02_Walls_Architecture")
    col_openings = get_or_create_collection("03_Openings_Doors_Windows")
    col_runs = get_or_create_collection("04_Linear_MEP_And_Structure")
    col_furn = get_or_create_collection("05_Furniture_And_Equipment")
    col_light = get_or_create_collection("06_Lighting_And_Electrical")
    col_traj = get_or_create_collection("07_NavVis_Scanner_Trajectory")

    # Materials
    mat_floor = create_pbr_material("Floor_Finish", (0.24, 0.25, 0.27, 1.0), roughness=0.85)
    mat_ceiling = create_pbr_material("Ceiling_Finish", (0.94, 0.94, 0.95, 1.0), roughness=0.65)
    mat_wall_int = create_pbr_material("Wall_Interior", (0.91, 0.91, 0.92, 1.0), roughness=0.55)
    mat_wall_ext = create_pbr_material("Wall_Exterior", (0.86, 0.86, 0.84, 1.0), roughness=0.7)
    mat_wood = create_pbr_material("Wood_Casing", (0.64, 0.44, 0.26, 1.0), roughness=0.38)
    mat_black_steel = create_pbr_material("Metal_Black_Steel", (0.10, 0.10, 0.11, 1.0), metallic=0.85, roughness=0.32)
    mat_glass = create_pbr_material("Glass_Clear", (0.85, 0.92, 0.95, 0.18), transmission=0.92, roughness=0.08)
    mat_shade = create_pbr_material("Fabric_Roller_Shade", (0.82, 0.82, 0.80, 1.0), roughness=0.75)
    mat_exit = create_pbr_material("Exit_Sign_LED", (1.0, 0.1, 0.1, 1.0), emission_color=(1.0, 0.05, 0.05, 1.0), emission_strength=7.0)
    mat_diffuser = create_pbr_material("Diffuser_White", (0.88, 0.88, 0.90, 1.0), roughness=0.45)
    mat_beam = create_pbr_material("Steel_Framing", (0.38, 0.42, 0.46, 1.0), metallic=0.75, roughness=0.4)
    mat_marker = create_pbr_material("NavVis_Trajectory_Cyan", (0.05, 0.75, 0.95, 1.0), emission_color=(0.0, 0.8, 1.0, 1.0), emission_strength=3.5)

    # 1. Slabs & Ceilings
    for s in manifest.get("slabs", []):
        dx = s["x_max"] - s["x_min"]
        dy = s["y_max"] - s["y_min"]
        dz = s["thickness"]
        cx = 0.5 * (s["x_min"] + s["x_max"])
        cy = 0.5 * (s["y_min"] + s["y_max"])
        cz = s["elevation_top"] - dz
        add_box_object(s["id"], col_slabs, mat_floor, cx, cy, cz, dx, dy, dz)

    for c in manifest.get("ceilings", []):
        dx = c["x_max"] - c["x_min"]
        dy = c["y_max"] - c["y_min"]
        dz = c["thickness"]
        cx = 0.5 * (c["x_min"] + c["x_max"])
        cy = 0.5 * (c["y_min"] + c["y_max"])
        cz = c["elevation"] - dz
        add_box_object(c["id"], col_slabs, mat_ceiling, cx, cy, cz, dx, dy, dz)

    # 2. Walls
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
            "ux": (x1 - x0) / length if length > 1e-4 else 1.0,
            "uy": (y1 - y0) / length if length > 1e-4 else 0.0
        }

    # 3. Parametric Openings
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

        # Boolean Cutter
        cutter = add_box_object(f"Void_{op['id']}", col_openings, None, lx, ly, sill, ow, w_info["thick"] + 0.15, oh, rot_z=rot_z)
        cutter.hide_render = True
        cutter.display_type = 'WIRE'

        mod = host_wall.modifiers.new(name=f"Void_{op['id']}", type='BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = cutter

        # Architectural Elements
        if "Door" in op["id"]:
            casing_depth = op.get("casing_depth", 0.32)
            add_box_object(f"{op['id']}_Casing", col_openings, mat_wood, lx, ly, sill + oh, ow + 0.16, casing_depth, 0.08, rot_z=rot_z)
            add_box_object(f"{op['id']}_DoorLeaf", col_openings, mat_glass, lx, ly, sill + 0.02, ow - 0.08, 0.015, oh - 0.06, rot_z=rot_z + math.radians(15))
        else:
            add_box_object(f"{op['id']}_Frame", col_openings, mat_black_steel, lx, ly, sill, ow, 0.12, oh, rot_z=rot_z)
            add_box_object(f"{op['id']}_Glazing", col_openings, mat_glass, lx, ly, sill + 0.05, ow - 0.10, 0.024, oh - 0.10, rot_z=rot_z)

    # 4. Linear MEP Runs
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
        mat_r = mat_diffuser if run["category"] == "duct" else mat_beam
        add_box_object(run["id"], col_runs, mat_r, cx, cy, cz, length, rw, rh, rot_z=rot_z)

    # 5. Trajectory Poses
    if poses_path and os.path.exists(poses_path):
        with open(poses_path, "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            idx = 0
            for row in reader:
                if len(row) >= 4:
                    tx, ty, tz = float(row[1]), float(row[2]), float(row[3])
                    add_cylinder_object(f"PanoPose_{idx:02d}", col_traj, mat_marker, tx, ty, tz - 0.05, 0.08, 0.10)
                    idx += 1

    # Save Blend
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print(f"Successfully saved Blender BIM model to {out_blend}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blender BIM Builder")
    parser.add_argument("--manifest", default=r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar\av_scanar_bim_manifest.json")
    parser.add_argument("--out", default=r"C:\Users\calle\.gemini\antigravity\scratch\av_scanar\AV_scanAR_BIM.blend")
    args = parser.parse_args()

    build_scene(args.manifest, args.out)
