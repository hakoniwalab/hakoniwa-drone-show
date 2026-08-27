import assert from 'node:assert/strict';
import { bytesToHex, sha256Bytes, sha256Fallback } from './sha256.mjs';

const encoder = new TextEncoder();
const vectors = [
  ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
  ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
  [
    'The quick brown fox jumps over the lazy dog',
    'd7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592',
  ],
];

for (const [input, expected] of vectors) {
  const encoded = encoder.encode(input);
  assert.equal(bytesToHex(sha256Fallback(encoded)), expected);
  assert.equal(bytesToHex(await sha256Bytes(encoded, {})), expected);
}

console.log('sha256: Web Crypto-independent fallback ok');
