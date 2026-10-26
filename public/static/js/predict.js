/* Predict page: builds the form from the catalog, posts it, and draws the result. */
(function () {
  'use strict';

  var CONFIG = JSON.parse(document.getElementById('config-data').textContent);
  var CATALOG = JSON.parse(document.getElementById('catalog-data').textContent);

  var form = document.getElementById('predict-form');
  var brandSel = document.getElementById('brand');
  var modelSel = document.getElementById('model');
  var brandOtherWrap = document.getElementById('brand-other-wrap');
  var brandOther = document.getElementById('brand-other');
  var listedNote = document.getElementById('listed-note');
  var specsBox = document.getElementById('specs');
  var choicesBox = document.getElementById('choices');
  var fuelSel = document.getElementById('fuel');
  var priceInput = document.getElementById('price');
  var priceLabel = document.getElementById('price-label');
  var priceUnit = document.getElementById('price-unit');
  var priceHint = document.getElementById('price-hint');
  var acWrap = document.getElementById('ac-wrap');
  var acBox = document.getElementById('ac_on');
  var errorBox = document.getElementById('form-error');
  var submit = document.getElementById('submit');
  var resultArea = document.getElementById('result-area');

  var OTHER = '__other__';
  var vehicle = 'bike';

  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } }
  function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function option(value, label) {
    var o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    return o;
  }

  // ------------------------------------------------------------------- build form
  function buildSpecs() {
    var cfg = CONFIG[vehicle];
    specsBox.textContent = '';
    cfg.specs.forEach(function (spec) {
      var wrap = document.createElement('div');
      wrap.className = 'field';
      var id = 'spec-' + spec.key;
      wrap.innerHTML =
        '<label for="' + id + '">' + esc(spec.label) + '</label>' +
        '<div class="affix"><input id="' + id + '" name="' + spec.key + '" type="number" inputmode="decimal" min="' + spec.min + '" max="' + spec.max + '" step="' + spec.step + '" required>' +
        '<span class="affix-text">' + (spec.unit ? esc(spec.unit) : '#') + '</span></div>' +
        (spec.hint ? '<p class="hint">' + esc(spec.hint) + '</p>' : '');
      specsBox.appendChild(wrap);
      wrap.querySelector('input').addEventListener('input', markCustom);
    });

    choicesBox.textContent = '';
    Object.keys(cfg.choices).forEach(function (key) {
      var wrap = document.createElement('div');
      wrap.className = 'field';
      var label = key === 'category' ? 'Body type' : 'Cooling';
      wrap.innerHTML = '<label for="choice-' + key + '">' + label + '</label><select id="choice-' + key + '" name="' + key + '"></select>';
      var sel = wrap.querySelector('select');
      Object.keys(cfg.choices[key]).forEach(function (v) { sel.appendChild(option(v, cfg.choices[key][v])); });
      sel.addEventListener('change', markCustom);
      choicesBox.appendChild(wrap);
    });
  }

  function buildBrands() {
    brandSel.textContent = '';
    Object.keys(CATALOG[vehicle]).forEach(function (b) { brandSel.appendChild(option(b, b)); });
    brandSel.appendChild(option(OTHER, 'Other brand…'));
    var wanted = CONFIG[vehicle].default.brand;
    brandSel.value = CATALOG[vehicle][wanted] ? wanted : brandSel.options[0].value;
  }

  function buildModels() {
    modelSel.textContent = '';
    var isOther = brandSel.value === OTHER;
    brandOtherWrap.hidden = !isOther;
    if (!isOther) {
      CATALOG[vehicle][brandSel.value].forEach(function (e, i) { modelSel.appendChild(option(String(i), e.model)); });
    }
    modelSel.appendChild(option('', 'My own specs'));
    modelSel.value = isOther ? '' : '0';
    applyModel();
  }

  function currentEntry() {
    if (brandSel.value === OTHER || modelSel.value === '') { return null; }
    return CATALOG[vehicle][brandSel.value][Number(modelSel.value)] || null;
  }

  function applyModel() {
    var entry = currentEntry();
    if (entry) {
      CONFIG[vehicle].specs.forEach(function (spec) {
        document.getElementById('spec-' + spec.key).value = entry[spec.key];
      });
      Object.keys(CONFIG[vehicle].choices).forEach(function (key) {
        var sel = document.getElementById('choice-' + key);
        if (entry[key]) { sel.value = entry[key]; }
      });
      listedNote.hidden = false;
      listedNote.textContent = 'The dataset lists this model at ' + entry.listed + ' ' + CONFIG[vehicle].unit + '. The prediction below comes from its specs, not from that number.';
    } else {
      listedNote.hidden = true;
    }
  }

  function markCustom() {
    if (modelSel.value !== '') {
      modelSel.value = '';
      listedNote.hidden = true;
    }
  }

  function buildFuel() {
    var cfg = CONFIG[vehicle];
    fuelSel.textContent = '';
    Object.keys(cfg.fuels).forEach(function (f) { fuelSel.appendChild(option(f, cfg.fuels[f])); });
    fuelSel.disabled = Object.keys(cfg.fuels).length === 1;
    acWrap.hidden = vehicle !== 'car';
    if (vehicle !== 'car') { acBox.checked = false; }
    updatePrice();
  }

  function updatePrice() {
    var cfg = CONFIG[vehicle];
    var fuel = fuelSel.value;
    var unit = fuel === 'cng' ? 'kg' : cfg.price_unit;
    priceLabel.textContent = (fuel === 'cng' ? 'CNG price' : cfg.price_label);
    priceUnit.textContent = 'per ' + unit;
    priceInput.placeholder = vehicle === 'escooter' ? 'e.g. 8' : 'e.g. 100';
    priceInput.max = vehicle === 'escooter' ? 100 : 300;
    var saved = recall('mm-price-' + fuel);
    priceInput.value = saved && !isNaN(parseFloat(saved)) ? saved : '';
    priceHint.textContent = vehicle === 'escooter'
      ? 'Type your electricity tariff per unit (kWh) from your bill.'
      : 'Type today’s price from your pump. It is remembered on this device.';
  }

  function setVehicle(v) {
    vehicle = v;
    buildSpecs();
    buildBrands();
    buildFuel();
    buildModels();
    errorBox.hidden = true;
  }

  // -------------------------------------------------------------------- events
  Array.prototype.forEach.call(document.querySelectorAll('input[name="vehicle"]'), function (r) {
    r.addEventListener('change', function () { if (r.checked) { setVehicle(r.value); } });
  });
  brandSel.addEventListener('change', buildModels);
  modelSel.addEventListener('change', applyModel);
  fuelSel.addEventListener('change', updatePrice);
  Array.prototype.forEach.call(document.querySelectorAll('#distance-chips .chip'), function (c) {
    c.addEventListener('click', function () { document.getElementById('distance_km').value = c.getAttribute('data-km'); });
  });

  // ------------------------------------------------------------------ rendering
  function emptyState() {
    resultArea.innerHTML =
      '<div class="instrument"><div class="instrument-pad empty">' +
      '<p class="instrument-title">Trip cost</p>' +
      '<div class="odo" id="odo"></div>' +
      '<p class="instrument-sub">Your trip cost appears here. Choose a vehicle and enter today’s fuel price, then press Predict trip cost.</p>' +
      '</div></div>';
    MM.odometer(document.getElementById('odo'), '0.00', '₹', true);
  }

  function bars(rows, key, fmt, nameFn) {
    var max = Math.max.apply(null, rows.map(function (r) { return r[key]; })) || 1;
    return '<ul class="bars">' + rows.map(function (r) {
      return '<li class="bar-row' + (r.is_best || r.selected ? ' best' : '') + '">' +
        '<span class="bar-name">' + nameFn(r) + '</span>' +
        '<span class="bar-track"><span class="bar-fill" data-pct="' + (r[key] / max * 100).toFixed(1) + '"></span></span>' +
        '<span class="bar-val num">' + fmt(r) + '</span></li>';
    }).join('') + '</ul>';
  }

  var ROAD_LABEL = { city: 'City', mixed: 'Mixed', highway: 'Highway' };

  function render(res) {
    var s = res.summary, p = res.inputs, unit = res.unit;
    var cls = res.classification;
    var lowT = res.scale.thresholds[0], highT = res.scale.thresholds[1];
    var agree = cls.votes[cls.consensus];
    var vehicleName = (p.brand + ' ' + (p.model === 'Custom' ? '' : p.model)).trim();

    var costRows = bars(res.regression, 'cost', function (r) { return MM.inr(r.cost, 2); }, function (r) {
      return esc(r.name) + '<small>' + r.real.toFixed(1) + ' ' + esc(unit) + (r.is_best ? ', best model' : '') + '</small>';
    });
    var votesBar = ['Thirsty', 'Balanced', 'Efficient'].map(function (l) {
      return '<span class="v-' + l.toLowerCase() + '" data-pct="' + (cls.votes[l] / cls.models.length * 100).toFixed(1) + '"></span>';
    }).join('');
    var votesLegend = ['Thirsty', 'Balanced', 'Efficient'].map(function (l) {
      return '<span class="pill pill-' + l.toLowerCase() + '">' + l + ' ' + cls.votes[l] + '</span>';
    }).join('');
    var clsRows = '<ul class="bars">' + cls.models.map(function (m) {
      return '<li class="bar-row' + (m.is_best ? ' best' : '') + '">' +
        '<span class="bar-name">' + esc(m.name) + '<small>' + Math.round(m.accuracy * 100) + '% accurate' + (m.is_best ? ', best model' : '') + '</small></span>' +
        '<span class="bar-track"><span class="bar-fill" data-pct="' + m.confidence + '"></span></span>' +
        '<span class="bar-val"><span class="pill pill-' + m.label.toLowerCase() + '">' + m.label + '</span></span></li>';
    }).join('') + '</ul>';
    var roadRows = bars(res.roads, 'cost', function (r) { return MM.inr(r.cost, 2); }, function (r) {
      return ROAD_LABEL[r.road] + '<small>' + r.mileage.toFixed(1) + ' ' + esc(unit) + (r.selected ? ', your choice' : '') + '</small>';
    });
    var warnings = res.warnings.length
      ? '<ul class="warn-list">' + res.warnings.map(function (w) { return '<li>' + esc(w) + '</li>'; }).join('') + '</ul>' : '';

    resultArea.innerHTML =
      '<div class="instrument"><div class="instrument-pad result-inner">' +
        '<div><p class="instrument-title">Trip cost for ' + MM.group(s.distance, s.distance % 1 ? 1 : 0) + ' km on ' + esc(vehicleName) + '</p>' +
        '<div class="odo" id="odo"></div>' +
        '<p class="instrument-sub">At ' + MM.inr(s.price, 2) + ' per ' + esc(res.price_unit) + ', using ' + esc(s.best_model) + '. All six models land between <strong>' + MM.inr(s.cost_min, 2) + '</strong> and <strong>' + MM.inr(s.cost_max, 2) + '</strong>.</p></div>' +
        '<div class="gauge-wrap"><svg class="gauge" id="gauge" aria-hidden="true"></svg>' +
        '<div class="gauge-caption"><span class="pill pill-' + cls.consensus.toLowerCase() + '">' + cls.consensus + '</span><span class="muted small">' + agree + ' of ' + cls.models.length + ' classifiers agree. Efficient is above ' + highT.toFixed(1) + ' ' + esc(unit) + ', Thirsty is below ' + lowT.toFixed(1) + '.</span></div></div>' +
        '<div class="budget"><div><span>Each month</span><strong class="num">' + MM.inr(s.monthly, 0) + '</strong><small>' + MM.group(s.km_per_month, 0) + ' km over ' + s.days_per_month + ' days</small></div>' +
        '<div><span>Each year</span><strong class="num">' + MM.inr(s.yearly, 0) + '</strong><small>' + MM.group(s.km_per_month * 12, 0) + ' km</small></div></div>' +
        '<div class="explain"><div><strong class="num">' + s.rated.toFixed(1) + '</strong>rated ' + esc(unit) + '</div><div aria-hidden="true">×' + res.factor.toFixed(2) + '</div><div><strong class="num">' + s.real.toFixed(1) + '</strong>on your roads</div></div>' +
        '<p class="instrument-sub">Cost per km is ' + MM.inr(s.cost_per_km, 2) + '. You would use about ' + s.fuel_used.toFixed(2) + ' ' + esc(res.price_unit) + '.' + (s.listed ? ' The dataset lists this exact model at ' + s.listed + ' ' + esc(unit) + '.' : '') + '</p>' +
      '</div></div>' +
      '<div class="panel panel-pad">' +
        '<div class="tabs" role="tablist" aria-label="Result details">' +
          '<button type="button" role="tab" id="t-cost" aria-selected="true" aria-controls="p-cost">Cost by model</button>' +
          '<button type="button" role="tab" id="t-class" aria-selected="false" aria-controls="p-class" tabindex="-1">Efficiency class</button>' +
          '<button type="button" role="tab" id="t-road" aria-selected="false" aria-controls="p-road" tabindex="-1">Road types</button>' +
        '</div>' +
        '<div role="tabpanel" id="p-cost" aria-labelledby="t-cost">' + costRows +
          '<p class="note">Sorted by how well each model scored on unseen data. <a href="/results">See the scores</a>.</p></div>' +
        '<div role="tabpanel" id="p-class" aria-labelledby="t-class" hidden>' +
          '<div class="votes" aria-hidden="true">' + votesBar + '</div><div class="vote-legend">' + votesLegend + '</div>' + clsRows +
          '<p class="note">Bars show how sure each classifier is.</p></div>' +
        '<div role="tabpanel" id="p-road" aria-labelledby="t-road" hidden>' + roadRows +
          '<p class="note">Same vehicle and trip, different roads. City traffic costs the most.</p></div>' +
        warnings +
      '</div>';

    MM.odometer(document.getElementById('odo'), MM.group(s.cost, 2), '₹');
    MM.gauge(document.getElementById('gauge'), res.scale, s.rated, 'Rated mileage ' + s.rated.toFixed(1) + ' ' + unit + ' among ' + res.scale.rows + ' vehicles');
    MM.fillBars(resultArea);
    wireTabs();
  }

  function wireTabs() {
    var tabs = resultArea.querySelectorAll('[role="tab"]');
    function select(tab) {
      Array.prototype.forEach.call(tabs, function (t) {
        var on = t === tab;
        t.setAttribute('aria-selected', on);
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
      });
      MM.fillBars(resultArea);
    }
    Array.prototype.forEach.call(tabs, function (t, i) {
      t.addEventListener('click', function () { select(t); });
      t.addEventListener('keydown', function (e) {
        var n = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (n) { var next = tabs[(i + n + tabs.length) % tabs.length]; select(next); next.focus(); e.preventDefault(); }
      });
    });
  }

  // -------------------------------------------------------------------- submit
  function showError(msg, field) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    if (field) { field.setAttribute('aria-invalid', 'true'); field.focus(); }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    errorBox.hidden = true;
    Array.prototype.forEach.call(form.querySelectorAll('[aria-invalid]'), function (n) { n.removeAttribute('aria-invalid'); });

    var cfg = CONFIG[vehicle];
    var payload = {
      vehicle: vehicle,
      fuel: fuelSel.value,
      road_type: form.querySelector('input[name="road_type"]:checked').value,
      load_kg: form.load_kg.value,
      vehicle_age: form.vehicle_age.value,
      distance_km: form.distance_km.value,
      price: priceInput.value,
      days_per_month: form.days_per_month.value,
      ac_on: acBox.checked,
      service_overdue: document.getElementById('service_overdue').checked
    };
    if (brandSel.value === OTHER) {
      payload.brand = brandOther.value.trim();
      payload.model = 'Custom';
    } else {
      payload.brand = brandSel.value;
      var entry = currentEntry();
      payload.model = entry ? entry.model : 'Custom';
    }
    cfg.specs.forEach(function (s) { payload[s.key] = document.getElementById('spec-' + s.key).value; });
    Object.keys(cfg.choices).forEach(function (k) { payload[k] = document.getElementById('choice-' + k).value; });

    // Friendly checks before the request (the server validates again).
    if (!payload.brand) { return showError('Type your brand name.', brandOther); }
    if (payload.price === '' || isNaN(parseFloat(payload.price)) || parseFloat(payload.price) <= 0) {
      return showError('Enter today’s fuel price so the cost can be worked out.', priceInput);
    }
    for (var i = 0; i < cfg.specs.length; i++) {
      var f = document.getElementById('spec-' + cfg.specs[i].key);
      var v = parseFloat(f.value);
      if (isNaN(v) || v < cfg.specs[i].min || v > cfg.specs[i].max) {
        return showError(cfg.specs[i].label + ' must be between ' + cfg.specs[i].min + ' and ' + cfg.specs[i].max + '.', f);
      }
    }

    submit.disabled = true;
    submit.textContent = 'Predicting…';
    fetch('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (r) {
        if (!r.ok) { return showError(r.body.error || 'Something went wrong. Try again.'); }
        store('mm-price-' + payload.fuel, payload.price);
        render(r.body);
        if (window.matchMedia('(max-width: 960px)').matches) { resultArea.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      })
      .catch(function () { showError('Could not reach the server. Check that app.py is still running.'); })
      .then(function () { submit.disabled = false; submit.textContent = 'Predict trip cost'; });
  });

  setVehicle('bike');
  emptyState();
})();
