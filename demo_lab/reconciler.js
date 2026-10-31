/* The reconciler, ported to JavaScript so the demo page can run it in a tab.
 *
 * This is a PORT, not a reimplementation. It is kept honest by
 * test_demo_app.py, which runs this file under node and evidence.reconcile()
 * under Python over every item in every corpus and fails if any verdict,
 * conflict, agreement, gap or unexpected aspect differs. A port with no
 * parity test is a second implementation that will drift; the test is the
 * only thing that makes the word "port" mean anything.
 *
 * Dual-use: inlined into demo.html by demo_lab/build_app.py (where `module`
 * is undefined), and require()d by the test under node.
 *
 * The one semantic difference from the Python, stated rather than hidden:
 * Python sorts aspect names with `sorted()` and JS sorts with the default
 * comparator, which compares UTF-16 code units. For the ASCII aspect names
 * this system uses ("state", "outcome", "cause") the two orders are
 * identical, and the parity test compares the ordered lists rather than sets.
 */
'use strict';

// The kinds of source that can make a claim.
var KINDS = ['card', 'receipt', 'commit', 'check', 'verdict', 'web'];

// An ASPECT is a property of the item, not of the source. Two sources that
// speak about different aspects never contradict each other.
var DEFAULT_ASPECT = {
  card: 'state',
  commit: 'state',
  check: 'state',
  receipt: 'outcome',
  verdict: 'outcome',
  web: 'state'
};

// An aspect nobody spoke about is an UNKNOWN, not a pass.
var EXPECTED_ASPECTS = ['state', 'outcome', 'cause'];

var UNKNOWN = 'UNKNOWN';

function hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

/* Mirrors Evidence.aspect_name: an explicit aspect wins, otherwise the kind's
 * default, otherwise the kind itself. An empty string is falsy in both
 * languages, which is the behaviour the Python `or` relies on. */
function aspectName(claim) {
  if (claim.aspect) {
    return claim.aspect;
  }
  var kind = claim.kind || 'card';
  return hasOwn(DEFAULT_ASPECT, kind) ? DEFAULT_ASPECT[kind] : kind;
}

/* Mirrors Evidence.citation(): a claim is never a bare assertion. */
function citation(claim) {
  return claim.locator ? claim.source + ' \u2014 ' + claim.locator : claim.source;
}

/* Mirrors evidence.reconcile(). Groups the claims by aspect, then says plainly
 * where they disagree. A forged or unknown aspect is cited and then ignored by
 * the verdict: it cannot agree its way into CORROBORATED and cannot stand in
 * for state, outcome or cause. */
function reconcile(item, claims) {
  var byAspect = new Map();
  var i, claim, aspect, group;

  for (i = 0; i < claims.length; i++) {
    claim = claims[i];
    aspect = aspectName(claim);
    if (!byAspect.has(aspect)) {
      byAspect.set(aspect, []);
    }
    byAspect.get(aspect).push(claim);
  }

  var aspects = Array.from(byAspect.keys()).sort();
  var conflicts = [];
  var agreements = [];
  var unexpected = [];

  for (i = 0; i < aspects.length; i++) {
    aspect = aspects[i];
    group = byAspect.get(aspect);
    if (EXPECTED_ASPECTS.indexOf(aspect) === -1) {
      unexpected.push([aspect, group]);
      continue;
    }
    var values = new Set();
    for (var j = 0; j < group.length; j++) {
      values.add(group[j].value);
    }
    if (values.size === 1) {
      agreements.push([aspect, group]);
    } else {
      conflicts.push([aspect, group]);
    }
  }

  var unknownAspects = [];
  for (i = 0; i < EXPECTED_ASPECTS.length; i++) {
    if (!byAspect.has(EXPECTED_ASPECTS[i])) {
      unknownAspects.push(EXPECTED_ASPECTS[i]);
    }
  }

  return {
    item: item,
    byAspect: byAspect,
    conflicts: conflicts,
    agreements: agreements,
    unknown_aspects: unknownAspects,
    unexpected: unexpected
  };
}

/* Mirrors Reconciliation.confidence(): a word, not a number. A number here
 * would be a number we did not measure. */
function confidence(r) {
  if (r.conflicts.length) {
    return 'CONFLICTED';
  }
  if (r.byAspect.size === 0) {
    return 'NO EVIDENCE';
  }
  if (r.unknown_aspects.length) {
    return 'PARTIAL';
  }
  return 'CORROBORATED';
}

/* Mirrors evidence.explain(): an unknown item is an unknown, not an empty
 * answer. */
function explain(items, claims, itemId) {
  var item = items[itemId] || { item_id: itemId, title: '', declared_status: '' };
  var mine = claims.filter(function (c) { return c.item_id === itemId; });
  return reconcile(item, mine);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    KINDS: KINDS,
    DEFAULT_ASPECT: DEFAULT_ASPECT,
    EXPECTED_ASPECTS: EXPECTED_ASPECTS,
    UNKNOWN: UNKNOWN,
    aspectName: aspectName,
    citation: citation,
    reconcile: reconcile,
    confidence: confidence,
    explain: explain
  };
}
