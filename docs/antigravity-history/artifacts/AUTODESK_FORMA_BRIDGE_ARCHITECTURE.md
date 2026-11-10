# Autodesk Forma Bridge Architecture & Cloud Coordination Space

**Project**: 24502 Wasatch Peaks Ranch Residence  
**VDC Orchestrator**: ReiSource (Jonathan Griffiths)  
**Architect**: Bohlin Cywinski Jackson (BCJ)  
**Platform**: Autodesk Forma Model Coordination & Autodesk Construction Cloud (ACC)  

---

## 1. Overview & Cloud Bridge Topology

The coordination environment for Wasatch Peaks Ranch establishes a real-time data bridge between the Architect's cloud project and ReiSource's VDC authoring hub:

```
┌────────────────────────────────────────────────────────┐
│             BCJ Autodesk Forma Project                 │
│        "25402 Wasatch Peaks Ranch Residence"           │
│                                                        │
│  ├── Architecture/ (Wasatch Peaks Ranch Residence.rvt) │
│  ├── Electrical/   (G25-031-ELEC-R25-TDH.rvt)          │
│  ├── Mechanical/   (G25-031-MECH-R25-TDH.rvt)          │
│  ├── Structural/   (Structural - WPR.rvt)              │
│  ├── Landscape/    (Landscape.rvt)                     │
│  └── Lighting/     (Lighting.rvt)                      │
└──────────────────────────┬─────────────────────────────┘
                           │
                 AUTODESK FORMA BRIDGE
                 (Cloud Synchronization)
                           │
┌──────────────────────────▼─────────────────────────────┐
│          ReiSource Autodesk Forma Project              │
│                  "WPR - Lot G9"                        │
│                                                        │
│  ├── 01_INCOMING REFERENCES/  (Linked via Bridge)      │
│  │   ├── Architecture Link                             │
│  │   ├── MEP Links                                     │
│  │   └── Structural / Spearhead Links                  │
│  │                                                     │
│  └── 02_OUTPUT/                                        │
│      └── Wasatch Peaks Ranch Residence_FEDERATED.rvt   │
└────────────────────────────────────────────────────────┘
```

---

## 2. Dynamic Automated Clash Detection

When the master federated model is published to Autodesk Forma:
1. **Dynamic Search**: Forma automatically scans the 13 dedicated 3D coordination views.
2. **Automated Register Updates**: Resolved clashes from updated models are automatically cleared; newly introduced spatial conflicts are indexed and categorized.
3. **Weekly Publishing Cycle**: ReiSource synchronizes the federated model every Friday, generating automated clash clusters for trade review.
