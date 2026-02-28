#include <Arduino.h>
#include <TFT_eSPI.h>

TFT_eSPI tft = TFT_eSPI();

// Cycle through these colors in loop()
static const uint16_t COLORS[] = {
    TFT_RED, TFT_GREEN, TFT_BLUE,
    TFT_YELLOW, TFT_CYAN, TFT_MAGENTA
};
static const char* COLOR_NAMES[] = {
    "RED", "GREEN", "BLUE",
    "YELLOW", "CYAN", "MAGENTA"
};
static const uint8_t NUM_COLORS = 6;

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== ESP32-S3 TFT Display Test ===");

    tft.init();
    tft.setRotation(1);  // landscape, USB connector on right
    tft.fillScreen(TFT_BLACK);
    Serial.println("TFT initialized OK");

    // --- Color fill tests ---
    for (uint8_t i = 0; i < NUM_COLORS; i++) {
        tft.fillScreen(COLORS[i]);
        Serial.printf("Fill: %s\n", COLOR_NAMES[i]);
        delay(600);
    }

    // --- Hello World ---
    tft.fillScreen(TFT_BLACK);

    tft.setTextDatum(MC_DATUM);  // middle-center

    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.setTextSize(1);
    tft.drawString("Hello ESP32-S3!", tft.width() / 2, tft.height() / 2 - 20, 4);

    tft.setTextColor(TFT_GREEN, TFT_BLACK);
    tft.drawString("TFT_eSPI OK", tft.width() / 2, tft.height() / 2 + 20, 4);

    Serial.println("Hello World displayed — setup complete");
}

void loop() {
    static uint32_t lastSwap = 0;
    static uint8_t idx = 0;

    if (millis() - lastSwap > 2000) {
        lastSwap = millis();

        tft.fillScreen(COLORS[idx]);

        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE);
        tft.drawString(COLOR_NAMES[idx], tft.width() / 2, tft.height() / 2, 4);

        Serial.printf("Cycling: %s\n", COLOR_NAMES[idx]);
        idx = (idx + 1) % NUM_COLORS;
    }
}
