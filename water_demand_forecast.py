"""
Water Demand Forecasting Pipeline
──────────────────────────────────
Combined model for all service areas with:
- One-hot encoded area IDs
- Total capacity as a feature
- Time-sorted splits (every fold contains all areas)
- AutoML model selection with cross-validation
- Per-area saturation date estimation
- Model persistence (joblib)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe for Flask
import matplotlib.pyplot as plt
import warnings
import joblib
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

MODEL_PATH    = "water_model.pkl"
METADATA_PATH = "water_model_meta.pkl"

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

def validate_inputs(df):
    """
    Validates the combined dataframe before any ML work.
    df must have: year, month, total_water, population, area_id, total_capacity
    Raises ValueError with a clear message on any failure.
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
        print(f"VALIDATION FAIL — only {total_rows} rows across {n_areas} areas, "
              f"need at least 24")
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
    Adds all derived columns and one-hot encodes area_id.

    Sorting by [year, month, area_id] is critical — it ensures every
    time slice groups together so train/test splits cut across TIME,
    not across areas. This means every fold sees all areas.

    One-hot encoding:
        area_id_3, area_id_5 ... one column per area except the first
        (drop_first=True removes the reference area to avoid
        multicollinearity — having N-1 dummies fully represents N areas)
    """
    df = df.copy()

    # Sort by TIME first — this is the key fix for correct CV splits
    # Each time slice (Jul 2025, Aug 2025 ...) has one row per area
    # so splitting by row index = splitting by time period
    df = df.sort_values(["year", "month", "area_id"]).reset_index(drop=True)

    df["month_sin"]      = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"]      = np.cos(2 * np.pi * df["month"] / 12)
    df["log_population"] = np.log(df["population"])
    df["log_water"]      = np.log(df["total_water"])
    df["log_capacity"]   = np.log(df["total_capacity"])

    # One-hot encode area_id — converts categorical area IDs into
    # binary columns the model can use without implying numeric ordering
    df = pd.get_dummies(df, columns=["area_id"], drop_first=True)

    return df


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — VALIDATE CV FOLDS
# Confirms every fold contains multiple areas before training starts
# ═══════════════════════════════════════════════════════════════════════

def validate_cv_folds(df, cv, features):
    """
    Prints area count per fold. After the time-sort fix you should see
    all 26 areas in every train and test fold.

    If test areas < total areas, the sort didn't work as expected
    or data is missing for some areas in certain months.
    """
    # Recover area_id from one-hot columns for counting
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    print(f"\n── CV fold validation ──────────────────────────────────────")
    print(f"  {'Fold':<6} {'Train rows':>11} {'Train areas':>12} "
          f"{'Test rows':>10} {'Test areas':>11}")
    print("  " + "─" * 55)

    for fold_idx, (train_idx, test_idx) in enumerate(cv.split(df[features])):
        # Count distinct areas by checking which dummy cols are 1
        # (reference area = row where all dummies are 0)
        train_df    = df.iloc[train_idx]
        test_df     = df.iloc[test_idx]

        # Each row is one area-month — just count unique row groups
        # approximated by row count / months in fold
        train_rows  = len(train_idx)
        test_rows   = len(test_idx)

        # Estimate areas: if data is balanced, rows / months = areas
        # Use dummy columns to count actual unique area combinations
        if area_dummy_cols:
            train_area_count = len(train_df[area_dummy_cols].drop_duplicates())
            test_area_count  = len(test_df[area_dummy_cols].drop_duplicates())
        else:
            train_area_count = "?"
            test_area_count  = "?"

        print(f"  Fold {fold_idx + 1:<2}  "
              f"{train_rows:>10}   "
              f"{str(train_area_count):>11}   "
              f"{test_rows:>9}   "
              f"{str(test_area_count):>10}")

        if isinstance(test_area_count, int) and test_area_count < 2:
            print(f"  ⚠ WARNING fold {fold_idx + 1}: test set has < 2 areas — "
                  f"check data completeness across months")


# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — FEATURE SET SELECTION (year vs population)
# ═══════════════════════════════════════════════════════════════════════

def select_feature_set(df, cv):
    """
    Compares year-based vs population-based features using LinearRegression
    as a neutral referee. Capacity and area dummies included in both.
    """
    print("\n── Feature set selection ──────────────────────────────────")

    corr          = df[["year", "population", "log_population", "log_water"]].corr()
    year_pop_corr = abs(corr.loc["year", "population"])
    print(f"year ↔ population correlation : {year_pop_corr:.3f}")
    if year_pop_corr > 0.90:
        print("  → High collinearity confirmed — correct to use only one.")

    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    feature_sets = {
        "year":       ["year",           "month_sin", "month_cos",
                       "log_capacity"]   + area_dummy_cols,
        "population": ["log_population", "month_sin", "month_cos",
                       "log_capacity"]   + area_dummy_cols,
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
# STEP 5 — PIPELINE FACTORY
# ═══════════════════════════════════════════════════════════════════════

def make_pipeline(name, model, feature_set, df):
    """
    Builds (pipeline, features, target, is_log) for each model type.

    Feature sets:
        Linear models → log_capacity + log_population or year + area dummies
        Tree models   → total_capacity + population or year + area dummies
        SVR           → same as tree but with StandardScaler

    Why different capacity columns?
        Linear models need log_capacity because the relationship is
        multiplicative. Tree models find the right split regardless of scale.
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
# STEP 6 — AUTOML RACE
# ═══════════════════════════════════════════════════════════════════════

def run_model_race(df, feature_set, cv):
    """
    Runs cross-validation for every candidate model.
    Data is already time-sorted so CV folds are time-aware.
    """
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
# STEP 7 — HYPERPARAMETER TUNING
# ═══════════════════════════════════════════════════════════════════════

def tune_best_model(best_name, best_info, df, cv):
    """
    Tunes only the winning model — no wasted computation on losers.
    LinearRegression has no hyperparameters so it's skipped.
    """
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
# STEP 8 — FINAL EVALUATION
# ═══════════════════════════════════════════════════════════════════════

def evaluate_final_model(best_pipeline, best_info, df):
    """
    80/20 time-ordered split across the combined dataset.

    Because df is sorted by [year, month, area_id], the split cuts
    across time — train = early months of ALL areas,
    test = later months of ALL areas.

    This correctly simulates deployment: the model has seen all areas
    and is tested on whether it can predict their FUTURE demand.
    """
    features  = best_info["features"]
    is_log    = best_info["is_log"]
    split_idx = int(len(df) * 0.8)

    X_train = df[features].iloc[:split_idx]
    X_test  = df[features].iloc[split_idx:]

    # Recover area_id counts for verification
    area_dummy_cols      = [c for c in features if c.startswith("area_id_")]
    train_area_count     = (len(df.iloc[:split_idx][area_dummy_cols].drop_duplicates())
                            if area_dummy_cols else "?")
    test_area_count      = (len(df.iloc[split_idx:][area_dummy_cols].drop_duplicates())
                            if area_dummy_cols else "?")

    print(f"\n── Final evaluation (combined model) ──────────────────────")
    print(f"  Train : {split_idx} rows / {train_area_count} areas"
          f"  (months up to split)")
    print(f"  Test  : {len(df) - split_idx} rows / {test_area_count} areas"
          f"  (most recent months)")

    if isinstance(test_area_count, int) and test_area_count < 2:
        print("  ⚠ WARNING: test set has fewer than 2 areas — "
              "data may not be balanced across months")

    if is_log:
        y_train         = df["log_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]
    else:
        y_train         = df["total_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]

    best_pipeline.fit(X_train, y_train)

    # Smearing factor corrects the bias introduced by log → exp inversion
    # For raw-target models it stays 1.0 (no correction needed)
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

    print(f"  R²  (original scale) : {r2:.4f}")
    print(f"  MAE (original scale) : {mae:.2f}")
    print(f"  Smearing factor      : {smearing_factor:.4f}")

    return smearing_factor, r2, mae


# ═══════════════════════════════════════════════════════════════════════
# STEP 9 — POPULATION GROWTH RATE
# Used only when feature_set == "population"
# ═══════════════════════════════════════════════════════════════════════

def estimate_growth_rate(area_df):
    """
    Fits log-linear trend over all available years for one area.
    Uses yearly averages to reduce monthly noise.
    Returns monthly_rate and std_err for uncertainty propagation.
    """
    yearly  = area_df.groupby("year")["population"].mean().reset_index()
    years   = yearly["year"].values.astype(float)
    log_pop = np.log(yearly["population"].values)

    if len(years) < 2:
        print("  ⚠ Only one year of data — assuming zero growth")
        return 0.0, 0.0, 0.0, 0.0, 0.0

    slope, intercept, r_value, p_value, std_err = linregress(years, log_pop)

    annual_rate  = np.exp(slope) - 1
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    print(f"  Annual growth rate   : {annual_rate * 100:.3f}%")
    print(f"  R² of log-linear fit : {r_value ** 2:.4f}")

    if r_value ** 2 < 0.85:
        print("  ⚠ R² < 0.85 — population trend not consistently exponential")
    if p_value > 0.05:
        print("  ⚠ p-value > 0.05 — trend may not be statistically real")

    return monthly_rate, annual_rate, r_value ** 2, std_err, slope


# ═══════════════════════════════════════════════════════════════════════
# STEP 10 — SATURATION DATE FINDER
# ═══════════════════════════════════════════════════════════════════════

def build_probe_row(area_id, predictor_val, peak_month,
                    capacity, feature_set, is_log,
                    all_area_ids, features):
    """
    Builds a single-row DataFrame for prediction for a specific area.

    One-hot dummy columns are set correctly:
        - reference area (first sorted ID): all dummies = 0
        - any other area: its dummy column = 1, all others = 0

    capacity is log-transformed for linear models, raw for tree models.
    """
    sorted_ids   = sorted(all_area_ids)
    reference_id = sorted_ids[0]
    cap_val      = np.log(capacity) if is_log else capacity

    # Base row
    if feature_set == "year":
        row = {
            "year":      predictor_val,
            "month_sin": np.sin(2 * np.pi * peak_month / 12),
            "month_cos": np.cos(2 * np.pi * peak_month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }
    else:
        pred_col = "log_population" if is_log else "population"
        row = {
            pred_col:    predictor_val,
            "month_sin": np.sin(2 * np.pi * peak_month / 12),
            "month_cos": np.cos(2 * np.pi * peak_month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }

    # Set all area dummies to 0
    for aid in sorted_ids[1:]:
        row[f"area_id_{aid}"] = 0

    # Set this area's dummy to 1 (unless it's the reference area)
    if area_id != reference_id:
        col_name = f"area_id_{area_id}"
        if col_name in features:
            row[col_name] = 1

    return pd.DataFrame([row], columns=features)


def find_peak_month(best_pipeline, features, feature_set,
                    is_log, smearing_factor,
                    area_id, area_df, capacity, all_area_ids):
    """
    Sweeps all 12 months at a reference predictor value and returns
    which month produces the highest predicted demand for this area.
    """
    if feature_set == "year":
        ref_val = float(area_df["year"].median())
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
                              area_id, area_df, capacity, all_area_ids):
    """
    Finds saturation date for one area using the combined model.
    Each area uses its own capacity as the threshold.

    Year-based  → sweeps future years until demand >= capacity
    Pop-based   → uses brentq to find the exact population at capacity,
                  then converts to date using growth rate
    """
    print(f"\n  ── Area {area_id} ──────────────────────────────────────")

    peak_month = find_peak_month(
        best_pipeline, features, feature_set, is_log,
        smearing_factor, area_id, area_df, capacity, all_area_ids
    )
    print(f"  Peak demand month : {peak_month}")

    # ── Year-based ────────────────────────────────────────────────────
    if feature_set == "year":
        current_year    = int(area_df["year"].max())
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

    # ── Population-based ──────────────────────────────────────────────
    else:
        monthly_rate, _, _, slope_std_err, _ = estimate_growth_rate(area_df)
        P0 = area_df["population"].iloc[-1]

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
            return {"year": None, "month": None,
                    "peak_month": peak_month,
                    "warning": "already_exceeded"}

        # Expand upper bound until root is bracketed
        P_high = P0 * 2
        for _ in range(20):
            if water_minus_capacity(P_high) > 0:
                break
            P_high *= 2
        else:
            print("  ⚠ Capacity not reached within reasonable population range")
            return {"year": None, "month": None, "peak_month": peak_month}

        pop_max = brentq(water_minus_capacity, P0, P_high, xtol=1.0)

        # Convert population to date — 3 scenarios for uncertainty
        scenarios = {}
        for label, rate_adj in [("pessimistic", -slope_std_err),
                                 ("expected",     0),
                                 ("optimistic",  +slope_std_err)]:
            adj_annual  = np.exp(slope_std_err * rate_adj
                                 + np.log(1 + monthly_rate * 12)) - 1
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
# STEP 11 — FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════

def print_feature_importance(best_name, best_pipeline, features):
    """
    Tree models expose feature_importances_ — prints a ranked bar chart.
    If total_capacity or area dummies dominate over year/population,
    the model is learning infrastructure differences more than demand trends.
    """
    if best_name not in TREE_MODELS:
        return

    print(f"\n── Feature importance ({best_name}) ────────────────────────")
    importances = best_pipeline.named_steps["model"].feature_importances_

    for feat, imp in sorted(zip(features, importances), key=lambda x: -x[1]):
        bar = "█" * int(imp * 40)
        print(f"  {feat:<28} {imp:.4f}  {bar}")


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
                        Must NOT be pre-sorted — sorting is done here.
    area_capacities   : dict {area_id: total_capacity}
    requested_area_id : int — the area from the POST request

    Returns
    -------
    dict with:
        best_model                  : winning model name
        cv_r2_mean / cv_r2_std      : cross-validation scores
        final_r2 / final_mae        : holdout test scores
        requested_area_saturation   : saturation result for requested area
        all_areas_saturation        : saturation for every area
        at_risk_areas               : areas saturating within 10 years, sorted
    """
    print(f"\n{'═' * 60}")
    print(f"  WATER DEMAND FORECAST — Combined Model")
    print(f"  Requested area : {requested_area_id}")
    print(f"{'═' * 60}")

    # ── 1. Validate ───────────────────────────────────────────────────
    validate_inputs(df)

    # ── 2. Feature engineering + time sort ───────────────────────────
    # original_df keeps area_id as integer for saturation calculations
    # df gets one-hot encoded and is used for all ML steps
    original_df = df.copy()
    original_df = original_df.sort_values(
        ["year", "month", "area_id"]
    ).reset_index(drop=True)

    df          = engineer_features(df)
    all_area_ids = sorted(original_df["area_id"].unique().tolist())

    print(f"  Areas in model : {all_area_ids}")

    # ── 3. CV splitter ────────────────────────────────────────────────
    # n_splits capped so each fold has at least 6 rows
    # gap=1 leaves one time slice between train and test to avoid
    # leakage from autocorrelated consecutive months
    n_splits = min(5, len(df) // 6)
    cv       = TimeSeriesSplit(n_splits=n_splits, gap=1)
    print(f"  CV splits      : {n_splits}")

    # ── 4. Select feature set ─────────────────────────────────────────
    feature_set = select_feature_set(df, cv)

    # ── 5. Validate CV folds — confirm all areas in every fold ────────
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]
    probe_features  = (["year", "month_sin", "month_cos", "log_capacity"]
                       + area_dummy_cols)
    validate_cv_folds(df, cv, probe_features)

    # ── 6. Model race ─────────────────────────────────────────────────
    race_results, best_name = run_model_race(df, feature_set, cv)
    best_info               = race_results[best_name]

    # ── 7. Tune best model ────────────────────────────────────────────
    best_pipeline = tune_best_model(best_name, best_info, df, cv)

    # ── 8. Final evaluation ───────────────────────────────────────────
    smearing_factor, final_r2, final_mae = evaluate_final_model(
        best_pipeline, best_info, df
    )

    # Refit on ALL data after evaluation so saturation predictions
    # use the maximum available information
    best_pipeline.fit(df[best_info["features"]], best_info["target"])

    # ── 9. Feature importance ─────────────────────────────────────────
    print_feature_importance(best_name, best_pipeline, best_info["features"])

    # ── 10. Save model ────────────────────────────────────────────────
    joblib.dump(best_pipeline, MODEL_PATH)
    joblib.dump({
        "features":        best_info["features"],
        "feature_set":     feature_set,
        "is_log":          best_info["is_log"],
        "smearing_factor": smearing_factor,
        "all_area_ids":    all_area_ids,
        "best_name":       best_name,
    }, METADATA_PATH)
    print(f"\n✓ Model saved → {MODEL_PATH}")

    # ── 11. Per-area saturation ───────────────────────────────────────
    print(f"\n── Saturation analysis (all areas) ────────────────────────")

    all_areas_saturation  = {}
    requested_area_result = None

    for area_id in all_area_ids:
        # Use original_df (not one-hot encoded) for per-area stats
        # like population growth rate and reference year
        area_df  = original_df[original_df["area_id"] == area_id].copy()
        capacity = area_capacities.get(area_id, 0)

        if capacity <= 0:
            print(f"  ⚠ Area {area_id} has no capacity — skipping")
            continue

        sat = find_saturation_for_area(
            best_pipeline, best_info["features"], feature_set,
            best_info["is_log"], smearing_factor,
            area_id, area_df, capacity, all_area_ids
        )
        all_areas_saturation[str(area_id)] = sat

        if area_id == requested_area_id:
            requested_area_result = sat

    # ── 12. Rank by urgency ───────────────────────────────────────────
    def saturation_sort_key(item):
        sat = item[1]
        if feature_set == "year":
            return sat.get("year") or 9999
        else:
            expected = sat.get("scenarios", {}).get("expected", {})
            return expected.get("year") or 9999

    sorted_areas  = sorted(all_areas_saturation.items(),
                           key=saturation_sort_key)

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

    # ── 13. Summary ───────────────────────────────────────────────────
    print(f"\n── Summary ─────────────────────────────────────────────────")
    print(f"  Best model     : {best_name}")
    print(f"  Feature set    : {feature_set}-based")
    print(f"  CV R²          : {race_results[best_name]['mean_r2']:.4f} "
          f"± {race_results[best_name]['std_r2']:.4f}")
    print(f"  Final R²       : {final_r2:.4f}")
    print(f"  Final MAE      : {final_mae:.2f}")
    print(f"  Requested area ({requested_area_id}) : {requested_area_result}")
    print(f"{'═' * 60}\n")

    return {
        "best_model":                best_name,
        "feature_set":               feature_set,
        "cv_r2_mean":                round(race_results[best_name]["mean_r2"], 4),
        "cv_r2_std":                 round(race_results[best_name]["std_r2"],  4),
        "final_r2":                  round(final_r2,  4),
        "final_mae":                 round(final_mae, 2),
        "smearing_factor":           smearing_factor,
        "requested_area_id":         requested_area_id,
        "requested_area_saturation": requested_area_result,
        "all_areas_saturation":      dict(sorted_areas),
        "at_risk_areas":             at_risk_areas,
    }