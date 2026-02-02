import subprocess
import os
from qgis.utils import iface

# Get current path
p = os.path.dirname(QgsProject.instance().fileName())

# Set paths
raster_path = os.path.join(p, "spatial_data", "DEM", "DEM_fondodeadaptacion.tif")
output_raster_path = os.path.join(p, "spatial_data", "DEM", "DEM_fondodeadaptacion_without_water.tif")

# Define the NoData value you want to use for the "water" areas
# Usually -9999 or the original raster's NoData value
nodata = -9999 

# One-step Command:
# If A is less than 19.95, set it to nodata, otherwise keep A.
gdal_calc_command = (
    f'gdal_calc.py -A "{raster_path}" '
    f'--outfile="{output_raster_path}" '
    f'--calc="where(A < 19.95, {nodata}, A)" '
    f'--NoDataValue={nodata} --overwrite'
)

subprocess.run(gdal_calc_command, shell=True)

if os.path.exists(output_raster_path):
    print(f"Success! Saved to: {output_raster_path}")
    iface.addRasterLayer(output_raster_path, "DEM without water (<19.95)")
else:
    print("Error: Output file was not created.")