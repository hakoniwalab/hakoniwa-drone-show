import assert from 'node:assert/strict';

import { formatStatusTimeUsec } from './show-clock.mjs';

assert.equal(formatStatusTimeUsec(0), '0.00 s');
assert.equal(formatStatusTimeUsec(15_250_000), '15.25 s');
assert.equal(formatStatusTimeUsec(null), '--');
assert.equal(formatStatusTimeUsec(-1), '--');

console.log('show clock tests passed');
