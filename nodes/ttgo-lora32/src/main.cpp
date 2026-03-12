#include <Arduino.h>
#include <ArduinoJson.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <PubSubClient.h>
#include <TinyGPSPlus.h>
#include <Wire.h>
#include <axp20x.h>
#ifdef HAS_OLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#endif
#include <WiFi.h>
#include <WiFiClient.h>

#include "config.h"

// ── Constants ─────────────────────────────────────────────────────────────────

static constexpr uint32_t SCAN_INTERVAL_MS    = 30000;
static constexpr uint32_t DISPLAY_INTERVAL_MS = 5000;
static constexpr uint8_t  MAX_WIFI            = 20;
static constexpr uint8_t  MAX_BLE             = 20;

// ── Types ─────────────────────────────────────────────────────────────────────

struct WifiResult {
    char    ssid[33];   // 32 chars + null terminator
    uint8_t bssid[6];
    int32_t rssi;
    uint8_t channel;
};

struct BleResult {
    char    name[32];
    char    mac[18];    // "AA:BB:CC:DD:EE:FF\0"
    int32_t rssi;
};

// ── State ─────────────────────────────────────────────────────────────────────

static AXP20X_Class axp;

#ifdef HAS_OLED
static Adafruit_SSD1306 oled(128, 64, &Wire, DISP_RST);
#endif

static TinyGPSPlus gps;

static WifiResult wifiResults[MAX_WIFI];
static uint8_t    wifiCount  = 0;
static uint32_t   scanCount  = 0;
static BleResult  bleResults[MAX_BLE];
static uint8_t    bleCount   = 0;

// ── MQTT ──────────────────────────────────────────────────────────────────────

static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);

static char topicWifi[64];
static char topicBle[64];
static char topicStatus[64];
static char mqttBuf[4096];

// ── AXP192 PMIC ───────────────────────────────────────────────────────────────

static void initAXP192() {
    if (axp.begin(Wire, AXP192_SLAVE_ADDRESS) != AXP_PASS) {
        Serial.println("[AXP] Init failed — PMIC not responding at 0x34");
        return;
    }
    axp.setLDO2Voltage(3300);                        // LoRa module (SX1276)
    axp.setPowerOutPut(AXP192_LDO2, AXP202_ON);
    axp.setLDO3Voltage(3300);                        // GPS (u-blox NEO-M8N)
    axp.setPowerOutPut(AXP192_LDO3, AXP202_ON);
    Serial.printf("[AXP] PMIC OK — Batt: %.2f V\n", axp.getBattVoltage() / 1000.0f);
}

// ── Battery ───────────────────────────────────────────────────────────────────

static float readBatteryVolts() {
    return axp.getBattVoltage() / 1000.0f;
}

static uint8_t voltageToPercent(float v) {
    if (v >= 4.2f) return 100;
    if (v <= 3.0f) return 0;
    return static_cast<uint8_t>((v - 3.0f) / 1.2f * 100.0f);
}

// ── Connectivity ──────────────────────────────────────────────────────────────

static void connectWifi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    for (uint8_t attempts = 0;
         WiFi.status() != WL_CONNECTED && attempts < 20;
         attempts++) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected. IP: %s\n",
            WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WiFi] Failed — will retry next cycle");
    }
}

static void connectMqtt() {
    if (mqtt.connected()) return;

    Serial.printf("[MQTT] Connecting to %s:%d as %s\n",
        MQTT_HOST, MQTT_PORT, NODE_ID);

    if (mqtt.connect(NODE_ID)) {
        Serial.println("[MQTT] Connected");
    } else {
        Serial.printf("[MQTT] Failed, state=%d\n", mqtt.state());
    }
}

// ── WiFi scan ─────────────────────────────────────────────────────────────────

static void scanWifi() {
    int found = WiFi.scanNetworks(/*async=*/false, /*show_hidden=*/true);
    if (found < 0) found = 0;

    wifiCount = static_cast<uint8_t>(found > MAX_WIFI ? MAX_WIFI : found);

    for (uint8_t i = 0; i < wifiCount; i++) {
        String ssid = WiFi.SSID(i);
        strncpy(wifiResults[i].ssid, ssid.c_str(), 32);
        wifiResults[i].ssid[32] = '\0';
        const uint8_t* bssid = WiFi.BSSID(i);
        if (bssid != nullptr) {
            memcpy(wifiResults[i].bssid, bssid, 6);
        } else {
            memset(wifiResults[i].bssid, 0, 6);
        }
        wifiResults[i].rssi    = WiFi.RSSI(i);
        wifiResults[i].channel = static_cast<uint8_t>(WiFi.channel(i));
    }

    WiFi.scanDelete();

    Serial.printf("[WiFi] %u networks\n", wifiCount);
}

// ── BLE scan ──────────────────────────────────────────────────────────────────

static void scanBle() {
    BLEScan* pScan = BLEDevice::getScan();
    if (pScan == nullptr) {
        Serial.println("[BLE] getScan() returned null — skipping");
        bleCount = 0;
        return;
    }

    pScan->setActiveScan(false);
    pScan->setInterval(100);
    pScan->setWindow(99);

    BLEScanResults results = pScan->start(/*seconds=*/5, /*is_continue=*/false);
    int found = results.getCount();

    bleCount = static_cast<uint8_t>(found > MAX_BLE ? MAX_BLE : found);

    for (uint8_t i = 0; i < bleCount; i++) {
        BLEAdvertisedDevice dev = results.getDevice(i);

        strncpy(bleResults[i].name, dev.getName().c_str(), 31);
        bleResults[i].name[31] = '\0';

        strncpy(bleResults[i].mac, dev.getAddress().toString().c_str(), 17);
        bleResults[i].mac[17] = '\0';

        bleResults[i].rssi = dev.getRSSI();
    }

    pScan->clearResults();

    Serial.printf("[BLE] %u devices\n", bleCount);
}

// ── MQTT publish ──────────────────────────────────────────────────────────────

static void publishWifi() {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();

    for (uint8_t i = 0; i < wifiCount; i++) {
        JsonObject obj = arr.add<JsonObject>();
        obj["ssid"] = wifiResults[i].ssid;

        char bssid[18];
        snprintf(bssid, sizeof(bssid),
            "%02X:%02X:%02X:%02X:%02X:%02X",
            wifiResults[i].bssid[0], wifiResults[i].bssid[1],
            wifiResults[i].bssid[2], wifiResults[i].bssid[3],
            wifiResults[i].bssid[4], wifiResults[i].bssid[5]);
        obj["bssid"]   = bssid;
        obj["rssi"]    = wifiResults[i].rssi;
        obj["channel"] = wifiResults[i].channel;
    }

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicWifi, mqttBuf);
    Serial.printf("[MQTT] → %s (%u entries)\n", topicWifi, wifiCount);
}

static void publishBle() {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();

    for (uint8_t i = 0; i < bleCount; i++) {
        JsonObject obj = arr.add<JsonObject>();
        obj["mac"]  = bleResults[i].mac;
        obj["name"] = bleResults[i].name;
        obj["rssi"] = bleResults[i].rssi;
    }

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicBle, mqttBuf);
    Serial.printf("[MQTT] → %s (%u entries)\n", topicBle, bleCount);
}

static void publishStatus() {
    JsonDocument doc;
    doc["uptime_ms"]    = millis();
    doc["free_heap"]    = ESP.getFreeHeap();
    doc["ip"]           = WiFi.localIP().toString();
    doc["firmware_ver"] = FIRMWARE_VER;
    doc["wifi_rssi"]    = WiFi.RSSI();

    float volts = readBatteryVolts();
    doc["battery_v"]   = serialized(String(volts, 2));
    doc["battery_pct"] = voltageToPercent(volts);

    if (gps.location.isValid()) {
        doc["gps_lat"]  = serialized(String(gps.location.lat(), 6));
        doc["gps_lon"]  = serialized(String(gps.location.lng(), 6));
        doc["gps_alt"]  = serialized(String(gps.altitude.meters(), 1));
        doc["gps_sats"] = gps.satellites.value();
        doc["gps_fix"]  = true;
    } else {
        doc["gps_fix"]  = false;
        doc["gps_sats"] = gps.satellites.isValid() ? gps.satellites.value() : 0;
    }

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicStatus, mqttBuf);
    Serial.printf("[MQTT] → %s\n", topicStatus);
}

// ── Display render ────────────────────────────────────────────────────────────
//
// Layout (128×64, font size 1 = 6×8 px):
//   y= 0  Batt: 3.82V 62%
//   y= 9  ─────────────────
//   y=11  Lat: 48.8234N         (or "GPS: no fix")
//   y=20  Lon:  2.3560E         (or "Sats: 3")
//   y=29  Alt:45m  Sats:8       (or blank)
//   y=38  ─────────────────
//   y=40  WiFi: -65 dBm         (or "WiFi: offline")
//   y=49  <NODE_ID>
//
static void renderDisplay() {
#ifdef HAS_OLED
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);

    // Battery
    char buf[32];
    float volts = readBatteryVolts();
    snprintf(buf, sizeof(buf), "Batt:%.2fV %u%%",
        volts, voltageToPercent(volts));
    oled.setCursor(0, 0);
    oled.print(buf);

    oled.drawFastHLine(0, 9, 128, SSD1306_WHITE);

    // GPS
    if (gps.location.isValid() && gps.location.age() < 5000) {
        double lat = gps.location.lat();
        double lon = gps.location.lng();

        snprintf(buf, sizeof(buf), "Lat:%s%.4f",
            lat >= 0 ? " " : "", lat);
        oled.setCursor(0, 11);
        oled.print(buf);

        snprintf(buf, sizeof(buf), "Lon:%s%.4f",
            lon >= 0 ? " " : "", lon);
        oled.setCursor(0, 20);
        oled.print(buf);

        uint32_t sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
        snprintf(buf, sizeof(buf), "Alt:%.0fm  Sats:%lu",
            gps.altitude.isValid() ? gps.altitude.meters() : 0.0,
            static_cast<unsigned long>(sats));
        oled.setCursor(0, 29);
        oled.print(buf);
    } else {
        oled.setCursor(0, 11);
        oled.print("GPS: no fix");

        uint32_t sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
        snprintf(buf, sizeof(buf), "Sats: %lu visible",
            static_cast<unsigned long>(sats));
        oled.setCursor(0, 20);
        oled.print(buf);
    }

    oled.drawFastHLine(0, 38, 128, SSD1306_WHITE);

    // WiFi signal
    if (WiFi.status() == WL_CONNECTED) {
        snprintf(buf, sizeof(buf), "WiFi: %d dBm", WiFi.RSSI());
    } else {
        snprintf(buf, sizeof(buf), "WiFi: offline");
    }
    oled.setCursor(0, 40);
    oled.print(buf);

    // Node ID footer
    char nodeId[22];
    strncpy(nodeId, NODE_ID, 21);
    nodeId[21] = '\0';
    oled.setCursor(0, 49);
    oled.print(nodeId);

    oled.display();
#endif
}

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== botanical-sentinel ttgo-lora32 node ===");

    // I2C — shared by AXP192 PMIC (0x34) and OLED SSD1306 (0x3C)
    Wire.begin(I2C_SDA, I2C_SCL);
    initAXP192();

    // GPS — powered by AXP192 LDO3; allow brief settle time after power-on
    delay(100);
    Serial1.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    Serial.printf("[GPS] Serial1 at 9600 baud RX=%d TX=%d\n",
        GPS_RX_PIN, GPS_TX_PIN);

#ifdef HAS_OLED
    // periphBegin=false prevents oled.begin() from resetting Wire to default pins
    if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C, /*reset=*/true, /*periphBegin=*/false)) {
        Serial.println("[OLED] Init failed — display not responding at 0x3C");
        Serial.printf("[OLED] Pins: SDA=%d SCL=%d RST=%d\n",
            I2C_SDA, I2C_SCL, DISP_RST);
    } else {
        Serial.println("[OLED] Initialised");
        oled.clearDisplay();
        oled.setTextSize(1);
        oled.setTextColor(SSD1306_WHITE);
        oled.setCursor(0, 0);
        oled.println("botanical-sentinel");
        oled.println("Connecting...");
        oled.display();
    }
#endif

    snprintf(topicWifi,   sizeof(topicWifi),   "nodes/%s/scan/wifi", NODE_ID);
    snprintf(topicBle,    sizeof(topicBle),    "nodes/%s/scan/bt",   NODE_ID);
    snprintf(topicStatus, sizeof(topicStatus), "nodes/%s/status",    NODE_ID);

    WiFi.mode(WIFI_STA);
    connectWifi();

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    connectMqtt();

    if (mqtt.connected()) {
        publishStatus();
    }

    BLEDevice::init("");
}

void loop() {
    // Feed GPS parser continuously — must run every loop iteration
    while (Serial1.available()) {
        gps.encode(Serial1.read());
    }

    // Maintain WiFi/MQTT
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
    } else {
        if (!mqtt.connected()) {
            connectMqtt();
        }
        mqtt.loop();
    }

    // Refresh display every 5 s (independent of 30 s scan cycle)
    static uint32_t lastDisplay = 0;
    if (millis() - lastDisplay >= DISPLAY_INTERVAL_MS) {
        lastDisplay = millis();
        renderDisplay();
    }

    // Scan + publish every 30 s
    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;
    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        lastScan = millis();
        scanCount++;
        Serial.printf("\n--- Scan #%lu ---\n", scanCount);

        scanWifi();
        scanBle();

        if (mqtt.connected()) {
            publishWifi();
            publishBle();
            publishStatus();
        } else {
            Serial.println("[MQTT] Not connected — skipping publish");
        }
    }
}
