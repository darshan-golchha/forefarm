from flask import jsonify, abort
import geopandas as gpd

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

