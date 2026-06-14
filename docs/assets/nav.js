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

// GitHub-style copy button for code blocks marked with .codeblock
(function () {
  var COPY_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg>';
  var CHECK_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/></svg>';

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'absolute';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); }
      catch (e) { reject(e); }
      document.body.removeChild(ta);
    });
  }

  document.querySelectorAll('.codeblock').forEach(function (block) {
    var code = block.querySelector('pre code') || block.querySelector('pre');
    if (!code) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.setAttribute('aria-label', 'Copy to clipboard');
    btn.innerHTML = COPY_ICON;
    block.appendChild(btn);

    var resetTimer;
    btn.addEventListener('click', function () {
      copyText(code.textContent).then(function () {
        btn.innerHTML = CHECK_ICON;
        btn.classList.add('copied');
        btn.setAttribute('aria-label', 'Copied!');
        clearTimeout(resetTimer);
        resetTimer = setTimeout(function () {
          btn.innerHTML = COPY_ICON;
          btn.classList.remove('copied');
          btn.setAttribute('aria-label', 'Copy to clipboard');
        }, 2000);
      });
    });
  });
})();
