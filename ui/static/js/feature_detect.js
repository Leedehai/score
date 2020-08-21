// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the LICENSE.txt file.

/**
 * Run this function after page load, because it requires a <body>
 * tag to insert nodes, if it found errors.
 * Do not throw an Error in this function, otherwise the Error
 * can't stop the HTML from continuing to be rendered.
 */
function throwOnMissingFeatures() {
  const makeMessageDom = (what) => {
    return '<h1 style="font-size: 24px; font-weight: bold;">' +
        'Oh.. your browser is not compliant with the modern Web ' +
        `Standard: it does not support ${what}.</h1>`;
  };
  const BROWSER_ERRS = {
    // Though checking the user agent string is considered a bad
    // practice, let me make an exception for Internet Explorer.
    'internet_explorer':
        '<h1 style="font-size: 24px; font-weight: bold;">Oh.. ' +
        'your browser is Internet Explorer. Too many features ' +
        'required by the modern Web Standard are missing.</h1>',
    // Feature detection errors.
    'js-object-entries': makeMessageDom('JavaScript Object.entries()'),
    'css-custom-properties': makeMessageDom('CSS custom properties'),
    'css-grid': makeMessageDom('CSS grid'),
    'api-custom-elements': makeMessageDom('API CustomElementRegistry'),
    'api-scroll-into-view': makeMessageDom('API Element.scrollIntoView()'),
    'api-intersection-observer': makeMessageDom('API IntersectionObserver'),
  };
  const browserFeatureErrs = [];
  if (navigator.userAgent.includes('MSIE')) {
    browserFeatureErrs.push(BROWSER_ERRS['internet_explorer']);
  }
  if (Object.entries === undefined) {
    browserFeatureErrs.push(BROWSER_ERRS['js-object-entries']);
  }
  if (!(window.CSS && CSS.supports('color', 'var(--random-name)'))) {
    browserFeatureErrs.push(BROWSER_ERRS['css-custom-properties']);
  }
  if (!(window.CSS && CSS.supports('display', 'grid'))) {
    browserFeatureErrs.push(BROWSER_ERRS['css-grid']);
  }
  if (!window.customElements) {
    browserFeatureErrs.push(BROWSER_ERRS['api-custom-elements']);
  }
  if (!document.createElement('div').scrollIntoView) {
    browserFeatureErrs.push(BROWSER_ERRS['api-scroll-into-view']);
  }
  if (!window.IntersectionObserver) {
    browserFeatureErrs.push(BROWSER_ERRS['api-intersection-observer']);
  }
  if (browserFeatureErrs.length) {
    const body = document.querySelector('body');
    // This background color works well if the page was in either
    // light or dark mode.
    body.style.backgroundColor = 'lavender';
    body.style.padding = '1em';
    body.innerHTML = browserFeatureErrs.join('');
    throw new Error('browser feature missing.');
  }
}
