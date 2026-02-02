library(here)

# load calculated_volumes
volume_results <- read.csv(here("outputs","data","volume_results.csv"))
# load results of clustering and merge
cluster_results <- read.csv(here("outputs","data","camellones_with_auto_clusters.csv"))

combined <- merge(volume_results,cluster_results,by="polygon_id")

# load pop estimates
pop_est <- read.csv(here("outputs","data","platforms_houses_pop.csv"))

# Load and prepare combined
combined <- combined[!is.na(combined$total_volume),]
combined$cluster_id <- factor(combined$cluster_id, levels = c(1,2,3,4))
combined$cluster_id <- droplevels(combined$cluster_id)

# Formatter function for months
fmt_month <- function(x) {
  ifelse(x < 5,
         sprintf("%.1f", round(x, 1)),  # one decimal if < 5
         sprintf("%.0f", round(x, 0)))  # no decimals otherwise
}

# ----------------------------------

# Create list of clusters
clusters <- list()
for (i in levels(combined$cluster_id)) {
  clusters[[i]] <- subset(combined, combined$cluster_id == i)
}

# Initialize summary combined frame
summary_df <- data.frame(
  camellon_type = character(),
  quantity = numeric(),
  combined_volume = numeric(),
  person_days = numeric(),
  person_weeks = numeric(),
  person_months = numeric(),
  family_days = numeric(),
  family_weeks = numeric(),
  family_months = numeric(),
  community_days = numeric(),
  community_weeks = numeric(),
  community_months = numeric(),
  stringsAsFactors = FALSE
)

# Populate summary combined frame
for (i in 1:4) {
  total_volume <- sum(clusters[[i]]$total_volume)
  quantity <- nrow(clusters[[i]])
  camellon_type <- as.character(unique(clusters[[i]]$cluster_id))
  
  person_min <- total_volume / 5
  person_max <- total_volume / 2.5
  family_min <- person_min / 5
  family_max <- person_max / 5
  community_min <- person_min / sum(pop_est$pop) / 2
  community_max <- person_max / sum(pop_est$pop) / 2
  
  # months values (numeric)
  person_m_min <- person_min / 30
  person_m_max <- person_max / 30
  family_m_min <- family_min / 30
  family_m_max <- family_max / 30
  community_m_min <- community_min / 30
  community_m_max <- community_max / 30
  
  summary_df[i, ] <- list(
    camellon_type,
    quantity,
    round(total_volume, 0),
    paste(round(person_min, 0), "-", round(person_max, 0)),
    paste(round(person_min / 7, 0), "-", round(person_max / 7, 0)),
    # --- CHANGED: use fmt_month for months ---
    paste(fmt_month(person_m_min), "-", fmt_month(person_m_max)),
    # -----------------------------------------
    paste(round(family_min, 0), "-", round(family_max, 0)),
    paste(round(family_min / 7, 0), "-", round(family_max / 7, 0)),
    paste(fmt_month(family_m_min), "-", fmt_month(family_m_max)),
    paste(round(community_min, 0), "-", round(community_max, 0)),
    paste(round(community_min / 7, 0), "-", round(community_max / 7, 0)),
    paste(fmt_month(community_m_min), "-", fmt_month(community_m_max))
  )
}

# Build the final table from summary_df
df <- data.frame(
  camellon_type = character(),
  quantity = character(),
  combined_volume = character(),
  unit = character(),
  person = character(),
  family = character(),
  community = character(),
  stringsAsFactors = FALSE
)

for (i in 1:nrow(summary_df)) {
  # Days
  df[nrow(df) + 1, ] <- c(
    summary_df$camellon_type[i],
    summary_df$quantity[i],
    summary_df$combined_volume[i],
    "Days",
    summary_df$person_days[i],
    summary_df$family_days[i],
    summary_df$community_days[i]
  )
  # Weeks
  df[nrow(df) + 1, ] <- c(
    summary_df$camellon_type[i],
    "", "", "Weeks",
    summary_df$person_weeks[i],
    summary_df$family_weeks[i],
    summary_df$community_weeks[i]
  )
  # Months
  df[nrow(df) + 1, ] <- c(
    summary_df$camellon_type[i],
    "", "", "Months",
    summary_df$person_months[i],
    summary_df$family_months[i],
    summary_df$community_months[i]
  )
}

df <- df[order(df$camellon_type), ]

# Add total rows
total_volume <- sum(combined$total_volume)
total_quantity <- nrow(combined)

add_row <- function(unit, div) {
  # base values for this unit
  person_min <- total_volume / 5 / div
  person_max <- total_volume / 2.5 / div
  family_min <- total_volume / 5 / 5 / div
  family_max <- total_volume / 2.5 / 5 / div
  community_min <- total_volume / 5 / sum(pop_est$pop) / 2 / div
  community_max <- total_volume / 2.5 / sum(pop_est$pop) / 2 / div
  
  if (unit == "Months") {
    # --- CHANGED: formatted months ---
    person <- paste(fmt_month(person_min), "-", fmt_month(person_max))
    family <- paste(fmt_month(family_min), "-", fmt_month(family_max))
    community <- paste(fmt_month(community_min), "-", fmt_month(community_max))
  } else {
    person <- paste(round(person_min, 0), "-", round(person_max, 0))
    family <- paste(round(family_min, 0), "-", round(family_max, 0))
    community <- paste(round(community_min, 0), "-", round(community_max, 0))
  }
  
  df[nrow(df) + 1, ] <<- c(
    ifelse(unit == "Days", "Total", ""), 
    ifelse(unit == "Days", total_quantity, ""), 
    ifelse(unit == "Days", round(total_volume, 0), ""),
    unit, person, family, community
  )
}

add_row("Days", 1)
add_row("Weeks", 7)
add_row("Months", 30)

write.csv(df, here("outputs","tables","table2.csv"))

