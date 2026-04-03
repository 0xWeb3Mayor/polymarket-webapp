import numpy as np
import config

# Model loaded once at module level — expensive operation
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            import timesfm
            print("Loading TimesFM model (first run may download weights)...")
            _model = timesfm.TimesFm(
                hparams=timesfm.TimesFmHparams(
                    backend="cpu",
                    per_core_batch_size=32,
                    horizon_len=config.FORECAST_HORIZON_HOURS,
                    input_patch_len=32,
                    output_patch_len=128,
                    num_layers=20,
                    model_dims=1280,
                ),
                checkpoint=timesfm.TimesFmCheckpoint(
                    huggingface_repo_id="google/timesfm-1.0-200m-pytorch"
                ),
            )
            print("TimesFM loaded.")
        except Exception as e:
            raise RuntimeError(f"Failed to load TimesFM: {e}")
    return _model


def run_forecast(condition_id: str, price_series: list[float]) -> dict:
    """Run zero-shot TimesFM inference on hourly price series.

    Args:
        condition_id: Market identifier (for logging)
        price_series: List of hourly YES prices (0.0–1.0), most recent last

    Returns:
        dict with forecast_price, ci_80_low, ci_80_high, horizon_hours
    """
    model = _get_model()
    series = np.array(price_series, dtype=np.float32)

    point_forecast, quantile_forecast = model.forecast(
        [series],
        freq=[0],  # 0 = high frequency
    )

    # Use final timestep of horizon (48h out)
    forecast_price = float(np.clip(point_forecast[0, -1], 0.0, 1.0))
    ci_80_low = float(np.clip(quantile_forecast[0, -1, 0], 0.0, 1.0))   # 0.1 quantile
    ci_80_high = float(np.clip(quantile_forecast[0, -1, 8], 0.0, 1.0))  # 0.9 quantile

    return {
        "forecast_price": forecast_price,
        "ci_80_low": ci_80_low,
        "ci_80_high": ci_80_high,
        "horizon_hours": config.FORECAST_HORIZON_HOURS,
    }
