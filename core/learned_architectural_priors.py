# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Learned Architectural Priors
Reverse-engineered from Autodesk Revit Ground Truth Models (Eyes on Park.rvt)
Encapsulates architectural drafting conventions, orthogonal grid snapping,
standardized commercial wall types, door hosting rules, and ADA assemblies.
"""

LEARNED_ARCHITECTURAL_PRIORS = {
    "project_grid_rules": {
        "snapping_mode": "Orthogonal_Grid_Dominant",
        "rationale": "Architectural conventions standardize demising boundaries to orthogonal axes (90-degree corners) rather than following minor physical framing taper or scan drift."
    },
    
    "datums": {
        "finish_floor_elevation": 0.000,
        "ceiling_grid_elevation": 2.743,   # 9'-0"
        "partition_top_elevation": 2.851,  # 9'-4 1/4" (extends above ACT ceiling for acoustic privacy)
        "structural_deck_elevation": 3.943 # 12'-11 1/4" (full underside of deck)
    },
    
    "wall_standards": {
        "demising_wall": {
            "thickness": 0.152,  # 6" Metal Stud / CMU Demising
            "height": 3.943,     # Extends to underside of structural deck
            "type": "Exterior_Demising"
        },
        "interior_partition": {
            "thickness": 0.127,  # 5" GWB on 3-5/8" Metal Stud
            "height": 2.851,     # Extends to above ceiling grid
            "type": "Interior_Partition"
        },
        "curtain_wall_pier": {
            "thickness": 0.305,  # 12" Structural Pier / Pilaster
            "height": 3.943,
            "type": "Storefront_Pier"
        },
        "low_divider": {
            "thickness": 0.102,  # 4" Pony Wall / Divider
            "height": 0.914,     # 36" Counter Height
            "type": "Low_Divider"
        }
    },
    
    "door_standards": {
        "commercial_storefront_double": {
            "width": 1.829,  # 6'-0"
            "height": 2.692, # 8'-10"
            "panel_type": "Glazed_Double_Aluminum"
        },
        "interior_single_standard": {
            "width": 0.914,  # 36" Clear ADA
            "height": 2.134, # 7'-0"
            "panel_type": "Flush_Wood_With_Glazing"
        },
        "interior_storage_single": {
            "width": 0.762,  # 30"
            "height": 2.134, # 7'-0"
            "panel_type": "Flush_Wood"
        }
    },
    
    "plumbing_ada_standards": {
        "water_closet": {
            "centerline_to_side_wall": 0.457, # 18" ADA requirement
            "mounting_height": 0.432,         # 17"-19" ADA seat height
            "carrier_type": "Wall-Hung Commercial"
        },
        "grab_bars": {
            "rear_wall_length": 0.914,        # 36" Grab Bar
            "side_wall_length": 1.067,        # 42" Grab Bar
            "mounting_height": 0.864          # 33"-36" AFF
        },
        "vanity_lavatory": {
            "rim_height": 0.864,              # 34" max AFF
            "knee_clearance_depth": 0.483     # 19" min
        }
    }
}
