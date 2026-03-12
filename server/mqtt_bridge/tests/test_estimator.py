import math
import pytest
from mqtt_bridge.estimator import haversine, rssi_to_distance, weighted_centroid


def test_haversine_same_point_is_zero():
    assert haversine(38.0, -122.0, 38.0, -122.0) == pytest.approx(0.0)


def test_haversine_known_distance():
    # Approx 1 degree of latitude ≈ 111,195 m
    d = haversine(0.0, 0.0, 1.0, 0.0)
    assert 111_000 < d < 112_000


def test_rssi_to_distance_at_minus59_is_1m():
    # At reference RSSI (-59 dBm at 1m), distance should be ≈ 1m
    d = rssi_to_distance(-59)
    assert d == pytest.approx(1.0, rel=0.01)


def test_rssi_to_distance_weaker_signal_is_farther():
    assert rssi_to_distance(-80) > rssi_to_distance(-60)


def test_weighted_centroid_single_node():
    nodes = [(38.0, -122.0, -60)]
    lat, lon = weighted_centroid(nodes)
    assert lat == pytest.approx(38.0)
    assert lon == pytest.approx(-122.0)


def test_weighted_centroid_equal_rssi_is_midpoint():
    # Two nodes at equal RSSI → midpoint
    nodes = [(38.0, -122.0, -60), (38.2, -122.0, -60)]
    lat, lon = weighted_centroid(nodes)
    assert lat == pytest.approx(38.1, rel=0.001)
    assert lon == pytest.approx(-122.0, rel=0.001)


def test_weighted_centroid_stronger_rssi_pulls_toward_closer_node():
    # Node A is strong (-50), node B is weak (-80) → estimate closer to A
    nodes = [(38.0, -122.0, -50), (38.4, -122.0, -80)]
    lat, lon = weighted_centroid(nodes)
    assert lat < 38.2  # pulled toward A (38.0)
