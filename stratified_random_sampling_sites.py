# -*- coding: utf-8 -*-
"""
Stratified Random Sampling (GLG Contractor) - ArcGIS Pro Script Tool
====================================================================

Purpose
-------
This script performs stratified (hierarchy-based) random sampling from an input
feature layer for QA / audit workflows. It filters records maintained by a
specific contractor (GLG) and then selects a fixed number of random samples per
"Hierarchy" category.

Special Rule
------------
For the "Major Community Parks" hierarchy, the script avoids selecting Asset_IDs
that were already sampled in a previous period. The previous period sample is
provided as a CSV (comparison file).

Inputs (ArcGIS Pro Script Tool Parameters)
------------------------------------------
Parameter 0 (Input):  Feature Layer (current period dataset)
Parameter 1 (Input):  Comparison CSV (previous period sample results)
Parameter 2 (Output): Output CSV (current period sample results)

Outputs
-------
- A CSV file containing the sampled records.
- Column structure is aligned to the comparison CSV where possible.

Requirements
------------
- ArcGIS Pro with arcpy available
- pandas installed in the ArcGIS Pro Python environment

Notes
-----
- Ensure the input feature layer contains fields:
  - "PG_MNTND"
  - "Hierarchy"
  - "Asset_ID"
- If some columns in the comparison CSV do not exist in the current dataset,
  they will be skipped (with a warning message).
"""

import os
import random
import arcpy
import pandas as pd


def feature_class_to_df(fc, field_list):
    """Convert a feature class/table to a pandas DataFrame using arcpy.da.SearchCursor."""
    rows = [row for row in arcpy.da.SearchCursor(fc, field_list)]
    return pd.DataFrame(rows, columns=field_list)


def ensure_folder(path):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)


def main():
    # --- Parameters ---
    feature_layer = arcpy.GetParameterAsText(0)
    comparison_csv = arcpy.GetParameterAsText(1)
    output_csv = arcpy.GetParameterAsText(2)

    arcpy.AddMessage("=== Stratified Random Sampling (GLG) ===")
    arcpy.AddMessage(f"Input feature layer : {feature_layer}")
    arcpy.AddMessage(f"Comparison CSV      : {comparison_csv}")
    arcpy.AddMessage(f"Output CSV          : {output_csv}")

    # --- Read previous sample (Major Community Parks Asset_IDs) ---
    comparison_df = pd.read_csv(comparison_csv)

    required_cols = {"Hierarchy", "Asset_ID"}
    missing_required = required_cols - set(comparison_df.columns)
    if missing_required:
        raise ValueError(
            f"Comparison CSV is missing required columns: {sorted(missing_required)}"
        )

    previous_major_parks_asset_ids = set(
        comparison_df.loc[
            comparison_df["Hierarchy"] == "Major Community Parks", "Asset_ID"
        ].astype(str)
    )
    arcpy.AddMessage(f"Previous Major Community Parks Asset_ID count: {len(previous_major_parks_asset_ids)}")

    # --- Sampling plan (per hierarchy) ---
    hierarchy_samples = {
        "Civic & Commercial Facilities": 10,
        "Landscape Site": 15,
        "Major Community Parks": 2,
        "Municipal Open Space": 16,
        "Neighbourhood & Local Open Space": 29,
        "Streetscape": 10
    }

    # --- Build SQL (safer field delimiters) ---
    pg_field = arcpy.AddFieldDelimiters(feature_layer, "PG_MNTND")
    hierarchy_field = arcpy.AddFieldDelimiters(feature_layer, "Hierarchy")
    asset_id_field = arcpy.AddFieldDelimiters(feature_layer, "Asset_ID")

    contractor_value = "Parks Maintenance Contractor GLG"
    base_query = f"{pg_field} = '{contractor_value}'"

    # --- Ensure we are working with a layer ---
    base_layer = arcpy.management.MakeFeatureLayer(feature_layer, "base_layer_glg").getOutput(0)

    # Apply contractor filter
    arcpy.management.SelectLayerByAttribute(base_layer, "NEW_SELECTION", base_query)

    oid_field = arcpy.Describe(base_layer).OIDFieldName

    selected_oids_by_hierarchy = {}

    # --- Stratified selection ---
    for hierarchy_value, sample_size in hierarchy_samples.items():
        arcpy.AddMessage(f"\n--- Hierarchy: {hierarchy_value} | Target sample: {sample_size} ---")

        # Subset selection for this hierarchy + contractor filter
        subset_query = f"{hierarchy_field} = '{hierarchy_value}' AND {base_query}"
        arcpy.management.SelectLayerByAttribute(base_layer, "NEW_SELECTION", subset_query)

        if hierarchy_value == "Major Community Parks":
            # Pull (OID, Asset_ID) and exclude previous Asset_IDs
            pairs = []
            with arcpy.da.SearchCursor(base_layer, [oid_field, "Asset_ID"]) as cur:
                for oid, aid in cur:
                    if aid is None:
                        continue
                    pairs.append((oid, str(aid)))

            valid_oids = [oid for oid, aid in pairs if aid not in previous_major_parks_asset_ids]

            arcpy.AddMessage(f"Candidates (total): {len(pairs)}")
            arcpy.AddMessage(f"Candidates (after excluding previous Asset_IDs): {len(valid_oids)}")

            if len(valid_oids) > sample_size:
                chosen = random.sample(valid_oids, sample_size)
            else:
                chosen = valid_oids

            selected_oids_by_hierarchy[hierarchy_value] = chosen
            arcpy.AddMessage(f"Selected: {len(chosen)}")

        else:
            # Regular: sample by OID
            oids = [row[0] for row in arcpy.da.SearchCursor(base_layer, [oid_field])]
            arcpy.AddMessage(f"Candidates: {len(oids)}")

            if len(oids) > sample_size:
                chosen = random.sample(oids, sample_size)
            else:
                chosen = oids

            selected_oids_by_hierarchy[hierarchy_value] = chosen
            arcpy.AddMessage(f"Selected: {len(chosen)}")

    # --- Combine all selected OIDs ---
    all_selected_oids = [oid for oids in selected_oids_by_hierarchy.values() for oid in oids]
    all_selected_oids = sorted(set(all_selected_oids))

    if not all_selected_oids:
        raise ValueError("No features were selected. Please check filters and sampling plan.")

    arcpy.AddMessage(f"\nTotal selected features (all hierarchies): {len(all_selected_oids)}")

    # Build final selection layer
    # (OID IN (...)) is safe here because sample sizes are small.
    oid_delim = arcpy.AddFieldDelimiters(feature_layer, oid_field)
    final_query = f"{oid_delim} IN ({', '.join(map(str, all_selected_oids))})"

    final_layer = arcpy.management.MakeFeatureLayer(base_layer, "final_sample_layer", final_query).getOutput(0)

    # Export selected features to in_memory and convert to DataFrame
    temp_fc = "in_memory/temp_sample_fc"
    arcpy.management.CopyFeatures(final_layer, temp_fc)

    # Export fields (exclude geometry)
    field_list = [f.name for f in arcpy.ListFields(temp_fc) if f.type != "Geometry"]
    selected_df = feature_class_to_df(temp_fc, field_list)

    # Align columns to comparison CSV where possible
    desired_cols = list(comparison_df.columns)
    available_cols = [c for c in desired_cols if c in selected_df.columns]
    missing_cols = [c for c in desired_cols if c not in selected_df.columns]

    if missing_cols:
        arcpy.AddMessage(f"WARNING: These columns exist in comparison CSV but not in current dataset, skipping: {missing_cols}")

    output_df = selected_df[available_cols]

    ensure_folder(output_csv)
    output_df.to_csv(output_csv, index=False)
    arcpy.AddMessage(f"\nOutput CSV saved: {output_csv}")
    arcpy.AddMessage(f"Columns exported: {len(available_cols)}")

    # Cleanup
    arcpy.management.Delete(temp_fc)
    arcpy.AddMessage("Cleanup done. Finished.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        arcpy.AddError(str(e))
        raise
