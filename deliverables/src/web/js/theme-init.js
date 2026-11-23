// Runs before first paint: restore the saved colour theme and mark that scripts are available.
(function () {
  var root = document.documentElement;
  try {
    var saved = window.localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') {
      root.setAttribute('data-theme', saved);
    }
  } catch (e) {
    // Storage can be unavailable (private mode); the theme then follows the system setting.
  }
  root.classList.add('js');
})();
