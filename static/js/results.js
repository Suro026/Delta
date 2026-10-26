/* Model results page: switches vehicle type and draws a chart for every model on first view. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('metrics-data').textContent);
  var names = data.names;
  var charts = {};   // key -> [Chart]
  var drawn = {};
  var SERIES = ['#7c9082', '#d4958a', '#d3b66b', '#7fa3c0', '#b79ac0', '#a0aa88'];

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function theme() {
    return { ink: css('--ink'), mute: css('--ink-2'), line: css('--line'), primary: css('--primary'), peach: '#d4958a', gray: css('--ink-3') };
  }
  function short(name) {
    return name.replace('K-Nearest Neighbors', 'KNN').replace('Support Vector Machine', 'SVM').replace(' Regression', '').replace('Gradient Boosting', 'Grad. Boosting').replace('Logistic', 'Logistic');
  }

  // Start the radar just below the weakest score so the differences between models are visible.
  function radarMin(clf, defs) {
    var low = 100;
    clf.models.forEach(function (r) { defs.forEach(function (d) { low = Math.min(low, r[d[1]] * 100); }); });
    return Math.max(0, Math.floor(low / 10) * 10 - 10);
  }

  function grouped(canvas, labels, sets, opts) {
    return new Chart(canvas, {
      type: 'bar',
      data: { labels: labels, datasets: sets },
      options: Object.assign({
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12 } } },
        scales: { x: { grid: { display: false }, ticks: { maxRotation: 40, minRotation: 0 } }, y: { beginAtZero: true, grid: { color: css('--line') } } }
      }, opts || {})
    });
  }

  function importanceChart(key, name, c) {
    var reg = data.metrics[key].regression;
    var imp = reg.importance_all[name].filter(function (d) { return d.value > 0.0005; });
    return new Chart(document.getElementById(key + '-imp'), {
      type: 'bar',
      data: { labels: imp.map(function (d) { return names[d.feature] || d.feature; }), datasets: [{ data: imp.map(function (d) { return d.value; }), backgroundColor: imp.map(function (_, i) { return i === 0 ? c.peach : c.primary; }), borderRadius: 6 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (x) { return 'Score drop ' + x.parsed.x.toFixed(3); } } } },
        scales: { x: { beginAtZero: true, grid: { color: c.line }, title: { display: true, text: 'Drop in R² when shuffled' } }, y: { grid: { display: false } } }
      }
    });
  }

  function draw(key) {
    if (!window.Chart) { return; }
    var c = theme();
    Chart.defaults.font.family = '"Figtree", "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 13;
    Chart.defaults.color = c.mute;
    var m = data.metrics[key], reg = m.regression, clf = m.classification, unit = m.unit;
    var list = [];
    var regNames = reg.models.map(function (r) { return short(r.name); });

    // Regression: score, error and time for every model.
    list.push(grouped(document.getElementById(key + '-r2'), regNames, [
      { label: 'R² (train)', data: reg.models.map(function (r) { return r.train_r2; }), backgroundColor: '#a0aa88', borderRadius: 6 },
      { label: 'R² (test)', data: reg.models.map(function (r) { return r.r2; }), backgroundColor: c.primary, borderRadius: 6 },
      { label: 'R² (5-fold)', data: reg.models.map(function (r) { return r.cv_r2; }), backgroundColor: c.peach, borderRadius: 6 }
    ], { scales: { x: { grid: { display: false }, ticks: { maxRotation: 40, minRotation: 0 } }, y: { suggestedMin: Math.min(0, Math.min.apply(null, reg.models.map(function (r) { return r.cv_r2; }))), suggestedMax: 1, grid: { color: c.line } } } }));
    list.push(grouped(document.getElementById(key + '-err'), regNames, [
      { label: 'MAE', data: reg.models.map(function (r) { return r.mae; }), backgroundColor: c.primary, borderRadius: 6 },
      { label: 'RMSE', data: reg.models.map(function (r) { return r.rmse; }), backgroundColor: c.peach, borderRadius: 6 }
    ]));
    list.push(new Chart(document.getElementById(key + '-time'), {
      type: 'bar',
      data: { labels: regNames, datasets: [{ data: reg.models.map(function (r) { return r.fit_seconds; }), backgroundColor: reg.models.map(function (r) { return r.name === reg.best ? c.primary : c.gray; }), borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxRotation: 40, minRotation: 0 } }, y: { beginAtZero: true, grid: { color: c.line }, title: { display: true, text: 'Seconds' } } } }
    }));

    // Regression: actual vs predicted, one small chart per model.
    var actual = reg.scatter.actual;
    var lo = Math.min.apply(null, actual), hi = Math.max.apply(null, actual);
    reg.models.forEach(function (r, i) {
      var pred = reg.scatter.predicted_all[r.name];
      var pts = actual.map(function (a, j) { return { x: a, y: pred[j] }; });
      list.push(new Chart(document.getElementById(key + '-sc-' + i), {
        type: 'scatter',
        data: { datasets: [
          { data: pts, backgroundColor: SERIES[i % SERIES.length], pointRadius: 4, pointHoverRadius: 6 },
          { type: 'line', data: [{ x: lo, y: lo }, { x: hi, y: hi }], borderColor: c.ink, borderDash: [6, 5], borderWidth: 1.2, pointRadius: 0 }
        ] },
        options: {
          responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
          scales: { x: { grid: { color: c.line }, title: { display: true, text: 'Actual (' + unit + ')' } }, y: { grid: { color: c.line }, title: { display: true, text: 'Predicted' } } }
        }
      }));
    });

    // Regression: what each model relies on (switchable).
    var select = document.getElementById(key + '-imp-select');
    var impChart = importanceChart(key, select.value, c);
    list.push(impChart);
    select.onchange = function () {
      impChart.destroy();
      list.splice(list.indexOf(impChart), 1);
      impChart = importanceChart(key, select.value, theme());
      list.push(impChart);
    };

    // Classification: all scores for every model, plus a radar.
    var clfNames = clf.models.map(function (r) { return short(r.name); });
    var metricDefs = [['Accuracy', 'accuracy'], ['Precision', 'precision'], ['Recall', 'recall'], ['F1', 'f1'], ['5-fold accuracy', 'cv_accuracy']];
    var barDefs = [['Train accuracy', 'train_accuracy']].concat(metricDefs.map(function (d) { return d[0] === 'Accuracy' ? ['Test accuracy', 'accuracy'] : d; }));
    list.push(grouped(document.getElementById(key + '-clf'), clfNames, barDefs.map(function (d, i) {
      return { label: d[0], data: clf.models.map(function (r) { return r[d[1]] * 100; }), backgroundColor: SERIES[i], borderRadius: 4 };
    }), {
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12 } }, tooltip: { callbacks: { label: function (x) { return x.dataset.label + ' ' + x.parsed.y.toFixed(1) + '%'; } } } },
      scales: { y: { beginAtZero: true, max: 100, grid: { color: c.line }, title: { display: true, text: 'Percent' } }, x: { grid: { display: false }, ticks: { maxRotation: 40, minRotation: 0 } } }
    }));
    list.push(new Chart(document.getElementById(key + '-radar'), {
      type: 'radar',
      data: { labels: metricDefs.map(function (d) { return d[0]; }), datasets: clf.models.map(function (r, i) {
        return { label: short(r.name), data: metricDefs.map(function (d) { return r[d[1]] * 100; }), borderColor: SERIES[i % SERIES.length], backgroundColor: SERIES[i % SERIES.length] + '22', borderWidth: 2, pointRadius: 2 };
      }) },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12 } } },
        scales: { r: { min: radarMin(clf, metricDefs), max: 100, angleLines: { color: c.line }, grid: { color: c.line }, pointLabels: { color: c.mute, font: { size: 12 } }, ticks: { display: false } } }
      }
    }));

    charts[key] = list;
    drawn[key] = true;
  }

  // Confusion matrices: darker cell = more rows. Diagonal (correct) is lavender, mistakes are coral.
  function shade(key) {
    var pane = document.getElementById('pane-' + key);
    Array.prototype.forEach.call(pane.querySelectorAll('.matrix'), function (table) {
      var matrix = JSON.parse(table.getAttribute('data-matrix'));
      var max = Math.max.apply(null, [].concat.apply([], matrix)) || 1;
      var rows = table.querySelectorAll('tbody tr');
      matrix.forEach(function (row, r) {
        row.forEach(function (v, col) {
          var cell = rows[r].querySelectorAll('td')[col];
          var base = r === col ? '124, 144, 130' : '212, 149, 138';
          cell.style.background = v ? 'rgba(' + base + ',' + (0.22 + 0.78 * v / max).toFixed(2) + ')' : '';
          cell.style.color = v ? '#1a1f2e' : '';
        });
      });
    });
  }

  function show(key) {
    Array.prototype.forEach.call(document.querySelectorAll('.vehicle-pane'), function (p) { p.hidden = p.getAttribute('data-key') !== key; });
    if (!drawn[key]) { draw(key); shade(key); }
  }

  Array.prototype.forEach.call(document.querySelectorAll('input[name="vt"]'), function (r) {
    r.addEventListener('change', function () { if (r.checked) { show(r.value); } });
  });

  // Charts read their colours from the theme, so rebuild them when it changes.
  document.addEventListener('mm-theme', function () {
    Object.keys(charts).forEach(function (key) {
      charts[key].forEach(function (ch) { ch.destroy(); });
      drawn[key] = false;
    });
    show(document.querySelector('input[name="vt"]:checked').value);
  });

  show(document.querySelector('input[name="vt"]:checked').value);
})();
