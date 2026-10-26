/* Home page: the live demo. Sliders re-price a real predicted mileage in the browser. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('demo-data').textContent);
  var km = document.getElementById('demo-km');
  var price = document.getElementById('demo-price');
  var odo = document.getElementById('demo-odo');
  var sub = document.getElementById('demo-sub');
  var kmOut = document.getElementById('demo-km-out');
  var priceOut = document.getElementById('demo-price-out');

  function update() {
    var d = parseFloat(km.value), p = parseFloat(price.value);
    var cost = d / data.real * p;
    MM.odometer(odo, MM.group(cost, 2), '₹');
    kmOut.textContent = d + ' km';
    priceOut.textContent = '₹' + p + ' per litre';
    sub.innerHTML = '';
    var strong = document.createElement('strong');
    strong.textContent = data.real.toFixed(1) + ' ' + data.unit;
    sub.appendChild(strong);
    sub.appendChild(document.createTextNode(' real-road mileage from the ' + data.model + ' model. Its rated mileage is ' + data.rated.toFixed(1) + ' ' + data.unit + ', which the classifiers call ' + data.efficiency + '.'));
  }

  MM.gauge(document.getElementById('demo-gauge'), data.scale, data.rated, 'Rated mileage ' + data.rated.toFixed(1) + ' ' + data.unit);
  km.addEventListener('input', update);
  price.addEventListener('input', update);
  // Start the odometer from zero so it rolls up once on load.
  MM.odometer(odo, '0.00', '₹');
  requestAnimationFrame(function () { requestAnimationFrame(update); });
})();
