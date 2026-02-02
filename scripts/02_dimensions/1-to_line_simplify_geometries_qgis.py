import os
import processing

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsVectorFileWriter,
)
from PyQt5.QtCore import QVariant


# Get current project path
p = os.path.dirname(QgsProject.instance().fileName())

# Set input and output file paths
input_file_path = os.path.join(p, "spatial_data", "shapefiles", "camellones", "camellones.shp")
skeleton_file_path = os.path.join(p, "outputs", "temp", "output_line_layer.shp")
longest_line_output_path = os.path.join(p, "outputs", "temp", "longest_line_output.shp")

# Load the input layer
input_layer = QgsVectorLayer(input_file_path, "Input Layer", "ogr")

# Simplify the geometries of the input layer
simplify_params = {
    'INPUT': input_layer,
    'TOLERANCE': 0.1,
    'OUTPUT': 'memory:'
}

simplified_layer = processing.run("native:simplifygeometries", simplify_params)['OUTPUT']

# Run the GRASS GIS v.voronoi.skeleton algorithm using the simplified geometries
params = {
    'input': simplified_layer,
    'smoothness': 0.5,
    'thin': -1,
    '-a': False,
    '-s': True,
    '-l': False,
    '-t': False,
    'output': skeleton_file_path,
    'GRASS_SNAP_TOLERANCE_PARAMETER': -1,
    'GRASS_MIN_AREA_PARAMETER': 0.5,
    'GRASS_OUTPUT_TYPE_PARAMETER': 0
}
result = processing.run("grass7:v.voronoi.skeleton", params)

# Check results and handle the output
if result['output']:
    # Load the directly saved output file into the project
    skeleton_layer = QgsVectorLayer(skeleton_file_path, "Skeleton Layer", "ogr")
    if skeleton_layer.isValid():
        QgsProject.instance().addMapLayer(skeleton_layer)
        print("Skeleton layer added to the project and saved to:", skeleton_file_path)
        
        # Start editing the layer to add length field and remove cat (using polygon_id)
        skeleton_layer.startEditing()
        if "cat" in skeleton_layer.fields().names():
            cat_index = skeleton_layer.fields().indexFromName("cat")
            skeleton_layer.dataProvider().deleteAttributes([cat_index])
        skeleton_layer.dataProvider().addAttributes([QgsField("length", QVariant.Double)])
        skeleton_layer.updateFields()

        # Assign lengths to each feature
        length_index = skeleton_layer.fields().indexFromName("length")
        for feature in skeleton_layer.getFeatures():
            feature["length"] = feature.geometry().length()
            skeleton_layer.updateFeature(feature)

        skeleton_layer.commitChanges()
        print("Length field added and features updated.")
        
        # Step 1: Create an empty layer to store the longest lines
        longest_line_layer = QgsVectorLayer("LineString?crs=" + skeleton_layer.crs().authid(), "Longest Line Layer", "memory")
        longest_line_layer_data_provider = longest_line_layer.dataProvider()
        longest_line_layer_data_provider.addAttributes(skeleton_layer.fields())
        longest_line_layer.updateFields()
        
        # Step 2: Create a dictionary to store the longest line for each polygon_id
        longest_lines = {}
        
        # Step 3: Iterate through the features and group by 'polygon_id', retaining the longest line
        for feature in skeleton_layer.getFeatures():
            polygon_id_value = feature["polygon_id"]  # Group by polygon_id
            geom = feature.geometry()
            length = geom.length()
            
            # Check if this polygon_id already exists in the dictionary
            if polygon_id_value in longest_lines:
                # If it does, compare lengths and retain the longest
                if length > longest_lines[polygon_id_value].geometry().length():
                    longest_lines[polygon_id_value] = feature
            else:
                # If not, add it to the dictionary
                longest_lines[polygon_id_value] = feature
        
        # Step 4: Add the longest lines to the new layer
        for longest_feature in longest_lines.values():
            new_feature = QgsFeature(longest_feature)
            longest_line_layer_data_provider.addFeature(new_feature)
        
        # Update the new layer
        longest_line_layer.updateExtents()
        QgsProject.instance().addMapLayer(longest_line_layer)

        # Save the longest line layer to the output path
        err_code, err_msg = QgsVectorFileWriter.writeAsVectorFormat(
            longest_line_layer,
            longest_line_output_path,
            "UTF-8",
            skeleton_layer.crs(),
            "ESRI Shapefile"
        )

        if err_code == QgsVectorFileWriter.NoError:
            print("Longest line layer successfully saved to:", longest_line_output_path)
        else:
            print(f"Error saving longest line layer ({err_code}): {err_msg}")
