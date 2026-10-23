// Накопительная заявка: расчёты с разных страниц собираются в одну заявку (хранятся в браузере)
(function () {
  var KEY = 'pz-request';
  var MIN_ORDER = 3000;
  var DELIVERY = [
    { v: 0, name: 'Самовывоз', note: 'бесплатно' },
    { v: 1000, name: 'В пределах МКАД', note: '+1 000 ₽' },
    { v: 750, name: 'До транспортной компании', note: '+750 ₽' }
  ];

  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; } }
  function save(list) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {} render(); }
  function num(s) { return Number(String(s).replace(/[^\d,]/g, '').replace(',', '.')) || 0; }
  function money(v) { return Math.round(v).toLocaleString('ru-RU') + ' ₽'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  // ---------- Значок «Заявка (N)»: в оранжевой полосе и плавающий на телефоне ----------
  var home = /(\/|index\.html)$/.test(location.pathname) ? '#order' : 'index.html#order';
  var badges = [];
  function makeBadge(cls) {
    var a = document.createElement('a');
    a.className = 'basket-link ' + cls;
    a.href = home;
    a.innerHTML = '<svg aria-hidden="true"><use href="#i-calc"/></svg><span>Моя заявка</span><b></b>';
    badges.push(a);
    return a;
  }
  var sub = document.querySelector('.sub-nav-inner');
  if (sub) sub.appendChild(makeBadge('basket-sub'));
  document.body.appendChild(makeBadge('basket-float'));

  // ---------- Кнопка «Добавить в заявку» в калькуляторе ----------
  var order = document.querySelector('.calc-order');
  var receipt = document.querySelector('.calc-receipt');
  function currentCalc() {
    receipt = receipt || document.querySelector('.calc-receipt');
    if (!receipt || !order) return null;
    var q = new URLSearchParams((order.getAttribute('href').split('?')[1] || '').split('#')[0]);
    var rows = [], sum = 0;
    Array.prototype.forEach.call(receipt.querySelectorAll('li'), function (li) {
      if (li.classList.contains('calc-receipt-total')) return;
      var name = li.querySelector('span').textContent.trim(), v = num(li.querySelector('b').textContent);
      // Доставку и доплату до минимума считаем один раз на всю заявку
      if (/^Доставка|^Доплата до минимальной/.test(name)) return;
      rows.push({ name: name, sum: v, sub: li.classList.contains('is-sub') });
      sum += v;
    });
    var term = (q.get('opts') || '').split(', ').filter(function (o) { return /срочн|рабочих дн/.test(o) && !/\+/.test(o); })[0] || '';
    return { id: Date.now(), item: q.get('item') || document.title, page: location.pathname.split('/').pop() || 'index.html', rows: rows, sum: sum, term: term };
  }
  var toast = document.createElement('div');
  toast.className = 'basket-toast';
  document.body.appendChild(toast);
  function showToast(text) {
    toast.innerHTML = text;
    toast.classList.add('is-visible');
    clearTimeout(showToast.t);
    showToast.t = setTimeout(function () { toast.classList.remove('is-visible'); }, 3500);
  }
  var hint = null;
  function hintText(n) {
    return n
      ? 'В заявке уже ' + n + ' ' + plural(n) + '. <b>«Оформить заказ»</b> добавит этот расчёт в заявку и перейдёт к отправке.<br><b>«Добавить в заявку»</b> — если хотите добавить его и посчитать ещё товары.'
      : '<b>«Оформить заказ»</b> — если нужен только этот товар.<br><b>«Добавить в заявку»</b> — если хотите заказать несколько товаров одной заявкой, например значки и кружки.';
  }
  function plural(n) { var a = n % 10, b = n % 100; return a === 1 && b !== 11 ? 'товар' : a >= 2 && a <= 4 && (b < 12 || b > 14) ? 'товара' : 'товаров'; }
  if (order && document.querySelector('.calc-receipt, #calc')) {
    var add = document.createElement('button');
    add.type = 'button';
    add.className = 'btn btn--ghost-light calc-to-basket';
    add.innerHTML = '+ Добавить в заявку';
    order.insertAdjacentElement('afterend', add);
    hint = document.createElement('p');
    hint.className = 'calc-basket-hint';
    add.insertAdjacentElement('afterend', hint);
    add.addEventListener('click', function () {
      var c = currentCalc();
      if (!c || !c.rows.length) return;
      var list = load(); list.push(c); save(list);
      showToast('<b>Добавлено в заявку</b> ' + esc(c.item) + ' — ' + money(c.sum) + '<br><a href="index.html#order">Оформить заявку (' + list.length + ')</a> или посчитайте другие товары');
    });
    // Если в заявке уже есть товары — «Оформить заказ» добавляет текущий расчёт к ним
    order.addEventListener('click', function (e) {
      if (!load().length) return;
      var c = currentCalc();
      if (c && c.rows.length) { var list = load(); list.push(c); save(list); }
      e.preventDefault();
      e.stopImmediatePropagation();
      location.href = 'index.html#order';
    }, true);
  }

  // ---------- Блок заявки в форме на главной ----------
  var form = document.getElementById('request-form');
  var box = null, deliveryValue = 0;
  if (form) {
    box = document.createElement('div');
    box.className = 'basket-box';
    box.hidden = true;
    var anchor = form.querySelector('.order-summary');
    (anchor || form.firstChild).insertAdjacentElement(anchor ? 'afterend' : 'beforebegin', box);
    box.addEventListener('click', function (e) {
      var b = e.target.closest('[data-remove]');
      if (!b) return;
      var list = load().filter(function (it) { return String(it.id) !== b.dataset.remove; });
      save(list);
    });
    box.addEventListener('change', function (e) {
      if (e.target.name === 'basket-delivery') { deliveryValue = Number(e.target.value); render(); }
    });
    // После успешной отправки — очищаем заявку
    new MutationObserver(function () { if (form.classList.contains('is-sent')) save([]); }).observe(form, { attributes: true, attributeFilter: ['class'] });
    if (/[?&]sent=1/.test(location.search)) save([]);
  }

  function text(list, delivery, total) {
    var out = [];
    list.forEach(function (it, n) {
      out.push((n + 1) + '. ' + it.item + (it.term ? ' (' + it.term + ')' : ''));
      it.rows.forEach(function (r) { out.push((r.sub ? '      ' : '   • ') + r.name + ' — ' + money(r.sum)); });
      out.push('   Сумма: ' + money(it.sum));
    });
    var d = DELIVERY.filter(function (x) { return x.v === delivery; })[0];
    out.push('Доставка: ' + d.name + (delivery ? ' — ' + money(delivery) : ''));
    out.push('Итого по заявке: ' + money(total));
    return out.join('\n');
  }

  function render() {
    var list = load();
    badges.forEach(function (b) { b.hidden = !list.length; b.querySelector('b').textContent = list.length; });
    if (hint) hint.innerHTML = hintText(list.length);
    if (!box) return;
    box.hidden = !list.length;
    if (!list.length) { box.innerHTML = ''; fillMessage(''); return; }
    var goods = list.reduce(function (s, it) { return s + it.sum; }, 0);
    var rest = Math.max(0, MIN_ORDER - goods);
    var total = goods + rest + deliveryValue;
    box.innerHTML = '<div class="basket-head"><b>Ваша заявка</b><small>' + list.length + ' ' + plural(list.length) + '</small></div>' +
      list.map(function (it) {
        return '<div class="basket-item"><div class="basket-item-top"><a href="' + esc(it.page) + '#calc">' + esc(it.item) + '</a><b>' + money(it.sum) + '</b>' +
          '<button type="button" data-remove="' + it.id + '" aria-label="Убрать из заявки">×</button></div>' +
          (it.term ? '<small class="basket-term">' + esc(it.term) + '</small>' : '') +
          '<ul>' + it.rows.map(function (r) { return '<li' + (r.sub ? ' class="is-sub"' : '') + '><span>' + esc(r.name) + '</span><span>' + money(r.sum) + '</span></li>'; }).join('') + '</ul></div>';
      }).join('') +
      '<div class="basket-delivery"><span>Доставка всей заявки</span><div>' + DELIVERY.map(function (d) {
        return '<label><input type="radio" name="basket-delivery" value="' + d.v + '"' + (d.v === deliveryValue ? ' checked' : '') + '><span>' + d.name + '<small>' + d.note + '</small></span></label>';
      }).join('') + '</div></div>' +
      (rest ? '<p class="basket-min">Доплата до минимальной суммы заказа 3 000 ₽: ' + money(rest) + '</p>' : '') +
      '<div class="basket-total"><span>Итого по заявке</span><b>' + money(total) + '</b></div>' +
      '<input type="hidden" name="Заявка с сайта" value="' + esc(text(list, deliveryValue, total)) + '">' +
      '<a class="basket-more" href="index.html#catalog">+ Добавить ещё товар</a>';
    fillMessage('Хочу заказать:\n' + text(list, deliveryValue, total));
  }

  // Текст заявки в поле сообщения: при каждом изменении заменяем прежний блок новым,
  // не трогая то, что клиент дописал сам
  var lastBlock = '';
  function fillMessage(block) {
    var msg = document.getElementById('f-message');
    if (!msg) return;
    var v = msg.value;
    if (lastBlock && v.indexOf(lastBlock) !== -1) v = v.replace(lastBlock, function () { return block; });
    else if (!block) return;
    else if (!v.trim()) v = block + '\n\nМакет прикладываю.';
    else v = block + '\n\n' + v;
    if (!block) v = v.replace(/^\s+/, '').replace(/^Макет прикладываю\.\s*$/, '');
    msg.value = v;
    lastBlock = block;
  }

  window.addEventListener('storage', function (e) { if (e.key === KEY) render(); });
  render();
})();
