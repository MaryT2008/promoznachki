// Состав заказа по пунктам на оранжевой панели калькулятора.
// Данные берём из ссылки «Оформить заказ» — её собирает калькулятор каждой страницы.
(function () {
  var link = document.querySelector('.calc-order');
  var per = document.getElementById('calc-per');
  if (!link || !per) return;
  var box = document.createElement('ul');
  box.className = 'calc-receipt';
  per.insertAdjacentElement('afterend', box);
  var breakdown = document.getElementById('calc-breakdown');
  if (breakdown) breakdown.hidden = true;
  var MIN_ORDER = 3000;

  function num(s) { return Number(String(s).replace(/[^\d,]/g, '').replace(',', '.')) || 0; }
  function money(v) { return Math.round(v).toLocaleString('ru-RU') + ' ₽'; }
  function unit(v) { var r = Math.round(v * 100) / 100; var f = r % 1 ? 2 : 0; return r.toLocaleString('ru-RU', { minimumFractionDigits: f, maximumFractionDigits: f }) + '\u00a0₽'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function render() {
    var href = link.getAttribute('href') || '';
    var q = new URLSearchParams(href.split('?')[1] ? href.split('?')[1].split('#')[0] : '');
    if (!q.get('item')) { box.innerHTML = ''; return; }
    var total = num(q.get('total'));

    // Наценки, которые уже включены в цену за штуку
    var term = document.querySelector('input[name="calc-term"]:checked');
    var t = term ? Number(term.value) || 0 : 0;
    var personalBox = document.getElementById('calc-personal');
    var p = 0;
    if (personalBox && personalBox.checked) {
      var m = (personalBox.parentNode.textContent || '').match(/\+(\d+)\s*%/);
      p = m ? Number(m[1]) / 100 : 0.3;
    }
    var k = 1 + t + p;

    // Товарные позиции
    var goods = [];
    if (q.get('lines')) {
      q.get('lines').split('; ').forEach(function (l) {
        var parts = l.split(' = ');
        goods.push({ name: parts[0].replace(/ по [\d\s, ]+₽$/, ''), sum: num(parts[1]) });
      });
    } else {
      var qty = Number(q.get('qty')) || 0;
      var pr = num(q.get('per'));
      goods.push({ name: (q.get('size') ? q.get('size') + ' × ' : '') + qty.toLocaleString('ru-RU') + ' шт' + (pr ? ' по ' + unit(pr / k) : ''), sum: Math.round(pr * qty) });
    }
    var goodsSum = goods.reduce(function (s, g) { return s + g.sum; }, 0);
    var baseSum = Math.round(goodsSum / k);

    var rows = [];
    goods.forEach(function (g) { rows.push([g.name, Math.round(g.sum / k)]); });
    var termSum = Math.round(baseSum * t);
    var persSum = goodsSum - baseSum - termSum;
    if (t && term) rows.push([(term.dataset.name || 'срочное изготовление').replace(/^./, function (c) { return c.toUpperCase(); }) + ' (+' + Math.round(t * 100) + '%)', termSum]);
    if (p) rows.push(['Персонализация (+' + Math.round(p * 100) + '%)', persSum]);

    // Дополнительные услуги с суммой: «упаковка в пакет +500 ₽»
    var extras = 0;
    (q.get('opts') || '').split(', ').forEach(function (o) {
      var mm = o.match(/^(.*?)\s*\+\s*([\d\s ]+)\s*₽$/);
      if (!mm) return;
      var v = num(mm[2]);
      extras += v;
      rows.push([mm[1].replace(/^./, function (c) { return c.toUpperCase(); }), v]);
    });
    // Минимальная сумма заказа
    var rest = total - goodsSum - extras;
    if (rest > 5) rows.push(['Доплата до минимальной суммы заказа ' + money(MIN_ORDER), rest]);

    box.innerHTML = rows.map(function (r) {
      return '<li><span>' + esc(r[0]) + '</span><b>' + money(r[1]) + '</b></li>';
    }).join('') + '<li class="calc-receipt-total"><span>Итого</span><b>' + money(total) + '</b></li>';
  }

  new MutationObserver(render).observe(link, { attributes: true, attributeFilter: ['href'] });
  render();
})();
