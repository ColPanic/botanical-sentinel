#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>

// ── Constants ────────────────────────────────────────────────────────────────

static constexpr uint32_t SCAN_INTERVAL_MS = 30000;
static constexpr uint8_t  MAX_WIFI         = 20;
static constexpr uint8_t  MAX_BLE          = 20;

// ── Types ─────────────────────────────────────────────────────────────────────

struct WifiResult {
    char    ssid[33];   // 32 chars + null terminator
    uint8_t bssid[6];
    int32_t rssi;
    uint8_t channel;
};

struct BleResult {
    char    name[32];
    char    mac[18];   // "AA:BB:CC:DD:EE:FF\0"
    int32_t rssi;
};

// ── State ─────────────────────────────────────────────────────────────────────

static TFT_eSPI tft;
static WifiResult wifiResults[MAX_WIFI];
static uint8_t    wifiCount  = 0;
static uint32_t   scanCount  = 0;
static BleResult  bleResults[MAX_BLE];
static uint8_t    bleCount   = 0;

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

// ── BLE scan ──────────────────────────────────────────────────────────────────

static void scanBle() {
    BLEScan* pScan = BLEDevice::getScan();
    pScan->setActiveScan(false);   // passive — never sends scan requests
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
    for (uint8_t i = 0; i < bleCount; i++) {
        const char* label = bleResults[i].name[0]
            ? bleResults[i].name : bleResults[i].mac;
        Serial.printf("  %-31s  %4d dBm\n", label, bleResults[i].rssi);
    }
}

// ── Display render ────────────────────────────────────────────────────────────

static void renderDisplay(uint32_t scanStartMs) {
    tft.fillScreen(TFT_BLACK);

    // ── Header ────────────────────────────────────────────────────────────────
    char buf[40];

    snprintf(buf, sizeof(buf), "WiFi(%u)", wifiCount);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(buf, 4, 4, 2);

    snprintf(buf, sizeof(buf), "BLE(%u)", bleCount);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(buf, 316, 4, 2);

    tft.drawFastHLine(0, 20, 320, TFT_DARKGREY);

    // ── WiFi list ─────────────────────────────────────────────────────────────
    tft.setTextDatum(TL_DATUM);
    static constexpr uint8_t WIFI_ROWS = 8;
    uint8_t wRows = wifiCount < WIFI_ROWS ? wifiCount : WIFI_ROWS;

    for (uint8_t i = 0; i < wRows; i++) {
        int16_t y = 22 + i * 16;

        // SSID — truncate at 20 chars
        const char* raw = wifiResults[i].ssid[0]
            ? wifiResults[i].ssid : "[hidden]";
        char ssidBuf[21];
        strncpy(ssidBuf, raw, 20);
        ssidBuf[20] = '\0';

        tft.setTextColor(TFT_CYAN, TFT_BLACK);
        tft.drawString(ssidBuf, 4, y, 2);

        // RSSI + channel — right-aligned
        snprintf(buf, sizeof(buf), "%ddBm ch%u",
            wifiResults[i].rssi, wifiResults[i].channel);
        tft.setTextColor(TFT_YELLOW, TFT_BLACK);
        tft.setTextDatum(TR_DATUM);
        tft.drawString(buf, 316, y, 2);
        tft.setTextDatum(TL_DATUM);
    }

    if (wifiCount > WIFI_ROWS) {
        tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
        tft.drawString("...", 4, 22 + WIFI_ROWS * 16, 2);
    }

    tft.drawFastHLine(0, 150, 320, TFT_DARKGREY);

    // ── BLE list ──────────────────────────────────────────────────────────────
    static constexpr uint8_t BLE_ROWS = 4;
    uint8_t bRows = bleCount < BLE_ROWS ? bleCount : BLE_ROWS;

    for (uint8_t i = 0; i < bRows; i++) {
        int16_t y = 152 + i * 16;

        const char* raw = bleResults[i].name[0]
            ? bleResults[i].name : bleResults[i].mac;
        char nameBuf[21];
        strncpy(nameBuf, raw, 20);
        nameBuf[20] = '\0';

        tft.setTextColor(TFT_GREEN, TFT_BLACK);
        tft.drawString(nameBuf, 4, y, 2);

        snprintf(buf, sizeof(buf), "%ddBm", bleResults[i].rssi);
        tft.setTextColor(TFT_YELLOW, TFT_BLACK);
        tft.setTextDatum(TR_DATUM);
        tft.drawString(buf, 316, y, 2);
        tft.setTextDatum(TL_DATUM);
    }

    tft.drawFastHLine(0, 222, 320, TFT_DARKGREY);

    // ── Footer ────────────────────────────────────────────────────────────────
    uint32_t elapsedSec = (millis() - scanStartMs) / 1000;
    snprintf(buf, sizeof(buf), "Scan #%lu   %lus ago",
        scanCount, static_cast<unsigned long>(elapsedSec));
    tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
    tft.drawString(buf, 4, 225, 2);
}

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== botanical-sentinel scanner node ===");

    tft.init();
    tft.setRotation(1);   // landscape: 320x240, USB connector on right
    tft.fillScreen(TFT_BLACK);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    BLEDevice::init("");
}

void loop() {
    // Subtract SCAN_INTERVAL_MS from 0 (uint32_t underflow) so the first
    // scan fires immediately without a 30-second wait on boot.
    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;

    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        // Show "Scanning..." splash while working
        tft.fillScreen(TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString("Scanning...", 160, 120, 4);

        lastScan = millis();
        scanCount++;
        Serial.printf("\n--- Scan #%lu ---\n", scanCount);

        scanWifi();
        scanBle();
        renderDisplay(lastScan);
    }
}
