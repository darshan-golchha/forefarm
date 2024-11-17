from flask import jsonify, abort
import geopandas as gpd
import ast
import pandas as pd
import numpy as np
from mlrunner import load_model, predictor

df = pd.read_csv("processed_data.csv")
m1 = load_model("ml_1_model.pkl")
m2 = load_model("ml_2_model.pkl")

# Simple GeoJSON validation
def is_valid_geojson(geojson):
    required_fields = ['type', 'geometry', 'properties']
    return all(field in geojson for field in required_fields)

def get_countyinfo(geojson):
    if not is_valid_geojson(geojson):
        abort(400, 'Invalid GeoJSON')
    polygon_gdf = gpd.GeoDataFrame.from_features([geojson], crs="EPSG:4326")
    counties_gdf = gpd.read_file("counties2.geojson")
    polygon_gdf = polygon_gdf.to_crs(counties_gdf.crs)
    farm_area = polygon_gdf.geometry.area.sum()
    intersecting_counties = counties_gdf[counties_gdf.geometry.intersects(polygon_gdf.unary_union)]
    intersecting_counties["intersection_area"] = intersecting_counties.geometry.intersection(
        polygon_gdf.unary_union
    ).area
    intersecting_counties["percentage_of_farm"] = (
        intersecting_counties["intersection_area"] / farm_area * 100
    )
    intersecting_counties.rename(columns={"COUNTY_NAME": "county"}, inplace=True)
    return intersecting_counties[["county", "percentage_of_farm"]].to_dict(orient="records")

def get_countyvec(county):
    global df
    # Filter the DataFrame
    filtered_df = df[df["county"] == county]
    
    if filtered_df.empty:
        # Handle the case where the county is not found
        print(f"No data found for county: {county}")
        return None  # or return a default value, e.g., [] or some placeholder

    try:
        # Extract and return the 'features' value
        return filtered_df["features"].apply(ast.literal_eval).values[0]
    except Exception as e:
        # Handle unexpected errors, e.g., invalid literal_eval or missing data
        print(f"An error occurred: {e}")
        return None  # or return a default value


# def get_labels(ctyinfo):
#     global m1, m2
#     vecs = []
#     for cty in ctyinfo:
#         info = cty["county"].lower()
#         county_vecs = get_countyvec(info.replace(" ", ""))
#         vecs.append(county_vecs)
#     vecs = np.array(vecs, dtype=float)

#     # Safely parse weights
#     weights = []
#     for cty in ctyinfo:
#         percentage = cty["percentage_of_farm"]
#         if isinstance(percentage, dict) and "$numberDouble" in percentage:
#             weights.append(float(percentage["$numberDouble"]))
#         elif isinstance(percentage, (float, int)):
#             weights.append(float(percentage))
#         else:
#             raise ValueError(f"Unexpected format for percentage_of_farm: {percentage}")

#     weights = np.array(weights, dtype=float)
#     weights = weights / weights.sum()

#     weighted_avg_vecs = []
#     for i in range(7):
#         weighted_avg_vec = (vecs[:, i, :] * weights[:, np.newaxis]).sum(axis=0)
#         weighted_avg_vecs.append(weighted_avg_vec)
#     weighted_avg_vecs = np.array(weighted_avg_vecs)

#     res = []
#     for vec in weighted_avg_vecs:
#         if vec is not None:
#             res.append(predictor([vec.tolist()], m1, m2).tolist()[0])
#         else:
#             res.append("Normal Weather")
#     return res


def get_labels(ctyinfo):
    global m1, m2
    vecs = []
    valid_weights = []
    for cty in ctyinfo:
        info = cty["county"].lower()
        county_vecs = get_countyvec(info.replace(" ", ""))
        if county_vecs is not None:
            vecs.append(county_vecs)
            valid_weights.append(cty["percentage_of_farm"])
        else:
            print(f"Skipping county '{info}' due to missing vector.")

    if not vecs:
        raise ValueError("No valid county vectors found.")

    vecs = np.array(vecs, dtype=object)  # Use object dtype for flexibility in dimensions

    # Safely parse weights
    weights = []
    for percentage in valid_weights:
        if isinstance(percentage, dict) and "$numberDouble" in percentage:
            weights.append(float(percentage["$numberDouble"]))
        elif isinstance(percentage, (float, int)):
            weights.append(float(percentage))
        else:
            raise ValueError(f"Unexpected format for percentage_of_farm: {percentage}")

    weights = np.array(weights, dtype=float)
    weights = weights / weights.sum()  # Normalize weights

    # Ensure weights match vecs
    if len(weights) != len(vecs):
        raise ValueError("Mismatch between number of valid vectors and weights.")

    # Compute weighted average vectors
    weighted_avg_vecs = []
    for i in range(7):  # Assuming 7 as the feature dimension
        try:
            # Collect valid vectors for the current dimension
            current_dim_vectors = np.array([vec[i] for vec in vecs], dtype=float)
            weighted_avg_vec = (current_dim_vectors * weights[:, np.newaxis]).sum(axis=0)
            weighted_avg_vecs.append(weighted_avg_vec)
        except IndexError:
            print(f"IndexError encountered while processing dimension {i}.")
            weighted_avg_vecs.append(None)

    # Predict using the weighted average vectors
    res = []
    for vec in weighted_avg_vecs:
        if vec is not None:
            try:
                res.append(predictor([vec.tolist()], m1, m2).tolist()[0])
            except Exception as e:
                print(f"Error in predictor: {e}")
                res.append("Error in Prediction")
        else:
            res.append("Normal Weather")  # Default fallback
    return res
