import assert from "node:assert/strict";
import test from "node:test";
import { base64ToUint8Array, pcm16ToFloat32 } from "@/lib/use-realtime-voice";

test("base64ToUint8Array decodes an empty string to a zero-length array", () => {
  const result = base64ToUint8Array("");
  assert.equal(result.length, 0);
  assert.deepEqual(Array.from(result), []);
});

test("base64ToUint8Array decodes the known Hello vector", () => {
  const result = base64ToUint8Array("SGVsbG8=");
  assert.deepEqual(Array.from(result), [72, 101, 108, 108, 111]);
});

test("base64ToUint8Array round-trips arbitrary binary bytes", () => {
  const bytes = [0, 255, 128, 1];
  const base64 = Buffer.from(bytes).toString("base64");
  const result = base64ToUint8Array(base64);
  assert.equal(result.length, bytes.length);
  assert.deepEqual(Array.from(result), bytes);
});

test("base64ToUint8Array preserves high-byte values exactly", () => {
  const bytes = [200, 255, 254, 127, 128, 0, 65];
  const base64 = Buffer.from(bytes).toString("base64");
  const result = base64ToUint8Array(base64);
  assert.deepEqual(Array.from(result), bytes);
  assert.ok(result.every((b) => b >= 0 && b <= 255));
});

test("pcm16ToFloat32 converts all-zero input to all zeros", () => {
  const pcm16 = new Uint8Array([0, 0, 0, 0, 0, 0]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 3);
  assert.ok(result.every((v) => v === 0));
});

test("pcm16ToFloat32 maps max positive int16 to approximately 1", () => {
  const pcm16 = new Uint8Array([0xff, 0x7f]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 1);
  assert.ok(Math.abs(result[0] - 1) < 1e-6);
});

test("pcm16ToFloat32 maps min int16 to exactly -1", () => {
  const pcm16 = new Uint8Array([0x00, 0x80]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 1);
  assert.equal(result[0], -1);
});

test("pcm16ToFloat32 maps a small negative int16 to -0.5", () => {
  const pcm16 = new Uint8Array([0x00, 0xc0]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 1);
  assert.equal(result[0], -0.5);
});

test("pcm16ToFloat32 maps a small positive int16 to 16383/32767", () => {
  const pcm16 = new Uint8Array([0xff, 0x3f]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 1);
  assert.ok(Math.abs(result[0] - 16383 / 32767) < 1e-6);
});

test("pcm16ToFloat32 decodes bytes little-endian (0xFF 0x7F is +32767, not -1)", () => {
  const pcm16 = new Uint8Array([0xff, 0x7f]);
  const result = pcm16ToFloat32(pcm16);
  assert.ok(Math.abs(result[0] - 1) < 1e-6);
  assert.ok(result[0] !== -1);
});

test("pcm16ToFloat32 honors byteOffset by decoding from the view, not the buffer", () => {
  const buffer = new ArrayBuffer(6);
  const view = new Uint8Array(buffer);
  view.set([0xde, 0xad, 0xff, 0x7f, 0x00, 0xc0]);
  const offsetView = new Uint8Array(buffer, 2, 4);
  assert.equal(offsetView.byteOffset, 2);
  const result = pcm16ToFloat32(offsetView);
  assert.equal(result.length, 2);
  assert.ok(Math.abs(result[0] - 1) < 1e-6);
  assert.equal(result[1], -0.5);
});

test("pcm16ToFloat32 returns a zero-length Float32Array for odd byte input", () => {
  const pcm16 = new Uint8Array([0x01]);
  const result = pcm16ToFloat32(pcm16);
  assert.equal(result.length, 0);
});
