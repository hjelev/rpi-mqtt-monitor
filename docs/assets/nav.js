// Mobile sidebar drawer toggle — no framework.
(function () {
  var btn = document.querySelector('.hamburger');
  var sidebar = document.querySelector('.sidebar');
  var backdrop = document.querySelector('.backdrop');
  if (!btn || !sidebar) return;

  function close() {
    sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('show');
  }
  function toggle() {
    sidebar.classList.toggle('open');
    if (backdrop) backdrop.classList.toggle('show');
  }

  btn.addEventListener('click', toggle);
  if (backdrop) backdrop.addEventListener('click', close);
  sidebar.addEventListener('click', function (e) {
    if (e.target.tagName === 'A') close();
  });
})();
