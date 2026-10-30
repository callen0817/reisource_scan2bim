import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Paths
MANIFEST_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\reisource_scan2bim\data\eyesonpark_bim_manifest.json"
PCD_PATH = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark_gt\eyesonpark_relocated_downsampled.npz"
ARTIFACTS_DIR = r"C:\Users\calle\.gemini\antigravity\brain\aaea3624-ea7d-4e9e-9586-ba31bb2668f4"

with open(MANIFEST_PATH, "r") as f:
    manifest = json.load(f)

pts = np.load(PCD_PATH)["points"]
mask = (pts[:, 2] >= 0.8) & (pts[:, 2] <= 1.4)
pts_slice = pts[mask]

# -------------------------------------------------------------
# GRAPHIC 1: 3D AXONOMETRIC CUTAWAY VIEW OF COMPLETE MODEL
# -------------------------------------------------------------
fig = plt.figure(figsize=(19, 10), dpi=160)
fig.patch.set_facecolor("#0b0f19")
ax = fig.add_subplot(111, projection="3d")
ax.set_facecolor("#0b0f19")

def add_box(ax, x0, y0, z0, dx, dy, dz, color, alpha=0.85, edgecolor="#ffffff", lw=0.6):
    vertices = [
        [[x0, y0, z0], [x0+dx, y0, z0], [x0+dx, y0+dy, z0], [x0, y0+dy, z0]],
        [[x0, y0, z0+dz], [x0+dx, y0, z0+dz], [x0+dx, y0+dy, z0+dz], [x0, y0+dy, z0+dz]],
        [[x0, y0, z0], [x0+dx, y0, z0], [x0+dx, y0, z0+dz], [x0, y0, z0+dz]],
        [[x0+dx, y0, z0], [x0+dx, y0+dy, z0], [x0+dx, y0+dy, z0+dz], [x0+dx, y0, z0+dz]],
        [[x0+dx, y0+dy, z0], [x0, y0+dy, z0], [x0, y0+dy, z0+dz], [x0+dx, y0+dy, z0+dz]],
        [[x0, y0+dy, z0], [x0, y0, z0], [x0, y0, z0+dz], [x0, y0+dy, z0+dz]]
    ]
    poly = Poly3DCollection(vertices, facecolors=color, linewidths=lw, edgecolors=edgecolor, alpha=alpha)
    ax.add_collection3d(poly)

# 1. Slabs
for flr in manifest["floors"]:
    poly = np.array(flr["polygon"])
    x_min, x_max = float(poly[:, 0].min()), float(poly[:, 0].max())
    y_min, y_max = float(poly[:, 1].min()), float(poly[:, 1].max())
    elev = float(flr["elevation"])
    thk = float(flr["thickness"])
    add_box(ax, x_min, y_min, elev - thk, x_max - x_min, y_max - y_min, thk, "#1e293b", alpha=0.9, edgecolor="#475569")

# 2. Walls (Cut to 2.40m for interior visibility)
cut_h = 2.40
for w in manifest["walls"]:
    p1 = np.array(w["p1"])
    p2 = np.array(w["p2"])
    thk = float(w["thickness"])
    b_z = float(w["base_z"])
    h = min(cut_h, float(w["height"]))
    
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1])
    ox = min(p1[0], p2[0]) - (0.0 if dx > 0.05 else thk*0.5)
    oy = min(p1[1], p2[1]) - (0.0 if dy > 0.05 else thk*0.5)
    dx_box = max(dx, thk)
    dy_box = max(dy, thk)
    
    col = "#2563eb" if w["type"] == "Exterior" else "#10b981" if w["type"] == "Interior" else "#f59e0b"
    add_box(ax, ox, oy, b_z, dx_box, dy_box, h, col, alpha=0.80, edgecolor="#ffffff", lw=0.7)

# 3. Storefront Mullions
for mul in manifest["curtain_system"]["mullions"]:
    add_box(ax, mul["x"] - mul["d"]*0.5, mul["y"] - mul["w"]*0.5, 0.0, mul["d"], mul["w"], cut_h, "#0284c7", alpha=0.95, edgecolor="#38bdf8", lw=0.8)

# 4. Doors
for d in manifest["doors"]:
    px, py, pz = d["pos"]
    dw = float(d["width"])
    dh = min(cut_h, float(d["height"]))
    add_box(ax, px - dw*0.5, py - 0.05, pz, dw, 0.10, dh, "#ef4444", alpha=0.90, edgecolor="#fca5a5", lw=0.9)

# 5. Casework & Tables
for cw in manifest["casework"]:
    c = cw["center"]
    s = cw["size"]
    add_box(ax, c[0]-s[0]/2, c[1]-s[1]/2, c[2], s[0], s[1], s[2], "#8b5cf6", alpha=0.88, edgecolor="#c084fc", lw=0.8)

# 6. Plumbing Fixtures (Toilet in cyan, Sink in teal)
for pl in manifest["plumbing"]:
    p = pl["pos"]
    s = pl["size"]
    col = "#06b6d4" if pl["type"] == "Toilet" else "#14b8a6" if pl["type"] == "Sink" else "#94a3b8"
    add_box(ax, p[0]-s[0]/2, p[1]-s[1]/2, p[2], s[0], s[1], s[2], col, alpha=0.92, edgecolor="#ffffff", lw=0.8)

ax.set_xlim(2, 20)
ax.set_ylim(-5.5, 2.5)
ax.set_zlim(0, 3.5)
ax.view_init(elev=32, azim=-62)
ax.set_title("AUTOMATED IFC4 MODEL — 3D AXONOMETRIC CUTAWAY VIEW\n(Complete Interior: Angled North Wall, Demising Partitions, Punched Doors, Dispensing Tables & Plumbing)", color="#f8fafc", fontsize=12, fontweight="bold", pad=20)
ax.tick_params(colors="#94a3b8")
ax.xaxis.pane.fill = False
ax.yaxis.pane.fill = False
ax.zaxis.pane.fill = False
ax.xaxis.pane.set_edgecolor("#1e293b")
ax.yaxis.pane.set_edgecolor("#1e293b")
ax.zaxis.pane.set_edgecolor("#1e293b")

out_3d = os.path.join(ARTIFACTS_DIR, "eyesonpark_automated_ifc_3d_axonometric.png")
plt.tight_layout()
plt.savefig(out_3d, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close()
print(f"Saved 3D view: {out_3d}")

# -------------------------------------------------------------------
# GRAPHIC 2: 2D FLOOR PLAN OVERLAY WITH TRUE ANGLED WALLS & SWINGS
# -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(22, 10), dpi=160)
fig.patch.set_facecolor("#0b0f19")
ax.set_facecolor("#0b0f19")
ax.tick_params(colors="#94a3b8")
ax.grid(True, color="#1e293b", ls=":", lw=0.8)
ax.set_xlabel("Revit Project X (Meters)", color="#94a3b8", fontsize=11)
ax.set_ylabel("Revit Project Y (Meters)", color="#94a3b8", fontsize=11)
ax.set_aspect("equal")

# 1. Point Cloud Points (bright cyan)
ax.scatter(pts_slice[::2, 0], pts_slice[::2, 1], s=0.9, c="#38bdf8", alpha=0.35, label="Point Cloud (260612_Eyes_on_Park.rcs / EyesOnPark.e57)", zorder=1)

# 2. Automated Walls (mitred polygons)
for w in manifest["walls"]:
    poly = np.array(w["mitred_polygon"])
    color = "#2563eb" if w["type"] == "Exterior" else "#10b981" if w["type"] == "Interior" else "#f59e0b"
    ax.fill(poly[:, 0], poly[:, 1], color=color, alpha=0.85, edgecolor="#ffffff", lw=1.2, zorder=3)
    ax.plot([w["p1"][0], w["p2"][0]], [w["p1"][1], w["p2"][1]], color="#ffffff", lw=0.8, ls="--", zorder=4)

# 3. Automated Doors with Architectural Swing Arcs
for dr in manifest["doors"]:
    p = dr["pos"]
    w = dr["width"]
    sdir = dr.get("swing_dir", "IN_LEFT")
    
    if dr["id"] == "DR_STOREFRONT":
        # Double swing door
        rect_l = patches.Rectangle((p[0]-0.05, p[1]-w*0.5), 0.10, w*0.5, facecolor="#ef4444", edgecolor="#ffffff", lw=1.0, zorder=6)
        rect_r = patches.Rectangle((p[0]-0.05, p[1]), 0.10, w*0.5, facecolor="#ef4444", edgecolor="#ffffff", lw=1.0, zorder=6)
        ax.add_patch(rect_l)
        ax.add_patch(rect_r)
        arc_l = patches.Arc((p[0], p[1]-w*0.5), w, w, angle=0, theta1=0, theta2=90, color="#ef4444", lw=1.2, ls=":", zorder=6)
        arc_r = patches.Arc((p[0], p[1]+w*0.5), w, w, angle=0, theta1=270, theta2=360, color="#ef4444", lw=1.2, ls=":", zorder=6)
        ax.add_patch(arc_l)
        ax.add_patch(arc_r)
    else:
        # Single swing door: door leaf rectangle + 90 deg swing arc
        rect = patches.Rectangle((p[0]-w*0.5, p[1]-0.04), w, 0.08, facecolor="#ef4444", edgecolor="#ffffff", lw=1.0, zorder=6)
        ax.add_patch(rect)
        # Swing arc
        arc = patches.Arc((p[0]-w*0.5, p[1]), w*2, w*2, angle=0, theta1=0, theta2=90, color="#ef4444", lw=1.2, ls=":", zorder=6)
        ax.add_patch(arc)
    ax.scatter(p[0], p[1], s=40, c="#ef4444", marker="o", edgecolors="#ffffff", lw=1.0, zorder=7)

# 4. Plumbing Fixtures (Toilet, Sink, Grab bars)
for pl in manifest["plumbing"]:
    p = pl["pos"]
    s = pl["size"]
    ptype = pl["type"]
    if ptype == "Toilet":
        tank = patches.Rectangle((p[0]-s[0]*0.5, p[1]-s[1]*0.5), s[0], s[1]*0.35, facecolor="#06b6d4", edgecolor="#ffffff", lw=1.2, zorder=6)
        bowl = patches.Ellipse((p[0], p[1]+s[1]*0.15), s[0]*0.85, s[1]*0.65, facecolor="#22d3ee", edgecolor="#ffffff", lw=1.2, zorder=6)
        ax.add_patch(tank)
        ax.add_patch(bowl)
        ax.text(p[0], p[1]-0.55, "ADA Toilet", color="#22d3ee", fontsize=8, fontweight="bold", ha="center")
    elif ptype == "Sink":
        rect = patches.Rectangle((p[0]-s[0]*0.5, p[1]-s[1]*0.5), s[0], s[1], facecolor="#14b8a6", edgecolor="#ffffff", lw=1.2, zorder=6)
        basin = patches.Ellipse((p[0], p[1]), s[0]*0.75, s[1]*0.75, facecolor="#2dd4bf", edgecolor="#ffffff", lw=1.0, zorder=7)
        ax.add_patch(rect)
        ax.add_patch(basin)
        ax.text(p[0], p[1]+0.35, "Vanity Sink", color="#2dd4bf", fontsize=8, fontweight="bold", ha="center")
    elif ptype == "GrabBar":
        rect = patches.Rectangle((p[0]-s[0]*0.5, p[1]-s[1]*0.5), s[0], s[1], facecolor="#e2e8f0", edgecolor="#38bdf8", lw=1.5, zorder=7)
        ax.add_patch(rect)

# 5. Casework & Tables
for cw in manifest["casework"]:
    c = cw["center"]
    s = cw["size"]
    ctype = cw["type"]
    col = "#9333ea" if ctype == "IslandDesk" else "#7c3aed" if ctype == "ServiceCounter" else "#6d28d9"
    rect = patches.Rectangle((c[0]-s[0]/2, c[1]-s[1]/2), s[0], s[1], linewidth=1.2, edgecolor="#c084fc", facecolor=col, alpha=0.85, zorder=5)
    ax.add_patch(rect)

# 6. Storefront Mullions
for mul in manifest["curtain_system"]["mullions"]:
    ax.scatter(mul["x"], mul["y"], s=45, c="#0284c7", marker="s", edgecolors="#ffffff", lw=1.0, zorder=6)

ax.set_xlim(2, 20)
ax.set_ylim(-6.5, 3.0)
ax.set_title("AUTOMATED IFC MODEL vs POINT CLOUD — CORRECTED ANGLED PLAN OVERLAY\n(Featuring True -3.38 deg Angled North Demising Wall, Door Swings, Partitions & Restroom Plumbing)", color="#f8fafc", fontsize=12, fontweight="bold", pad=12)

# Detail annotations
ax.annotate("Angled North Demising Wall (-3.38 deg Slope)\n(Y = 1.20m at Front -> Y = 0.39m at Rear)\nMatches Point Cloud Without Angular Error!", xy=(10.5, 0.86), xytext=(10.5, 2.3),
             arrowprops=dict(facecolor="#38bdf8", shrink=0.08, width=1.2, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#38bdf8"))

ax.annotate("Central Dispensing Island Desk\n(Parallel to Store Length | X=10.79m, Y=-0.91m)", xy=(10.79, -0.91), xytext=(7.5, -2.5),
             arrowprops=dict(facecolor="#c084fc", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#c084fc"))

ax.annotate("Punched Door to Exam 1 with Swing\n(IfcOpeningElement + IfcDoor)", xy=(15.34, -0.795), xytext=(13.2, 0.2),
             arrowprops=dict(facecolor="#ef4444", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#ef4444"))

ax.annotate("Punched Door to Exam 2 with Swing\n(IfcOpeningElement + IfcDoor)", xy=(15.63, -2.62), xytext=(13.2, -3.6),
             arrowprops=dict(facecolor="#ef4444", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#ef4444"))

ax.annotate("Restroom ADA Plumbing:\nWall-hung Toilet + Vanity Sink + Grab Bars", xy=(17.2, -4.1), xytext=(17.5, -5.5),
             arrowprops=dict(facecolor="#06b6d4", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#06b6d4"))

out_plan = os.path.join(ARTIFACTS_DIR, "eyesonpark_automated_ifc_plan_overlay.png")
plt.tight_layout()
plt.savefig(out_plan, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close()
print(f"Saved Plan view: {out_plan}")
