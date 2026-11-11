// SPDX-License-Identifier: MIT
// Arduino Uno R3 / ATmega328P, 16 MHz only.
// BD85 F -> D8 (ICP1); BD85 verified GND -> Uno GND.
// Disconnect the former RESET-GND jumper and all target wires to D0/D1.
// Measures falling edges only. It does not decode UART or transmit to BD85.
#include <Arduino.h>
#include <avr/interrupt.h>

constexpr uint8_t SAMPLE_COUNT = 192;
constexpr uint32_t TIMEOUT_MS = 20000UL;
volatile uint32_t edgeTicks[SAMPLE_COUNT];
volatile uint16_t timerHigh = 0;
volatile uint8_t edgeCount = 0;

ISR(TIMER1_OVF_vect) {
  ++timerHigh;
}

ISR(TIMER1_CAPT_vect) {
  const uint16_t low = ICR1;
  uint16_t high = timerHigh;
  // Account for an overflow pending while the capture interrupt runs first.
  if ((TIFR1 & _BV(TOV1)) && low < 0x8000) ++high;
  const uint8_t index = edgeCount;
  if (index < SAMPLE_COUNT) {
    edgeTicks[index] = (uint32_t(high) << 16) | low;
    edgeCount = index + 1;
    if (edgeCount == SAMPLE_COUNT) TIMSK1 &= ~_BV(ICIE1);
  }
}

void printHalfMicroseconds(uint32_t ticks) {
  Serial.print(ticks / 2);
  Serial.print((ticks & 1) ? F(".5") : F(".0"));
}

void capture() {
  Serial.println(F("ARMED: power on BD85 now. Waiting up to 20 seconds."));
  Serial.flush();
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TIMSK1 = 0;
  TCNT1 = 0;
  timerHigh = 0;
  edgeCount = 0;
  TIFR1 = _BV(ICF1) | _BV(TOV1);
  // Noise canceller; falling edge (ICES1=0); /8 gives 0.5 us per tick.
  TCCR1B = _BV(ICNC1) | _BV(CS11);
  TIMSK1 = _BV(ICIE1) | _BV(TOIE1);
  interrupts();
  const uint32_t started = millis();
  while (edgeCount < SAMPLE_COUNT && millis() - started < TIMEOUT_MS) {
    // No serial output while capturing. Hardware Timer1 timestamps the edges.
  }
  noInterrupts();
  TIMSK1 = 0;
  TCCR1B = 0;
  const uint8_t count = edgeCount;
  interrupts();

  Serial.print(F("DONE,edges="));
  Serial.println(count);
  Serial.println(F("index,time_us,delta_us"));
  uint32_t previous = 0;
  for (uint8_t i = 0; i < count; ++i) {
    const uint32_t current = edgeTicks[i];
    Serial.print(i);
    Serial.print(',');
    printHalfMicroseconds(current);
    Serial.print(',');
    if (i) printHalfMicroseconds(current - previous);
    Serial.println();
    previous = current;
  }
  Serial.println(F("Send g to measure again."));
}

void setup() {
  digitalWrite(8, LOW);  // No internal pull-up on the target signal.
  pinMode(8, INPUT);
  Serial.begin(115200);
  Serial.println(F("BD85 falling-edge meter: Uno R3, D8 input, 0.5 us ticks."));
  Serial.println(F("Send g, then power on BD85 when ARMED appears."));
}

void loop() {
  if (Serial.available()) {
    const char command = Serial.read();
    if (command == 'g' || command == 'G') capture();
  }
}
