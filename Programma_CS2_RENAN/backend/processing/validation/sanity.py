"""
Sanity Validation Module

Validates statistical plausibility of demo data.

Task 2.19.2: Added automatic outlier trimming as an alternative to
raising errors. When trim_outliers=True, impossible values are clamped
to boundaries instead of causing ingestion failure.
"""

import pandas as pd

from Programma_CS2_RENAN.observability.logger_setup import get_logger

LOGGER_NAME = "cs2analyzer.sanity"
logger = get_logger(LOGGER_NAME)

# Statistical limits for CS2 per-round stats
# Format: {column: (min, max)}
# R4-24-04: KAST is stored as a ratio [0, 1] (e.g., 0.70 = 70%),
# NOT as a percentage [0, 100]. estimate_kast_from_stats() returns ratio.
LIMITS = {
    "kills": (0, 10),
    "deaths": (0, 10),
    "assists": (0, 10),
    "adr": (0.0, 200.0),
    "headshot_pct": (0.0, 100.0),
    "kast": (0.0, 1.0),
}


def validate_demo_sanity(df: pd.DataFrame) -> None:
    """
    Validates statistical plausibility of demo data (strict mode).
    Raises ValueError if any value is outside limits.

    NOTE: Does NOT modify the input DataFrame. All checks are read-only.
    Use `validate_and_trim()` for a copy-based trim workflow.
    """
    logger.info("Sanity validation started (strict mode)")
    for column, limits in LIMITS.items():
        _check_column_limits(df, column, limits)
    logger.info("Sanity validation passed")


def validate_and_trim(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """
    Validate match data with optional outlier trimming.

    Task 2.19.2: Instead of failing on impossible values,
    this function can clamp them to valid boundaries.

    Args:
        df: DataFrame with match statistics
        strict: If True, raises ValueError on invalid data (original behavior).
                If False, clamps outliers to LIMITS boundaries.

    Returns:
        pd.DataFrame: Validated (and optionally trimmed) DataFrame

    Raises:
        ValueError: Only if strict=True and invalid data found
    """
    if strict:
        # Original behavior - raise on invalid
        validate_demo_sanity(df)
        return df

    # New behavior - clamp outliers to limits
    logger.info("Sanity validation started (trim mode)")

    trimmed_columns = []
    df_trimmed = df.copy()

    # P-SAN-01: Detect KAST stored as percentage (>1.0) and convert to ratio.
    if "kast" in df_trimmed.columns:
        pct_mask = df_trimmed["kast"] > 1.0
        if pct_mask.any():
            logger.warning(
                "P-SAN-01: %d KAST values > 1.0 detected — converting percentage to ratio",
                pct_mask.sum(),
            )
            df_trimmed.loc[pct_mask, "kast"] = df_trimmed.loc[pct_mask, "kast"] / 100.0

    for column, (min_val, max_val) in LIMITS.items():
        if column not in df_trimmed.columns:
            continue

        # Count outliers before clamping
        below_min = (df_trimmed[column] < min_val).sum()
        above_max = (df_trimmed[column] > max_val).sum()

        if below_min > 0 or above_max > 0:
            trimmed_columns.append(column)
            logger.warning(
                f"Trimming outliers in '{column}': "
                f"{below_min} below {min_val}, {above_max} above {max_val}"
            )

        # Clamp values to limits
        df_trimmed[column] = df_trimmed[column].clip(lower=min_val, upper=max_val)

    if trimmed_columns:
        logger.info("Sanity validation complete. Trimmed columns: %s", trimmed_columns)
    else:
        logger.info("Sanity validation passed (no outliers found)")

    return df_trimmed


def _check_column_limits(df: pd.DataFrame, column: str, limits: tuple) -> None:
    """Check if column values are within limits."""
    if column not in df.columns:
        return

    min_v, max_v = limits
    if not df[column].between(min_v, max_v).all():
        bad = df[~df[column].between(min_v, max_v)][[column]]
        if "round" in df.columns:
            bad = df[~df[column].between(min_v, max_v)][["round", column]]
        _raise_sanity_error(column, bad)


def _raise_sanity_error(col: str, bad_rows: pd.DataFrame) -> None:
    """Log error and raise ValueError for sanity failures."""
    logger.error("Sanity check failed for '%s'", col)
    raise ValueError(f"Invalid values in '{col}':\n{bad_rows}")
