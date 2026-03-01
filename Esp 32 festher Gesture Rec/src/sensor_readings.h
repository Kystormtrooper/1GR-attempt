#ifndef sensor_readings.h
#define sensor_readings.h

struct SensorReadings {
    unsigned long timestamp;
    int pinkey;
    int index;
    int middle;
    int ring;
};

SensorReadings readSensorsWithTimestamp();

#endif