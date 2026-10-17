# Optional starting point AFTER preregistering the analysis plan.
# Rscript backend/scripts/fit_research_models.R analysis-output/questions.csv models.txt
# Requires the R package lme4. Models are exploratory; no automatic study conclusions.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Supply questions.csv and an output .txt path")
if (!requireNamespace("lme4", quietly = TRUE)) stop("Install the R package lme4 first")
data <- read.csv(args[1], stringsAsFactors = FALSE, na.strings = c("", "NA"))
truth <- function(x) !is.na(x) & tolower(as.character(x)) == "true"
data <- data[truth(data$answered) & !truth(data$is_test) & !truth(data$archived), ]
# Base is fixed first. Exclude it rather than claiming position adjustment can
# identify a separate base effect. Analyze studies/versions separately by default.
data <- data[data$quiz_id != "base" & !is.na(data$question_version), ]
data$item_version <- paste(data$question_id, data$question_version, sep = ":")
sink(args[2])
cat("Exploratory models. Inspect singular fits, convergence, sparse cells and eligibility.\n")
cat("Wrong-AI agreement conditions on exposure; it is not a causal treatment effect.\n")
for (version in unique(na.omit(data$study_flow_version))) {
  group <- data[!is.na(data$study_flow_version) & data$study_flow_version == version, ]
  cat("\nStudy version:", version, "\n")
  for (outcome in c("correct", "matched_wrong_ai")) {
    eligible <- group
    if (outcome == "matched_wrong_ai") eligible <- eligible[truth(eligible$wrong_ai_exposed) & !is.na(eligible$matched_wrong_ai), ]
    eligible <- eligible[!is.na(eligible[[outcome]]), ]
    if (length(unique(eligible$participant_id)) < 5 || length(unique(eligible$quiz_id)) < 2 || length(unique(eligible$item_version)) < 2 || length(unique(eligible[[outcome]])) < 2) {
      cat(outcome, ": insufficient variation / participant coverage\n"); next
    }
    eligible$response <- as.integer(truth(eligible[[outcome]]))
    terms <- c("factor(quiz_id)", "(1 | participant_id)", "(1 | item_version)")
    for (covariate in c("variant_position", "question_set")) {
      if (length(unique(na.omit(eligible[[covariate]]))) > 1) terms <- c(terms, paste0("factor(", covariate, ")"))
    }
    formula <- as.formula(paste("response ~", paste(terms, collapse = " + ")))
    fit <- tryCatch(lme4::glmer(formula, data = eligible, family = binomial()), error = function(e) e)
    cat("\nOutcome:", outcome, " N:", nrow(eligible), "\n")
    if (inherits(fit, "error")) { cat(conditionMessage(fit), "\n"); next }
    print(summary(fit))
    cat("Singular fit:", lme4::isSingular(fit), "\n")
    print(fit@optinfo$conv$lme4$messages)
    print(confint(fit, parm = "beta_", method = "Wald"))
  }
}
sink()
