# -*- coding: utf-8 -*-
"""
reisource_scan2bim — IFC4 & Revit Classification, PropertySet, and Material Layer Engine
Provides canonical mappings from Scan2BIM semantic categories to:
- IFC4 entity classes & PredefinedTypes (replacing deprecated IFC2x3 entities)
- CSI MasterFormat / OmniClass Table 21 & 23 classification codes
- Standard buildingSMART Pset_*Common properties & Qto_*BaseQuantities
- Autodesk Revit BuiltInCategory & assembly matching metadata
"""

IFC4_TAXONOMY = {
    # Walls
    "Exterior": {
        "ifc_class": "IfcWall",
        "predefined_type": "SOLIDWALL",
        "revit_category": "OST_Walls",
        "omniclass": "21-01 10 20",
        "masterformat": "09 22 16",
        "pset_name": "Pset_WallCommon",
        "pset_props": {"IsExternal": True, "LoadBearing": False, "ExtendToStructure": True},
    },
    "Exterior_Demising": {
        "ifc_class": "IfcWall",
        "predefined_type": "SOLIDWALL",
        "revit_category": "OST_Walls",
        "omniclass": "21-01 10 20",
        "masterformat": "09 22 16",
        "pset_name": "Pset_WallCommon",
        "pset_props": {"IsExternal": True, "LoadBearing": False, "ExtendToStructure": True, "AcousticRating": "STC 50"},
    },
    "Interior": {
        "ifc_class": "IfcWall",
        "predefined_type": "PARTITIONING",
        "revit_category": "OST_Walls",
        "omniclass": "21-03 10 10",
        "masterformat": "09 29 00",
        "pset_name": "Pset_WallCommon",
        "pset_props": {"IsExternal": False, "LoadBearing": False, "ExtendToStructure": False},
    },
    "LowDivider": {
        "ifc_class": "IfcWall",
        "predefined_type": "PARTITIONING",
        "revit_category": "OST_Walls",
        "omniclass": "21-03 10 10",
        "masterformat": "09 29 00",
        "pset_name": "Pset_WallCommon",
        "pset_props": {"IsExternal": False, "LoadBearing": False, "ExtendToStructure": False},
    },
    # Openings & Curtain Walls
    "Door": {
        "ifc_class": "IfcDoor",
        "predefined_type": "DOOR",
        "revit_category": "OST_Doors",
        "omniclass": "21-03 20 10",
        "masterformat": "08 14 00",
        "pset_name": "Pset_DoorCommon",
        "pset_props": {"IsExternal": False, "HandicapAccessible": True},
    },
    "Window": {
        "ifc_class": "IfcWindow",
        "predefined_type": "WINDOW",
        "revit_category": "OST_Windows",
        "omniclass": "21-02 20 20",
        "masterformat": "08 51 13",
        "pset_name": "Pset_WindowCommon",
        "pset_props": {"IsExternal": True},
    },
    "CurtainWall": {
        "ifc_class": "IfcCurtainWall",
        "predefined_type": "NOTDEFINED",
        "revit_category": "OST_Walls",
        "omniclass": "21-02 20 10",
        "masterformat": "08 44 13",
        "pset_name": "Pset_CurtainWallCommon",
        "pset_props": {"IsExternal": True},
    },
    # Slabs, Ramps, Ceilings
    "InteriorFloor": {
        "ifc_class": "IfcSlab",
        "predefined_type": "FLOOR",
        "revit_category": "OST_Floors",
        "omniclass": "21-02 10 10",
        "masterformat": "03 30 00",
        "pset_name": "Pset_SlabCommon",
        "pset_props": {"IsExternal": False, "LoadBearing": True},
    },
    "Ramp": {
        "ifc_class": "IfcRamp",
        "predefined_type": "STRAIGHT_RUN_RAMP",
        "revit_category": "OST_Ramps",
        "omniclass": "21-03 40 20",
        "masterformat": "03 30 00",
        "pset_name": "Pset_RampCommon",
        "pset_props": {"IsExternal": True, "HandicapAccessible": True},
    },
    "SuspendedCeiling": {
        "ifc_class": "IfcCovering",
        "predefined_type": "CEILING",
        "revit_category": "OST_Ceilings",
        "omniclass": "21-03 30 50",
        "masterformat": "09 51 13",
        "pset_name": "Pset_CoveringCommon",
        "pset_props": {"IsExternal": False},
    },
    # Plumbing & ADA Fixtures
    "Toilet": {
        "ifc_class": "IfcSanitaryTerminal",
        "predefined_type": "TOILETPAN",
        "revit_category": "OST_PlumbingFixtures",
        "omniclass": "23-29 11 11",
        "masterformat": "22 42 13",
        "pset_name": "Pset_SanitaryTerminalTypeToiletPan",
        "pset_props": {"Mounting": "WALLHUNG"},
    },
    "Sink": {
        "ifc_class": "IfcSanitaryTerminal",
        "predefined_type": "WASHHANDBASIN",
        "revit_category": "OST_PlumbingFixtures",
        "omniclass": "23-29 11 13",
        "masterformat": "22 42 16",
        "pset_name": "Pset_SanitaryTerminalTypeWashHandBasin",
        "pset_props": {},
    },
    "GrabBar": {
        "ifc_class": "IfcRailing",
        "predefined_type": "HANDRAIL",
        "revit_category": "OST_SpecialityEquipment",
        "omniclass": "23-15 31 11",
        "masterformat": "10 28 13",
        "pset_name": "Pset_RailingCommon",
        "pset_props": {"IsExternal": False},
    },
    # Casework & Furniture
    "IslandDesk": {
        "ifc_class": "IfcFurniture",
        "predefined_type": "DESK",
        "revit_category": "OST_Casework",
        "omniclass": "23-21 11 11",
        "masterformat": "12 32 00",
        "pset_name": "Pset_FurnitureTypeDesk",
        "pset_props": {},
    },
    "ServiceCounter": {
        "ifc_class": "IfcFurniture",
        "predefined_type": "USERDEFINED",
        "revit_category": "OST_Casework",
        "omniclass": "23-21 11 15",
        "masterformat": "12 35 50",
        "pset_name": "Pset_FurnitureTypeCommon",
        "pset_props": {},
    },
    "WallDisplay": {
        "ifc_class": "IfcFurniture",
        "predefined_type": "SHELF",
        "revit_category": "OST_Casework",
        "omniclass": "23-21 15 11",
        "masterformat": "12 32 16",
        "pset_name": "Pset_FurnitureTypeCommon",
        "pset_props": {},
    },
    "Vanity": {
        "ifc_class": "IfcFurniture",
        "predefined_type": "CABINET",
        "revit_category": "OST_Casework",
        "omniclass": "23-21 15 13",
        "masterformat": "12 35 30",
        "pset_name": "Pset_FurnitureTypeCommon",
        "pset_props": {},
    },
    "Furniture": {
        "ifc_class": "IfcFurniture",
        "predefined_type": "USERDEFINED",
        "revit_category": "OST_Furniture",
        "omniclass": "23-21 11 00",
        "masterformat": "12 50 00",
        "pset_name": "Pset_FurnitureTypeCommon",
        "pset_props": {},
    },
    # MEP & Lighting
    "LightFixture": {
        "ifc_class": "IfcLightFixture",
        "predefined_type": "POINTSOURCE",
        "revit_category": "OST_LightingFixtures",
        "omniclass": "23-35 41 11",
        "masterformat": "26 51 00",
        "pset_name": "Pset_LightFixtureTypeCommon",
        "pset_props": {},
    },
    "Space": {
        "ifc_class": "IfcSpace",
        "predefined_type": "SPACE",
        "revit_category": "OST_Rooms",
        "omniclass": "13-11 00 00",
        "masterformat": "00 00 00",
        "pset_name": "Pset_SpaceCommon",
        "pset_props": {"IsExternal": False},
    },
}


def get_classification(category_key, fallback="Furniture"):
    """Returns canonical IFC4/Revit classification dict for a semantic key."""
    return IFC4_TAXONOMY.get(category_key, IFC4_TAXONOMY[fallback])


def attach_pset_and_classification(model, element, category_key, extra_props=None, classification_entity=None):
    """
    Attaches Pset_*Common and CSI/OmniClass IfcClassificationReference to an IFC4 entity.
    Requires an active ifcopenshell model.
    """
    import ifcopenshell.api

    spec = get_classification(category_key)
    props = dict(spec.get("pset_props", {}))
    if extra_props:
        props.update(extra_props)

    if props and spec.get("pset_name"):
        pset = ifcopenshell.api.run("pset.add_pset", model, product=element, name=spec["pset_name"])
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)

    if classification_entity is not None and spec.get("omniclass"):
        ifcopenshell.api.run(
            "classification.add_reference",
            model,
            products=[element],
            reference=classification_entity,
            identification=spec["omniclass"],
            name=f"CSI {spec.get('masterformat', '')} / {category_key}",
        )


def assign_wall_material_layers(model, wall_entity, thickness_m, wall_type="Interior"):
    """
    Assigns an IfcMaterialLayerSetUsage to an IfcWall so BIM viewers and Revit
    recognize compound stud + gypsum wallboard assemblies.
    """
    import ifcopenshell.api

    thk = float(thickness_m)
    if thk >= 0.145:
        gwb = 0.016  # 5/8" Type X GWB
        stud = max(0.01, thk - 2.0 * gwb)
        layers_spec = [
            ("Gypsum Wall Board 5/8in", gwb),
            ("Metal Stud / Acoustic Core", stud),
            ("Gypsum Wall Board 5/8in", gwb),
        ]
        set_name = f"Commercial Wall Assembly ({int(round(thk * 1000))}mm)"
    elif thk >= 0.115:
        gwb = 0.016
        stud = max(0.01, thk - 2.0 * gwb)
        layers_spec = [
            ("Gypsum Wall Board 5/8in", gwb),
            ("Metal Stud 3-5/8in", stud),
            ("Gypsum Wall Board 5/8in", gwb),
        ]
        set_name = "Interior Partition 5in GWB"
    else:
        layers_spec = [(f"Partition Core ({wall_type})", thk)]
        set_name = f"Single Layer Assembly ({int(round(thk * 1000))}mm)"

    layer_set = ifcopenshell.api.run("material.add_material_set", model, name=set_name, set_type="IfcMaterialLayerSet")
    for mat_name, layer_thk in layers_spec:
        mat = ifcopenshell.api.run("material.add_material", model, name=mat_name)
        layer = ifcopenshell.api.run("material.add_layer", model, layer_set=layer_set, material=mat)
        ifcopenshell.api.run("material.edit_layer", model, layer=layer, attributes={"LayerThickness": float(layer_thk)})

    ifcopenshell.api.run("material.assign_material", model, products=[wall_entity], material=layer_set)
