// Runs before first paint: restore the saved colour theme and mark that scripts are available.
(function () {
  var root = document.documentElement;
  try {
    var saved = window.localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') {
      root.setAttribute('data-theme', saved);
    } else if (saved !== 'auto') {
      root.setAttribute('data-theme', 'light'); // default: the light corporate theme
    }
  } catch (e) {
    root.setAttribute('data-theme', 'light'); // storage unavailable: light default
  }
  root.classList.add('js');
})();
