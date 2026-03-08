#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>

// ── Constants ────────────────────────────────────────────────────────────────

static constexpr uint32_t SCAN_INTERVAL_MS = 30000;
static constexpr uint8_t  MAX_WIFI         = 20;

// ── Types ─────────────────────────────────────────────────────────────────────

struct WifiResult {
    char    ssid[33];   // 32 chars + null terminator
    uint8_t bssid[6];
    int32_t rssi;
    uint8_t channel;
};

// ── State ─────────────────────────────────────────────────────────────────────

static TFT_eSPI tft;
static WifiResult wifiResults[MAX_WIFI];
static uint8_t    wifiCount  = 0;
static uint32_t   scanCount  = 0;

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
    for (uint8_t i = 0; i < wifiCount; i++) {
        const char* ssid = wifiResults[i].ssid[0]
            ? wifiResults[i].ssid : "[hidden]";
        Serial.printf("  %-32s  %4d dBm  ch%u\n",
            ssid, wifiResults[i].rssi, wifiResults[i].channel);
    }
}

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== esp_bot scanner node ===");

    tft.init();
    tft.setRotation(1);   // landscape: 320x240, USB connector on right
    tft.fillScreen(TFT_BLACK);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
}

void loop() {
    // Subtract SCAN_INTERVAL_MS from 0 (uint32_t underflow) so the first
    // scan fires immediately without a 30-second wait on boot.
    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;

    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        lastScan = millis();
        scanCount++;
        Serial.printf("\n--- Scan #%lu ---\n", scanCount);
        scanWifi();
    }
}
