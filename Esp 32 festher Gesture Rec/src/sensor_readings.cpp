#include "sensor_readings.h"
#include <Arduino.h>

// Define pins again or include them from main if needed
const int PINKEY_PIN  = A3;
const int INDEX_PIN  = A5;
const int MIDDLE_PIN = A4;
const int RING_PIN   = A2;

SensorReadings readSensorsWithTimestamp() {
    SensorReadings readings;
    readings.timestamp = millis();
    readings.pinkey  = analogRead(PINKEY_PIN);
    readings.index  = analogRead(INDEX_PIN);
    readings.middle = analogRead(MIDDLE_PIN);
    readings.ring   = analogRead(RING_PIN);
    return readings;
}