/* Runs in <head> so the saved theme is applied before the page paints. */
try {
  var saved = localStorage.getItem('mm-theme');
  if (saved === 'light' || saved === 'dark') {
    document.documentElement.setAttribute('data-theme', saved);
  }
} catch (e) { /* storage blocked: follow the system theme */ }
