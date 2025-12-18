# -*- coding: utf-8 -*-
"""
Find Overlapping Areas (Intersect) - ArcGIS Pro Script Tool
==========================================================

Author: Yunhao Zhao (project owner)
Script prepared for GitHub documentation & reuse.

Purpose
-------
This script identifies the spatial overlap between two input feature layers
(or feature classes) using the ArcGIS "Intersect" geoprocessing tool and
writes the result to a new feature class in a file geodatabase (GDB).

Key Behaviours
--------------
1) Output is saved into a geodatabase:
   - If the user supplies a full output path (recommended), that path is used.
   - If the user supplies ONLY a feature class name, the script will place
     the output in:
       a) arcpy.env.workspace (if it is a GDB), otherwise
       b) the same GDB as Input Layer 1 (if it can be resolved).

2) Attributes (fields) are preserved from BOTH inputs:
   - join_attributes is set to "ALL", which keeps attributes from all inputs.

3) The output feature class is added to the current ArcGIS Pro map (if available).

Toolbox Parameters (recommended)
--------------------------------
Parameter 0 (Input):  Input Layer 1        [Feature Layer]
Parameter 1 (Input):  Input Layer 2        [Feature Layer]
Parameter 2 (Output): Output Feature Class [Feature Class]

Recommended Setup in ArcGIS Pro Script Tool
-------------------------------------------
- Set "Output Feature Class" (Param 2) as a Feature Class output.
- Optionally enable "Add output to display" (ArcGIS Pro will usually do this
  automatically for output datasets, but the script also attempts to add it).

Requirements
------------
- ArcGIS Pro with arcpy available
- Appropriate license level to run analysis tools (Intersect)

Notes
-----
- Intersect works for points/lines/polygons; the geometry of the output depends
  on input types and spatial relationships.
- If inputs have many fields, the output may contain many fields as well.
- If you need only overlapping polygon parts for a polygon layer, Intersect is
  appropriate; for other workflows, tools like Pairwise Intersect / Clip / Erase
  may be more suitable.

"""

import os
import arcpy


def _resolve_output_path(output_fc: str, fallback_from_layer: str) -> str:
    """
    Resolve output feature class path.

    If output_fc is an existing path (contains .gdb or workspace separators),
    return it directly. If it's only a name, attempt to place it in:
    1) arcpy.env.workspace (if it is a .gdb),
    2) the same GDB as fallback_from_layer (if detectable),
    otherwise raise an error.
    """
    # If user provided a full path (common for Script Tools), keep it.
    # Heuristic: contains ".gdb" or ends with ".shp" (not preferred here) or contains a path separator.
    if ".gdb" in output_fc.lower() or os.path.sep in output_fc or output_fc.startswith(("\\\\", "/")):
        return output_fc

    # Otherwise treat as a name; place it into a GDB.
    env_ws = arcpy.env.workspace
    if env_ws and env_ws.lower().endswith(".gdb"):
        return os.path.join(env_ws, output_fc)

    # Try to derive the workspace from layer 1 (if it is a feature class in a GDB).
    desc = arcpy.Describe(fallback_from_layer)
    # For layers, catalogPath usually points to the underlying dataset path.
    base_path = getattr(desc, "catalogPath", None) or getattr(desc, "path", None)
    if base_path and ".gdb" in base_path.lower():
        # base_path might be "...something.gdb\\featureclass"
        gdb_index = base_path.lower().find(".gdb")
        gdb_path = base_path[: gdb_index + 4]  # include ".gdb"
        return os.path.join(gdb_path, output_fc)

    raise ValueError(
        "Output Feature Class was provided as a name only, but no valid GDB workspace "
        "could be resolved. Please set arcpy.env.workspace to a .gdb or provide a full "
        "output path like: C:\\path\\your.gdb\\OutputName"
    )


def find_overlaps(layer1: str, layer2: str, output_fc: str) -> str:
    """
    Perform Intersect analysis to generate overlapping features.

    Parameters
    ----------
    layer1 : str
        Input feature layer / feature class.
    layer2 : str
        Input feature layer / feature class.
    output_fc : str
        Output feature class path OR output name (if a valid GDB workspace can be resolved).

    Returns
    -------
    str
        Path to the output feature class.
    """
    try:
        out_path = _resolve_output_path(output_fc, fallback_from_layer=layer1)

        arcpy.AddMessage("=== Find Overlaps (Intersect) ===")
        arcpy.AddMessage(f"Input Layer 1: {layer1}")
        arcpy.AddMessage(f"Input Layer 2: {layer2}")
        arcpy.AddMessage(f"Output FC     : {out_path}")

        # Overwrite behaviour (recommended for iterative QA workflows)
        arcpy.env.overwriteOutput = True

        # Intersect: keep ALL attributes from all inputs
        # output_type defaults to "INPUT" which generally preserves the most appropriate geometry type
        arcpy.analysis.Intersect(
            in_features=[layer1, layer2],
            out_feature_class=out_path,
            join_attributes="ALL"
        )

        # Add output to current map if running inside ArcGIS Pro
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            m = aprx.activeMap
            if m:
                m.addDataFromPath(out_path)
                arcpy.AddMessage("Output added to the current map.")
        except Exception:
            # Safe to ignore if not running in Pro UI context
            arcpy.AddMessage("Running outside ArcGIS Pro UI context; skipped adding output to map.")

        arcpy.AddMessage("Done.")
        return out_path

    except Exception as e:
        arcpy.AddError(f"Error in find_overlaps(): {str(e)}")
        raise


if __name__ == "__main__":
    try:
        # ArcGIS Pro Script Tool parameters
        input_layer1 = arcpy.GetParameterAsText(0)
        input_layer2 = arcpy.GetParameterAsText(1)
        output_fc = arcpy.GetParameterAsText(2)

        out_fc_path = find_overlaps(input_layer1, input_layer2, output_fc)

        # Set output parameter (Feature Class)
        arcpy.SetParameterAsText(2, out_fc_path)

    except Exception as e:
        arcpy.AddError(f"Error in script: {str(e)}")
        raise
