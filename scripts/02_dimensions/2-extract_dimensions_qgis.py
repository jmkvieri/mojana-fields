import os
import csv
import math
import processing

from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsPointXY,
    QgsVectorFileWriter,
    QgsFeatureRequest,
    QgsApplication,
)
from PyQt5.QtCore import QVariant

# Get current project path
p = os.path.dirname(QgsProject.instance().fileName())

# Paths
polygon_layer_path = os.path.join(p, "spatial_data", "shapefiles", "camellones", "camellones.shp")
line_layer_path = os.path.join(p, "outputs", "temp", "longest_line_output.shp")
points_layer_path = os.path.join(p,  "outputs", "temp", "points_layer.shp")
perpendicular_lines_path = os.path.join(p,  "outputs", "temp", "perpendicular_lines.shp")

# CSV path for output
csv_widths_path = os.path.join(p, "outputs", "data", "output_widths.csv")

# Load layers (longest line along centre line, original polygons)
line_layer = QgsVectorLayer(line_layer_path, "Line Layer", "ogr")
polygon_layer = QgsVectorLayer(polygon_layer_path, "Polygon Layer", "ogr")

# Add layers for visual inspection
QgsProject.instance().addMapLayer(line_layer)
QgsProject.instance().addMapLayer(polygon_layer)

# Generate points along the lines at 0.5 map unit intervals
processing.run("qgis:pointsalonglines", {
    "INPUT": line_layer,
    "DISTANCE": 0.5,
    "OUTPUT": points_layer_path
})

# Add point layer for visual inspection
points_layer = QgsVectorLayer(points_layer_path, "Points Layer", "ogr")
QgsProject.instance().addMapLayer(points_layer)

# Define perpendicular lines layer schema (for immediate writing)
perpendicular_lines_layer = QgsVectorLayer("LineString?crs=EPSG:3116", "Perpendicular Lines", "memory")
perpendicular_lines_provider = perpendicular_lines_layer.dataProvider()
perpendicular_lines_provider.addAttributes([QgsField("polygon_id", QVariant.Int), QgsField("distance", QVariant.Double), QgsField("width", QVariant.Double)])
perpendicular_lines_layer.updateFields()

# Open the shapefile to write directly
writer = QgsVectorFileWriter(perpendicular_lines_path, "UTF-8", perpendicular_lines_provider.fields(), QgsWkbTypes.LineString, perpendicular_lines_layer.crs(), "ESRI Shapefile")

def calculate_angle(segment_start, segment_end):
    dx = segment_end.x() - segment_start.x()
    dy = segment_end.y() - segment_start.y()
    return math.atan2(dy, dx)

def create_perpendicular_line_within_polygon(point, angle, polygon_geom):
    perp_angle = angle + math.pi / 2
    max_length = 1000

    line_start = QgsPointXY(
        point.x() + math.cos(perp_angle) * max_length,
        point.y() + math.sin(perp_angle) * max_length
    )
    line_end = QgsPointXY(
        point.x() - math.cos(perp_angle) * max_length,
        point.y() - math.sin(perp_angle) * max_length
    )

    initial = QgsGeometry.fromPolylineXY([line_start, line_end])
    intersect_geom = polygon_geom.intersection(initial)

    if intersect_geom.isEmpty():
        return QgsGeometry.fromPolylineXY([])

    if intersect_geom.isMultipart():
        longest = max(
            intersect_geom.asMultiPolyline(),
            key=lambda ln: QgsGeometry.fromPolylineXY(ln).length()
        )
    else:
        longest = intersect_geom.asPolyline()

    return QgsGeometry.fromPolylineXY(longest)

# Collect typical (orientation) angles per polygon: length-weighted axial circular mean
polygon_angles = {}

for poly_feature in polygon_layer.getFeatures():
    poly_geom = poly_feature.geometry()
    s = 0.0
    c = 0.0
    wsum = 0.0

    req = QgsFeatureRequest().setFilterRect(poly_geom.boundingBox())
    for line_feature in line_layer.getFeatures(req):
        line_geom = line_feature.geometry()
        lines = line_geom.asMultiPolyline() if line_geom.isMultipart() else [line_geom.asPolyline()]

        for line in lines:
            for i in range(len(line) - 1):
                seg_start = line[i]
                seg_end = line[i + 1]
                seg_geom = QgsGeometry.fromPolylineXY([seg_start, seg_end])

                if not seg_geom.intersects(poly_geom):
                    continue

                a = calculate_angle(QgsPointXY(seg_start), QgsPointXY(seg_end))  # radians
                w = seg_geom.length()  # weight by segment length

                # axial mean: use 2*a so a and a+pi are equivalent
                s += w * math.sin(2 * a)
                c += w * math.cos(2 * a)
                wsum += w

    if wsum > 0:
        polygon_angles[poly_feature["polygon_id"]] = 0.5 * math.atan2(s, c)

# Output rows: polygon_id, distance, width
rows = []

for point_feature in points_layer.getFeatures():
    pt = point_feature.geometry().asPoint()

    polygon_id_val = point_feature["polygon_id"]  # Get the polygon_id from the point feature
    distance = point_feature["distance"]

    # Loop through the polygons and check if the point lies within each polygon
    for poly_feature in polygon_layer.getFeatures(
        QgsFeatureRequest().setFilterRect(QgsGeometry.fromPointXY(pt).boundingBox())
    ):
        poly_geom = poly_feature.geometry()

        # Check if the point is inside the polygon and if the polygon_id matches
        if poly_geom.contains(QgsGeometry.fromPointXY(pt)) and poly_feature["polygon_id"] == polygon_id_val:
            # Access polygon_angles using polygon_id_val
            if polygon_id_val in polygon_angles:
                avg_angle = polygon_angles[polygon_id_val]
                perp = create_perpendicular_line_within_polygon(pt, avg_angle, poly_geom)
                width = perp.length() if not perp.isEmpty() else 0.0

                # Create a feature for the perpendicular line
                perpendicular_feature = QgsFeature()
                perpendicular_feature.setGeometry(perp)
                perpendicular_feature.setAttributes([polygon_id_val, distance, width])

                # Add the feature directly to the shapefile
                writer.addFeature(perpendicular_feature)

                rows.append([polygon_id_val, distance, width])  # Store data for CSV
            else:
                print(f"Polygon ID {polygon_id_val} not found in polygon_angles")

            break

# Close the writer to save the shapefile
del writer

# Write widths CSV
with open(csv_widths_path, "w", newline="") as fp:
    w = csv.writer(fp)
    w.writerow(["polygon_id", "distance", "width"])
    w.writerows(rows)
