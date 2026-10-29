# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Native Autodesk Revit 2027 Automation Generator
Project: Eyes on Park Optical Clinic
Generated: 2026-10-29T14:06:55.286927
Execution: Run via Revit Python Shell, pyRevit, or Revit Journal
"""

import math
try:
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitServices")
    from Autodesk.Revit.DB import (
        Transaction, XYZ, Line, CurveLoop, Level, Wall, Floor,
        FilteredElementCollector, BuiltInCategory, Structure, CurveArray
    )
    IN_REVIT = True
except Exception:
    IN_REVIT = False

M_TO_FT = 3.280839895

def m2ft(val):
    return float(val) * M_TO_FT

def build_eyesonpark_model(doc):
    t = Transaction(doc, "reisource_scan2bim — Build Eyes on Park Model")
    t.Start()

    # 1. Create or Map Levels
    lvl_collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType()
    levels = {l.Name: l for l in lvl_collector}
    
    lvl_ground = levels.get("01_Ground Floor")
    if not lvl_ground:
        lvl_ground = Level.Create(doc, 0.0)
        lvl_ground.Name = "01_Ground Floor"

    lvl_ceiling = levels.get("02_Ceiling Grid")
    if not lvl_ceiling:
        lvl_ceiling = Level.Create(doc, m2ft(2.743))
        lvl_ceiling.Name = "02_Ceiling Grid"

    lvl_structure = levels.get("03_Structure Underside")
    if not lvl_structure:
        lvl_structure = Level.Create(doc, m2ft(3.943))
        lvl_structure.Name = "03_Structure Underside"

    # 2. Get Wall Types
    wall_types = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsElementType().ToElements()
    wall_type = wall_types[0] if len(wall_types) > 0 else None

    # 3. Create Walls
    walls_data = [
    {
        "id": "W_EXT_NORTH",
        "name": "Exterior Wall - North Demising 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 13.83,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            4.71,
            0.98
        ],
        "p2": [
            18.54,
            0.98
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.71,
                0.904
            ],
            [
                18.54,
                0.904
            ],
            [
                18.54,
                1.056
            ],
            [
                4.71,
                1.056
            ]
        ]
    },
    {
        "id": "W_EXT_SOUTH_A",
        "name": "Exterior Wall - South Demising Front 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 11.15,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            4.71,
            -4.29
        ],
        "p2": [
            15.86,
            -4.29
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.71,
                -4.366
            ],
            [
                15.86,
                -4.366
            ],
            [
                15.86,
                -4.214
            ],
            [
                4.71,
                -4.214
            ]
        ]
    },
    {
        "id": "W_EXT_SOUTH_B",
        "name": "Exterior Wall - South Demising Return 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 2.38,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            15.86,
            -4.29
        ],
        "p2": [
            18.24,
            -4.29
        ],
        "openings": [],
        "mitred_polygon": [
            [
                15.86,
                -4.366
            ],
            [
                18.24,
                -4.366
            ],
            [
                18.24,
                -4.214
            ],
            [
                15.86,
                -4.214
            ]
        ]
    },
    {
        "id": "W_EXT_EAST_A",
        "name": "Exterior Wall - East Demising Rear 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 3.62,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            18.54,
            0.98
        ],
        "p2": [
            18.54,
            -2.64
        ],
        "openings": [],
        "mitred_polygon": [
            [
                18.464,
                0.98
            ],
            [
                18.464,
                -2.64
            ],
            [
                18.616,
                -2.64
            ],
            [
                18.616,
                0.98
            ]
        ]
    },
    {
        "id": "W_EXT_EAST_B",
        "name": "Exterior Wall - East Demising Corner 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 1.65,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            18.24,
            -2.64
        ],
        "p2": [
            18.24,
            -4.29
        ],
        "openings": [],
        "mitred_polygon": [
            [
                18.163999999999998,
                -2.64
            ],
            [
                18.163999999999998,
                -4.29
            ],
            [
                18.316,
                -4.29
            ],
            [
                18.316,
                -2.64
            ]
        ]
    },
    {
        "id": "W_EXT_EAST_JOG",
        "name": "Exterior Wall - East Alcove Jog 6in",
        "type": "Exterior",
        "thickness": 0.152,
        "length": 0.3,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            18.54,
            -2.64
        ],
        "p2": [
            18.24,
            -2.64
        ],
        "openings": [],
        "mitred_polygon": [
            [
                18.54,
                -2.564
            ],
            [
                18.24,
                -2.564
            ],
            [
                18.24,
                -2.716
            ],
            [
                18.54,
                -2.716
            ]
        ]
    },
    {
        "id": "W_EXT_WEST_RET",
        "name": "Exterior Wall - Storefront West Pier 12in",
        "type": "Exterior",
        "thickness": 0.305,
        "length": 0.53,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            4.71,
            0.98
        ],
        "p2": [
            4.18,
            0.98
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.71,
                1.1325
            ],
            [
                4.18,
                1.1325
            ],
            [
                4.18,
                0.8275
            ],
            [
                4.71,
                0.8275
            ]
        ]
    },
    {
        "id": "W_EXT_WEST_JAMB",
        "name": "Exterior Wall - Storefront South Pier 12in",
        "type": "Exterior",
        "thickness": 0.305,
        "length": 0.53,
        "base_z": 0.0,
        "height": 3.943,
        "p1": [
            4.71,
            -4.29
        ],
        "p2": [
            4.18,
            -4.29
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.71,
                -4.1375
            ],
            [
                4.18,
                -4.1375
            ],
            [
                4.18,
                -4.4425
            ],
            [
                4.71,
                -4.4425
            ]
        ]
    },
    {
        "id": "W_INT_EXAM1_N",
        "name": "Interior Partition - Exam 1 North 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 1.78,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            14.82,
            0.98
        ],
        "p2": [
            14.82,
            -0.8
        ],
        "openings": [],
        "mitred_polygon": [
            [
                14.7565,
                0.98
            ],
            [
                14.7565,
                -0.8
            ],
            [
                14.8835,
                -0.8
            ],
            [
                14.8835,
                0.98
            ]
        ]
    },
    {
        "id": "W_INT_EXAM1_S",
        "name": "Interior Partition - Exam 1 South 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 3.72,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            14.82,
            -0.8
        ],
        "p2": [
            18.54,
            -0.8
        ],
        "openings": [
            {
                "id": "DR_EXAM1",
                "name": "00_Int Door - Single Glass Wood 36x84",
                "type": "Door",
                "offset": 0.5999999999999996,
                "width": 0.914,
                "height": 2.134,
                "sill_z": 0.0
            }
        ],
        "mitred_polygon": [
            [
                14.82,
                -0.8635
            ],
            [
                18.54,
                -0.8635
            ],
            [
                18.54,
                -0.7365
            ],
            [
                14.82,
                -0.7365
            ]
        ]
    },
    {
        "id": "W_INT_EXAM2_S",
        "name": "Interior Partition - Exam 2 South 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 3.42,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            14.82,
            -2.62
        ],
        "p2": [
            18.24,
            -2.62
        ],
        "openings": [
            {
                "id": "DR_EXAM2",
                "name": "00_Int Door - Single Glass Wood 36x84",
                "type": "Door",
                "offset": 0.5999999999999996,
                "width": 0.914,
                "height": 2.134,
                "sill_z": 0.0
            }
        ],
        "mitred_polygon": [
            [
                14.82,
                -2.6835
            ],
            [
                18.24,
                -2.6835
            ],
            [
                18.24,
                -2.5565
            ],
            [
                14.82,
                -2.5565
            ]
        ]
    },
    {
        "id": "W_INT_RESTROOM_W",
        "name": "Interior Partition - Restroom West 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 1.67,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            16.09,
            -2.62
        ],
        "p2": [
            16.09,
            -4.29
        ],
        "openings": [
            {
                "id": "DR_RESTROOM",
                "name": "00_Int Door - Single Flush Wood 36x84",
                "type": "Door",
                "offset": 0.8300000000000001,
                "width": 0.914,
                "height": 2.134,
                "sill_z": 0.0
            }
        ],
        "mitred_polygon": [
            [
                16.0265,
                -2.62
            ],
            [
                16.0265,
                -4.29
            ],
            [
                16.1535,
                -4.29
            ],
            [
                16.1535,
                -2.62
            ]
        ]
    },
    {
        "id": "W_INT_OFFICE_W",
        "name": "Interior Partition - Office / Lab West 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 2.76,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            12.87,
            0.98
        ],
        "p2": [
            12.87,
            -1.78
        ],
        "openings": [],
        "mitred_polygon": [
            [
                12.8065,
                0.98
            ],
            [
                12.8065,
                -1.78
            ],
            [
                12.933499999999999,
                -1.78
            ],
            [
                12.933499999999999,
                0.98
            ]
        ]
    },
    {
        "id": "W_INT_OFFICE_S",
        "name": "Interior Partition - Office / Lab South 5in",
        "type": "Interior",
        "thickness": 0.127,
        "length": 1.95,
        "base_z": 0.0,
        "height": 2.851,
        "p1": [
            12.87,
            -1.78
        ],
        "p2": [
            14.82,
            -1.78
        ],
        "openings": [
            {
                "id": "DR_OFFICE",
                "name": "00_Int Door - Single Glass Wood 36x84",
                "type": "Door",
                "offset": 0.9800000000000004,
                "width": 0.914,
                "height": 2.134,
                "sill_z": 0.0
            }
        ],
        "mitred_polygon": [
            [
                12.87,
                -1.8435000000000001
            ],
            [
                14.82,
                -1.8435000000000001
            ],
            [
                14.82,
                -1.7165
            ],
            [
                12.87,
                -1.7165
            ]
        ]
    },
    {
        "id": "W_PONY_EXAM_A",
        "name": "Divider - Pre-Testing Exam Booth A 4in",
        "type": "LowDivider",
        "thickness": 0.102,
        "length": 0.99,
        "base_z": 0.0,
        "height": 0.813,
        "p1": [
            4.32,
            -3.98
        ],
        "p2": [
            5.31,
            -3.98
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.32,
                -4.031
            ],
            [
                5.31,
                -4.031
            ],
            [
                5.31,
                -3.929
            ],
            [
                4.32,
                -3.929
            ]
        ]
    },
    {
        "id": "W_PONY_EXAM_B",
        "name": "Divider - Pre-Testing Exam Booth B 4in",
        "type": "LowDivider",
        "thickness": 0.102,
        "length": 0.74,
        "base_z": 0.0,
        "height": 0.813,
        "p1": [
            4.77,
            -3.98
        ],
        "p2": [
            4.77,
            -4.72
        ],
        "openings": [],
        "mitred_polygon": [
            [
                4.718999999999999,
                -3.98
            ],
            [
                4.718999999999999,
                -4.72
            ],
            [
                4.821,
                -4.72
            ],
            [
                4.821,
                -3.98
            ]
        ]
    },
    {
        "id": "W_PONY_EXAM_C",
        "name": "Divider - Pre-Testing Exam Booth C 4in",
        "type": "LowDivider",
        "thickness": 0.102,
        "length": 0.84,
        "base_z": 0.0,
        "height": 0.813,
        "p1": [
            3.83,
            -1.82
        ],
        "p2": [
            3.83,
            -2.66
        ],
        "openings": [],
        "mitred_polygon": [
            [
                3.779,
                -1.82
            ],
            [
                3.779,
                -2.66
            ],
            [
                3.8810000000000002,
                -2.66
            ],
            [
                3.8810000000000002,
                -1.82
            ]
        ]
    }
]
    created_walls = []
    for w in walls_data:
        p1 = XYZ(m2ft(w["p1"][0]), m2ft(w["p1"][1]), m2ft(w["base_z"]))
        p2 = XYZ(m2ft(w["p2"][0]), m2ft(w["p2"][1]), m2ft(w["base_z"]))
        geom_line = Line.CreateBound(p1, p2)
        h_ft = m2ft(w["height"])
        
        new_wall = Wall.Create(doc, geom_line, lvl_ground.Id, False)
        new_wall.get_Parameter(BuiltInCategory.WALL_USER_HEIGHT_PARAM).Set(h_ft)
        created_walls.append(new_wall)

    print(f"Successfully generated {len(created_walls)} native Revit walls.")

    # 4. Create Floors
    floors_data = [
    {
        "id": "FLR_MAIN",
        "name": "01_Commercial Concrete Slab Finish 3in",
        "thickness": 0.076,
        "elevation": 0.0,
        "polygon": [
            [
                4.71,
                0.98
            ],
            [
                18.54,
                0.98
            ],
            [
                18.54,
                -2.64
            ],
            [
                18.24,
                -2.64
            ],
            [
                18.24,
                -4.29
            ],
            [
                4.71,
                -4.29
            ]
        ]
    },
    {
        "id": "FLR_RAMP_LANDING",
        "name": "00_Exterior ADA Accessible Ramp & Landing 8in",
        "thickness": 0.203,
        "elevation": -0.21,
        "polygon": [
            [
                2.71,
                -1.48
            ],
            [
                4.41,
                -1.48
            ],
            [
                4.41,
                -4.29
            ],
            [
                2.71,
                -4.29
            ]
        ]
    }
]
    floor_types = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Floors).WhereElementIsElementType().ToElements()
    flr_type = floor_types[0] if len(floor_types) > 0 else None

    for flr in floors_data:
        curve_array = CurveArray()
        pts = flr["polygon"]
        for i in range(len(pts)):
            pt_a = pts[i]
            pt_b = pts[(i + 1) % len(pts)]
            xyz_a = XYZ(m2ft(pt_a[0]), m2ft(pt_a[1]), m2ft(flr["elevation"]))
            xyz_b = XYZ(m2ft(pt_b[0]), m2ft(pt_b[1]), m2ft(flr["elevation"]))
            curve_array.Append(Line.CreateBound(xyz_a, xyz_b))
        
        doc.Create.NewFloor(curve_array, flr_type, lvl_ground, False)

    print(f"Successfully generated {len(floors_data)} native Revit floors.")
    t.Commit()

if __name__ == "__main__":
    if IN_REVIT:
        uiapp = __revit__
        build_eyesonpark_model(uiapp.ActiveUIDocument.Document)
    else:
        print("Revit API not loaded. Run inside Autodesk Revit 2027.")
