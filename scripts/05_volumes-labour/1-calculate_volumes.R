library(here)

# Load dataset of polygon widths every 0.5m
segments <- read.csv(here("outputs","data","output_widths.csv"))

# Function to calculate volume for each segment
calculate_segment_volume <- function(length, height, width) {
  volume <- (2/3) * height * width * length
  return(volume)
}

# Create a dataframe to store volume_results
volume_results <- data.frame(
  polygon_id = numeric(), 
  total_volume = numeric(),
  stringsAsFactors = FALSE
)

# Process each group of segments by polygon_id
unique_polygon_ids <- unique(segments$polygon_id)

for (polygon_id in unique_polygon_ids) {
  # Filter the group based on polygon_id
  group <- segments[segments$polygon_id == polygon_id, ]
  
  # Ensure the distances and widths are sorted along with the segments
  group <- group[order(group$distance), ]
  
  # Calculate differences in 'distance' and drop the first NA
  group$length <- c(NA, diff(group$distance))
  group <- group[!is.na(group$length), ]
  
  # Calculate volumes for each segment; height fixed at 140cm/2=70cm, based on exc data 
  group$segment_volume <- mapply(calculate_segment_volume, group$length, 1.4/2, group$width)
  
  # Calculate the total volume and total area for the current polygon_id
  total_volume <- sum(group$segment_volume, na.rm = TRUE)
  total_length <- max(group$distance, na.rm = TRUE)
  
  
  # Append the result to the volume_results dataframe
  volume_results <- rbind(volume_results, data.frame(
    polygon_id = polygon_id, 
    total_volume = total_volume,
    total_length = total_length
  ))
}


# Store results
write.csv(volume_results, here("outputs","data","volume_results.csv"), row.names = FALSE)
