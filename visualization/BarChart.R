# Reproducible CBP Bar Chart — 2023 Employment by Selected Geography
#
# Source:
#   U.S. Census Bureau, County Business Patterns (CBP), 2023.
#
# Scope:
#   NAICS2017 00 — Total for all sectors
#   LFO 001 — All legal forms
#   EMPSZES 001 — All establishment sizes
#
# Input:
#   ../data/validated/cbp_2023_validated.csv
#
# Output:
#   ../results/charts/CBP_BarChart_2023_Employment_R.png
#
# This script uses the validated stable snapshot. It does not call the Census API.

suppressPackageStartupMessages({
  library(ggplot2)
  library(scales)
})

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) > 0) {
  script_path <- normalizePath(sub("^--file=", "", file_arg[1]))
  here <- dirname(script_path)
} else {
  here <- getwd()
}

data_path <- file.path(here, "..", "data", "validated", "cbp_2023_validated.csv")
out_path <- file.path(here, "..", "results", "charts", "CBP_BarChart_2023_Employment_R.png")

df <- read.csv(
  data_path,
  colClasses = c(
    state = "character",
    NAICS2017 = "character",
    LFO = "character",
    EMPSZES = "character",
    YEAR = "character"
  ),
  check.names = FALSE
)

required <- c(
  "NAME", "EMP", "EMP_N", "NAICS2017", "NAICS2017_LABEL",
  "LFO", "EMPSZES", "state", "YEAR"
)
missing <- setdiff(required, names(df))
if (length(missing) > 0) {
  stop(paste("Missing required columns:", paste(missing, collapse = ", ")))
}

df$state <- sprintf("%02d", as.integer(df$state))
df$NAICS2017 <- sprintf("%02d", as.integer(df$NAICS2017))
df$LFO <- sprintf("%03d", as.integer(df$LFO))
df$EMPSZES <- sprintf("%03d", as.integer(df$EMPSZES))
df$EMP <- as.numeric(df$EMP)
df$EMP_N <- as.numeric(df$EMP_N)

expected_states <- c("10", "11", "24", "42", "51")
if (!setequal(df$state, expected_states)) stop("Unexpected geography coverage.")
if (!all(df$YEAR == "2023")) stop("Input contains a year other than 2023.")
if (!all(df$NAICS2017 == "00")) stop("Expected NAICS2017 code 00.")
if (!all(df$LFO == "001") || !all(df$EMPSZES == "001")) {
  stop("Expected all legal forms and all establishment sizes.")
}
if (any(is.na(df$EMP)) || any(df$EMP < 0)) {
  stop("EMP contains missing or negative values.")
}

df <- df[order(df$EMP, df$NAME), ]
df$NAME <- factor(df$NAME, levels = df$NAME)

p <- ggplot(df, aes(x = EMP, y = NAME)) +
  geom_col(width = 0.68) +
  geom_text(
    aes(label = comma(EMP)),
    hjust = -0.08,
    size = 3.5
  ) +
  scale_x_continuous(
    limits = c(0, max(df$EMP) * 1.18),
    labels = label_number(scale = 1e-6, suffix = "M", accuracy = 0.1),
    expand = expansion(mult = c(0, 0))
  ) +
  labs(
    title = "Employment by Selected Geography, 2023",
    subtitle = "County Business Patterns • Total for all sectors",
    x = "Employment",
    y = NULL,
    caption = paste(
      "Source: U.S. Census Bureau, County Business Patterns (CBP), 2023.",
      "NAICS2017 00 (Total for all sectors)."
    )
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold", size = 16),
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    plot.caption = element_text(hjust = 0, size = 8)
  )

ggsave(out_path, p, width = 10, height = 6.2, dpi = 300)

cat("Saved:", out_path, "\n")
print(df[, c("state", "NAME", "EMP", "EMP_N")], row.names = FALSE)
