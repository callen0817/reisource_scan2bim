# reisource_scan2bim

> **Automated High-LOD Scan-to-BIM Engine with Apple Glassmorphism GUI & Multi-Walk NavVis VLX Unifier**

[![GitHub](https://img.shields.io/badge/GitHub-reisource__scan2bim-blue.svg)](https://github.com/callen0817/reisource_scan2bim)
[![BIM Standards](https://img.shields.io/badge/IFC4-buildingSMART%20Certified-emerald.svg)]()
[![Autodesk Revit](https://img.shields.io/badge/Autodesk%20Revit-2027%20API-orange.svg)]()
[![Blender](https://img.shields.io/badge/Blender-5.2%20LTS-purple.svg)]()

---

## 1. Overview

`reisource_scan2bim` is a modern, modular Scan-to-BIM transformation engine that turns dense LiDAR point clouds (`.e57`, `.las`, `.laz`, `.ply`) and **NavVis VLX multi-dataset walks** into parametric, high-LOD architectural BIM models ready for **Autodesk Revit 2027**, **IFC4**, and **Blender 5.2**.

---

## 2. Key Features

- **Apple "Liquid Glass" Desktop UI**:
  - Translucent frosted glass panels (`backdrop-filter: blur()`), responsive drag-and-drop ingestion, interactive 3D viewer, and real-time conversion feeds.
  - Informative hoverable tooltips explaining multi-dataset formats.
- **NavVis VLX Multi-Dataset Disambiguator**:
  - Automatically resolves naming collisions (e.g. `walk_01/pano-000001.jpg` vs `walk_02/pano-000001.jpg`) without altering raw files or breaking NavVis IVION processing.
  - Applies $4 \times 4$ rigid alignment matrices from `alignment.xml` to transform local trajectory poses into the global merged point cloud coordinate frame.
  - Synchronizes microsecond UNIX epoch timestamps across panos and poses.
- **Specular Mirror Denoising**:
  - Automatically identifies optical mirrors and eliminates ghost reflections behind physical demising walls.
- **High-LOD Parametric Elements (No Boxy Placeholders)**:
  - **Plumbing**: Vitreous china contoured elongated toilet bowls, vertical chrome flushometers with trip levers, ADA grab bars, wall-hung lavatories with gooseneck sensor faucets, exposed P-traps, and mirrors.
  - **Specialty Equipment**: Motorized ophthalmic examination chairs, articulated phoropter stands with dual ocular optics, digital slit lamp biomicroscopes, and visual field perimeter testing domes.
  - **Custom Millwork**: Authentic L-shaped reception desks with fluted white oak base cladding, dual-tier Calacatta quartz countertops with barrier-free ADA sections ($0.86\text{m}$), and display casework with cantilevered glass shelves and LED reveals.
  - **Exterior & Storefront**: Retractable canopy awnings with sloped fabric roofs and steel outriggers; concrete ADA ramps with $100\text{mm}$ edge protection curbs and continuous dual stainless steel handrails.
- **Strict BIM Taxonomy**:
  - Ceilings $\rightarrow$ strictly `IfcCovering` (`CEILING`) and Revit `OST_Ceilings` (never structural slabs).
  - Floors $\rightarrow$ `IfcSlab` (`FLOOR`) and Revit `OST_Floors`.
  - Awning $\rightarrow$ `IfcShadingDevice` (`AWNING`).
  - Storefront $\rightarrow$ `IfcCurtainWall`, `IfcMember`, `IfcPlate`.
  - Plumbing $\rightarrow$ `IfcSanitaryTerminal`.

---

## 3. Repository Architecture

```text
reisource_scan2bim/
├── core/
│   ├── __init__.py
│   ├── navvis_unifier.py       # Multi-dataset NavVis poses & alignment engine
│   ├── spatial_extractor.py    # Statistical elevation & 2D RANSAC wall fitting
│   └── bim_exporter.py         # IFC4 and native Revit 2027 API generators
├── gui/                        # Apple Glassmorphism GUI (React, Tailwind, Three.js)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx             # Translucent UI shell, drag-and-drop & 3D canvas
│       ├── main.jsx
│       └── index.css           # Glassmorphism utilities & SF Pro typography
├── scripts/
│   ├── build_blender.py        # Blender 5.2 live TCP socket builder
│   └── build_revit.py          # Native Revit 2027 automation script
├── .gitignore
└── README.md
```

---

## 4. Getting Started

### Prerequisites
- Node.js $\ge 18$
- Python $\ge 3.10$ with `numpy`, `pye57`, `ifcopenshell` (optional for IFC export)
- Autodesk Revit 2027 / Blender 5.2 LTS

### Running the Glassmorphism Desktop UI
```bash
cd gui
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the desktop interface.

---

## 5. License
MIT License • Engineered for Scan-to-BIM Automation.
