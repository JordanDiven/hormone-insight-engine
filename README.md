# Longitudinal Hormone Analytics and Insight Engine

An end-to-end personal data-science project exploring three connected problems in
longitudinal reproductive-health data:

1. User-level modelling of resemblance to a self-identified PCOS-pattern cohort.
2. Prospective fertile-window and ovulation guidance from LH, E3G and PdG,
   including explicit uncertainty and abstention.
3. A production-oriented biomarker insight architecture with confidence gates,
   claim controls, monitoring and constrained LLM integration.

The work goes beyond model fitting. It addresses longitudinal feature engineering,
repeated-measures leakage, leave-one-user-out validation, cold-start performance,
bootstrap uncertainty, subgroup diagnostics, temporal evaluation, weak reference
labels, product safety and system design.

> The included workbooks are anonymized demonstration data. These analyses
> are research prototypes, not diagnostic tools or clinically validated claims.

## Results at a glance

| Analysis | Result |
|---|---:|
| Users | 40 |
| Hormone observations | 9,249 |
| PCOS-pattern leave-one-user-out ROC AUC | 0.875 |
| PCOS-pattern average precision | 0.883 |
| First-cycle-only ROC AUC | 0.788 |
| Ovulation-reference cycles evaluated | 67 |
| Hormone-updated predictions within one day | 95.5% |
| Hormone-updated interval coverage | 95.5% |

These figures describe this small, selected dataset and do not estimate clinical
or production performance.

## Reports

- [PCOS-pattern resemblance](reports/pcos_pattern_report.md)
- [Prospective fertile-window and ovulation estimation](reports/ovulation_window_report.md)
- [Biomarker insight-system architecture](reports/insight_engine_architecture.md)

## Repository structure

- `data/`: anonymized demonstration Excel workbooks.
- `scripts/`: reproducible modelling, evaluation and figure-generation pipelines.
- `reports/`: three detailed technical and product case studies.
- `assets/`: selected figures used by the reports.
- `tests/`: leakage, cohort-integrity and prospective-timing checks.

## Setup

```bash
python -m pip install -r requirements.txt
```

## Reproduce

Run these commands from the repository root:

```bash
python scripts/pcos_pattern_analysis.py
python scripts/cold_start_evaluation.py
python scripts/bootstrap_uncertainty.py
python scripts/subgroup_diagnostics.py

python scripts/ovulation_window_model.py
python scripts/prospective_daily_evaluation.py
python scripts/user_journey_chart.py
python scripts/fertile_window_flowchart.py

python scripts/insight_engine_architecture_diagram.py
python -m unittest discover -s tests -v
```

The scripts write detailed intermediate tables to `assets/`. Generated CSV files,
secondary diagnostic figures and run summaries are intentionally ignored by Git;
the six selected report figures remain versioned.

## Interpretation boundary

The pattern model estimates resemblance to two development cohorts—not disease
probability. The ovulation analysis evaluates agreement with reference
annotations—not independent clinical ground truth. The architecture keeps
biological reasoning in validated algorithms and restricts the LLM to controlled
wording.

The central engineering conclusion is that longitudinal health models require
user-level validation, prospective information cutoffs, calibrated uncertainty,
explicit abstention and careful separation between observed patterns and medical
claims.
