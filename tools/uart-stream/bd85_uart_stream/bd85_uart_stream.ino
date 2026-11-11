// SPDX-License-Identifier: MIT
// Uno R3, ATmega328P at 16 MHz. Target F -> D8/ICP1, target GND -> GND.
// No RESET-GND jumper; no target wires on D0/D1 or power pins.
#include <Arduino.h>
#include <avr/interrupt.h>
#include <util/crc16.h>

constexpr uint32_t CAPTURE_MS = 20000UL;
volatile uint32_t ringTicks[256];
volatile uint8_t writeIndex = 0, readIndex = 0;
volatile uint16_t timerHigh = 0;
volatile uint32_t seenEdges = 0, droppedEdges = 0;
uint16_t sequence = 0;
uint8_t payload[64], used = 0;

ISR(TIMER1_OVF_vect) { ++timerHigh; }

ISR(TIMER1_CAPT_vect) {
  const uint16_t low = ICR1;
  uint16_t high = timerHigh;
  if ((TIFR1 & _BV(TOV1)) && low < 0x8000) ++high;
  ++seenEdges;
  const uint8_t next = uint8_t(writeIndex + 1);
  if (next == readIndex) { ++droppedEdges; return; }
  ringTicks[writeIndex] = (uint32_t(high) << 16) | low;
  writeIndex = next;
}

bool popEdge(uint32_t &ticks) {
  const uint8_t saved = SREG;
  cli();
  if (readIndex == writeIndex) { SREG = saved; return false; }
  ticks = ringTicks[readIndex];
  ++readIndex;
  SREG = saved;
  return true;
}

void frame(uint8_t type, const uint8_t *data, uint8_t size) {
  uint8_t packet[72];
  packet[0] = 0xa5; packet[1] = 0x5a;
  packet[2] = type; packet[3] = size;
  packet[4] = uint8_t(sequence); packet[5] = uint8_t(sequence >> 8);
  ++sequence;
  uint16_t crc = 0xffff;
  for (uint8_t i = 2; i < 6; ++i) crc = _crc_xmodem_update(crc, packet[i]);
  for (uint8_t i = 0; i < size; ++i) {
    packet[6 + i] = data[i];
    crc = _crc_xmodem_update(crc, data[i]);
  }
  packet[6 + size] = uint8_t(crc);
  packet[7 + size] = uint8_t(crc >> 8);
  Serial.write(packet, size + 8);
}

void flushPayload() {
  if (used) { frame(1, payload, used); used = 0; }
}

void encodeDelta(uint32_t delta) {
  do {
    uint8_t value = delta & 0x7f;
    delta >>= 7;
    if (delta) value |= 0x80;
    payload[used++] = value;
    if (used == sizeof(payload)) flushPayload();
  } while (delta);
}

void put32(uint8_t *out, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) { out[i] = uint8_t(value); value >>= 8; }
}

void capture() {
  Serial.println(F("ARMED: streaming for 20 seconds; power on BD85 now."));
  Serial.print(F("BD85STR1"));
  Serial.flush();
  sequence = 0; used = 0;
  noInterrupts();
  TCCR1A = 0; TCCR1B = 0; TIMSK1 = 0; TCNT1 = 0;
  timerHigh = 0; writeIndex = 0; readIndex = 0;
  seenEdges = 0; droppedEdges = 0;
  TIFR1 = _BV(ICF1) | _BV(TOV1);
  TCCR1B = _BV(ICNC1) | _BV(CS11);  // Falling edges; 0.5 us/tick.
  TIMSK1 = _BV(ICIE1) | _BV(TOIE1);
  interrupts();

  uint32_t previous = 0, sentEdges = 0, ticks;
  const uint32_t started = millis();
  uint32_t lastFlush = started;
  while (millis() - started < CAPTURE_MS) {
    if (popEdge(ticks)) {
      encodeDelta(ticks - previous);
      previous = ticks; ++sentEdges;
    }
    if (millis() - lastFlush >= 20) { flushPayload(); lastFlush = millis(); }
  }
  noInterrupts();
  TIMSK1 = 0; TCCR1B = 0;
  const uint32_t seen = seenEdges, dropped = droppedEdges;
  interrupts();
  while (popEdge(ticks)) {
    encodeDelta(ticks - previous); previous = ticks; ++sentEdges;
  }
  flushPayload();
  uint8_t summary[16];
  put32(summary, CAPTURE_MS); put32(summary + 4, seen);
  put32(summary + 8, dropped); put32(summary + 12, sentEdges);
  frame(2, summary, sizeof(summary));
  Serial.println();
  Serial.print(F("DONE,observed=")); Serial.print(seen);
  Serial.print(F(",buffer_dropped=")); Serial.print(dropped);
  Serial.print(F(",sent=")); Serial.println(sentEdges);
  Serial.println(F("Send g to capture again."));
}

void setup() {
  digitalWrite(8, LOW); pinMode(8, INPUT);
  Serial.begin(1000000);
  Serial.println(F("BD85 stream: PC baud 1000000, D8 input, falling edges only."));
  Serial.println(F("Start a BINARY log, then send g. Capture lasts 20 seconds."));
}

void loop() {
  if (Serial.available()) {
    const char c = Serial.read();
    if (c == 'g' || c == 'G') capture();
  }
}
