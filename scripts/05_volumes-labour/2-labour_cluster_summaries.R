library(here)

# load calculated_volumes
volume_results <- read.csv(here("outputs","data","volume_results.csv"))
# load results of clustering and merge
cluster_results <- read.csv(here("outputs","data","camellones_with_auto_clusters.csv"))

combined <- merge(volume_results,cluster_results,by="polygon_id")

# load pop estimates
pop_est <- read.csv(here("outputs","data","platforms_houses_pop.csv"))

# Helper rounding function:
# < 10  -> 1 decimal
# >= 10 -> 0 decimals
smart_round <- function(x) ifelse(abs(x) < 10, round(x, 1), round(x, 0))

# Load and prepare combined
# combined <- read.csv("./combined/camellones_with_auto_clusters.csv")

combined <- combined[!is.na(combined$total_volume) & !combined$total_volume == 0, ]
combined$cluster_id <- factor(combined$cluster_id, levels = c(1, 2, 3, 4))
combined$cluster_id <- droplevels(combined$cluster_id)

# Create list of clusters
clusters <- lapply(levels(combined$cluster_id), function(i) subset(combined, cluster_id == i))

# Initialize expanded summary combined frame
summary_df <- data.frame(
  camellon_type   = character(),
  summary         = character(),
  volume          = numeric(),
  person_days     = character(),
  family_days     = character(),
  community_days  = character(),
  stringsAsFactors = FALSE
)

# Populate summary combined frame with min, median, and max for each cluster
for (i in 1:4) {
  cluster_combined <- clusters[[i]]
  volumes <- cluster_combined$total_volume
  camellon_type <- as.character(unique(cluster_combined$cluster_id))
  
  stats <- list(
    minimum = min(volumes),
    median  = median(volumes),
    maximum = max(volumes)
  )
  
  for (label in names(stats)) {
    volume <- stats[[label]]
    person_min <- volume / 5
    person_max <- volume / 2.5
    family_min <- person_min / 5
    family_max <- person_max / 5
    community_min <- person_min / sum(pop_est$pop) / 2 
    community_max <- person_max / sum(pop_est$pop) / 2 
    
    summary_df[nrow(summary_df) + 1, ] <- list(
      camellon_type,
      label,
      smart_round(volume),
      paste(smart_round(person_min), "-", smart_round(person_max)),
      paste(smart_round(family_min), "-", smart_round(family_max)),
      paste(smart_round(community_min), "-", smart_round(community_max))
    )
  }
}

# Finalize table
df <- summary_df
names(df) <- c("camellon_type", "summary", "volume", "person", "family", "community")
df <- df[order(df$camellon_type, df$summary), ]

# Sort and output table
write.csv(df, here("outputs","tables","table1.csv"))
