# -*- coding: utf-8 -*-
"""
Apply ONE value to the currently selected features across multiple layers (minimal params).

Params (ArcGIS Pro script tool; keep this exact order):
0. Base layer (Feature Layer)  -> must have >=1 selected feature (we use the first if no manual override).
1. Source field (Field)        -> from the base layer; used unless Manual override is provided.
2. Manual override value       -> optional; if provided, use this instead of reading from base.
3. Targets table (Value Table) -> two columns: [TargetLayer, TargetField].

Author: Yunhao - SASA & GPT - GREAT helper

Last Update: 06/11/2025

Tested with ArcGIS Pro 3.5.4
"""

import arcpy
import sys
from datetime import datetime

EXCLUDE_FIELD_TYPES = {"Geometry", "OID"}
EXCLUDE_FIELD_NAMES = {"OBJECTID", "FID", "GLOBALID", "GlobalID", "Shape", "SHAPE", "Shape_Length", "Shape_Area"}


def add(msg): arcpy.AddMessage(msg)
def warn(msg): arcpy.AddWarning(msg)
def err(msg): arcpy.AddError(msg)


def make_view(layer, name_hint):
    """Ensure we work on a feature layer view (so selections are respected)."""
    return arcpy.management.MakeFeatureLayer(layer, name_hint).getOutput(0)


def get_first_selected_value(layer, field_name):
    """Return the value of 'field_name' from the FIRST selected feature in 'layer'."""
    count = int(arcpy.management.GetCount(layer).getOutput(0))
    if count < 1:
        raise RuntimeError(f"Base layer has no selection. Select at least one feature in: {layer}")
    with arcpy.da.SearchCursor(layer, [field_name]) as cur:
        for row in cur:
            return row[0]
    raise RuntimeError("Unexpected: could not read the first selected row.")


def parse_vt_targets(vt_text):
    """
    Parse a 2-col value table (as ArcGIS passes text) into list[(target_layer, target_field)].
    """
    pairs = []
    if not vt_text:
        return pairs
    rows = [r for r in vt_text.split(";") if r.strip()]
    for r in rows:
        parts = [p.strip() for p in r.split(",")]
        if len(parts) < 2:
            parts = r.split()
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def coerce_value_to_field(value, field):
    """
    Best-effort coercion of 'value' to the target field's type.
    """
    ftype = field.type  # 'String', 'Integer', 'Double', 'Date', ...
    if value is None:
        return None
    try:
        if ftype == "String":
            return str(value)
        elif ftype in ("Short", "SmallInteger", "Integer"):
            return int(value)
        elif ftype in ("Single", "Double", "Float"):
            return float(value)
        elif ftype == "Date":
            if isinstance(value, datetime):
                return value
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y"):
                try:
                    return datetime.strptime(str(value), fmt)
                except Exception:
                    pass
            return value
        else:
            return value
    except Exception:
        return value


def main():
    # ---------------- Parameters ----------------
    base_layer = arcpy.GetParameterAsText(0)          # Feature Layer
    source_field = arcpy.GetParameterAsText(1)        # Field (from base_layer)
    manual_override = arcpy.GetParameterAsText(2)     # String (optional)
    targets_vt_text = arcpy.GetParameterAsText(3)     # Value Table: [TargetLayer, TargetField]

    add("=== Apply ONE Value to Selections (minimal) — Started ===")

    targets = parse_vt_targets(targets_vt_text)
    if not targets:
        raise RuntimeError("No targets provided. Fill the Value Table with [TargetLayer, TargetField].")

    # Decide the value to apply
    if manual_override and manual_override.strip() != "":
        value_to_apply = manual_override
        add(f"Using manual override value: {repr(value_to_apply)}")
    else:
        base_view = make_view(base_layer, "base_view")
        value_to_apply = get_first_selected_value(base_view, source_field)
        add(f"Using value from FIRST selected in base: {source_field} = {repr(value_to_apply)}")

    total_layers, total_candidates, total_updates = 0, 0, 0
    per_layer = []

    for i, (tgt_layer_path, tgt_field_name) in enumerate(targets, 1):
        lyr_view = make_view(tgt_layer_path, f"tgt_view_{i}")

        # Validate field exists and is not system/geometry
        fields = {f.name: f for f in arcpy.ListFields(lyr_view)}
        if tgt_field_name not in fields:
            warn(f"[{tgt_layer_path}] Field '{tgt_field_name}' not found. Skipping.")
            continue
        fobj = fields[tgt_field_name]
        if fobj.type in EXCLUDE_FIELD_TYPES or tgt_field_name in EXCLUDE_FIELD_NAMES:
            warn(f"[{tgt_layer_path}] Field '{tgt_field_name}' is not updatable. Skipping.")
            continue

        # Respect current selection
        sel_count = int(arcpy.management.GetCount(lyr_view).getOutput(0))
        if sel_count == 0:
            warn(f"[{tgt_layer_path}] No selected features. Skipping.")
            continue

        total_layers += 1
        total_candidates += sel_count

        coerced_value = coerce_value_to_field(value_to_apply, fobj)

        updates_here = 0
        with arcpy.da.UpdateCursor(lyr_view, [tgt_field_name]) as cur:
            for (cur_val,) in cur:
                if cur_val != coerced_value:
                    cur.updateRow([coerced_value])
                    updates_here += 1

        total_updates += updates_here
        per_layer.append((tgt_layer_path, tgt_field_name, sel_count, updates_here))
        add(f"[DONE] [{tgt_layer_path}] Updated {updates_here} of {sel_count} in '{tgt_field_name}'.")

    # Summary
    add("=== Summary ===")
    for lyr, fld, cand, ups in per_layer:
        add(f"- {lyr} → {fld}: candidates={cand}, updated={ups}")
    add(f"Layers processed: {total_layers}")
    add(f"Features considered: {total_candidates}")
    add(f"Total updated: {total_updates}")
    add("=== Apply ONE Value to Selections (minimal) — Finished ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(str(e))
        tb = arcpy.GetMessages(2)
        if tb:
            err(tb)
        sys.exit(1)
