// Apply before styles load to avoid a flash of the other theme.
(() => {
  const key = 'careeros.theme';
  let theme = 'dark';
  try { const saved = localStorage.getItem(key); if (saved === 'light' || saved === 'dark') theme = saved; } catch {}
  function apply(next) {
    theme = next;
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0f0f0f' : '#ffffff');
    const button = document.getElementById('theme-toggle');
    if (button) {
      const target = theme === 'dark' ? 'claro' : 'oscuro';
      button.setAttribute('aria-label', 'Activar modo ' + target);
      document.getElementById('theme-label').textContent = 'Modo ' + target;
      document.getElementById('theme-icon').textContent = theme === 'dark' ? '☼' : '☾';
    }
  }
  apply(theme);
  window.addEventListener('storage', event => { if (event.key === key) apply(event.newValue === 'light' ? 'light' : 'dark'); });
  document.addEventListener('DOMContentLoaded', () => {
    apply(theme);
    document.getElementById('theme-toggle').addEventListener('click', () => {
      apply(theme === 'dark' ? 'light' : 'dark');
      try { localStorage.setItem(key, theme); } catch {}
    });
    const menu = document.getElementById('nav-toggle');
    const small = () => window.matchMedia('(max-width: 760px)').matches;
    const medium = () => window.matchMedia('(max-width: 1100px)').matches;
    function expanded() { return small() ? document.body.classList.contains('nav-open') : medium() ? document.body.classList.contains('nav-expanded') : !document.body.classList.contains('nav-collapsed'); }
    function updateMenu() { menu.setAttribute('aria-expanded', String(expanded())); menu.setAttribute('aria-label', expanded() ? 'Contraer menú' : 'Abrir menú'); }
    function closeMenu() { document.body.classList.remove('nav-open'); updateMenu(); }
    menu.addEventListener('click', () => { document.body.classList.toggle(small() ? 'nav-open' : medium() ? 'nav-expanded' : 'nav-collapsed'); updateMenu(); });
    document.getElementById('nav-scrim').addEventListener('click', closeMenu);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
    document.addEventListener('click', event => { if (small() && event.target.closest('[data-view]')) closeMenu(); });
    window.addEventListener('resize', () => { if (!small()) document.body.classList.remove('nav-open'); updateMenu(); });
    updateMenu();
  });
})();
