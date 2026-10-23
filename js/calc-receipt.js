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
        var qm = parts[0].match(/× ([\d\s\u00a0]+) шт/);
        goods.push({ name: parts[0].replace(/ по [\d\s,\u00a0]+₽$/, '').replace(/,? (на магните|в пакете)/g, ''), raw: parts[0], qty: qm ? num(qm[1]) : 0, sum: num(parts[1]), subs: [] });
      });
    } else {
      var qty = Number(q.get('qty')) || 0;
      var pr = num(q.get('per'));
      goods.push({ name: (q.get('size') ? q.get('size') + ' × ' : '') + qty.toLocaleString('ru-RU') + ' шт' + (pr ? ' по ' + unit(pr / k) : ''), raw: '', qty: qty, sum: Math.round(pr * qty), subs: [] });
    }
    var goodsSum = goods.reduce(function (s, g) { return s + g.sum; }, 0);
    var cap = function (s) { return s.replace(/^./, function (c) { return c.toUpperCase(); }); };

    // Наценки — под каждой позицией, своей суммой
    goods.forEach(function (g) {
      g.base = Math.round(g.sum / k);
      var ts = Math.round(g.base * t);
      if (t && term) g.subs.push([cap(term.dataset.name || 'срочное изготовление') + ' (+' + Math.round(t * 100) + '%)', ts]);
      if (p) g.subs.push(['Персонализация (+' + Math.round(p * 100) + '%)', g.sum - g.base - ts]);
    });

    // Допуслуги: штучные (магнит, упаковка, подставки) — под позициями, остальные — в конце
    var extras = 0, orderRows = [];
    (q.get('opts') || '').split(', ').forEach(function (o) {
      var mm = o.match(/^(.*?)\s*\+\s*([\d\s\u00a0]+)\s*₽$/);
      if (!mm) return;
      var v = num(mm[2]), name = cap(mm[1]);
      extras += v;
      if (!/магнит|упаковка|подставк/i.test(name)) { orderRows.push([name, v]); return; }
      var marker = /магнит/i.test(name) ? 'на магните' : /пакет/i.test(name) ? 'в пакете' : '';
      var elig = goods.filter(function (g) { return marker && g.raw.indexOf(marker) > -1; });
      if (!elig.length) elig = goods;
      var eq = elig.reduce(function (s, g) { return s + g.qty; }, 0) || 1, left = v;
      elig.forEach(function (g, n) {
        var part = n === elig.length - 1 ? left : Math.round(v * g.qty / eq);
        left -= part;
        g.subs.push([name, part]);
      });
    });

    var rows = [];
    goods.forEach(function (g) {
      rows.push([g.name, g.base, '']);
      g.subs.forEach(function (s) { rows.push(['+ ' + s[0].replace(/^./, function (c) { return c.toLowerCase(); }), s[1], 'sub']); });
    });
    orderRows.forEach(function (r) { rows.push([r[0], r[1], 'order']); });
    // Минимальная сумма заказа
    var rest = total - goodsSum - extras;
    if (rest > 5) rows.push(['Доплата до минимальной суммы заказа ' + money(MIN_ORDER), rest, 'order']);

    box.innerHTML = rows.map(function (r) {
      return '<li' + (r[2] ? ' class="is-' + r[2] + '"' : '') + '><span>' + esc(r[0]) + '</span><b>' + money(r[1]) + '</b></li>';
    }).join('') + '<li class="calc-receipt-total"><span>Итого</span><b>' + money(total) + '</b></li>';
  }

  new MutationObserver(render).observe(link, { attributes: true, attributeFilter: ['href'] });
  render();
})();
