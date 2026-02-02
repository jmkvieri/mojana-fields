library(here)

# Load camellones on clustered camellones
camellones <- read.csv(here("outputs","data", "camellones_with_auto_clusters.csv"),na.strings=c(NA,NULL,""))

camellones$cluster_id <- as.factor(camellones$cluster_id)

cols <- c("#3975d4", "#ef9a1a","#da47c9","#00760c")

# Create summary boxplots with optimized settings
png(here("outputs","figures","figS1.png"), width = 2480, height = 4008, res = 300)

# Better spacing and scaling
par(
  mfrow = c(3, 1),
  mai = c(0.5, 1, 1, 0.5),  # margins: bottom, left, top, right
  cex=1.1,
  cex.lab=1.1)

# Use consistent and correct labels, and improved titles
boxplot(
  camellones$total_length ~ camellones$cluster_id,
  xlab = NA,
  ylab = "Total Camellon Length",
  main = "Total Length by Cluster",
  lwd = 2,
  col = cols,
  cex.pch = 1.2
)

boxplot(
  camellones$angle_cos ~ camellones$cluster_id,
  xlab = NA,
  ylab = "Cosine of Angle",
  main = "Cosine of Orientation by Cluster",
  lwd = 2,
  col = cols,
  cex.pch = 1.2
)

boxplot(
  camellones$angle_sin ~ camellones$cluster_id,
  xlab = "Cluster ID",
  ylab = "Sine of Angle",
  main = "Sine of Orientation by Cluster",
  lwd = 2,
  col = cols,
  cex.pch = 1.2
)

dev.off()
