// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the MIT LICENSE.txt file.

(function() {
// Favicon.
const matcher = window.matchMedia('(prefers-color-scheme: dark)');
function onUpdate() {
  const prevIcon = document.querySelector('link#favicon');
  if (prevIcon) {
    prevIcon.remove();
  }
  const icon = document.createElement('link');
  icon.rel = 'icon';
  icon.id = 'favicon';
  icon.href = matcher.matches ? 'static/img/check_logo_dark.png' :
                                'static/img/check_logo_light.png';
  document.head.append(icon);
}
matcher.addListener(onUpdate);
onUpdate();

// Color mode of the page.
if (localStorage.getItem('data-color-mode') === 'dark' ||
    (matcher.matches && !localStorage.getItem('data-color-mode'))) {
  document.documentElement.setAttribute('data-color-mode', 'dark');
}
})();
