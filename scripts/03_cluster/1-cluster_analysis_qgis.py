import geopandas as gpd
import pandas as pd
import os
from sklearn.cluster import KMeans
import numpy as np
from shapely.geometry import LineString
from math import atan2, degrees
from sklearn.preprocessing import RobustScaler
import networkx as nx

# Helper function to calculate orientation of polygon longest axist
def get_orientation(polygon):
    if polygon is None or polygon.is_empty:
        return np.nan
    try:
        mrr = polygon.minimum_rotated_rectangle
        coords = list(mrr.exterior.coords)
        edges = [LineString([coords[i], coords[i + 1]]) for i in range(4)]
        lengths = [edge.length for edge in edges]
        longest_edge = edges[np.argmax(lengths)]
        dx = longest_edge.coords[1][0] - longest_edge.coords[0][0]
        dy = longest_edge.coords[1][1] - longest_edge.coords[0][1]
        angle_deg = degrees(atan2(dy, dx)) % 180
        return angle_deg
    except Exception:
        return np.nan


# Paths
p = os.path.dirname(QgsProject.instance().fileName())
shapefile_path = os.path.join(p, "spatial_data", "shapefiles", "camellones", "camellones.shp")
csv_widths_path = os.path.join(p, "outputs", "data", "output_widths.csv")
output_path = os.path.join(p, "outputs", "final_shapefiles", "camellones_with_auto_clusters.shp")
csv_output_path = os.path.join(p, "outputs", "data", "camellones_with_auto_clusters.csv")

# -Load data
shapefile = gpd.read_file(shapefile_path)
csv_widths_data = pd.read_csv(csv_widths_path)

# Ensure the CSV contains polygon_id and distance columns
max_distances = csv_widths_data.groupby('polygon_id')['distance'].max().reset_index()

# Subset shapefile to only include polygon_ids from the CSV
polygon_ids_from_csv = csv_widths_data['polygon_id'].unique()
shapefile = shapefile[shapefile['polygon_id'].isin(polygon_ids_from_csv)]

# Merge the max_distance into the shapefile
shapefile = shapefile.merge(max_distances, on='polygon_id', how='left')

# Rename max_distance to total_length
shapefile.rename(columns={'distance': 'total_length'}, inplace=True)

# Calculate orientation
shapefile['angle'] = shapefile.geometry.apply(get_orientation)

# Handle circular angles
shapefile['angle_rad'] = np.deg2rad(2 * shapefile['angle'])
shapefile['angle_sin'] = np.sin(shapefile['angle_rad'])
shapefile['angle_cos'] = np.cos(shapefile['angle_rad'])

# Clustering features
clustering_features = ['angle_sin', 'angle_cos', 'total_length']
clustering_data = shapefile[clustering_features].dropna()
scaler = RobustScaler()
scaled_data = scaler.fit_transform(clustering_data)

# Determine optimal K
inertias = []
K_range = range(1, min(15, len(scaled_data)))

for k in K_range:
    km = KMeans(n_clusters=k, random_state=15).fit(scaled_data)
    inertias.append(km.inertia_)

total_variance = inertias[0]
explained = [1 - (i / total_variance) for i in inertias]

for i in range(1, len(explained) - 1):
    gain = explained[i] - explained[i - 1]
    if gain < 0.10:
        optimal_k = i + 1
        break

# Run clustering
kmeans = KMeans(n_clusters=optimal_k, random_state=15)
shapefile['cluster_id'] = kmeans.fit_predict(scaled_data)

# Rename clusters based on descending average total_length
avg_lengths = shapefile.groupby('cluster_id')['total_length'].mean()
sorted_clusters = avg_lengths.sort_values(ascending=False).index.tolist()
cluster_mapping = {old: new + 1 for new, old in enumerate(sorted_clusters)}
shapefile['cluster_id'] = shapefile['cluster_id'].map(cluster_mapping)

# Save results
shapefile.to_file(output_path)

shapefile_csv = shapefile.copy()
shapefile_csv['geometry'] = shapefile_csv['geometry'].apply(lambda geom: geom.wkt)
shapefile_csv.to_csv(csv_output_path, index=False)


# Add shapefile for visual inspection
with_clusters = QgsVectorLayer(output_path, "Camellones with cluster ids", "ogr")
QgsProject.instance().addMapLayer(with_clusters)
