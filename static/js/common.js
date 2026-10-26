/* Shared helpers: theme toggle, rupee formatting, the rolling odometer and the efficiency gauge.
   Styles are set from script (CSSOM) rather than inline attributes, so the strict
   Content-Security-Policy can stay in place. */
(function () {
  'use strict';
  var MM = (window.MM = window.MM || {});
  var SVGNS = 'http://www.w3.org/2000/svg';

  // ---------------------------------------------------------------- formatting
  // 1234567.5 -> "12,34,567.50" (Indian digit grouping)
  MM.group = function (value, decimals) {
    var fixed = Math.abs(value).toFixed(decimals);
    var parts = fixed.split('.');
    var whole = parts[0];
    if (whole.length > 3) {
      var tail = whole.slice(-3);
      var head = whole.slice(0, -3);
      var out = [];
      while (head.length > 2) { out.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) { out.unshift(head); }
      whole = out.join(',') + ',' + tail;
    }
    return (value < 0 ? '-' : '') + whole + (parts[1] ? '.' + parts[1] : '');
  };
  MM.inr = function (value, decimals) { return '₹' + MM.group(value, decimals == null ? 0 : decimals); };

  // ---------------------------------------------------------------------- theme
  var btn = document.querySelector('.theme-btn');
  if (btn) {
    btn.addEventListener('click', function () {
      var root = document.documentElement;
      var current = root.getAttribute('data-theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = current === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('mm-theme', next); } catch (e) { /* ignore */ }
      document.dispatchEvent(new CustomEvent('mm-theme'));
    });
  }

  // ------------------------------------------------------------------ bar fills
  MM.fillBars = function (root) {
    var els = (root || document).querySelectorAll('[data-pct]');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call(els, function (el) {
          var pct = parseFloat(el.getAttribute('data-pct'));
          if (!isNaN(pct)) { el.style.width = Math.max(0, Math.min(100, pct)) + '%'; }
        });
      });
    });
  };
  MM.fillBars(document);

  // ------------------------------------------------------------------- odometer
  // MM.odometer(el, "1,234.50", "₹") builds one rolling column per digit.
  // Calling it again with a same-shaped number rolls the digits to the new value.
  MM.odometer = function (el, text, prefix, off) {
    var shape = text.replace(/\d/g, '0');
    if (!el._odo || el._odo.shape !== shape) {
      el.textContent = '';
      var digits = [];
      if (prefix) {
        var pre = document.createElement('span');
        pre.className = 'odo-prefix';
        pre.setAttribute('aria-hidden', 'true');
        pre.textContent = prefix;
        el.appendChild(pre);
      }
      text.split('').forEach(function (ch) {
        if (/\d/.test(ch)) {
          var box = document.createElement('span');
          box.className = 'odo-digit';
          box.setAttribute('aria-hidden', 'true');
          var strip = document.createElement('span');
          strip.className = 'odo-strip';
          for (var i = 0; i < 10; i++) {
            var s = document.createElement('span');
            s.textContent = i;
            strip.appendChild(s);
          }
          box.appendChild(strip);
          el.appendChild(box);
          digits.push(strip);
        } else {
          var sym = document.createElement('span');
          sym.className = 'odo-char odo-sym';
          sym.setAttribute('aria-hidden', 'true');
          sym.textContent = ch;
          el.appendChild(sym);
        }
      });
      el._odo = { shape: shape, digits: digits };
      void el.offsetWidth; // start every digit at 0, then roll
    }
    el.setAttribute('role', 'img');
    el.setAttribute('aria-label', off ? 'No result yet' : (prefix || '') + text);
    el.classList.toggle('odo-off', !!off);
    var d = text.replace(/\D/g, '');
    el._odo.digits.forEach(function (strip, i) {
      strip.style.transform = 'translateY(' + (-1.1 * Number(d.charAt(i) || 0)) + 'em)';
    });
  };

  // ---------------------------------------------------------------------- gauge
  function pt(cx, cy, r, t) {
    var a = Math.PI * (1 - t);
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  }
  function arc(cx, cy, r, t0, t1) {
    var p0 = pt(cx, cy, r, t0), p1 = pt(cx, cy, r, t1);
    return 'M' + p0[0].toFixed(2) + ' ' + p0[1].toFixed(2) + ' A' + r + ' ' + r + ' 0 0 1 ' + p1[0].toFixed(2) + ' ' + p1[1].toFixed(2);
  }
  function el(name, attrs, text) {
    var n = document.createElementNS(SVGNS, name);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) { n.textContent = text; }
    return n;
  }

  // scale: {min, max, thresholds:[lo, hi], unit}. The needle shows where one value sits among all vehicles in the data.
  MM.gauge = function (svg, scale, value, label) {
    var cx = 160, cy = 150, r = 118;
    var span = scale.max - scale.min || 1;
    var t = function (v) { return Math.max(0, Math.min(1, (v - scale.min) / span)); };
    var key = [scale.min, scale.max, scale.thresholds[0], scale.thresholds[1], scale.unit].join('|');
    if (svg._key !== key) {
      svg._key = key;
      svg.textContent = '';
      svg.setAttribute('viewBox', '0 0 320 212');
      var t1 = t(scale.thresholds[0]), t2 = t(scale.thresholds[1]);
      svg.appendChild(el('path', { d: arc(cx, cy, r, 0, t1), class: 'gauge-track gauge-thirsty' }));
      svg.appendChild(el('path', { d: arc(cx, cy, r, t1, t2), class: 'gauge-track gauge-balanced' }));
      svg.appendChild(el('path', { d: arc(cx, cy, r, t2, 1), class: 'gauge-track gauge-efficient' }));
      svg.appendChild(el('text', { x: cx - r, y: cy + 22, 'text-anchor': 'middle', class: 'gauge-label' }, String(Math.round(scale.min))));
      svg.appendChild(el('text', { x: cx + r, y: cy + 22, 'text-anchor': 'middle', class: 'gauge-label' }, String(Math.round(scale.max))));
      var needle = el('g', { class: 'gauge-needle' });
      needle.appendChild(el('line', { x1: cx, y1: cy, x2: cx - (r - 22), y2: cy }));
      svg.appendChild(needle);
      svg.appendChild(el('circle', { cx: cx, cy: cy, r: 9, fill: 'var(--panel-ink)' }));
      svg.appendChild(el('circle', { cx: cx, cy: cy, r: 3.5, fill: 'var(--panel)' }));
      svg._needle = needle;
      svg._value = el('text', { x: cx, y: 194, 'text-anchor': 'middle', class: 'gauge-value' });
      svg._unit = el('text', { x: cx, y: 210, 'text-anchor': 'middle', class: 'gauge-unit' }, scale.unit);
      svg.appendChild(svg._value);
      svg.appendChild(svg._unit);
      svg._needle.style.transform = 'rotate(0deg)';
      void svg.getBoundingClientRect();
    }
    svg._value.textContent = value.toFixed(1);
    svg._needle.style.transform = 'rotate(' + (t(value) * 180).toFixed(1) + 'deg)';
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', label || (value.toFixed(1) + ' ' + scale.unit));
  };
})();
