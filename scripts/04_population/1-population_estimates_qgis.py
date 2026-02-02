import os
import math
import processing
import pandas as pd

from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsFeature,
    QgsField,
    QgsVectorFileWriter,
    QgsFeatureRequest,
    QgsGeometry,
)
from PyQt5.QtCore import QVariant

# Get current project path
p = os.path.dirname(QgsProject.instance().fileName())

# Paths
polygon_layer_path = os.path.join(p, "spatial_data", "shapefiles", "platforms", "platforms.shp")
out_polys_path = os.path.join(p, "outputs", "final_shapefiles", "platforms_houses_pop.shp")
csv_output_path = os.path.join(p, "outputs", "data", "platforms_houses_pop.csv")

polygon_layer = QgsVectorLayer(polygon_layer_path, "Polygon Layer", "ogr")

# Create output memory layer with same CRS + polygon geometry
out_layer = QgsVectorLayer(
    f"Polygon?crs={polygon_layer.crs().authid()}",
    "Camellones Houses Pop",
    "memory",
)
prov = out_layer.dataProvider()

# Copy original fields + add new ones
prov.addAttributes(polygon_layer.fields())
prov.addAttributes([
    QgsField("sqm", QVariant.Double),     # area in square meters
    QgsField("houses", QVariant.Int),     # floor(sqm/500)
    QgsField("pop", QVariant.Int),        # houses * 5
])
out_layer.updateFields()

# Build features
out_feats = []
for f in polygon_layer.getFeatures():
    geom = f.geometry()
    if geom is None or geom.isEmpty():
        continue

    # IMPORTANT: area units depend on CRS. If CRS is projected in meters, this is m^2.
    sqm = geom.area()

    houses = int(math.floor(sqm / 500.0))
    pop = houses * 5

    out_f = QgsFeature(out_layer.fields())
    out_f.setGeometry(geom)

    attrs = f.attributes()  # original attributes
    attrs += [float(sqm), houses, pop]  # appended new fields in same order as added
    out_f.setAttributes(attrs)

    out_feats.append(out_f)

prov.addFeatures(out_feats)
out_layer.updateExtents()

# Save to shapefile
QgsVectorFileWriter.writeAsVectorFormat(
    out_layer,
    out_polys_path,
    "UTF-8",
    out_layer.crs(),
    "ESRI Shapefile",
)

# Save to CSV
# Extract the attributes from the output layer
csv_data = []

for f in out_layer.getFeatures():
    attributes = f.attributes()
    geom = f.geometry().asWkt()  # Convert geometry to WKT for CSV
    attributes.append(geom)
    csv_data.append(attributes)

# Create DataFrame for CSV
columns = [field.name() for field in out_layer.fields()] + ["geometry"]
df = pd.DataFrame(csv_data, columns=columns)


# Save DataFrame to CSV
df.to_csv(csv_output_path, index=False)

# Add to project for visual inspection
QgsProject.instance().addMapLayer(out_layer)
