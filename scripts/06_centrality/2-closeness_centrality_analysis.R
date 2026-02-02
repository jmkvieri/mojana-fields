# Install and load the neccesary packages
# install.packages("sf")
# install.packages("igraph")
# install.packages("tidyverse")
# install.packages("here")
library(sf)
library(igraph)
library(tidyverse)
library(here)

# Load camellones
camellones <- st_read(here("outputs","final_shapefiles", "camellones_with_auto_clusters.shp"))

# Eliminate camellones with geometry problems
empty_geometries <- camellones[st_is_empty(camellones), ]
camellones <- camellones[!st_is_empty(camellones), ]

# Convert to multilinestring
camellones_lines <- st_cast(camellones$geometry, "MULTILINESTRING")

# Extract the node's coordinates
nodes <- st_coordinates(camellones_lines)

# Create a data frame with the node's coordinates
nodes_df <- as.data.frame(nodes)
colnames(nodes_df) <- c("x", "y", "L1", "line_id")

# Set an unique ID for each node
nodes_df <- nodes_df %>%
    distinct(x, y, .keep_all = TRUE) %>%
    mutate(node_id = row_number())

# Create a table of edges using node_id
edges_df <- as.data.frame(nodes) %>%
    mutate(node_id = nodes_df$node_id[match(
        paste(nodes[, 1], nodes[, 2]),
        paste(nodes_df$x, nodes_df$y))]) %>%
    select(L1, node_id) %>%
    group_by(L1) %>%
    mutate(next_node_id = lead(node_id)) %>%
    ungroup() %>%
    filter(!is.na(next_node_id)) %>%
    select(node_id, next_node_id)

# Create the graph
g <- graph_from_data_frame(d = edges_df, vertices = nodes_df %>%
    select(node_id, x, y), directed = FALSE)

# Identify central nodes in the camellones network
# Calculate node centralities
centrality_degree <- degree(g)
centrality_betweenness <- betweenness(g)
centrality_closeness <- closeness(g)

# Add centralities to the node table
nodes_df$degree <- centrality_degree
nodes_df$betweenness <- centrality_betweenness
nodes_df$closeness <- centrality_closeness

# Remove nodes with NA closeness
nodes_df <- nodes_df %>% filter(!is.na(closeness))

# Filter nodes with centrality above 90th percentile
threshold <- quantile(nodes_df$closeness, 0.90)
nodes_df_filtered <- nodes_df %>% filter(closeness > threshold)

# Convert to sf object for visualization
nodes_sf_filtered <- st_as_sf(nodes_df_filtered,
    coords = c("x", "y"),
    crs = st_crs(camellones))

# Visualize only the most central nodes on the plot (CLOSENESS CENTRALITY)
e <- ggplot() +
    geom_sf(data = camellones, color = "grey") +
    geom_sf(
        data = nodes_sf_filtered,
        aes(size = closeness), color = "blue") +
    theme_minimal() +
    labs(
        title = "Nodes with high closeness centrality",
        size = "Closeness\nCentrality") +
    scale_size_continuous(range = c(0.2, 5))

# Save the figure
ggsave(here("outputs","figures","figS2.png"), plot = e, dpi = 300)
png(here("outputs","figures","figS2.png"), width = 3000, height = 1500, res = 300)
print(e)
dev.off()

sessionInfo()
