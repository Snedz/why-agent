/* The workbench: the reconciler, driven by the reader.
 *
 * Inlined into demo.html by demo_page.py, after reconciler.js and after the
 * corpus blob. No network, no key, no server: the claims are in the page, the
 * reconciler is in the page, and every verdict on screen is computed by it.
 *
 * Three things it is built to show, because they are the three claims the
 * submission makes and a reader should not have to take on trust:
 *
 *   1. edit a value -> the sources stop agreeing -> CONFLICTED, every side cited
 *   2. invent an aspect -> it is cited and then ignored by the verdict
 *   3. remove the model-lane rows -> the verdict flips, and only the lane rows
 *      made the disagreement visible (the same flip flip_check.py proves)
 */
(function () {
  'use strict';

  var DATA = window.__WHY_AGENT__;
  var EXPECTED = ['state', 'outcome', 'cause'];
  var LANE = DATA.lane_sources;

  var state = { itemId: null, rows: [] };

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function itemById(id) {
    for (var i = 0; i < DATA.items.length; i++) {
      if (DATA.items[i].id === id) { return DATA.items[i]; }
    }
    return null;
  }

  function isLane(row) {
    return Object.prototype.hasOwnProperty.call(LANE, row.source);
  }

  function claimOf(row) {
    return {
      item_id: row.item_id, kind: row.kind, source: row.source,
      locator: row.locator, statement: row.statement, value: row.value,
      aspect: row.aspect
    };
  }

  function verdictOf(rows) {
    var claims = rows.filter(function (r) { return r.include; }).map(claimOf);
    var r = reconcile({ item_id: state.itemId }, claims);
    return { verdict: confidence(r), r: r, count: claims.length };
  }

  function load(id) {
    var item = itemById(id);
    state.itemId = id;
    state.rows = item.rows.map(function (r) {
      return {
        item_id: r.item_id, kind: r.kind, source: r.source, locator: r.locator,
        statement: r.statement, value: r.value, aspect: r.aspect, include: true
      };
    });
    $('wb-case').value = id;
    $('wb-headline').textContent = item.headline || item.id;
    $('wb-meta').textContent = item.corpus + ' · ' + state.rows.length + ' claims' +
      (item.note ? '' : '');
    var note = $('wb-note');
    if (item.note) { note.hidden = false; note.textContent = item.note; }
    else { note.hidden = true; }
    renderTable();
    refresh();
  }

  function renderTable() {
    var tb = $('wb-rows');
    tb.innerHTML = '';
    state.rows.forEach(function (row) {
      var tr = document.createElement('tr');
      if (!row.include) { tr.className = 'off'; }

      var tdChk = document.createElement('td');
      var chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.checked = row.include;
      chk.setAttribute('aria-label', 'include ' + row.source);
      chk.addEventListener('change', function () {
        row.include = chk.checked;
        tr.className = row.include ? '' : 'off';
        refresh();
      });
      tdChk.appendChild(chk);
      tr.appendChild(tdChk);

      var tdSrc = document.createElement('td');
      tdSrc.className = 'src';
      tdSrc.innerHTML = '<span class="' + (isLane(row) ? 'lane' : '') + '">' +
        esc(row.source) + '</span><br><span class="kind">' + esc(row.kind) +
        (isLane(row) ? ' · lane' : '') + '</span>';
      tr.appendChild(tdSrc);

      var tdAsp = document.createElement('td');
      var sel = document.createElement('select');
      sel.className = 'asp';
      var opts = EXPECTED.slice();
      if (row.aspect && EXPECTED.indexOf(row.aspect) === -1) { opts.push(row.aspect); }
      opts.push('__other__');
      opts.forEach(function (a) {
        var o = document.createElement('option');
        o.value = a;
        o.textContent = a === '__other__' ? 'other…' : a;
        if ((row.aspect || '') === a) { o.selected = true; }
        sel.appendChild(o);
      });
      if (!row.aspect) {
        // Show what the reconciler will actually use, and mark it inherited.
        var d = document.createElement('option');
        d.value = '';
        d.textContent = aspectName(row);
        d.title = 'no explicit aspect in the corpus — a ' + row.kind +
                  ' defaults to ' + aspectName(row);
        sel.insertBefore(d, sel.firstChild);
        d.selected = true;
        sel.className = 'asp inherited';
      }
      sel.addEventListener('change', function () {
        if (sel.value === '__other__') {
          var typed = window.prompt(
            'Aspect name. state, outcome and cause are the aspects a reader ' +
            'expects; anything else is cited and then ignored by the verdict.', '');
          if (typed === null) { sel.value = row.aspect; return; }
          row.aspect = typed.trim();
        } else {
          row.aspect = sel.value;
        }
        renderTable();
        refresh();
      });
      tdAsp.appendChild(sel);
      tr.appendChild(tdAsp);

      var tdVal = document.createElement('td');
      var inp = document.createElement('input');
      inp.className = 'val';
      inp.type = 'text';
      inp.value = row.value;
      inp.setAttribute('aria-label', 'value for ' + row.source);
      inp.addEventListener('input', function () { row.value = inp.value; refresh(); });
      tdVal.appendChild(inp);
      tr.appendChild(tdVal);

      var tdStmt = document.createElement('td');
      tdStmt.className = 'stmt';
      tdStmt.textContent = row.statement;
      tr.appendChild(tdStmt);

      var tdLoc = document.createElement('td');
      tdLoc.className = 'loc';
      tdLoc.textContent = row.locator;
      tr.appendChild(tdLoc);

      tb.appendChild(tr);
    });
  }

  function refresh() {
    var out = verdictOf(state.rows);
    var r = out.r;
    var v = out.verdict;

    var el = $('wb-verdict');
    el.textContent = v;
    el.className = 'verdict v-' + v.replace(/ /g, '');

    var card = null;
    state.rows.forEach(function (row) {
      if (row.include && row.kind === 'card') { card = row; }
    });
    var says = '';
    if (card) {
      says = 'The card says <b>' + esc(card.value) + '</b>. The reconciler says <b>' +
             esc(v) + '</b>.';
      if (v === 'CONFLICTED') {
        says += ' The card is one of the sides — it does not win.';
      } else if (v === 'PARTIAL') {
        says += ' The sources agree where they speak; something a reader expects is unreported.';
      } else if (v === 'NO EVIDENCE') {
        says += ' Nothing else was written about this item, so nothing corroborates the card.';
      }
    } else {
      says = 'No card row is included, so there is no declared status to compare against.';
    }
    says += ' <span class="quiet">' + out.count + ' claim' +
            (out.count === 1 ? '' : 's') + ' considered.</span>';
    $('wb-says').innerHTML = says;

    var c = $('wb-conflict');
    if (r.conflicts.length) {
      var h = '<p class="sech">Conflicts — every side shown, none chosen</p>';
      r.conflicts.forEach(function (pair) {
        h += '<div class="grp"><div class="aspname">' + esc(pair[0]) + '</div>';
        pair[1].forEach(function (cl) {
          h += '<div class="cl"><span class="who">' + esc(cl.source) + '</span> says ' +
               '<span class="val2">' + esc(cl.value) + '</span> ' +
               '<span class="cite">— ' + esc(citation(cl)) + '</span></div>';
        });
        h += '</div>';
      });
      c.innerHTML = h;
    } else { c.innerHTML = ''; }

    var a = $('wb-agree');
    if (r.agreements.length) {
      var h2 = '<p class="sech">Agrees</p>';
      r.agreements.forEach(function (pair) {
        var n = pair[1].length;
        h2 += '<div class="grp"><div class="aspname">' + esc(pair[0]) +
              ' — <span class="val2">' + esc(pair[1][0].value) + '</span></div>' +
              '<div class="cl">' + n + (n === 1 ? ' source' : ' sources') + ': ' +
              pair[1].map(function (cl) { return esc(cl.source); }).join(', ') +
              '</div></div>';
      });
      a.innerHTML = h2;
    } else { a.innerHTML = ''; }

    var g = $('wb-gap');
    if (r.unknown_aspects.length) {
      g.innerHTML = '<p class="sech">Gaps — nobody said</p>' +
        r.unknown_aspects.map(function (x) {
          return '<div class="gap">' + esc(x) + ' — no source made a claim about this</div>';
        }).join('') +
        '<p class="quiet">An aspect nobody reported is a gap. It is not a pass, and it ' +
        'is not a plausible explanation.</p>';
    } else { g.innerHTML = ''; }

    var u = $('wb-unexp');
    if (r.unexpected.length) {
      u.innerHTML = '<p class="sech">Cited, then ignored by the verdict</p>' +
        r.unexpected.map(function (pair) {
          return '<div class="gap quiet">' + esc(pair[0]) + ' — ' +
            pair[1].map(function (cl) {
              return esc(cl.source) + ' says <span class="val2">' + esc(cl.value) + '</span>';
            }).join(', ') + '</div>';
        }).join('') +
        '<p class="quiet">Not state, outcome or cause. A claim about an invented aspect ' +
        'cannot agree its way into a CORROBORATED verdict.</p>';
    } else { u.innerHTML = ''; }

    var laneRows = state.rows.filter(isLane);
    var btn = $('wb-lanes');
    var flip = $('wb-flip');
    if (laneRows.length) {
      btn.hidden = false;
      var anyIncluded = laneRows.some(function (x) { return x.include; });
      btn.textContent = anyIncluded ? 'Remove the model-lane rows'
                                    : 'Put the model-lane rows back';
      var without = state.rows.map(function (x) {
        return { include: isLane(x) ? false : x.include, row: x };
      });
      var flipped = verdictOf(without.map(function (w) {
        return Object.assign({}, w.row, { include: w.include });
      })).verdict;
      if (anyIncluded && flipped !== v) {
        flip.hidden = false;
        flip.innerHTML = '<b>Lane-dependent.</b> Remove the ' + laneRows.length +
          ' model-lane row' + (laneRows.length === 1 ? '' : 's') +
          ' and this same reconciler returns <b>' + esc(flipped) + '</b> instead of <b>' +
          esc(v) + '</b>. The disagreement was visible nowhere else. ' +
          '<code>python3 demo_lab/flip_check.py</code> proves the same flip in Python.';
      } else if (!anyIncluded) {
        flip.hidden = false;
        flip.innerHTML = '<b>Lane rows removed.</b> The verdict is <b>' + esc(v) +
          '</b>. Put them back and it becomes <b>' +
          esc(verdictOf(state.rows.map(function (x) {
            return Object.assign({}, x, { include: isLane(x) ? true : x.include });
          })).verdict) + '</b>.';
      } else {
        flip.hidden = true;
      }
    } else {
      btn.hidden = true;
      flip.hidden = true;
    }
  }

  $('wb-lanes').addEventListener('click', function () {
    var anyIncluded = state.rows.some(function (x) { return isLane(x) && x.include; });
    state.rows.forEach(function (x) { if (isLane(x)) { x.include = !anyIncluded; } });
    renderTable();
    refresh();
  });

  $('wb-reset').addEventListener('click', function () { load(state.itemId); });

  $('wb-add').addEventListener('click', function () {
    state.rows.push({
      item_id: state.itemId, kind: 'check', source: 'you',
      locator: 'typed on this page', statement: 'a claim you just added',
      value: 'shipped', aspect: 'state', include: true
    });
    renderTable();
    refresh();
  });

  var picker = $('wb-case');
  var html = '';
  DATA.corpora.forEach(function (c) {
    html += '<optgroup label="' + esc(c.label) + '">';
    DATA.items.filter(function (i) { return i.corpus === c.id; }).forEach(function (i) {
      html += '<option value="' + esc(i.id) + '">' + esc(i.id) +
              (i.title ? ' — ' + esc(i.title) : '') + '</option>';
    });
    html += '</optgroup>';
  });
  picker.innerHTML = html;
  picker.addEventListener('change', function () { load(picker.value); });

  load(DATA.items[0].id);
})();
