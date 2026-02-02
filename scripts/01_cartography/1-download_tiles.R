library(httr)
library(terra)

# Replace with your Google API key
api_key <- ""

# Function to convert latitude and longitude to tile indices
lat_lon_to_tile_indices <- function(latitude, longitude, zoom) {
  pixelX <- ((longitude + 180) / 360) * 256 * 2^zoom
  pixelY <- ((1 - log(tan(latitude * pi / 180) + (1 / cos(latitude * pi / 180))) / pi) / 2) * 256 * 2^zoom
  tileX <- floor(pixelX / 256)
  tileY <- floor(pixelY / 256)
  return(list(tileX = tileX, tileY = tileY))
}

# Function to calculate the bounds of a tile
tile_bounds <- function(tileX, tileY, zoom, tile_size) {
  n <- 2^zoom
  lon_min <- tileX / n * 360.0 - 180.0
  lat_rad_min <- atan(sinh(pi * (1 - 2 * tileY / n)))
  lat_min <- lat_rad_min * (180.0 / pi)
  
  lon_max <- (tileX + tile_size / 256) / n * 360.0 - 180.0
  lat_rad_max <- atan(sinh(pi * (1 - 2 * (tileY + tile_size / 256) / n)))
  lat_max <- lat_rad_max * (180.0 / pi)
  
  return(c(lon_min, lon_max, lat_min, lat_max))
}

# Function to download Google map tile
download_google_tile <- function(latitude, longitude, zoom, api_key, file_path, tile_size) {
  base_url <- "https://maps.googleapis.com/maps/api/staticmap"
  location <- paste(latitude, longitude, sep = ",")
  url <- paste0(
    base_url, "?center=", location, "&zoom=", zoom, 
    "&scale=4&size=", tile_size, "x", tile_size, "&scale=1&maptype=satellite&key=", api_key
  )
  
  response <- GET(url)
  
  if (response$status_code == 200) {
    dir.create(dirname(file_path), recursive = TRUE, showWarnings = FALSE)
    writeBin(content(response, "raw"), file_path)
    message("Tile successfully downloaded: ", file_path)
  } else {
    message("Failed to download tile: ", response$status_code)
    message("URL: ", url)
  }
}

# Function to georeference an existing image
georeference_image <- function(tileX, tileY, zoom, file_path, tile_size) {
  img <- rast(file_path)
  
  # Calculate the bounds of the tile
  bounds <- tile_bounds(tileX, tileY, zoom, tile_size)
  lon_min <- bounds[1]
  lon_max <- bounds[2]
  lat_min <- bounds[4]
  lat_max <- bounds[3]
  
  # Ensure the bounds are valid
  if (lon_min >= lon_max || lat_min >= lat_max) {
    stop("Invalid extent: Check tile indices and bounds calculation.")
  }
  
  ext(img) <- ext(lon_min, lon_max, lat_min, lat_max)  # Set extent in the order xmin, xmax, ymin, ymax
  crs(img) <- "EPSG:4326"
  
  georeferenced_file_path <- gsub(".png", ".tif", file_path)
  writeRaster(img, georeferenced_file_path, filetype = "GTiff", overwrite = TRUE)
  
  message("Georeferenced image saved as: ", georeferenced_file_path)
  return(georeferenced_file_path)
}

# Parameters
zoom <- 21
tile_size <- 640

#replace with desired coordinates
lat_start <- 8.5049
lat_end <- 8.5069
long_start <- -75.1367
long_end <- -75.1342

tile_start <- lat_lon_to_tile_indices(lat_start, long_start, zoom)
tile_end <- lat_lon_to_tile_indices(lat_end, long_end, zoom)

tileX_start <- tile_start$tileX
tileY_start <- tile_start$tileY
tileX_end <- tile_end$tileX
tileY_end <- tile_end$tileY

message("Tile indices range: X from ", tileX_start, " to ", tileX_end, ", Y from ", tileY_start, " to ", tileY_end)

#Download tiles
for (tileX in tileX_start:tileX_end) {
  for (tileY in tileY_start:tileY_end) {
    bounds <- tile_bounds(tileX, tileY, zoom, tile_size)
    center_lat <- (bounds[4] + bounds[3]) / 2
    center_lon <- (bounds[1] + bounds[2]) / 2
    file_path <- paste('./test2/google_tile', tileX, tileY, '.png', sep = "_")
    download_google_tile(center_lat, center_lon, zoom, api_key, file_path, tile_size)
  }
}

# Georeference downloaded tiles
georeferenced_files <- c()
for (tileX in tileX_start:tileX_end) {
  for (tileY in tileY_start:tileY_end) {
    file_path <- paste('./test2/google_tile', tileX, tileY, '.png', sep = "_")
    if (file.exists(file_path)) {
      try({
        georeferenced_file_path <- georeference_image(tileX, tileY, zoom, file_path, tile_size)
        georeferenced_files <- c(georeferenced_files, georeferenced_file_path)
      }, silent = TRUE)
    } else {
      message("File does not exist: ", file_path)
    }
  }
}

# Merge georeferenced tiles
merged_file_path <- './test2/merged_tile.tif'
if (length(georeferenced_files) > 0) {
  mosaic_tiles <- lapply(georeferenced_files, rast)
  merged_tiles <- do.call(merge, mosaic_tiles)
  writeRaster(merged_tiles, merged_file_path, filetype = "GTiff", datatype = "INT1U", overwrite = TRUE)
  message("Merged georeferenced image saved as: ", merged_file_path)
} else {
  message("No georeferenced tiles found to merge.")
}