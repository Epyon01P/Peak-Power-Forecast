"""Tests for end-of-quarter projection and blend (no high-water-mark floor)."""

from custom_components.peak_power_forecast.forecast import (
    compute_final,
    compute_projected,
    detect_reset,
)


def test_projected_without_prior_matches_current_when_flat() -> None:
    """No prior sample => zero slope => projection is current average (capped)."""
    projected = compute_projected(
        current_value=2.0,
        previous_quarter_final=5.0,
        current_quarter_max=8.0,
        minutes_elapsed=10.0,
    )
    assert projected == 2.0
    assert projected < 8.0


def test_projected_with_rising_trend() -> None:
    """Linear trend extends current average toward quarter end."""
    projected = compute_projected(
        current_value=2.0,
        previous_quarter_final=5.0,
        current_quarter_max=8.0,
        minutes_elapsed=10.0,
        prior_minutes=5.0,
        prior_value=1.0,
    )
    # slope = (2-1)/(10-5) = 0.2 kW/min, remaining 5 min -> +1.0 kW
    assert projected == 3.0


def test_projected_at_quarter_end_is_current_value() -> None:
    assert (
        compute_projected(
            current_value=3.5,
            previous_quarter_final=10.0,
            current_quarter_max=12.0,
            minutes_elapsed=15.0,
        )
        == 3.5
    )


def test_final_can_decrease_below_quarter_max_with_confidence() -> None:
    """Blend toward a lower projection must be allowed below current_quarter_max."""
    projected = compute_projected(
        current_value=2.0,
        previous_quarter_final=6.0,
        current_quarter_max=9.0,
        minutes_elapsed=10.0,
    )
    final = compute_final(
        stale=False,
        minutes_elapsed=10.0,
        confidence_ramp_minutes=5.0,
        current_value=2.0,
        previous_quarter_final=6.0,
        current_quarter_max=9.0,
        projected=projected,
        last_good_prediction=9.0,
    )
    assert final < 9.0
    assert final < 6.0


def test_stale_does_not_pin_to_previous_quarter() -> None:
    """Stale path must not max() with previous_quarter_final (post-gap plateau bug)."""
    final = compute_final(
        stale=True,
        minutes_elapsed=10.0,
        confidence_ramp_minutes=5.0,
        current_value=0.2,
        previous_quarter_final=5.0,
        current_quarter_max=5.0,
        projected=0.25,
        last_good_prediction=5.0,
    )
    assert final < 5.0
    assert final >= 0.2


def test_detect_reset_requires_hard_drop() -> None:
    assert detect_reset(0.8, 0.7) is False
    assert detect_reset(0.8, 0.3) is False
    assert detect_reset(0.8, 0.05) is True
