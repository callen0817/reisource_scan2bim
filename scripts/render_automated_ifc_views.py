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
# GRAPHIC 1: 3D AXONOMETRIC CUTAWAY VIEW OF AUTOMATED IFC MODEL
# -------------------------------------------------------------
fig = plt.figure(figsize=(18, 10), dpi=160)
fig.patch.set_facecolor("#0b0f19")
ax = fig.add_subplot(111, projection="3d")
ax.set_facecolor("#0b0f19")

def add_box(ax, x0, y0, z0, dx, dy, dz, color, alpha=0.85, edgecolor="#ffffff", lw=0.6):
    vertices = [
        # bottom
        [[x0, y0, z0], [x0+dx, y0, z0], [x0+dx, y0+dy, z0], [x0, y0+dy, z0]],
        # top
        [[x0, y0, z0+dz], [x0+dx, y0, z0+dz], [x0+dx, y0+dy, z0+dz], [x0, y0+dy, z0+dz]],
        # sides
        [[x0, y0, z0], [x0+dx, y0, z0], [x0+dx, y0, z0+dz], [x0, y0, z0+dz]],
        [[x0+dx, y0, z0], [x0+dx, y0+dy, z0], [x0+dx, y0+dy, z0+dz], [x0+dx, y0, z0+dz]],
        [[x0+dx, y0+dy, z0], [x0, y0+dy, z0], [x0, y0+dy, z0+dz], [x0+dx, y0+dy, z0+dz]],
        [[x0, y0+dy, z0], [x0, y0, z0], [x0, y0, z0+dz], [x0, y0+dy, z0+dz]]
    ]
    poly = Poly3DCollection(vertices, facecolors=color, linewidths=lw, edgecolors=edgecolor, alpha=alpha)
    ax.add_collection3d(poly)

# 1. Plot Slabs
for flr in manifest["floors"]:
    poly = np.array(flr["polygon"])
    x_min, x_max = float(poly[:, 0].min()), float(poly[:, 0].max())
    y_min, y_max = float(poly[:, 1].min()), float(poly[:, 1].max())
    elev = float(flr["elevation"])
    thk = float(flr["thickness"])
    add_box(ax, x_min, y_min, elev - thk, x_max - x_min, y_max - y_min, thk, "#1e293b", alpha=0.9, edgecolor="#475569")

# 2. Plot Walls (Cut height to 2.5m for clear axonometric cutaway visibility)
cut_h = 2.40
for w in manifest["walls"]:
    p1 = np.array(w["p1"])
    p2 = np.array(w["p2"])
    L = float(w["length"])
    thk = float(w["thickness"])
    b_z = float(w["base_z"])
    h = min(cut_h, float(w["height"]))
    
    # Bounding representation
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1])
    ox = min(p1[0], p2[0]) - (0.0 if dx > 0.05 else thk*0.5)
    oy = min(p1[1], p2[1]) - (0.0 if dy > 0.05 else thk*0.5)
    dx_box = max(dx, thk)
    dy_box = max(dy, thk)
    
    col = "#2563eb" if w["type"] == "Exterior" else "#10b981" if w["type"] == "Interior" else "#f59e0b"
    add_box(ax, ox, oy, b_z, dx_box, dy_box, h, col, alpha=0.80, edgecolor="#ffffff", lw=0.7)

# 3. Plot Storefront Mullions & Glazing
for mul in manifest["curtain_system"]["mullions"]:
    add_box(ax, mul["x"] - mul["d"]*0.5, mul["y"] - mul["w"]*0.5, 0.0, mul["d"], mul["w"], cut_h, "#0284c7", alpha=0.95, edgecolor="#38bdf8", lw=0.8)

# 4. Plot Doors
for d in manifest["doors"]:
    px, py, pz = d["pos"]
    dw = float(d["width"])
    dh = min(cut_h, float(d["height"]))
    add_box(ax, px - dw*0.5, py - 0.05, pz, dw, 0.10, dh, "#ef4444", alpha=0.90, edgecolor="#fca5a5", lw=0.9)

# 5. Plot Casework & Dispensing Tables
for cw in manifest["casework"]:
    c = cw["center"]
    s = cw["size"]
    add_box(ax, c[0]-s[0]/2, c[1]-s[1]/2, c[2], s[0], s[1], s[2], "#8b5cf6", alpha=0.88, edgecolor="#c084fc", lw=0.8)

# 6. Plot Plumbing Fixtures
for pl in manifest["plumbing"]:
    p = pl["pos"]
    s = pl["size"]
    add_box(ax, p[0]-s[0]/2, p[1]-s[1]/2, p[2], s[0], s[1], s[2], "#06b6d4", alpha=0.90, edgecolor="#67e8f9", lw=0.8)

ax.set_xlim(2, 20)
ax.set_ylim(-5.5, 2.5)
ax.set_zlim(0, 3.5)

ax.view_init(elev=32, azim=-62)
ax.set_title("AUTOMATED IFC4 MODEL — 3D AXONOMETRIC CUTAWAY VIEW\n(EyesonPark_Automated_BIM.ifc Generated via Trained Scan2BIM Engine)", color="#f8fafc", fontsize=13, fontweight="bold", pad=20)
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
print(f"Generated 3D Axonometric view: {out_3d}")

# -------------------------------------------------------------------
# GRAPHIC 2: 2D FLOOR PLAN OVERLAY: AUTOMATED IFC vs POINT CLOUD
# -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(20, 9), dpi=160)
fig.patch.set_facecolor("#0b0f19")
ax.set_facecolor("#0b0f19")
ax.tick_params(colors="#94a3b8")
ax.grid(True, color="#1e293b", ls=":", lw=0.8)
ax.set_xlabel("Revit Project X (Meters)", color="#94a3b8", fontsize=11)
ax.set_ylabel("Revit Project Y (Meters)", color="#94a3b8", fontsize=11)
ax.set_aspect("equal")

# Scatter Point Cloud in bright cyan
ax.scatter(pts_slice[::2, 0], pts_slice[::2, 1], s=0.9, c="#38bdf8", alpha=0.35, label="Point Cloud (260612_Eyes_on_Park.rcs / EyesOnPark.e57)", zorder=1)

# Plot automated walls
for w in manifest["walls"]:
    poly = np.array(w["mitred_polygon"])
    color = "#2563eb" if w["type"] == "Exterior" else "#10b981" if w["type"] == "Interior" else "#f59e0b"
    ax.fill(poly[:, 0], poly[:, 1], color=color, alpha=0.85, edgecolor="#ffffff", lw=1.2, zorder=3)
    ax.plot([w["p1"][0], w["p2"][0]], [w["p1"][1], w["p2"][1]], color="#ffffff", lw=0.8, ls="--", zorder=4)

# Plot automated doors
for dr in manifest["doors"]:
    p = dr["pos"]
    w = dr["width"]
    ax.scatter(p[0], p[1], s=55, c="#ef4444", marker="D", edgecolors="#ffffff", lw=1.2, zorder=6, label="Automated Door" if dr["id"] == "DR_STOREFRONT" else "")

# Plot automated casework & dispensing table
for cw in manifest["casework"]:
    c = cw["center"]
    s = cw["size"]
    rect = patches.Rectangle((c[0]-s[0]/2, c[1]-s[1]/2), s[0], s[1], linewidth=1.2, edgecolor="#c084fc", facecolor="#9333ea", alpha=0.85, zorder=5, label="Automated Casework / Table" if cw["id"] == "CW_DISPENSING_ISLAND" else "")
    ax.add_patch(rect)

# Plot Storefront Mullions
for mul in manifest["curtain_system"]["mullions"]:
    ax.scatter(mul["x"], mul["y"], s=40, c="#0284c7", marker="s", edgecolors="#ffffff", lw=1.0, zorder=6, label="Storefront Mullion" if mul["id"] == "MUL_0" else "")

ax.set_xlim(2, 20)
ax.set_ylim(-6.5, 3.0)
ax.set_title("AUTOMATED IFC MODEL vs POINT CLOUD — PLAN OVERLAY\n(Demonstrating Direct Cloud-to-BIM Coincidence with Punched Doors and Central Dispensing Table)", color="#f8fafc", fontsize=12, fontweight="bold", pad=12)

# Detail annotations
ax.annotate("Central Dispensing Island Desk\n(Parallel to Store Length | X=10.79m, Y=-0.91m)", xy=(10.79, -0.91), xytext=(7.5, -2.5),
             arrowprops=dict(facecolor="#c084fc", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#c084fc"))

ax.annotate("North Perimeter Display Run\n(Y=+0.49m | Aligned to North Demising Wall)", xy=(8.5, 0.49), xytext=(8.5, 1.8),
             arrowprops=dict(facecolor="#c084fc", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#c084fc"))

ax.annotate("South Perimeter Display Run\n(Y=-3.79m | Aligned to South Demising Wall)", xy=(8.5, -3.79), xytext=(8.5, -5.2),
             arrowprops=dict(facecolor="#c084fc", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#c084fc"))

ax.annotate("Punched Door to Exam 1\n(IfcOpeningElement + IfcDoor)", xy=(15.34, -0.80), xytext=(13.5, 0.2),
             arrowprops=dict(facecolor="#ef4444", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#ef4444"))

ax.annotate("Punched Door to Exam 2\n(IfcOpeningElement + IfcDoor)", xy=(15.63, -2.62), xytext=(13.5, -3.8),
             arrowprops=dict(facecolor="#ef4444", shrink=0.08, width=1, headwidth=6),
             color="#ffffff", fontsize=9, fontweight="bold", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#0f172a", ec="#ef4444"))

ax.legend(loc="upper left", facecolor="#1e293b", edgecolor="#475569", labelcolor="#f8fafc", fontsize=9)

out_plan = os.path.join(ARTIFACTS_DIR, "eyesonpark_automated_ifc_plan_overlay.png")
plt.tight_layout()
plt.savefig(out_plan, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close()
print(f"Generated 2D Plan Overlay view: {out_plan}")
