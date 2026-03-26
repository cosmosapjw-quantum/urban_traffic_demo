def ema_update(old_value: float, observed_value: float, rate: float) -> float:
    if not (0.0 <= rate <= 1.0):
        raise ValueError("EMA rate must be in [0,1].")
    return (1.0 - rate) * old_value + rate * observed_value
