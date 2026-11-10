# ReiSource Scan2BIM — Exclusions & Local Environment Rebuild Guide

This document explicitly identifies all heavy assets, large scan binaries, dependencies, and environment artifacts excluded from git tracking (`.gitignore`), along with precise instructions to acquire or rebuild them locally for development and production execution.

---

## 📦 Excluded Asset Inventory

| Category | File Extensions / Directories | Description | Why Excluded |
|---|---|---|---|
| **Raw LiDAR Scans** | `*.e57`, `*.las`, `*.laz`, `*.ply`, `*.pcap`, `*.bag` | High-density terrestrial and mobile LiDAR point clouds (e.g. NavVis VLX, Leica RTC360, EyesOnPark.e57) | Exceeds GitHub 100MB file limit (typically 5GB–50GB per scan) |
| **Autodesk Recap Data** | `*.rcp`, `*.rcs` | Indexed point cloud projects and support folders | Platform-specific indexed cache formats |
| **BIM Binary Models** | `*.rvt`, `*.rfa` | Native Autodesk Revit 2024/2025 project and family models (`Wasatch Peaks Ranch Residence_FEDERATED.rvt`) | Maintained on Autodesk Construction Cloud (ACC) and Autodesk Forma Bridge |
| **Blender Backup Files** | `*.blend1`, `*.blend@` | Automated autosave copies of 3D Blender scenes | Transient auto-generated cache |
| **Node.js Dependencies** | `node_modules/`, `.vite/` | Frontend packages for the Scan2BIM GUI React/Vite dashboard | Rebuilt deterministically via `npm install` |
| **Python Environments** | `venv/`, `.env/`, `__pycache__/`, `*.pyc` | Local virtual environments and compiled bytecode | Host-architecture specific |
| **System / App Logs** | `*.log`, `Thumbs.db`, `.DS_Store` | Local runtime logs and OS metadata | Non-deterministic runtime artifacts |

---

## 🛠 Step-by-Step Local Rebuild Instructions

### 1. Python Backend & Scan Processing Engine
Ensure Python 3.10+ (or 3.11 recommended) is installed on your system:
```bash
# Clone the repository
git clone https://github.com/callen0817/reisource_scan2bim.git
cd reisource_scan2bim

# Create and activate a clean virtual environment
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Install core dependencies (ifcopenhell, numpy, trimesh, scipy, open3d)
pip install ifcopenshell numpy scipy trimesh open3d
```

### 2. Frontend GUI Dashboard
To run the interactive Scan2BIM visualizer and coordination dashboard:
```bash
cd gui
npm install
npm run dev
```
The dashboard will launch locally at `http://localhost:5173`.

### 3. Acquiring Heavy LiDAR Datasets
Raw LiDAR point clouds (`EyesOnPark.e57`, etc.) are hosted on the ReiSource Google Drive / ACC storage:
1. Contact the project administrator or VDC lead to request access to the raw scan bucket.
2. Download `EyesOnPark.e57` and place it in the `data/` directory:
   ```
   data/EyesonPark.e57
   ```
3. Run the automated feature extraction pipeline:
   ```bash
   python scripts/build_eyesonpark_automated.py
   python scripts/export_ifc.py
   ```
   This will regenerate the clean parametric IFC4 BIM model: `data/EyesonPark_Automated_BIM.ifc`.

### 4. Autodesk Forma Bridge & Revit Federation
For multidisciplinary coordination on Wasatch Peaks Ranch and related projects:
1. Install **Autodesk Desktop Connector** with Autodesk Construction Cloud (ACC) Docs access.
2. Ensure your Autodesk Forma account is added to the project:
   - **ReiSource Hub**: `WPR - Lot G9`
   - **Architect Hub**: `25402 Wasatch Peaks Ranch Residence`
3. The master federated model is automatically synchronized through the Forma Bridge at:
   ```
   02_OUTPUT / Wasatch Peaks Ranch Residence_FEDERATED.rvt
   ```
4. All worksets (`A-TRIM`, `A-WALLS`, `A-WALLS (EXT)`, `S-CONCRETE FOUNDATIONS`, and link worksets) and 3D coordination views (`Coord_Federated`, `Coord_Wall Framing`, etc.) are configured according to the specifications in [`docs/antigravity-history/artifacts/BIM_EXECUTION_PLAN_WASATCH_PEAKS_RANCH_v1_2.md`](docs/antigravity-history/artifacts/BIM_EXECUTION_PLAN_WASATCH_PEAKS_RANCH_v1_2.md).
