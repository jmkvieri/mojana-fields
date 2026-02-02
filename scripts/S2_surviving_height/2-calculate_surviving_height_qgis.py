import os
import csv
import numpy as np
from osgeo import gdal

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsVectorFileWriter,
    QgsWkbTypes
)
from PyQt5.QtCore import QVariant


# ----------------------------
# Paths (relative to project)
# ----------------------------
project_path = os.path.dirname(QgsProject.instance().fileName())

polygon_layer_path = os.path.join(project_path, "spatial_data", "shapefiles", "camellones", "camellones.shp")
points_layer_path  = os.path.join(project_path, "outputs", "temp", "temp_shapefiles", "points_layer.shp")
dem_raster_path = os.path.join(project_path, "spatial_data", "DEM", "DEM_fondodeadaptacion_without_water.tif")

csv_output_path = os.path.join(project_path, "outputs", "data", "surviving_heights.csv")
shapefile_output_path = os.path.join(project_path, "outputs", "final_shapefiles", "camellones_surviving_heights.shp")

# Ensure output directories exist
os.makedirs(os.path.dirname(csv_output_path), exist_ok=True)
os.makedirs(os.path.dirname(shapefile_output_path), exist_ok=True)


# ----------------------------
# Load DEM
# ----------------------------
dem_dataset = gdal.Open(dem_raster_path)
if not dem_dataset:
    raise RuntimeError(f"Failed to open DEM raster: {dem_raster_path}")

gt = dem_dataset.GetGeoTransform()
raster_band = dem_dataset.GetRasterBand(1)
no_data_value = raster_band.GetNoDataValue()
print("DEM raster loaded successfully.")


# ----------------------------
# Load layers
# ----------------------------
polygon_layer = QgsVectorLayer(polygon_layer_path, "Polygon Layer", "ogr")
if not polygon_layer.isValid():
    raise RuntimeError(f"Failed to load polygon layer: {polygon_layer_path}")
QgsProject.instance().addMapLayer(polygon_layer)
print("Polygon layer loaded successfully.")

points_layer = QgsVectorLayer(points_layer_path, "Points Layer", "ogr")
if not points_layer.isValid():
    raise RuntimeError(f"Failed to load points layer: {points_layer_path}")
QgsProject.instance().addMapLayer(points_layer)
print("Points layer loaded successfully.")


# ----------------------------
# Build quick lookup: polygon_id -> geometry (+ attributes)
# ----------------------------
if "polygon_id" not in [f.name() for f in polygon_layer.fields()]:
    raise RuntimeError("Polygon layer is missing required field: polygon_id")

polygon_by_id = {}
for f in polygon_layer.getFeatures():
    pid = f["polygon_id"]
    # keep as-is (int/str), but use same type consistently
    polygon_by_id[pid] = f  # store whole feature


# ----------------------------
# Accumulate elevations per polygon_id
# ----------------------------
polygon_data = {}  # polygon_id -> lists

# Validate points field exists
if "polygon_id" not in [f.name() for f in points_layer.fields()]:
    raise RuntimeError("Points layer is missing required field: polygon_id")

for pt_feat in points_layer.getFeatures():
    pid = pt_feat["polygon_id"]
    poly_feat = polygon_by_id.get(pid)

    if poly_feat is None:
        # points reference a polygon_id that doesn't exist in polygon layer
        continue

    pt_geom = pt_feat.geometry()
    if pt_geom is None or pt_geom.isEmpty():
        continue

    point = pt_geom.asPoint()
    poly_geom = poly_feat.geometry()

    # Optional safety check: ensure point is inside its referenced polygon
    if not poly_geom or not poly_geom.contains(pt_geom):
        continue

    # ----------------------------
    # DEM sampling (ALWAYS compute a 4m window)
    # ----------------------------
    px = int((point.x() - gt[0]) / gt[1])
    py = int((point.y() - gt[3]) / gt[5])

    # Clamp to raster bounds
    px = min(max(px, 0), raster_band.XSize - 1)
    py = min(max(py, 0), raster_band.YSize - 1)

    # Read point elevation
    elev = raster_band.ReadAsArray(px, py, 1, 1)[0, 0]

    # 4m window around pixel (assumes square pixels; see note below if not)
    buffer_px = int(4 / abs(gt[1]))
    xmin = max(px - buffer_px, 0)
    xmax = min(px + buffer_px + 1, raster_band.XSize)
    ymin = max(py - buffer_px, 0)
    ymax = min(py + buffer_px + 1, raster_band.YSize)

    window = raster_band.ReadAsArray(xmin, ymin, xmax - xmin, ymax - ymin)

    if no_data_value is not None:
        window = np.ma.masked_equal(window, no_data_value)

    vals = window.compressed() if hasattr(window, "compressed") else window.ravel()
    vals = vals[~np.isnan(vals)]
    vals_pos = vals[vals > 0]  # ignore zeros

    # Fallback for invalid/zero/nodata point elevation
    if elev == no_data_value or np.isnan(elev) or elev == 0:
        elev = float(np.mean(vals_pos)) if vals_pos.size > 0 else 0.0
    else:
        elev = float(elev)

    # Min/max from neighborhood (fallback to elev if neighborhood has no valid values)
    min_elev = float(np.min(vals_pos)) if vals_pos.size > 0 else elev
    max_elev = float(np.max(vals_pos)) if vals_pos.size > 0 else elev

    # Accumulate
    if pid not in polygon_data:
        polygon_data[pid] = {"elevations": [], "min_elevations": [], "max_elevations": []}

    if elev != 0:
        polygon_data[pid]["elevations"].append(elev)
    if min_elev != 0:
        polygon_data[pid]["min_elevations"].append(min_elev)
    if max_elev != 0:
        polygon_data[pid]["max_elevations"].append(max_elev)


# ----------------------------
# Compute averages + write CSV
# ----------------------------
averages_dict = {}  # polygon_id -> avg values
rows = []

for pid, data in polygon_data.items():
    valid_elev = [v for v in data["elevations"] if v != 0]
    valid_min  = [v for v in data["min_elevations"] if v != 0]
    valid_max  = [v for v in data["max_elevations"] if v != 0]

    avg_elev = float(np.mean(valid_elev)) if valid_elev else 0.0
    avg_min  = float(np.mean(valid_min))  if valid_min else 0.0
    avg_max  = float(np.mean(valid_max))  if valid_max else 0.0

    averages_dict[pid] = {"avg_elev": avg_elev, "avg_min_elev": avg_min, "avg_max_elev": avg_max}
    rows.append([pid, avg_elev, avg_min, avg_max])

with open(csv_output_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["polygon_id", "avg_elev", "avg_min_elev", "avg_max_elev"])
    w.writerows(rows)

print(f"Attributes saved to {csv_output_path}")


# ----------------------------
# Create output polygon layer (copy original fields + add new)
# ----------------------------
crs_id = polygon_layer.crs().authid() or polygon_layer.crs().toWkt()
geom_str = QgsWkbTypes.displayString(polygon_layer.wkbType())
new_layer = QgsVectorLayer(f"{geom_str}?crs={crs_id}", "camellones_surviving_heights", "memory")
prov = new_layer.dataProvider()

# Start with all original fields
all_fields = polygon_layer.fields()

# Add new fields if missing
new_fields = [
    QgsField("avg_elev", QVariant.Double),
    QgsField("avg_min_elev", QVariant.Double),
    QgsField("avg_max_elev", QVariant.Double),
]
existing = {f.name() for f in all_fields}
for nf in new_fields:
    if nf.name() not in existing:
        all_fields.append(nf)

prov.addAttributes(all_fields.toList())
new_layer.updateFields()

# Copy features + set new attributes
for f in polygon_layer.getFeatures():
    pid = f["polygon_id"]
    avg = averages_dict.get(pid, {"avg_elev": 0.0, "avg_min_elev": 0.0, "avg_max_elev": 0.0})

    out_f = QgsFeature(new_layer.fields())
    out_f.setGeometry(f.geometry())

    # Copy all original attributes by field name
    for field in polygon_layer.fields():
        out_f.setAttribute(field.name(), f[field.name()])

    # Set new values
    out_f.setAttribute("avg_elev", avg["avg_elev"])
    out_f.setAttribute("avg_min_elev", avg["avg_min_elev"])
    out_f.setAttribute("avg_max_elev", avg["avg_max_elev"])

    prov.addFeature(out_f)

new_layer.updateExtents()
QgsProject.instance().addMapLayer(new_layer)


result = QgsVectorFileWriter.writeAsVectorFormat(
    new_layer,
    shapefile_output_path,
    "UTF-8",
    new_layer.crs(),
    "ESRI Shapefile"
)


"""
NOTE (pixel size):
If your DEM pixels are not square, replace:
    buffer_px = int(4 / abs(gt[1]))
with:
    buffer_px_x = int(4 / abs(gt[1]))
    buffer_px_y = int(4 / abs(gt[5]))
and use buffer_px_x for xmin/xmax and buffer_px_y for ymin/ymax.
"""
