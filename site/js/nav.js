/* Mobile nav toggle */

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.sg-header__toggle');
  const nav    = document.querySelector('.sg-header__nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', () => {
    nav.classList.toggle('open');
    const expanded = nav.classList.contains('open');
    toggle.setAttribute('aria-expanded', expanded);
  });
});
