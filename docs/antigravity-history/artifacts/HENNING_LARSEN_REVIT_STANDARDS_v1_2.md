# Henning Larsen US Office — Revit Standards v1.2

**Document Title**: `HL. Revit Standards v1.2_FINAL`  
**Revision Date**: November 2026  
**Author / Standard Coordinator**: ReiSource (Jonathan Griffiths)  
**Client / Review Team**: David, Eliana, DBUR (Henning Larsen US)  
**Core Platform**: Autodesk Revit (US Office Template Ecosystem)  

---

## 1. Henning Larsen Software Ecosystem

Section 1.1 incorporates the full digital interoperability pipeline:
- **Early Design & Parametric Analysis**: Autodesk Forma, McNeel Rhino, Grasshopper, ClimateStudio (Daylight, Energy, Embodied Carbon).
- **Interoperability Bridges**: Speckle (Cloud Object Streamer), Rhino.Inside.Revit, Autodesk Data Exchange, BEAM.
- **Production & Cloud Delivery**: Autodesk Revit, Autodesk Construction Cloud (ACC Docs & Model Coordination), Navisworks Manage, Solibri Model Checker, Enscape, D5 Render, Twinmotion.

---

## 2. Key Standards Revisions in v1.2

### 2.1 Model Organization & Worksets (Section 5)
- **Removal of 5.2, 5.3, and 5.4**: The duplicate 24-row baseline worksets table and static workset expansion lists were completely removed from the office Revit standard.
- **BEP as Single Source of Truth (Section 5.1)**: Project worksets and consultant link allocations are officially defined within each project's BIM Execution Plan (BEP) to prevent cross-document synchronization conflicts.
- **Renumbered Subsections**:
  - `5.1 What Worksets Are`
  - `5.2 Scope Boxes` (formerly 5.5)
  - `5.3 Groups` (formerly 5.6)
  - `5.4 Model Splitting` (formerly 5.7)

### 2.2 Material Naming Standard (`HL_[MATERIALTYPE]_[SUBTYPE]`)
- **Streamlined Section 7.8**: Replaced duplicate naming rules with direct cross-references to Section 11 (Materials Standards).
- **Downstream Interoperability (Section 11.1.1)**:
  - **Rendering Engines (Enscape, D5, Twinmotion)**: Identity names group materials cleanly in the browser while Appearance Assets retain high-res PBR textures.
  - **Model Exports (DWG, IFC, NWC, Speckle)**: Clean syntax ensures deterministic IFC material classes and automated Speckle filtering.
  - **Embodied Carbon (OneClick LCA)**: Standard prefixes (`HL_CONC_`, `HL_INS_`, `HL_GLZ_`) map directly into automated EPD classifications.

### 2.3 Project-Specific Bitmap Override Policy (Section 11.6.1)
- Project teams are authorized to introduce custom textures under `[PROJECT#]_[MATERIALTYPE]_[SUBTYPE]`.
- Stored on ACC at `03_PROJECT_FILES/08_RESOURCES/MATERIALS_BITMAPS/`.
- **Policy**: Project bitmaps explicitly **supersede** the central template library during active design as an agile middle ground before formal Taskforce library promotion.

### 2.4 Tagging & Dimensioning Split Rationale (Section 9.5.1)
- Category tags read live model database parameters, updating bi-directionally with schedules.
- Dimension styles provide view-scale graphic clarity: standard architectural tick marks (`HL_DIM-OVERALL`) for floor plans vs. filled 15° arrowheads (`HL_DIM-DETAIL`) for congested 1-1/2" and 3" details to prevent overlapping black blobs.
- Dedicated centerline styles (`HL_DIM-CENTERLINE`) reference true framing centerlines.

### 2.5 Multi-Category & Material Keynote Tagging (Section 9.9.4)
- Multi-Category and Material Tags configure instance/type toggles between Material Type (`WD-1`), CSI Keynote (`06 XX XX`), and Description.
- Allows finish plans and interior elevations to be tagged using Material Tags alone, preserving a single parameter truth.

### 2.6 Ceiling Type vs. Ceiling Finish (Section 13.1.1)
- **Ceiling Type (Physical Assembly)**:
  - `HL_CLG_GWB_5-8`: 5/8" GWB on metal furring channels.
  - `HL_CLG_ACT_2x2`: 2'x2' acoustic grid and tile.
  - `HL_CLG_LINEAR-WOOD`: Linear wood slat ceiling on concealed suspension.
- **Ceiling Finish (Surface Coating)**:
  - `P-01`: White flat latex paint.
  - `P-02`: Acoustic plaster smooth white finish.
  - `ACT-01`: High-NRC acoustical tile.
  - `WD-01`: Micro-perforated white oak veneer with clear matte sealer.
- **Tagging Protocol**:
  - *RCPs*: Ceiling Tag reads Ceiling Type Mark (`C-1`) and height (`+9'-6" AFF`).
  - *Finish Plans*: Room Key Schedule drives Room Finish Schedule displaying finish (`P-01`).
  - *Elevations/Details*: Material Tag reads surface finish spec directly.

### 2.7 Document Formatting & Layout Optimization
- Removed 320 artificial empty spacer paragraphs.
- Universal `keep_with_next` on all 152 headings prevents orphan titles at page bottoms.
- Table formatting (`cantSplit`, `tblHeader`, compact padding) reduced total page count from 68 to under 30 pages while maximizing readability.
