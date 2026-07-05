/* shared sidebar / topbar JS — wires up cmd-k visual, tag clicks, etc. */
(function () {
  // Click-to-flash cmd-k (no real modal in this prototype)
  document.querySelectorAll('.cmdk').forEach(function (el) {
    el.addEventListener('click', function () {
      el.style.borderColor = 'var(--fg)';
      setTimeout(function () { el.style.borderColor = ''; }, 220);
    });
  });

  // Keyboard ⌘K / Ctrl+K visual highlight
  document.addEventListener('keydown', function (e) {
    var isK = (e.key === 'k' || e.key === 'K');
    if (isK && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      var el = document.querySelector('.cmdk');
      if (!el) return;
      el.style.borderColor = 'var(--fg)';
      el.style.boxShadow = '0 0 0 3px oklch(82% 0.08 150 / 0.4)';
      setTimeout(function () {
        el.style.borderColor = '';
        el.style.boxShadow = '';
      }, 300);
    }
  });
})();
