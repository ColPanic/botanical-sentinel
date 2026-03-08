import json

from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi


def test_extract_node_id_scan_topic():
    assert extract_node_id("nodes/scanner-01/scan/wifi") == "scanner-01"


def test_extract_node_id_status_topic():
    assert extract_node_id("nodes/pi-cam-gate/status") == "pi-cam-gate"


def test_parse_wifi_basic():
    payload = json.dumps([
        {"ssid": "MyNet", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -45, "channel": 6}
    ]).encode()
    events = parse_wifi("scanner-01", payload)
    assert len(events) == 1
    assert events[0].mac == "AA:BB:CC:DD:EE:FF"
    assert events[0].rssi == -45
    assert events[0].ssid == "MyNet"
    assert events[0].scan_type == "wifi"
    assert events[0].node_id == "scanner-01"


def test_parse_wifi_empty_ssid_becomes_none():
    payload = json.dumps([
        {"ssid": "", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -80, "channel": 1}
    ]).encode()
    events = parse_wifi("scanner-01", payload)
    assert events[0].ssid is None


def test_parse_wifi_skips_empty_bssid():
    payload = json.dumps([
        {"ssid": "x", "bssid": "", "rssi": -50, "channel": 6}
    ]).encode()
    assert parse_wifi("scanner-01", payload) == []


def test_parse_wifi_empty_list():
    assert parse_wifi("scanner-01", b"[]") == []


def test_parse_ble_basic():
    payload = json.dumps([
        {"mac": "7a:3f:cc:dd:ee:ff", "name": "iPhone", "rssi": -61}
    ]).encode()
    events = parse_ble("scanner-01", payload)
    assert len(events) == 1
    assert events[0].mac == "7A:3F:CC:DD:EE:FF"
    assert events[0].rssi == -61
    assert events[0].scan_type == "ble"
    assert events[0].ssid is None


def test_parse_ble_skips_empty_mac():
    payload = json.dumps([
        {"mac": "", "name": "x", "rssi": -50}
    ]).encode()
    assert parse_ble("scanner-01", payload) == []


def test_parse_ble_empty_list():
    assert parse_ble("scanner-01", b"[]") == []
