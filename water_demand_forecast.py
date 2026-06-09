"""
Water Demand Forecasting Pipeline
──────────────────────────────────
Combined model for all service areas with:
- One-hot encoded area IDs
- Total capacity as a feature
- AutoML model selection with cross-validation
- Per-area saturation date estimation
- Model persistence (joblib)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — safe for Flask
import matplotlib.pyplot as plt
import warnings
import joblib
import os
warnings.filterwarnings("ignore")

from scipy.stats      import linregress
from scipy.optimize   import brentq

from sklearn.pipeline        import Pipeline
from sklearn.preprocessing   import StandardScaler
from sklearn.linear_model    import LinearRegression, Ridge, Lasso
from sklearn.ensemble        import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm             import SVR
from sklearn.model_selection import TimeSeriesSplit, cross_val_score, GridSearchCV
from sklearn.metrics         import r2_score, mean_absolute_error


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

MODEL_PATH    = "water_model.pkl"   # saved model location
METADATA_PATH = "water_model_meta.pkl"   # saved feature names + area ids

LINEAR_MODELS = {"LinearRegression", "Ridge", "Lasso"}
TREE_MODELS   = {"RandomForest", "GradientBoosting"}
SVR_MODELS    = {"SVR"}

CANDIDATE_MODELS = {
    "LinearRegression": LinearRegression(),
    "Ridge":            Ridge(),
    "Lasso":            Lasso(),
    "RandomForest":     RandomForestRegressor(n_estimators=100, random_state=42),
    "GradientBoosting": GradientBoostingRegressor(n_estimators=100, random_state=42),
    "SVR":              SVR(kernel="rbf"),
}

PARAM_GRIDS = {
    "Ridge":            {"model__alpha": [0.01, 0.1, 1.0, 10.0, 100.0]},
    "Lasso":            {"model__alpha": [0.001, 0.01, 0.1, 1.0]},
    "RandomForest":     {"model__n_estimators":    [100, 200],
                         "model__max_depth":        [None, 10, 20],
                         "model__min_samples_leaf": [1, 3]},
    "GradientBoosting": {"model__n_estimators":  [100, 200],
                         "model__learning_rate": [0.05, 0.1, 0.2],
                         "model__max_depth":     [3, 5]},
    "SVR":              {"model__C":       [1, 10, 100],
                         "model__epsilon": [0.05, 0.1, 0.2]},
}


# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def validate_inputs(df, area_capacities):
    """
    area_capacities: dict {area_id: capacity}
    df must have: year, month, total_water, population, area_id, total_capacity
    """
    required_cols = ["year", "month", "total_water", "population",
                     "area_id", "total_capacity"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"VALIDATION FAIL — missing columns: {missing}")
        raise ValueError(f"Missing columns: {missing}")

    if (df["total_water"] <= 0).any():
        print("VALIDATION FAIL — total_water has zeros or negatives")
        print(df[df["total_water"] <= 0][["area_id", "year", "month", "total_water"]])
        raise ValueError("total_water contains zeros or negatives")

    if (df["population"] <= 0).any():
        print("VALIDATION FAIL — population has zeros or negatives")
        raise ValueError("population contains zeros or negatives")

    if (df["total_capacity"] <= 0).any():
        print("VALIDATION FAIL — total_capacity has zeros or negatives")
        raise ValueError("total_capacity contains zeros or negatives")

    if df[required_cols].isna().any().any():
        print("VALIDATION FAIL — NaN values found")
        print(df[required_cols].isna().sum())
        raise ValueError("NaN values found in required columns")

    total_rows = len(df)
    n_areas    = df["area_id"].nunique()
    if total_rows < 24:
        print(f"VALIDATION FAIL — only {total_rows} rows across {n_areas} areas, need at least 24")
        raise ValueError(
            f"Only {total_rows} rows across {n_areas} areas — "
            f"need at least 24 total for meaningful cross-validation."
        )

    print(f"✓ Input validation passed — {total_rows} rows, {n_areas} areas")


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════

def engineer_features(df):
    """
    Adds derived columns. One-hot encodes area_id so the model can learn
    a fixed offset per area without imposing a false numeric ordering.

    drop_first=True drops one area column to avoid multicollinearity —
    the dropped area becomes the implicit reference all others are
    compared against.
    """
    df = df.copy()
    df = df.sort_values(["area_id", "year", "month"]).reset_index(drop=True)

    df["month_sin"]      = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"]      = np.cos(2 * np.pi * df["month"] / 12)
    df["log_population"] = np.log(df["population"])
    df["log_water"]      = np.log(df["total_water"])
    df["log_capacity"]   = np.log(df["total_capacity"])

    # One-hot encode area_id
    # area_id_3, area_id_5 ... etc columns are added
    # each is 1 if that row belongs to that area, 0 otherwise
    df = pd.get_dummies(df, columns=["area_id"], drop_first=True)

    return df


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — FEATURE SET SELECTION (year vs population)
# ═══════════════════════════════════════════════════════════════════════

def select_feature_set(df, cv):
    """
    Compares year-based vs population-based using LinearRegression as
    neutral referee. Capacity and area dummies included in both.
    """
    print("\n── Feature set selection ──────────────────────────────────")

    # Collinearity check
    corr          = df[["year", "population", "log_population", "log_water"]].corr()
    year_pop_corr = abs(corr.loc["year", "population"])
    print(f"year ↔ population correlation : {year_pop_corr:.3f}")
    if year_pop_corr > 0.90:
        print("  → High collinearity confirmed — correct to use only one.")

    # Area dummy column names
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    # Capacity column: log for linear, raw not needed here (referee is linear)
    base_extra = ["log_capacity"] + area_dummy_cols

    feature_sets = {
        "year":       ["year",           "month_sin", "month_cos"] + base_extra,
        "population": ["log_population", "month_sin", "month_cos"] + base_extra,
    }

    scores_summary = {}
    for label, feats in feature_sets.items():
        pipe   = Pipeline([("scaler", StandardScaler()),
                           ("model",  LinearRegression())])
        scores = cross_val_score(pipe, df[feats], df["log_water"],
                                 cv=cv, scoring="r2")
        scores_summary[label] = scores.mean()
        print(f"\n  {label}-based  →  CV R² = {scores.mean():.4f} ± {scores.std():.4f}")

    winner = max(scores_summary, key=scores_summary.get)
    margin = abs(scores_summary["year"] - scores_summary["population"])

    print(f"\n✓ Selected feature set : {winner}-based", end="")
    if margin < 0.02:
        print(f"  (margin only {margin:.4f} — year preferred for simpler extrapolation)")
        winner = "year"
    else:
        print(f"  (margin = {margin:.4f})")

    return winner


# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — PIPELINE FACTORY
# ═══════════════════════════════════════════════════════════════════════

def make_pipeline(name, model, feature_set, df):
    """
    Builds (pipeline, features, target, is_log) for each model type.

    Features now include:
      - main predictor  : year OR log_population/population
      - seasonality     : month_sin, month_cos
      - capacity        : log_capacity (linear) / total_capacity (tree)
      - area identity   : one-hot area_id_* columns

    Linear models get log_capacity because the relationship between
    capacity and water is multiplicative, not additive.
    Tree models get raw total_capacity — trees find the right splits
    regardless of scale.
    """
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    if feature_set == "year":
        features_linear = (["year",           "month_sin", "month_cos",
                             "log_capacity"]   + area_dummy_cols)
        features_tree   = (["year",           "month_sin", "month_cos",
                             "total_capacity"] + area_dummy_cols)
    else:
        features_linear = (["log_population", "month_sin", "month_cos",
                             "log_capacity"]   + area_dummy_cols)
        features_tree   = (["population",     "month_sin", "month_cos",
                             "total_capacity"] + area_dummy_cols)

    if name in LINEAR_MODELS:
        pipe     = Pipeline([("scaler", StandardScaler()), ("model", model)])
        features = features_linear
        target   = df["log_water"]
        is_log   = True

    elif name in TREE_MODELS:
        pipe     = Pipeline([("model", model)])
        features = features_tree
        target   = df["total_water"]
        is_log   = False

    else:  # SVR
        pipe     = Pipeline([("scaler", StandardScaler()), ("model", model)])
        features = features_tree
        target   = df["total_water"]
        is_log   = False

    return pipe, features, target, is_log


# ═══════════════════════════════════════════════════════════════════════
# STEP 5 — AUTOML RACE
# ═══════════════════════════════════════════════════════════════════════

def run_model_race(df, feature_set, cv):
    print("\n── Model race ─────────────────────────────────────────────")
    print(f"  {'Model':<22} {'Mean R²':>8} {'Std R²':>8} {'Features':>12}")
    print("  " + "─" * 55)

    results = {}
    for name, model in CANDIDATE_MODELS.items():
        pipe, features, target, is_log = make_pipeline(name, model, feature_set, df)
        scores = cross_val_score(pipe, df[features], target, cv=cv, scoring="r2")

        results[name] = {
            "pipeline": pipe,
            "features": features,
            "target":   target,
            "is_log":   is_log,
            "mean_r2":  scores.mean(),
            "std_r2":   scores.std(),
        }

        feat_label = "log" if is_log else "raw"
        print(f"  {name:<22} {scores.mean():>8.4f} {scores.std():>8.4f} {feat_label:>12}")

    best_name = max(results, key=lambda k: results[k]["mean_r2"])
    print(f"\n✓ Best model (pre-tuning): {best_name}  "
          f"R²={results[best_name]['mean_r2']:.4f} ± {results[best_name]['std_r2']:.4f}")

    return results, best_name


# ═══════════════════════════════════════════════════════════════════════
# STEP 6 — HYPERPARAMETER TUNING
# ═══════════════════════════════════════════════════════════════════════

def tune_best_model(best_name, best_info, df, cv):
    if best_name not in PARAM_GRIDS:
        print(f"\n── Tuning: {best_name} has no hyperparameters to tune — skipping")
        return best_info["pipeline"]

    print(f"\n── Tuning {best_name} ──────────────────────────────────────")
    grid_search = GridSearchCV(
        best_info["pipeline"],
        PARAM_GRIDS[best_name],
        cv=cv, scoring="r2",
        n_jobs=-1, refit=True
    )
    grid_search.fit(df[best_info["features"]], best_info["target"])

    print(f"  Best params : {grid_search.best_params_}")
    print(f"  Tuned R²    : {grid_search.best_score_:.4f}  "
          f"(was {best_info['mean_r2']:.4f})")

    return grid_search.best_estimator_


# ═══════════════════════════════════════════════════════════════════════
# STEP 7 — FINAL EVALUATION
# ═══════════════════════════════════════════════════════════════════════

def evaluate_final_model(best_pipeline, best_info, df):
    """
    Time-ordered 80/20 split across the combined dataset.
    Smearing factor computed for log-space models.
    """
    features = best_info["features"]
    is_log   = best_info["is_log"]

    split_idx = int(len(df) * 0.8)
    X_train   = df[features].iloc[:split_idx]
    X_test    = df[features].iloc[split_idx:]

    if is_log:
        y_train         = df["log_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]
    else:
        y_train         = df["total_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]

    best_pipeline.fit(X_train, y_train)

    if is_log:
        train_preds     = best_pipeline.predict(X_train)
        residuals       = y_train - train_preds
        smearing_factor = np.mean(np.exp(residuals))
        y_pred          = np.exp(best_pipeline.predict(X_test)) * smearing_factor
    else:
        smearing_factor = 1.0
        y_pred          = best_pipeline.predict(X_test)

    r2  = r2_score(y_test_original, y_pred)
    mae = mean_absolute_error(y_test_original, y_pred)

    print(f"\n── Final evaluation (combined model) ──────────────────────")
    print(f"  R²  (original scale) : {r2:.4f}")
    print(f"  MAE (original scale) : {mae:.2f}")
    print(f"  Smearing factor      : {smearing_factor:.4f}")

    return smearing_factor, r2, mae


# ═══════════════════════════════════════════════════════════════════════
# STEP 8 — POPULATION GROWTH RATE
# ═══════════════════════════════════════════════════════════════════════

def estimate_growth_rate(area_df):
    """
    Fits log-linear trend for a single area's population series.
    area_df must have columns: year, month, population
    """
    # One population value per year (average across months to reduce noise)
    yearly = area_df.groupby("year")["population"].mean().reset_index()
    years   = yearly["year"].values.astype(float)
    log_pop = np.log(yearly["population"].values)

    if len(years) < 2:
        # Only one year of data — fall back to zero growth
        print("  ⚠ Only one year of population data — assuming zero growth")
        return 0.0, 0.0, 0.0, 0.0, 0.0

    slope, intercept, r_value, p_value, std_err = linregress(years, log_pop)

    annual_rate  = np.exp(slope) - 1
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    print(f"  Annual growth rate  : {annual_rate * 100:.3f}%")
    print(f"  R² of log-linear fit: {r_value ** 2:.4f}")

    if r_value ** 2 < 0.85:
        print("  ⚠ R² < 0.85 — population trend not consistently exponential")
    if p_value > 0.05:
        print("  ⚠ p-value > 0.05 — trend may not be statistically real")

    return monthly_rate, annual_rate, r_value ** 2, std_err, slope


# ═══════════════════════════════════════════════════════════════════════
# STEP 9 — SATURATION DATE FINDER
# Per area — uses the combined model but each area's own capacity
# ═══════════════════════════════════════════════════════════════════════

def build_probe_row(area_id, year_or_pop_val, peak_month,
                    capacity, feature_set, is_log, all_area_ids, features):
    """
    Builds a single-row DataFrame for prediction, correctly setting
    the area's one-hot dummy columns.

    area_id      : the area we're probing
    all_area_ids : sorted list of ALL area ids (needed to know which
                   dummy columns exist and which is the reference)
    """
    # The reference area (drop_first=True dropped the first sorted area)
    sorted_ids   = sorted(all_area_ids)
    reference_id = sorted_ids[0]

    # Capacity value depends on model type
    cap_val = np.log(capacity) if is_log else capacity

    if feature_set == "year":
        row = {
            "year":        year_or_pop_val,
            "month_sin":   np.sin(2 * np.pi * peak_month / 12),
            "month_cos":   np.cos(2 * np.pi * peak_month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }
    else:
        pred_col = "log_population" if is_log else "population"
        row = {
            pred_col:      year_or_pop_val,
            "month_sin":   np.sin(2 * np.pi * peak_month / 12),
            "month_cos":   np.cos(2 * np.pi * peak_month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }

    # Set all area dummy columns to 0 first
    for aid in sorted_ids[1:]:   # skip reference (it was dropped)
        row[f"area_id_{aid}"] = 0

    # Set this area's dummy to 1 (unless it's the reference area)
    if area_id != reference_id:
        col_name = f"area_id_{area_id}"
        if col_name in features:
            row[col_name] = 1

    return pd.DataFrame([row], columns=features)


def find_peak_month(best_pipeline, features, feature_set, is_log,
                    smearing_factor, area_id, area_df,
                    capacity, all_area_ids):
    """Finds which month produces highest demand for a specific area."""
    if feature_set == "year":
        ref_val = area_df["year"].median()
    else:
        ref_val = (area_df["log_population"].median() if is_log
                   else area_df["population"].median())

    monthly_preds = []
    for m in range(1, 13):
        X_probe = build_probe_row(
            area_id, ref_val, m, capacity,
            feature_set, is_log, all_area_ids, features
        )
        pred = best_pipeline.predict(X_probe)[0]
        if is_log:
            pred = np.exp(pred) * smearing_factor
        monthly_preds.append(pred)

    return int(np.argmax(monthly_preds)) + 1


def find_saturation_for_area(best_pipeline, features, feature_set,
                              is_log, smearing_factor,
                              area_id, area_df, capacity,
                              all_area_ids):
    """
    Finds saturation date for one area using the combined model.
    Each area uses its own capacity as the threshold.
    """
    print(f"\n  ── Area {area_id} ──────────────────────────────────────")

    peak_month = find_peak_month(
        best_pipeline, features, feature_set, is_log,
        smearing_factor, area_id, area_df, capacity, all_area_ids
    )
    print(f"  Peak demand month : {peak_month}")

    if feature_set == "year":
        # Sweep future years
        current_year = int(area_df["year"].max())
        sat_year, sat_month = None, None

        for future_year in range(current_year, current_year + 100):
            X_probe = build_probe_row(
                area_id, future_year, peak_month, capacity,
                feature_set, is_log, all_area_ids, features
            )
            pred = best_pipeline.predict(X_probe)[0]
            if is_log:
                pred = np.exp(pred) * smearing_factor

            if pred >= capacity:
                sat_year, sat_month = future_year, peak_month
                break

        if sat_year:
            print(f"  Predicted saturation : {sat_year}/{sat_month:02d}")
            return {"year": sat_year, "month": sat_month,
                    "peak_month": peak_month}
        else:
            print("  Capacity not reached within 100 years")
            return {"year": None, "month": None, "peak_month": peak_month}

    else:
        # Population-based — brentq root finding
        monthly_rate, _, _, slope_std_err, _ = estimate_growth_rate(area_df)

        pred_col = "log_population" if is_log else "population"
        P0       = area_df["population"].iloc[-1]

        def water_minus_capacity(population):
            pop_val = np.log(population) if is_log else population
            X_probe = build_probe_row(
                area_id, pop_val, peak_month, capacity,
                feature_set, is_log, all_area_ids, features
            )
            pred = best_pipeline.predict(X_probe)[0]
            if is_log:
                pred = np.exp(pred) * smearing_factor
            return pred - capacity

        if water_minus_capacity(P0) > 0:
            print("  ⚠ Current population already exceeds capacity")
            return {"year": None, "month": None, "peak_month": peak_month,
                    "warning": "already_exceeded"}

        # Expand upper bound until we bracket the root
        P_high = P0 * 2
        for _ in range(20):
            if water_minus_capacity(P_high) > 0:
                break
            P_high *= 2
        else:
            print("  ⚠ Capacity not reached within reasonable range")
            return {"year": None, "month": None, "peak_month": peak_month}

        pop_max = brentq(water_minus_capacity, P0, P_high, xtol=1.0)

        # Convert to date — 3 scenarios based on growth rate uncertainty
        scenarios = {}
        for label, rate_adj in [("pessimistic", -slope_std_err),
                                 ("expected",     0),
                                 ("optimistic",  +slope_std_err)]:
            adj_annual  = np.exp(slope_std_err * rate_adj + np.log(1 + monthly_rate * 12)) - 1
            adj_monthly = (1 + adj_annual) ** (1 / 12) - 1

            if adj_monthly <= 0:
                scenarios[label] = {"year": None, "month": None}
                continue

            months_diff = np.log(pop_max / P0) / np.log(1 + adj_monthly)
            scenarios[label] = {
                "year":  int(area_df["year"].iloc[-1] + months_diff // 12),
                "month": int((months_diff % 12) + 1)
            }

        print(f"  Saturation population : {int(pop_max):,}")
        for label, val in scenarios.items():
            if val["year"]:
                print(f"  {label:<14} : {val['year']}/{val['month']:02d}")

        return {"pop_max": int(pop_max), "scenarios": scenarios,
                "peak_month": peak_month}


# ═══════════════════════════════════════════════════════════════════════
# STEP 10 — FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════

def print_feature_importance(best_name, best_pipeline, features):
    if best_name not in TREE_MODELS:
        return

    print(f"\n── Feature importance ({best_name}) ────────────────────────")
    importances = best_pipeline.named_steps["model"].feature_importances_

    for feat, imp in sorted(zip(features, importances), key=lambda x: -x[1]):
        bar = "█" * int(imp * 40)
        print(f"  {feat:<25} {imp:.4f}  {bar}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def run_forecast(df, area_capacities, requested_area_id):
    """
    Combined model for all service areas.

    Parameters
    ----------
    df                : DataFrame with columns:
                        year, month, total_water, population,
                        area_id, total_capacity
    area_capacities   : dict {area_id: total_capacity}
    requested_area_id : the area from the POST request — highlighted in results

    Returns
    -------
    dict with:
        - model info (best_model, cv scores, final scores)
        - requested_area_saturation : saturation result for the requested area
        - all_areas_saturation      : saturation for every area sorted by urgency
        - at_risk_areas             : areas predicted to hit capacity soonest
    """

    print(f"\n{'═' * 60}")
    print(f"  WATER DEMAND FORECAST — Combined Model")
    print(f"  Requested area : {requested_area_id}")
    print(f"{'═' * 60}")

    # ── 1. Validate ───────────────────────────────────────────────────
    validate_inputs(df, area_capacities)

    # ── 2. Feature engineering ────────────────────────────────────────
    # Keep original df for per-area saturation calculations
    original_df = df.copy()
    df          = engineer_features(df)

    all_area_ids = sorted(original_df["area_id"].unique().tolist())
    print(f"  Areas in model : {all_area_ids}")

    # ── 3. CV splitter ────────────────────────────────────────────────
    n_splits = min(5, len(df) // 6)
    cv       = TimeSeriesSplit(n_splits=n_splits, gap=1)
    print(f"  CV splits      : {n_splits}")

    # ── 4. Select feature set ─────────────────────────────────────────
    feature_set = select_feature_set(df, cv)

    # ── 5. Model race ─────────────────────────────────────────────────
    race_results, best_name = run_model_race(df, feature_set, cv)
    best_info               = race_results[best_name]

    # ── 6. Tune best model ────────────────────────────────────────────
    best_pipeline = tune_best_model(best_name, best_info, df, cv)

    # ── 7. Final evaluation ───────────────────────────────────────────
    smearing_factor, final_r2, final_mae = evaluate_final_model(
        best_pipeline, best_info, df
    )

    # Refit on full data after evaluation so predictions use all data
    best_pipeline.fit(df[best_info["features"]], best_info["target"])

    # ── 8. Feature importance ─────────────────────────────────────────
    print_feature_importance(best_name, best_pipeline, best_info["features"])

    # ── 9. Save model ─────────────────────────────────────────────────
    # One combined model — safe to save because it covers all areas
    joblib.dump(best_pipeline, MODEL_PATH)
    joblib.dump({
        "features":       best_info["features"],
        "feature_set":    feature_set,
        "is_log":         best_info["is_log"],
        "smearing_factor": smearing_factor,
        "all_area_ids":   all_area_ids,
        "best_name":      best_name,
    }, METADATA_PATH)
    print(f"\n✓ Model saved → {MODEL_PATH}")

    # ── 10. Per-area saturation ───────────────────────────────────────
    print(f"\n── Saturation analysis (all areas) ────────────────────────")

    all_areas_saturation   = {}
    requested_area_result  = None

    for area_id in all_area_ids:
        area_df  = original_df[original_df["area_id"] == area_id].copy()
        capacity = area_capacities.get(area_id, 0)

        if capacity <= 0:
            print(f"  ⚠ Area {area_id} has no capacity data — skipping")
            continue

        sat = find_saturation_for_area(
            best_pipeline, best_info["features"], feature_set,
            best_info["is_log"], smearing_factor,
            area_id, area_df, capacity, all_area_ids
        )
        all_areas_saturation[str(area_id)] = sat

        if area_id == requested_area_id:
            requested_area_result = sat

    # ── 11. Rank areas by urgency ─────────────────────────────────────
    # Extract the expected saturation year for sorting
    # Areas with no saturation year (capacity never reached) go last
    def saturation_sort_key(item):
        sat = item[1]
        if feature_set == "year":
            return sat.get("year") or 9999
        else:
            scenarios = sat.get("scenarios", {})
            expected  = scenarios.get("expected", {})
            return expected.get("year") or 9999

    sorted_areas = sorted(all_areas_saturation.items(),
                          key=saturation_sort_key)

    # At-risk: areas saturating within 10 years
    current_year  = int(original_df["year"].max())
    at_risk_areas = [
        {"area_id": aid, "saturation": sat}
        for aid, sat in sorted_areas
        if saturation_sort_key((aid, sat)) <= current_year + 10
    ]

    print(f"\n── At-risk areas (saturating within 10 years) ─────────────")
    if at_risk_areas:
        for item in at_risk_areas:
            print(f"  Area {item['area_id']:<5} → {item['saturation']}")
    else:
        print("  None — all areas have capacity for 10+ years")

    # ── 12. Summary ───────────────────────────────────────────────────
    print(f"\n── Summary ─────────────────────────────────────────────────")
    print(f"  Best model           : {best_name}")
    print(f"  Feature set          : {feature_set}-based")
    print(f"  CV R²                : {race_results[best_name]['mean_r2']:.4f} "
          f"± {race_results[best_name]['std_r2']:.4f}")
    print(f"  Final R²             : {final_r2:.4f}")
    print(f"  Final MAE            : {final_mae:.2f}")
    print(f"  Requested area ({requested_area_id}) : {requested_area_result}")
    print(f"{'═' * 60}\n")

    return {
        "best_model":               best_name,
        "feature_set":              feature_set,
        "cv_r2_mean":               round(race_results[best_name]["mean_r2"], 4),
        "cv_r2_std":                round(race_results[best_name]["std_r2"],  4),
        "final_r2":                 round(final_r2,  4),
        "final_mae":                round(final_mae, 2),
        "smearing_factor":          smearing_factor,
        "requested_area_id":        requested_area_id,
        "requested_area_saturation": requested_area_result,
        "all_areas_saturation":     dict(sorted_areas),
        "at_risk_areas":            at_risk_areas,
    }
