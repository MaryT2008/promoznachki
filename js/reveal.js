// Плавное появление блоков при прокрутке: лёгкий подъём и проявление
(function () {
  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var SELECTORS = [
    '.section-head', '.section-title--left',
    '.catalog-grid > li', '.adv-card', '.product-card', '.work',
    '.feature-grid > li', '.price-card', '.price-table-wrap', '.calc-card',
    '.template-card', '.pp-gallery-grid > li', '.seo-article', '.faq',
    '.chameleon-how-img', '.chameleon-steps > li', '.delivery-card', '.delivery-note',
    '.contacts-card', '.contacts-map', '.contacts-req', '.faq-group', '.policy-sec',
    '.stats-grid > *', '.steps > li', '.cta-card', '.request-card'
  ].join(',');

  var vh = window.innerHeight;
  var items = Array.prototype.filter.call(document.querySelectorAll(SELECTORS), function (el) {
    // То, что уже видно на первом экране, не прячем — без «мигания»
    return el.getBoundingClientRect().top > vh * 0.92 && !el.closest('.reveal');
  });

  // Соседние карточки в одном ряду появляются друг за другом
  items.forEach(function (el) {
    var siblings = Array.prototype.filter.call(el.parentNode.children, function (s) { return items.indexOf(s) > -1; });
    var i = siblings.indexOf(el);
    el.style.transitionDelay = (i > 0 ? Math.min(i, 5) * 80 : 0) + 'ms';
    el.classList.add('reveal');
  });

  function done(e) {
    if (e.target !== this) return;
    this.classList.remove('reveal', 'is-in');
    this.style.transitionDelay = '';
    this.removeEventListener('transitionend', done);
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var el = entry.target;
      io.unobserve(el);
      el.addEventListener('transitionend', done);
      el.classList.add('is-in');
      // Подстраховка, если transitionend не придёт
      setTimeout(function () { done.call(el, { target: el }); }, 1600);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

  items.forEach(function (el) { io.observe(el); });
})();
