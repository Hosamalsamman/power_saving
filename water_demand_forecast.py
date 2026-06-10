"""
Water Demand Forecasting Pipeline
──────────────────────────────────
Combined model for all service areas.
Designed for time-based prediction — train on past, predict future.

MINIMUM DATA REQUIREMENT:
    12 months across all areas for reliable seasonal pattern.
    24 months for reliable time trend + seasonality.
    Current runs will warn if below these thresholds but still execute.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
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

# Thresholds — model runs below these but warns about reliability
MONTHS_FOR_SEASONALITY = 12   # need at least one full cycle
MONTHS_FOR_TREND       = 24   # need two cycles for reliable trend

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
# STEP 1 — DATA QUALITY REPORT
# Warns about reliability without blocking execution
# ═══════════════════════════════════════════════════════════════════════

def data_quality_report(df):
    """
    Checks data sufficiency and prints a clear reliability warning.
    Does NOT raise — the model still runs, but the caller knows
    how much to trust the results.

    Returns a dict of warning flags the frontend can display.
    """
    required_cols = ["year", "month", "total_water", "population",
                     "area_id", "total_capacity"]

    # Hard failures — these break the model entirely
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if (df["total_water"] <= 0).any():
        bad = df[df["total_water"] <= 0][["area_id", "year", "month", "total_water"]]
        raise ValueError(f"total_water has zeros or negatives:\n{bad}")

    if (df["population"] <= 0).any():
        raise ValueError("population has zeros or negatives")

    if (df["total_capacity"] <= 0).any():
        raise ValueError("total_capacity has zeros or negatives")

    if df[required_cols].isna().any().any():
        raise ValueError(f"NaN values:\n{df[required_cols].isna().sum()}")

    # Soft warnings — model runs but results less reliable
    warnings_list = []
    total_rows    = len(df)
    n_areas       = df["area_id"].nunique()
    n_months      = df.groupby(["year", "month"]).ngroups  # unique time slices

    print(f"\n── Data quality report ─────────────────────────────────────")
    print(f"  Total rows     : {total_rows}")
    print(f"  Areas          : {n_areas}")
    print(f"  Unique months  : {n_months}")

    if n_months < MONTHS_FOR_SEASONALITY:
        msg = (f"Only {n_months} months of data — seasonal pattern unreliable. "
               f"Need {MONTHS_FOR_SEASONALITY} for one full cycle.")
        print(f"  ⚠ WARNING: {msg}")
        warnings_list.append({"code": "insufficient_seasonality", "message": msg})

    elif n_months < MONTHS_FOR_TREND:
        msg = (f"{n_months} months of data — seasonal pattern visible but "
               f"time trend is weak. Need {MONTHS_FOR_TREND} for reliable trend.")
        print(f"  ⚠ WARNING: {msg}")
        warnings_list.append({"code": "weak_trend", "message": msg})

    else:
        print(f"  ✓ Sufficient data for reliable forecasting")

    # Check area coverage — are all areas present in all months?
    month_area_coverage = df.groupby(["year", "month"])["area_id"].nunique()
    min_coverage = month_area_coverage.min()
    if min_coverage < n_areas:
        msg = (f"Some months have incomplete area coverage "
               f"(min {min_coverage}/{n_areas} areas in one month).")
        print(f"  ⚠ WARNING: {msg}")
        warnings_list.append({"code": "incomplete_coverage", "message": msg})

    if not warnings_list:
        print(f"  ✓ No data quality issues found")

    return {
        "total_rows":   total_rows,
        "n_areas":      n_areas,
        "n_months":     n_months,
        "warnings":     warnings_list,
        "reliable":     n_months >= MONTHS_FOR_TREND,
    }


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════

def engineer_features(df):
    """
    Adds derived columns and one-hot encodes area_id.

    Sorting by [year, month, area_id] ensures every time slice
    groups together — TimeSeriesSplit then cuts across time,
    not across areas. Every fold sees all areas.
    """
    df = df.copy()
    df = df.sort_values(["year", "month", "area_id"]).reset_index(drop=True)

    df["month_sin"]      = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"]      = np.cos(2 * np.pi * df["month"] / 12)
    df["log_population"] = np.log(df["population"])
    df["log_water"]      = np.log(df["total_water"])
    df["log_capacity"]   = np.log(df["total_capacity"])

    # One-hot encode area_id
    # drop_first=True: N-1 dummies fully represent N areas,
    # avoids multicollinearity with the intercept
    df = pd.get_dummies(df, columns=["area_id"], drop_first=True)

    return df


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — CV FOLD VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def validate_cv_folds(df, cv, features):
    """
    Confirms every fold contains multiple areas.
    After time-sort, each fold should have all areas in both
    train and test sets.
    """
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    print(f"\n── CV fold validation ──────────────────────────────────────")
    print(f"  {'Fold':<6} {'Train rows':>11} {'Train areas':>12} "
          f"{'Test rows':>10} {'Test areas':>11}")
    print("  " + "─" * 55)

    for i, (train_idx, test_idx) in enumerate(cv.split(df[features])):
        train_df = df.iloc[train_idx]
        test_df  = df.iloc[test_idx]

        if area_dummy_cols:
            n_train_areas = len(train_df[area_dummy_cols].drop_duplicates())
            n_test_areas  = len(test_df[area_dummy_cols].drop_duplicates())
        else:
            n_train_areas = n_test_areas = "?"

        print(f"  Fold {i + 1:<2}  "
              f"{len(train_idx):>10}   "
              f"{str(n_train_areas):>11}   "
              f"{len(test_idx):>9}   "
              f"{str(n_test_areas):>10}")

        if isinstance(n_test_areas, int) and n_test_areas < 2:
            print(f"  ⚠ Fold {i + 1}: test set has < 2 areas — "
                  f"consider reducing n_splits")


# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — FEATURE SET SELECTION (year vs population)
# ═══════════════════════════════════════════════════════════════════════

def select_feature_set(df, cv):
    """
    Compares year-based vs population-based features using
    LinearRegression as a neutral referee.
    Ties go to year — simpler extrapolation, no growth rate needed.
    """
    print("\n── Feature set selection ──────────────────────────────────")

    corr          = df[["year", "population", "log_population", "log_water"]].corr()
    year_pop_corr = abs(corr.loc["year", "population"])
    print(f"  year ↔ population correlation : {year_pop_corr:.3f}")
    if year_pop_corr > 0.90:
        print("  → High collinearity confirmed — correct to use only one.")

    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]

    candidates = {
        "year":       ["year",           "month_sin", "month_cos",
                       "log_capacity"]   + area_dummy_cols,
        "population": ["log_population", "month_sin", "month_cos",
                       "log_capacity"]   + area_dummy_cols,
    }

    scores = {}
    for label, feats in candidates.items():
        pipe   = Pipeline([("scaler", StandardScaler()),
                           ("model",  LinearRegression())])
        s      = cross_val_score(pipe, df[feats], df["log_water"],
                                 cv=cv, scoring="r2")
        scores[label] = s.mean()
        print(f"\n  {label}-based  →  CV R² = {s.mean():.4f} ± {s.std():.4f}")

    winner = max(scores, key=scores.get)
    margin = abs(scores["year"] - scores["population"])

    print(f"\n✓ Selected : {winner}-based", end="")
    if margin < 0.02:
        print(f"  (margin {margin:.4f} — year preferred for simpler extrapolation)")
        winner = "year"
    else:
        print(f"  (margin = {margin:.4f})")

    return winner


# ═══════════════════════════════════════════════════════════════════════
# STEP 5 — PIPELINE FACTORY
# ═══════════════════════════════════════════════════════════════════════

def make_pipeline(name, model, feature_set, df):
    """
    Each model type gets the right preprocessing:
        Linear → StandardScaler + log-space features + log target
        Tree   → no scaler (scale-invariant) + raw features + raw target
        SVR    → StandardScaler + raw features + raw target
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
        return (Pipeline([("scaler", StandardScaler()), ("model", model)]),
                features_linear, df["log_water"], True)

    elif name in TREE_MODELS:
        return (Pipeline([("model", model)]),
                features_tree, df["total_water"], False)

    else:  # SVR
        return (Pipeline([("scaler", StandardScaler()), ("model", model)]),
                features_tree, df["total_water"], False)


# ═══════════════════════════════════════════════════════════════════════
# STEP 6 — AUTOML RACE
# ═══════════════════════════════════════════════════════════════════════

def run_model_race(df, feature_set, cv):
    print("\n── Model race ─────────────────────────────────────────────")
    print(f"  {'Model':<22} {'Mean R²':>8} {'Std R²':>8} {'Space':>8}")
    print("  " + "─" * 52)

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

        print(f"  {name:<22} {scores.mean():>8.4f} {scores.std():>8.4f} "
              f"{'log' if is_log else 'raw':>8}")

    best_name = max(results, key=lambda k: results[k]["mean_r2"])
    print(f"\n✓ Best model: {best_name}  "
          f"R²={results[best_name]['mean_r2']:.4f} ± {results[best_name]['std_r2']:.4f}")

    return results, best_name


# ═══════════════════════════════════════════════════════════════════════
# STEP 7 — HYPERPARAMETER TUNING
# ═══════════════════════════════════════════════════════════════════════

def tune_best_model(best_name, best_info, df, cv):
    if best_name not in PARAM_GRIDS:
        print(f"\n── Tuning: {best_name} has no hyperparameters — skipping")
        return best_info["pipeline"]

    print(f"\n── Tuning {best_name} ──────────────────────────────────────")
    gs = GridSearchCV(best_info["pipeline"], PARAM_GRIDS[best_name],
                      cv=cv, scoring="r2", n_jobs=-1, refit=True)
    gs.fit(df[best_info["features"]], best_info["target"])

    print(f"  Best params : {gs.best_params_}")
    print(f"  Tuned R²    : {gs.best_score_:.4f}  (was {best_info['mean_r2']:.4f})")

    return gs.best_estimator_


# ═══════════════════════════════════════════════════════════════════════
# STEP 8 — FINAL EVALUATION
# ═══════════════════════════════════════════════════════════════════════

def evaluate_final_model(best_pipeline, best_info, df):
    """
    80/20 time-ordered holdout.
    df sorted by [year, month, area_id] so split cuts across time —
    train = early months ALL areas, test = recent months ALL areas.
    """
    features  = best_info["features"]
    is_log    = best_info["is_log"]
    split_idx = int(len(df) * 0.8)

    area_dummies     = [c for c in features if c.startswith("area_id_")]
    n_train_areas    = (len(df.iloc[:split_idx][area_dummies].drop_duplicates())
                        if area_dummies else "?")
    n_test_areas     = (len(df.iloc[split_idx:][area_dummies].drop_duplicates())
                        if area_dummies else "?")

    print(f"\n── Final evaluation ────────────────────────────────────────")
    print(f"  Train : {split_idx} rows / {n_train_areas} areas  (early months)")
    print(f"  Test  : {len(df) - split_idx} rows / {n_test_areas} areas  (recent months)")

    X_train = df[features].iloc[:split_idx]
    X_test  = df[features].iloc[split_idx:]

    if is_log:
        y_train         = df["log_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]
    else:
        y_train         = df["total_water"].iloc[:split_idx]
        y_test_original = df["total_water"].iloc[split_idx:]

    best_pipeline.fit(X_train, y_train)

    if is_log:
        residuals       = y_train - best_pipeline.predict(X_train)
        smearing_factor = np.mean(np.exp(residuals))
        y_pred          = np.exp(best_pipeline.predict(X_test)) * smearing_factor
    else:
        smearing_factor = 1.0
        y_pred          = best_pipeline.predict(X_test)

    r2  = r2_score(y_test_original, y_pred)
    mae = mean_absolute_error(y_test_original, y_pred)

    print(f"  R²  : {r2:.4f}  (NOTE: measures cross-area variance, not trend accuracy)")
    print(f"  MAE : {mae:.2f}")
    print(f"  Smearing factor : {smearing_factor:.4f}")

    return smearing_factor, r2, mae


# ═══════════════════════════════════════════════════════════════════════
# STEP 9 — MEANINGFUL METRICS
# R² alone is misleading — these three directly test saturation reliability
# ═══════════════════════════════════════════════════════════════════════

def build_probe_row(area_id, predictor_val, month, capacity,
                    feature_set, is_log, all_area_ids, features):
    """
    Builds a single-row DataFrame for one area at one point in time.
    Sets one-hot dummies correctly for the given area.
    """
    sorted_ids   = sorted(all_area_ids)
    reference_id = sorted_ids[0]
    cap_val      = np.log(capacity) if is_log else capacity

    if feature_set == "year":
        row = {
            "year":      predictor_val,
            "month_sin": np.sin(2 * np.pi * month / 12),
            "month_cos": np.cos(2 * np.pi * month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }
    else:
        pred_col = "log_population" if is_log else "population"
        row = {
            pred_col:    predictor_val,
            "month_sin": np.sin(2 * np.pi * month / 12),
            "month_cos": np.cos(2 * np.pi * month / 12),
            "log_capacity" if is_log else "total_capacity": cap_val,
        }

    for aid in sorted_ids[1:]:
        row[f"area_id_{aid}"] = 0

    if area_id != reference_id:
        col = f"area_id_{area_id}"
        if col in features:
            row[col] = 1

    return pd.DataFrame([row], columns=features)


def predict_for_row(best_pipeline, features, feature_set, is_log,
                    smearing_factor, area_id, row, capacity, all_area_ids):
    """Predicts water production for one row."""
    val = (float(row["year"]) if feature_set == "year"
           else (np.log(row["population"]) if is_log
                 else row["population"]))
    X   = build_probe_row(area_id, val, int(row["month"]),
                          capacity, feature_set, is_log,
                          all_area_ids, features)
    p   = best_pipeline.predict(X)[0]
    return np.exp(p) * smearing_factor if is_log else p


def evaluate_trend_accuracy(best_pipeline, best_info, original_df,
                             all_area_ids, smearing_factor,
                             feature_set, area_names):
    """
    Checks predicted trend direction vs actual for each area.
    Target > 80% correct — below this, saturation dates are unreliable.
    """
    print("\n── Trend direction accuracy ────────────────────────────────")
    print(f"  {'Area':<40} {'Actual':>11} {'Predicted':>10} {'Match':>6}")
    print("  " + "─" * 72)

    correct = 0
    total   = 0

    for area_id in all_area_ids:
        area_df   = (original_df[original_df["area_id"] == area_id]
                     .sort_values(["year", "month"])
                     .reset_index(drop=True))
        area_name = area_names.get(area_id, str(area_id))
        capacity  = area_df["total_capacity"].iloc[0]

        if len(area_df) < 2:
            continue

        slope, _, _, p_val, _ = linregress(range(len(area_df)),
                                           area_df["total_water"].values)
        actual_dir = "↑ growing" if slope > 0 else "↓ shrinking"

        pred_first = predict_for_row(best_pipeline, best_info["features"],
                                     feature_set, best_info["is_log"],
                                     smearing_factor, area_id,
                                     area_df.iloc[0], capacity, all_area_ids)
        pred_last  = predict_for_row(best_pipeline, best_info["features"],
                                     feature_set, best_info["is_log"],
                                     smearing_factor, area_id,
                                     area_df.iloc[-1], capacity, all_area_ids)
        pred_dir   = "↑ growing" if pred_last > pred_first else "↓ shrinking"

        match    = "✓" if actual_dir == pred_dir else "✗"
        correct += 1 if match == "✓" else 0
        total   += 1
        sig      = "" if p_val < 0.05 else " (weak)"
        print(f"  {area_name:<40} {actual_dir:>11} {pred_dir:>10} {match:>6}{sig}")

    accuracy = correct / total if total > 0 else 0
    print(f"\n  Result : {correct}/{total} = {accuracy:.1%}  "
          f"({'✓ reliable' if accuracy >= 0.8 else '✗ saturation dates unreliable — need more data'})")
    return accuracy


def evaluate_utilization_accuracy(best_pipeline, best_info, original_df,
                                   all_area_ids, smearing_factor,
                                   feature_set, area_names):
    """
    Compares predicted vs actual utilization (water/capacity) per area.
    Scale-independent — errors are relative to each area's own capacity.
    Target < 10%.
    """
    print("\n── Per-area utilization accuracy ───────────────────────────")
    print(f"  {'Area':<40} {'Actual':>10} {'Predicted':>10} {'Error':>8}")
    print("  " + "─" * 72)

    errors = []
    for area_id in all_area_ids:
        area_df   = original_df[original_df["area_id"] == area_id].copy()
        area_name = area_names.get(area_id, str(area_id))
        capacity  = area_df["total_capacity"].iloc[0]

        preds = [predict_for_row(best_pipeline, best_info["features"],
                                 feature_set, best_info["is_log"],
                                 smearing_factor, area_id, row,
                                 capacity, all_area_ids)
                 for _, row in area_df.iterrows()]

        actual_util = area_df["total_water"].mean() / capacity
        pred_util   = np.mean(preds) / capacity
        error       = abs(actual_util - pred_util)
        errors.append(error)

        flag = " ⚠" if error > 0.15 else ""
        print(f"  {area_name:<40} {actual_util:>9.1%} {pred_util:>9.1%} "
              f"{error:>7.1%}{flag}")

    mean_err = np.mean(errors)
    print(f"\n  Result : {mean_err:.1%}  "
          f"({'✓ reliable' if mean_err <= 0.10 else '✗ predictions too far from actual — need more data'})")
    return mean_err


def evaluate_mape(best_pipeline, best_info, original_df,
                  all_area_ids, smearing_factor,
                  feature_set, area_names):
    """
    Holds out last observed month per area, tests prediction accuracy.
    Directly answers: can the model predict next month for this area?
    Target MAPE < 15%.
    """
    print("\n── Last-month holdout MAPE ─────────────────────────────────")
    print(f"  {'Area':<40} {'Actual':>12} {'Predicted':>12} {'Error%':>8}")
    print("  " + "─" * 76)

    actuals = []
    preds   = []

    for area_id in all_area_ids:
        area_df   = (original_df[original_df["area_id"] == area_id]
                     .sort_values(["year", "month"])
                     .reset_index(drop=True))
        area_name = area_names.get(area_id, str(area_id))
        capacity  = area_df["total_capacity"].iloc[0]

        if len(area_df) < 3:
            print(f"  {area_name:<40} — skipped (< 3 rows)")
            continue

        last_row  = area_df.iloc[-1]
        pred      = predict_for_row(best_pipeline, best_info["features"],
                                    feature_set, best_info["is_log"],
                                    smearing_factor, area_id,
                                    last_row, capacity, all_area_ids)
        actual    = last_row["total_water"]
        pct_err   = abs(pred - actual) / actual * 100

        actuals.append(actual)
        preds.append(pred)

        flag = " ⚠" if pct_err > 20 else ""
        print(f"  {area_name:<40} {actual:>12,.0f} {pred:>12,.0f} "
              f"{pct_err:>7.1f}%{flag}")

    if not actuals:
        return 0.0

    mape = np.mean([abs(p - a) / a * 100 for p, a in zip(preds, actuals)])
    print(f"\n  Result : MAPE = {mape:.1f}%  "
          f"({'✓ reliable' if mape <= 15 else '✗ next-month predictions inaccurate — need more data'})")
    return mape


# ═══════════════════════════════════════════════════════════════════════
# STEP 10 — FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════

def print_feature_importance(best_name, best_pipeline, features):
    if best_name not in TREE_MODELS:
        return

    print(f"\n── Feature importance ({best_name}) ────────────────────────")
    importances = best_pipeline.named_steps["model"].feature_importances_
    for feat, imp in sorted(zip(features, importances), key=lambda x: -x[1]):
        print(f"  {feat:<30} {imp:.4f}  {'█' * int(imp * 40)}")


# ═══════════════════════════════════════════════════════════════════════
# STEP 11 — POPULATION GROWTH RATE
# ═══════════════════════════════════════════════════════════════════════

def estimate_growth_rate(area_df):
    """Log-linear fit over all available years. Returns monthly rate."""
    yearly  = area_df.groupby("year")["population"].mean().reset_index()
    years   = yearly["year"].values.astype(float)
    log_pop = np.log(yearly["population"].values)

    if len(years) < 2:
        print("  ⚠ Only one year — assuming zero growth")
        return 0.0, 0.0, 0.0, 0.0, 0.0

    slope, _, r_value, p_value, std_err = linregress(years, log_pop)
    annual_rate  = np.exp(slope) - 1
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

    print(f"  Annual growth : {annual_rate * 100:.3f}%  "
          f"R²={r_value**2:.4f}  p={p_value:.4f}")

    if r_value ** 2 < 0.85:
        print("  ⚠ R² < 0.85 — population trend unreliable")

    return monthly_rate, annual_rate, r_value ** 2, std_err, slope


# ═══════════════════════════════════════════════════════════════════════
# STEP 12 — SATURATION DATE FINDER
# ═══════════════════════════════════════════════════════════════════════

def find_peak_month(best_pipeline, features, feature_set, is_log,
                    smearing_factor, area_id, area_df,
                    capacity, all_area_ids):
    """
    Sweeps only observed months — never extrapolates to unseen months.
    Prevents the model from picking an unseen month as peak.
    """
    ref_val = (float(area_df["year"].median()) if feature_set == "year"
               else (area_df["log_population"].median() if is_log
                     else area_df["population"].median()))

    observed_months = sorted(area_df["month"].unique().tolist())
    monthly_preds   = []

    for m in observed_months:
        X    = build_probe_row(area_id, ref_val, m, capacity,
                               feature_set, is_log, all_area_ids, features)
        pred = best_pipeline.predict(X)[0]
        if is_log:
            pred = np.exp(pred) * smearing_factor
        monthly_preds.append((m, pred))

    return max(monthly_preds, key=lambda x: x[1])[0]


def find_saturation_for_area(best_pipeline, features, feature_set,
                              is_log, smearing_factor,
                              area_id, area_df, capacity,
                              all_area_ids, area_name):
    """
    Finds saturation date for one area.
    Shows current utilization before predicting.
    Year-based: sweeps future years.
    Population-based: brentq root finding + 3 growth scenarios.
    """
    print(f"\n  ── {area_name} (id={area_id})")

    max_obs     = area_df["total_water"].max()
    utilization = max_obs / capacity
    util_str    = f"{utilization:.1%}"

    flag = (" ⚠ EXCEEDING" if utilization >= 1.0
            else " ⚠ CRITICAL" if utilization >= 0.9
            else " ⚠ WARNING"  if utilization >= 0.75
            else "")

    print(f"  Utilization : {util_str}{flag}  "
          f"({max_obs:,.0f} / {capacity:,.0f})")

    peak_month = find_peak_month(best_pipeline, features, feature_set,
                                 is_log, smearing_factor, area_id,
                                 area_df, capacity, all_area_ids)
    print(f"  Peak month  : {peak_month}")

    base_result = {
        "area_name":   area_name,
        "peak_month":  peak_month,
        "utilization": round(utilization, 4),
    }

    # ── Year-based ────────────────────────────────────────────────────
    if feature_set == "year":
        current_year = int(area_df["year"].max())

        for future_year in range(current_year, current_year + 100):
            X    = build_probe_row(area_id, future_year, peak_month, capacity,
                                   feature_set, is_log, all_area_ids, features)
            pred = best_pipeline.predict(X)[0]
            if is_log:
                pred = np.exp(pred) * smearing_factor

            if pred >= capacity:
                print(f"  Saturation  : {future_year}/{peak_month:02d}")
                return {**base_result, "year": future_year, "month": peak_month}

        print("  Saturation  : not reached within 100 years")
        return {**base_result, "year": None, "month": None}

    # ── Population-based ──────────────────────────────────────────────
    else:
        monthly_rate, _, _, slope_std_err, _ = estimate_growth_rate(area_df)
        P0 = area_df["population"].iloc[-1]

        def water_minus_capacity(pop):
            pop_val = np.log(pop) if is_log else pop
            X       = build_probe_row(area_id, pop_val, peak_month, capacity,
                                      feature_set, is_log, all_area_ids, features)
            pred    = best_pipeline.predict(X)[0]
            return (np.exp(pred) * smearing_factor if is_log else pred) - capacity

        if water_minus_capacity(P0) > 0:
            print("  ⚠ Already exceeds capacity at current population")
            return {**base_result, "year": None, "month": None,
                    "warning": "already_exceeded"}

        P_high = P0 * 2
        for _ in range(20):
            if water_minus_capacity(P_high) > 0:
                break
            P_high *= 2
        else:
            print("  Saturation not reached within reasonable population range")
            return {**base_result, "year": None, "month": None}

        pop_max   = brentq(water_minus_capacity, P0, P_high, xtol=1.0)
        scenarios = {}

        for label, adj in [("pessimistic", -slope_std_err),
                            ("expected",    0),
                            ("optimistic",  +slope_std_err)]:
            adj_annual  = np.exp(slope_std_err * adj
                                 + np.log(1 + monthly_rate * 12)) - 1
            adj_monthly = (1 + adj_annual) ** (1 / 12) - 1

            if adj_monthly <= 0:
                scenarios[label] = {"year": None, "month": None}
                continue

            months_diff = np.log(pop_max / P0) / np.log(1 + adj_monthly)
            scenarios[label] = {
                "year":  int(area_df["year"].iloc[-1] + months_diff // 12),
                "month": int((months_diff % 12) + 1),
            }
            print(f"  {label:<14}: {scenarios[label]['year']}/"
                  f"{scenarios[label]['month']:02d}")

        return {**base_result, "pop_max": int(pop_max), "scenarios": scenarios}


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def run_forecast(df, area_capacities, requested_area_id, area_names=None):
    """
    Combined time-based forecast for all service areas.

    Parameters
    ----------
    df                : DataFrame — year, month, total_water, population,
                                    area_id, total_capacity
    area_capacities   : dict {area_id: capacity}
    requested_area_id : int — area from the POST request
    area_names        : dict {area_id: name} — optional

    Returns
    -------
    dict with model info, data quality, evaluation metrics,
    per-area saturation sorted by urgency, and requested area result
    """
    print(f"\n{'═' * 60}")
    print(f"  WATER DEMAND FORECAST — Combined Model")
    print(f"  Requested area : {requested_area_id}")
    print(f"{'═' * 60}")

    # ── 1. Data quality report ────────────────────────────────────────
    quality = data_quality_report(df)

    # ── 2. Area names ─────────────────────────────────────────────────
    all_area_ids_raw = sorted(df["area_id"].unique().tolist())
    if area_names is None:
        area_names = {aid: str(aid) for aid in all_area_ids_raw}

    # ── 3. Feature engineering ────────────────────────────────────────
    original_df  = df.copy()
    original_df  = original_df.sort_values(
        ["year", "month", "area_id"]
    ).reset_index(drop=True)

    df           = engineer_features(df)
    all_area_ids = sorted(original_df["area_id"].unique().tolist())
    print(f"\n  Areas : {all_area_ids}")

    # ── 4. CV splitter ────────────────────────────────────────────────
    # Scale splits to data size — at least 6 rows per fold
    n_splits = min(5, len(df) // 6)
    cv       = TimeSeriesSplit(n_splits=n_splits, gap=1)
    print(f"  CV splits : {n_splits}")

    # ── 5. Feature set selection ──────────────────────────────────────
    feature_set = select_feature_set(df, cv)

    # ── 6. Validate CV folds ──────────────────────────────────────────
    area_dummy_cols = [c for c in df.columns if c.startswith("area_id_")]
    validate_cv_folds(df, cv,
                      ["year", "month_sin", "month_cos", "log_capacity"]
                      + area_dummy_cols)

    # ── 7. Model race ─────────────────────────────────────────────────
    race_results, best_name = run_model_race(df, feature_set, cv)
    best_info               = race_results[best_name]

    # ── 8. Tune best model ────────────────────────────────────────────
    best_pipeline = tune_best_model(best_name, best_info, df, cv)

    # ── 9. Final evaluation ───────────────────────────────────────────
    smearing_factor, final_r2, final_mae = evaluate_final_model(
        best_pipeline, best_info, df
    )

    # Refit on ALL data so predictions use maximum information
    best_pipeline.fit(df[best_info["features"]], best_info["target"])

    # ── 10. Meaningful metrics ────────────────────────────────────────
    trend_acc  = evaluate_trend_accuracy(
        best_pipeline, best_info, original_df,
        all_area_ids, smearing_factor, feature_set, area_names
    )
    util_err   = evaluate_utilization_accuracy(
        best_pipeline, best_info, original_df,
        all_area_ids, smearing_factor, feature_set, area_names
    )
    mape       = evaluate_mape(
        best_pipeline, best_info, original_df,
        all_area_ids, smearing_factor, feature_set, area_names
    )

    # ── 11. Feature importance ────────────────────────────────────────
    print_feature_importance(best_name, best_pipeline, best_info["features"])

    # ── 12. Save model ────────────────────────────────────────────────
    joblib.dump(best_pipeline, MODEL_PATH)
    joblib.dump({
        "features":        best_info["features"],
        "feature_set":     feature_set,
        "is_log":          best_info["is_log"],
        "smearing_factor": smearing_factor,
        "all_area_ids":    all_area_ids,
        "best_name":       best_name,
        "area_names":      area_names,
    }, METADATA_PATH)
    print(f"\n✓ Model saved → {MODEL_PATH}")

    # ── 13. Per-area saturation ───────────────────────────────────────
    print(f"\n── Saturation analysis ─────────────────────────────────────")

    all_areas_saturation  = {}
    requested_area_result = None

    for area_id in all_area_ids:
        area_df   = original_df[original_df["area_id"] == area_id].copy()
        capacity  = area_capacities.get(area_id, 0)
        area_name = area_names.get(area_id, str(area_id))

        if capacity <= 0:
            print(f"  ⚠ Area {area_id} — no capacity data, skipping")
            continue

        sat = find_saturation_for_area(
            best_pipeline, best_info["features"], feature_set,
            best_info["is_log"], smearing_factor,
            area_id, area_df, capacity, all_area_ids, area_name
        )
        all_areas_saturation[str(area_id)] = sat

        if area_id == requested_area_id:
            requested_area_result = sat

    # ── 14. Rank by urgency ───────────────────────────────────────────
    def sort_key(item):
        sat = item[1]
        if feature_set == "year":
            return sat.get("year") or 9999
        return (sat.get("scenarios", {})
                   .get("expected", {})
                   .get("year") or 9999)

    sorted_areas  = sorted(all_areas_saturation.items(), key=sort_key)
    current_year  = int(original_df["year"].max())

    at_risk_areas = [
        {
            "area_id":   aid,
            "area_name": all_areas_saturation[aid].get("area_name", aid),
            "saturation": sat,
        }
        for aid, sat in sorted_areas
        if sort_key((aid, sat)) <= current_year + 10
    ]

    print(f"\n── At-risk areas (within 10 years) ────────────────────────")
    if at_risk_areas:
        for item in at_risk_areas:
            yr = item["saturation"].get("year")
            mo = item["saturation"].get("month")
            print(f"  {item['area_name']:<42} → "
                  f"{yr}/{str(mo).zfill(2) if mo else '??'}")
    else:
        print("  None — all areas safe for 10+ years")

    # ── 15. Summary ───────────────────────────────────────────────────
    print(f"\n── Summary ─────────────────────────────────────────────────")
    print(f"  Best model        : {best_name}")
    print(f"  Feature set       : {feature_set}-based")
    print(f"  CV R²             : {race_results[best_name]['mean_r2']:.4f} "
          f"± {race_results[best_name]['std_r2']:.4f}")
    print(f"  Final R²          : {final_r2:.4f}")
    print(f"  Final MAE         : {final_mae:.2f}")
    print(f"  Trend accuracy    : {trend_acc:.1%}   target >80%")
    print(f"  Utilization error : {util_err:.1%}   target <10%")
    print(f"  MAPE              : {mape:.1f}%   target <15%")
    print(f"  Data reliable     : {'✓ YES' if quality['reliable'] else '✗ NO — ' + str(quality['n_months']) + ' months (need 24)'}")
    print(f"  Requested area    : {requested_area_result}")
    print(f"{'═' * 60}\n")

    return {
        "best_model":                best_name,
        "feature_set":               feature_set,
        "cv_r2_mean":                round(race_results[best_name]["mean_r2"], 4),
        "cv_r2_std":                 round(race_results[best_name]["std_r2"],  4),
        "final_r2":                  round(final_r2,  4),
        "final_mae":                 round(final_mae, 2),
        "smearing_factor":           smearing_factor,
        "trend_accuracy":            round(trend_acc, 4),
        "utilization_error":         round(util_err,  4),
        "mape":                      round(mape, 2),
        "data_quality":              quality,
        "requested_area_id":         requested_area_id,
        "requested_area_saturation": requested_area_result,
        "all_areas_saturation":      dict(sorted_areas),
        "at_risk_areas":             at_risk_areas,
    }