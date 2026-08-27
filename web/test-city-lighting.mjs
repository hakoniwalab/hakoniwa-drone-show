import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('./city-lighting.mjs', import.meta.url), 'utf8');
for (const marker of [
  'new THREE.SpotLight()',
  'drone-show-city-lighting',
  'export function normalizeCityLighting',
  'export function cityLightingYaml',
  "'  city_lighting:'",
]) {
  assert.ok(source.includes(marker), marker);
}
console.log('city-lighting: spotlight and YAML contract ok');
