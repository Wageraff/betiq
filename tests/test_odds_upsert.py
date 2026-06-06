from decimal import Decimal

from src.api_clients.odds import MOVEMENT_THRESHOLD_PCT, SIGNIFICANT_THRESHOLD_PCT


def test_movement_thresholds():
    assert MOVEMENT_THRESHOLD_PCT == 5.0
    assert SIGNIFICANT_THRESHOLD_PCT == 10.0


def test_movement_calc():
    old = 2.0
    new = 1.87
    movement = (new - old) / old * 100
    assert movement < -5
    assert abs(movement) < 10 or round(movement, 1) == -6.5
