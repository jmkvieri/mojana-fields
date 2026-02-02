from qgis.core import (
    QgsRasterLayer,
    QgsVectorLayer,
    QgsProject
)
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
import processing
import os


# NB! Need to set raster path to satellite imagery downloaded using your own API in script "download_tiles.R"
raster_path = ""

if not os.path.isfile(raster_path):
    raise FileNotFoundError(
        f'Could not load .tif raster at:\n  {raster_path}\n\n'
        'NB! Need to set raster path to satellite imagery downloaded using your own API in script "download_tiles.R".'
    )

# Band / threshold for "blue mask", but could use any other band or threshold as suited to your case study area
blue_band = 3
blue_min, blue_max = 75, 100

# Outputs
project_path = os.path.dirname(QgsProject.instance().fileName())
out_dir = os.path.join(project_path,"outputs",  "temp")

blue_mask_path            = os.path.join(out_dir, "blue_mask.tif")
no_data_mask_path         = os.path.join(out_dir, "no_data_blue_mask.tif")
filled_mask_path          = os.path.join(out_dir, "filled_blue_mask.tif")

# Critical: re-binarize after fillnodata so DN values are not "random"
filled_binary_path        = os.path.join(out_dir, "filled_blue_mask_binary.tif")
filled_binary_nodata_path = os.path.join(out_dir, "filled_blue_mask_binary_nodata.tif")

sieved_mask_path          = os.path.join(out_dir, "sieved_blue_mask.tif")

# Polygon outputs
polygons_all_path         = os.path.join(out_dir, "blue_mask_polygons_all.gpkg")
polygons_mask_path        = os.path.join(out_dir, "blue_mask_polygons_dn1.gpkg")


# ----------------------------
# Load raster
# ----------------------------
raster_layer = QgsRasterLayer(raster_path, "study_area")
if not raster_layer.isValid():
    raise RuntimeError("Failed to load raster layer! Please check the path / download imagery.")
QgsProject.instance().addMapLayer(raster_layer)
print(f"Raster loaded: {raster_layer.name()} | bands: {raster_layer.bandCount()}")


# ----------------------------
# Function: create binary mask from band range
# ----------------------------
def create_range_mask(layer: QgsRasterLayer, band: int, min_val: float, max_val: float, output_path: str) -> int:
    """
    Writes a raster where pixels in [min_val, max_val] become 1, else 0.
    Returns QgsRasterCalculator processCalculation() code (0 = success).
    """
    entry = QgsRasterCalculatorEntry()
    entry.ref = f"{layer.name()}@{band}"
    entry.raster = layer
    entry.bandNumber = band
    entries = [entry]

    # robust boolean math: comparisons yield 0/1; multiply to represent AND; then *1 to force numeric output
    expr = f"(({entry.ref} >= {min_val}) * ({entry.ref} <= {max_val})) * 1"

    calc = QgsRasterCalculator(
        expr,
        output_path,
        "GTiff",
        layer.extent(),
        layer.width(),
        layer.height(),
        entries
    )
    return calc.processCalculation()


# ----------------------------
# 1) Initial mask (0/1)
# ----------------------------
rc = create_range_mask(raster_layer, blue_band, blue_min, blue_max, blue_mask_path)
if rc != 0:
    raise RuntimeError(f"Failed to create initial mask. RasterCalculator code: {rc}")
print("Initial (0/1) mask created.")

blue_mask_layer = QgsRasterLayer(blue_mask_path, "Blue_Mask_0_1")
if not blue_mask_layer.isValid():
    raise RuntimeError("Blue mask layer is not valid.")
QgsProject.instance().addMapLayer(blue_mask_layer)


# ----------------------------
# 2) Set 0 to NoData (so background can be ignored downstream)
# ----------------------------
res = processing.run("gdal:translate", {
    "INPUT": blue_mask_path,
    "NODATA": 0,
    "COPY_SUBDATASETS": False,
    "OPTIONS": "",
    "EXTRA": "",
    "DATA_TYPE": 0,  # keep same
    "OUTPUT": no_data_mask_path
})
print("Set background (0) to NoData.")

no_data_mask_layer = QgsRasterLayer(no_data_mask_path, "Blue_Mask_NoData")
if not no_data_mask_layer.isValid():
    raise RuntimeError("NoData mask layer is not valid.")
QgsProject.instance().addMapLayer(no_data_mask_layer)


# ----------------------------
# 3) Fill NoData gaps (numeric interpolation)
#    NOTE: this can produce non-integer values; we will re-binarize after this.
# ----------------------------
processing.run("gdal:fillnodata", {
    "INPUT": no_data_mask_path,
    "BAND": 1,
    "DISTANCE": 3,     # pixels
    "ITERATIONS": 0,   # 0 = default
    "MASK_LAYER": None,
    "OPTIONS": "",
    "EXTRA": "",
    "OUTPUT": filled_mask_path
})
print("fillnodata completed.")

filled_mask_layer = QgsRasterLayer(filled_mask_path, "Blue_Mask_Filled")
if not filled_mask_layer.isValid():
    raise RuntimeError("Filled mask layer is not valid.")
QgsProject.instance().addMapLayer(filled_mask_layer)


# ----------------------------
# 4) RE-BINARIZE to remove “random DN values”
#    Anything >= 0.5 => 1 else 0
# ----------------------------
rc2 = create_range_mask(filled_mask_layer, 1, 0.5, 1e9, filled_binary_path)
if rc2 != 0:
    raise RuntimeError(f"Failed to re-binarize filled raster. RasterCalculator code: {rc2}")
print("Re-binarized filled raster back to 0/1.")

filled_binary_layer = QgsRasterLayer(filled_binary_path, "Blue_Mask_Filled_Binary_0_1")
if not filled_binary_layer.isValid():
    raise RuntimeError("Filled binary layer is not valid.")
QgsProject.instance().addMapLayer(filled_binary_layer)


# ----------------------------
# 5) Set background 0 to NoData AGAIN (so background is ignored)
# ----------------------------
processing.run("gdal:translate", {
    "INPUT": filled_binary_path,
    "NODATA": 0,
    "COPY_SUBDATASETS": False,
    "OPTIONS": "",
    "EXTRA": "",
    "DATA_TYPE": 1,  # Byte (makes sieve/polygonize happier)
    "OUTPUT": filled_binary_nodata_path
})
print("Set 0 to NoData after re-binarizing.")

filled_binary_nodata_layer = QgsRasterLayer(filled_binary_nodata_path, "Blue_Mask_Filled_Binary_NoData")
if not filled_binary_nodata_layer.isValid():
    raise RuntimeError("Filled binary NoData layer is not valid.")
QgsProject.instance().addMapLayer(filled_binary_nodata_layer)


# ----------------------------
# 6) Sieve (remove small regions)
# ----------------------------
# Threshold is pixel-count (like your -st 500). 8-connectedness matches your -8.
processing.run("gdal:sieve", {
    "INPUT": filled_binary_nodata_path,
    "THRESHOLD": 500,
    "EIGHT_CONNECTEDNESS": True,
    "NO_MASK": True,
    "MASK": None,
    "OPTIONS": "",
    "EXTRA": "",
    "OUTPUT": sieved_mask_path
})
print("Sieve operation completed.")

sieved_layer = QgsRasterLayer(sieved_mask_path, "Blue_Mask_Sieved")
if not sieved_layer.isValid():
    raise RuntimeError("Sieved mask layer is not valid.")
QgsProject.instance().addMapLayer(sieved_layer)


# ----------------------------
# 7) Polygonize
# ----------------------------
# This may still polygonize background depending on GDAL/QGIS behavior,
# so we will *guarantee* background is ignored by filtering DN=1 afterwards.
processing.run("gdal:polygonize", {
    "INPUT": sieved_mask_path,
    "BAND": 1,
    "FIELD": "DN",
    "EIGHT_CONNECTEDNESS": True,
    "EXTRA": "",
    "OUTPUT": polygons_all_path
})
print("Polygonization completed (raw output).")

polys_all = QgsVectorLayer(polygons_all_path, "Blue_Mask_Polygons_ALL", "ogr")
if not polys_all.isValid():
    raise RuntimeError("Polygonized vector layer (ALL) is not valid.")
QgsProject.instance().addMapLayer(polys_all)


# ----------------------------
# 8) GUARANTEE background ignored: keep only DN = 1
# ----------------------------
processing.run("native:extractbyattribute", {
    "INPUT": polygons_all_path,
    "FIELD": "DN",
    "OPERATOR": 0,  # =
    "VALUE": 1,
    "OUTPUT": polygons_mask_path
})
print("Filtered polygons to DN=1 (background ignored).")

polys_dn1 = QgsVectorLayer(polygons_mask_path, "Blue_Mask_Polygons_DN1", "ogr")
if not polys_dn1.isValid():
    raise RuntimeError("Filtered DN=1 layer is not valid.")
QgsProject.instance().addMapLayer(polys_dn1)

print(f"Done. Final polygons (DN=1 only): {polygons_mask_path}")
