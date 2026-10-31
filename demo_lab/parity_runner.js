/* Run demo_lab/reconciler.js over a payload and print the result as JSON.
 *
 * Used only by test_demo_app.py, which compares this output against
 * evidence.reconcile() under Python. Kept as a separate file so the test has
 * no inline-JS escaping to get wrong, and so the same reconciler.js that the
 * browser runs is the one that is checked.
 *
 *   node demo_lab/parity_runner.js payload.json > out.json
 *
 * payload.json: {"items": [{"item": {...}, "claims": [...]}, ...]}
 */
'use strict';

const fs = require('fs');
const path = require('path');
const reconciler = require(path.join(__dirname, 'reconciler.js'));

const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

function valuesOf(group) {
  return group.map(function (c) { return c.value; });
}

function pairs(list) {
  return list.map(function (pair) { return [pair[0], valuesOf(pair[1])]; });
}

const out = payload.items.map(function (entry) {
  const r = reconciler.reconcile(entry.item, entry.claims);
  return {
    item_id: entry.item.item_id,
    verdict: reconciler.confidence(r),
    conflicts: pairs(r.conflicts),
    agreements: pairs(r.agreements),
    unknown_aspects: r.unknown_aspects,
    unexpected: pairs(r.unexpected),
    aspects: Array.from(r.byAspect.keys()),
    sources: entry.claims.length
  };
});

process.stdout.write(JSON.stringify(out));
