# Wasatch Peaks Ranch Residence — BIM Execution Plan (BEP) v1.2

**Document Title**: `ReiSource_24502_Wasatch_Peaks_Ranch_BIM_Execution_Plan_v1.2`  
**Project**: 24502 Wasatch Peaks Ranch Residence  
**Author / VDC Lead**: ReiSource (Jonathan Griffiths)  
**General Contractor**: Reis Contracting  
**Architect**: Bohlin Cywinski Jackson (BCJ)  
**Structural / Mass Timber Fabricator**: Spearhead  
**Revit Version**: Autodesk Revit 2025  
**Federated Model**: `Wasatch Peaks Ranch Residence_FEDERATED.rvt`  
**Cloud Storage Location**: `02_OUTPUT` folder of ReiSource's `WPR - Lot G9` Autodesk Forma project  

---

## 1. Executive Summary & Project Mandate

The **Wasatch Peaks Ranch BIM Execution Plan (BEP) v1.2** defines the multidisciplinary Virtual Design and Construction (VDC) protocols, model authoring standards, cloud coordination workflows, and reality capture verifications for the construction of the Wasatch Peaks Ranch Residence.

ReiSource is designated by the General Contractor (Reis Contracting) as the **Overall BIM/VDC Coordinator, Model Author, and Reality Capture Lead**. ReiSource authors the core architectural envelope, interior finish assemblies, structural concrete foundations (sub-grade), and coordinates all multidisciplinary trades within Autodesk Forma.

---

## 2. Autodesk Forma Bridge & Project Topology

### 2.1 Forma Bridge Connection
- **ReiSource Project**: `WPR - Lot G9`
- **BCJ Design Team Project**: `25402 Wasatch Peaks Ranch Residence`
- **Bridge Configuration**: BCJ configured an Autodesk Forma Bridge to their shared project folder, enabling live cloud synchronization of design reference models into ReiSource's coordination environment.

### 2.2 Shared Folder Structure & Ingested Reference Models
```
BCJ Shared Forma Project (25402 Wasatch Peaks Ranch Residence)
│
├── Architecture/
│   └── Wasatch Peaks Ranch Residence.rvt
├── Electrical/
│   └── G25-031-ELEC-R25-TDH.rvt
├── Mechanical/
│   └── G25-031-MECH-R25-TDH.rvt   (Contains both Mechanical HVAC and Plumbing systems)
├── Structural/
│   └── Structural - WPR.rvt       (Integrated with Spearhead timber fabrication models)
├── Landscape/
│   └── Landscape.rvt
└── Lighting/
    └── Lighting.rvt
```

### 2.3 Master Federated Model Output
- **Model Path**: `02_OUTPUT / Wasatch Peaks Ranch Residence_FEDERATED.rvt` in `WPR - Lot G9`
- **Role**: Houses all ReiSource-authored scope and links all referenced consultant models via dedicated worksets.

---

## 3. Master Workset Architecture

ReiSource authors and federates model content using a strict workset structure in Revit 2025:

| Workset Name | Scope & Content |
|---|---|
| `A-TRIM` | Interior finishes, millwork, casing, baseboards, and architectural trim |
| `A-WALLS` | Interior walls (decomposed 3-wall system: interior stud core and drywall assemblies) |
| `A-WALLS (EXT)` | Exterior walls, exterior framing, sheathing, weather barriers, and cladding assemblies |
| `G-ANNO, DIMS, TAGS, NOTES, KEYNOTES` | All 2D annotations, dimensions, tags, notes, and keynotes |
| `G-CAD` | Reference 2D/3D CAD backgrounds |
| `G-REALITY CAPTURE` | Laser scan point clouds (LiDAR) and drone photogrammetry meshes |
| `G-REFERENCE_ARCHITECTURE` | Architectural reference link (`Wasatch Peaks Ranch Residence.rvt`) |
| `G-REFERENCE_ELECTRICAL` | Electrical reference link (`G25-031-ELEC-R25-TDH.rvt`) |
| `G-REFERENCE_LANDSCAPE` | Landscape reference link (`Landscape.rvt`) |
| `G-REFERENCE_LIGHTING` | Architectural and specialty lighting reference link (`Lighting.rvt`) |
| `G-REFERENCE_MECHANICAL` | Mechanical HVAC reference link (`G25-031-MECH-R25-TDH.rvt`) |
| `G-REFERENCE_PLUMBING` | Plumbing piping reference link (`G25-031-MECH-R25-TDH.rvt`) |
| `G-REFERENCE_STRUCTURE` | Structural reference link (`Structural - WPR.rvt` and Spearhead models) |
| `G-VIEWS, LEVELS, GRIDS, REFR LINES` | Shared project levels, column grids, reference planes, and view controls |
| `S-CONCRETE FOUNDATIONS` | Underground concrete foundations, footings, grade beams, piers, and slab depressions *(excluding concrete rebar, which is explicitly out of scope)* |
| `Additional Worksets (As Needed)` | Created dynamically to isolate specialized scope, trade packages, or fabrication interfaces |
| `Ingested Designer Worksets` | Native designer worksets assigned to dedicated 3D coordination views |

---

## 4. 3D Coordination Views & Dynamic Autodesk Forma Clash Detection

All model elements are isolated into 13 dedicated 3D views. When published to Autodesk Forma, the system automatically searches for clashes and dynamically updates clash registers:

1. **`Coord_Federated` (`3d FEDERATED`)** — Full composite view displaying all active project disciplines.
2. **`Coord_Wall Framing`** — ReiSource wall framing (interior stud core on `A-WALLS`, exterior framing on `A-WALLS (EXT)`, headers, rough openings, and shade pocket framing).
3. **`Coord_Arch`** — Architectural reference model on `G-REFERENCE_ARCHITECTURE`.
4. **`Coord_Elec`** — Electrical systems, conduit, and switchgear on `G-REFERENCE_ELECTRICAL`.
5. **`Coord_FF&E`** — Furniture, Fixtures & Equipment from architectural and interior models.
6. **`Coord_FP`** — Fire protection sprinkler mains, risers, and branch lines *(as applicable)*.
7. **`Coord_Lighting`** — Architectural and specialty lighting fixtures on `G-REFERENCE_LIGHTING`.
8. **`Coord_M Duct`** — Mechanical ductwork, air distribution, and air-handling units.
9. **`Coord_M Pipe`** — Mechanical hydronic and process piping *(if needed)*.
10. **`Coord_Plumb`** — Domestic water, sanitary, waste, and storm piping on `G-REFERENCE_PLUMBING`.
11. **`Coord_Site`** — Hardscape, civil grading, and landscape on `G-REFERENCE_LANDSCAPE`.
12. **`Coord_Struct`** — Structural steel, timber, glulam, and roof framing from `Structural - WPR.rvt` & Spearhead.
13. **`Coord_Sub`** — Foundations and sub-ground elevation structural elements on `S-CONCRETE FOUNDATIONS` *(excluding rebar)*.

---

## 5. Issue Management & The Action List Workflow

ReiSource manages project coordination issues without third-party pre-VDC software via a structured **Action List** synchronized weekly with Autodesk Forma clash tests and prioritized by **Reis Contracting** construction schedule milestones:

1. **Federated Model Completion Items**: Tracks modeling, detailing, and coordination tasks required to finalize the federated model for shop drawing reference and field installation.
2. **Design Reference Discrepancy Tracking**: Catalogs contradictions, missing information, dimension misalignments, and specification gaps across design reference models, CAD files, and 2D PDFs.
3. **Weekly Publishing & Reporting**: ReiSource publishes the federated model and distributes comprehensive clash reports weekly to all stakeholders.

---

## 6. Reality Capture & Field Verification (4D Removal)

All 4D simulation requirements were removed from the BEP in Revision 1.2. In its place, ReiSource executes a comprehensive **Reality Capture Verification Program**:
- **LiDAR Laser Scanning**: Millimeter-accurate scans of underground foundations, concrete slabs, and structural timber frames.
- **Drone Photogrammetry**: Site-wide aerial meshes capturing earthwork, civil utilities, and topography.
- **Matterport Visual Walkthroughs**: High-resolution 360° visual progress documentation.
- **Model-to-Field Deviation Analysis**: Comparison of scan point clouds directly against `Wasatch Peaks Ranch Residence_FEDERATED.rvt` to identify constructability clashes prior to trade mobilization.
