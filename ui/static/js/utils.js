// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the MIT LICENSE.txt file.

// We can't use ES6 import (see README.md), so we have to use object
// scoping to simulate a namespace.
const utils = {};

/**
 * @enum {number}
 */
utils.TimeConversionMode = {
  AS_TIME_ELAPSE: 0,
  AS_LOCALE_STRING: 1,
  AS_ISO_STRING: 2,
};

/**
 * Convert a msec number to a human-friendly time string.
 * @param {number} msec
 * @param {!utils.TimeConversionMode} mode
 * @return {string}
 */
utils.timeToString = (msec, mode) => {
  function asElapse(msec) {
    const sec = (msec / 1e3) % 60;
    const min = Math.floor((msec / (1e3 * 60)) % 60);
    const hr = Math.floor((msec / (1e3 * 60) / 60));
    const secStr = (sec >= 10 || sec < 1 ? '' : '0') + sec.toFixed(1);
    let ans = `${secStr} sec`;
    if (min > 0 || hr > 0) {
      const minStr = (min >= 10 || min < 1 ? '' : '0') + min;
      ans = `${minStr} min ${ans}`;
    }
    if (hr > 0) {
      const hrStr = (hr >= 10 || hr < 1 ? '' : '0') + hr;
      ans = `${hrStr} hr ${ans}`;
    }
    return ans;
  }
  switch (mode) {
    case utils.TimeConversionMode.AS_TIME_ELAPSE:
      return asElapse(msec);
    case utils.TimeConversionMode.AS_LOCALE_STRING:
      return (new Date(msec)).toLocaleString();
    case utils.TimeConversionMode.AS_ISO_STRING:
      return (new Date(msec)).toISOString();
    default:
      throw new Error(`Unknown mode: ${mode}`);
  }
};

/**
 * @enum {number}
 */
utils.SortOrder = {
  ASCENDING: 0,  // Small value comes first
  DESCENDING: 1,  // Large value comes first
};

/**
 * @param {{key: string|null, order: utils.SortOrder}|null} primary
 * @param {{key: string, order: utils.SortOrder}} fallback
 * @return {function(object, object): number}
 */
utils.objectSortingComparerFactory = (primary, fallback) => (a, b) => {
  if (!primary || !primary.key || a[primary.key] === b[primary.key]) {
    return (fallback.order === utils.SortOrder.DESCENDING ? -1 : 1) *
        (a[fallback.key] < b[fallback.key] ? -1 : 1);
  }
  return (primary.order === utils.SortOrder.DESCENDING ? -1 : 1) *
      (a[primary.key] < b[primary.key] ? -1 : 1);
};

/**
 * @param {HTMLElement} parent
 * @param {function(HTMLElement, HTMLElement):number} compare
 */
utils.sortChildren = (parent, compare) => {
  const moveElement = (newParent, element) => {
    // If element is already under a parent, append() removes it from the
    // original parent before appending it to the new parent.
    newParent.append(element);
    return newParent;
  };
  parent.append(Array.from(parent.children)
                    .sort(compare)
                    .reduce(moveElement, document.createDocumentFragment()));
};

/**
 * A querySelector() plus an assertion for HTMLElement. If the root param is
 * omitted, the search starts from document.body.
 * @param {string} query
 * @param {HTMLElement=} root
 * @return {HTMLElement}
 */
utils.querySelector = (query, root) => {
  if (!root) {
    root = document.body;
  }
  const e = root.querySelector(query);
  if (!e || !(e instanceof HTMLElement)) {
    throw new Error(`unable to find HTMLElement ${query}.`);
  }
  return /** @type {HTMLElement} */ (e);
};

/**
 * A querySelectorAll() plus an assertion for array size and HTMLElement. If
 * the root param is omitted, the search starts from document.body.
 * @param {string} query
 * @param {HTMLElement=} root
 * @return {!Array<HTMLElement>}
 */
utils.querySelectorAll = (query, root) => {
  if (!root) {
    root = document.body;
  }
  const es = Array.from(root.querySelectorAll(query));
  if (es.length === 0 || !(es[0] instanceof HTMLElement)) {
    // Ignore possibilities where any of es[i] (i > 0) is not HTMLElement.
    throw new Error(`unable to find HTMLElement objects ${query}.`);
  }
  return /** @type {!Array<HTMLElement>} */ (es);
};

/**
 * Material icon, requiring importing its CSS (in main.html).
 * https://material.io/resources/icons
 * @param {string|null} icon_name
 * @return {!HTMLElement}
 */
utils.makeMaterialIcon = (icon_name) => {
  const e = document.createElement('i');
  e.classList.add('material-icons');  // Stylesheet ready in index.html.
  e.textContent = icon_name ? icon_name : '';
  return e;
};

/**
 * @param {HTMLElement} button
 */
utils.styleButtonClickEffect = (button) => {
  button.classList.add('button_just_clicked');
  setTimeout(() => {
    button.classList.remove('button_just_clicked');
  }, 100);
};

/**
 * @param {function} callback
 * @param {number} millisec
 * @return {function}
 */
utils.throttle = (callback, millisec) => {
  let timerId = 0;
  return (...args) => {
    clearTimeout(timerId);
    timerId = setTimeout(() => {
      callback(...args);
    }, millisec || 0);
  };
};

/**
 * Copy to clipboard. The specification requires this function is called
 * after querying and getting the clipboard permission, but Firefox does
 * not need (and does not support) the permission, and Safari does not
 * support Permission API and Clipboard API at all.
 * NOTE Alternative approach: execCommand('copy') is not supported in
 * Safari, and execCommand() is a deprecating feature.
 * NOTE It turns out Chrome/Chromium is indeed the best! (1/2020)
 * https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Interact_with_the_clipboard
 * https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText
 * @param {string} content
 */
utils.copyToClipboard = (content) => {
  const copyToClipboardImpl = () => {
    navigator.clipboard.writeText(content);
  };
  try {
    if (navigator.permissions) {
      navigator.permissions.query({name: 'clipboard-write'})
          .then(result => {
            if (result.state == 'granted' || result.state == 'prompt') {
              copyToClipboardImpl();
            }
          })
          .catch(() => {  // Firefox does not fully support the Permission API.
            copyToClipboardImpl();
          });
    } else {  // Some others do not support the Permission API at all.
      copyToClipboardImpl();
    }
  } catch (e) {  // Safari, uh..
    if (e instanceof TypeError) {
      window.alert(
          'The copy-text feature encountered a bug.\n\n' +
          'It needs Clipboard API and Permissions API, features required \n' +
          'in the Web Standard. Your browser does not support them.');
    }
  }
};

/**
 * @param {string} s
 * @return {{regexp: ?RegExp, error: ?string}}
 */
utils.parseRegexNoexcept = (s) => {
  let regexp = null, error = null;
  try {
    regexp = new RegExp(s);
  } catch (e) {
    console.warn(`regex error: ${s}`);
    error = e.message;
  }
  return {regexp, error};
};

/**
 * @param {HTMLElement} element
 */
utils.scrollIntoView = (element) => {
  try {
    element.scrollIntoView({block: 'center', behavior: 'smooth'});
  } catch {  // Safari
    element.scrollIntoView(/*alignToTop=*/ true);
  }
};

/**
 * Get an element's offset relative to <body>,
 * @param {HTMLElement} element
 * @return {{top: number, left: number}}
 */
utils.getBodyOffset = (element) => {
  const offsetToViewport = element.getBoundingClientRect();
  const scrollTop =  // Chrome || Firefox
      document.documentElement.scrollTop || document.body.scrollTop;
  const scrollLeft =  // Chrome || Firefox
      document.documentElement.scrollLeft || document.body.scrollLeft;
  const top = offsetToViewport.top + scrollTop;
  const left = offsetToViewport.left + scrollLeft;
  return {top, left};
};

/**
 * Install a tooltip on an element (the owner).
 * The native tooltip (HTML "title" attribute) is slow to emerge and not able
 * to be styled using CSS.
 *
 * The HTML+CSS-only tooltip (https://www.w3schools.com/css/css_tooltip.asp)
 * will interfere with the owner's parent's border if the tooltip would span
 * across the border:
 * 1. if owner's parent height/width isn't fixed, then the parent border will
 *    be pushed outward (i.e. the owner's parent got larger compared with the
 *    situation of not having the tooltip), even if the tooltip isn't visible;
 * 2. if owner's parent height/width is fixed:
 *      2.1. if owner's parent's CSS 'overflow' is 'hidden', the tooltip will
 *           be clipped by the owner's parent's border;
 *      2.2. if owner's parent's CSS 'overflow' is 'auto'/'scroll', the tooltip
 *           will result in a scroll bar.
 * There are other proposals to fix it, but not in a clear, robust way (spoiler
 * alert: 'z-index', 'overflow' don't work).
 *
 * This solution utilizes a hidden element directly under <body> and the fact
 * that we can get an element's offset to <body> with function getBodyOffset()
 * given above.
 * There's a drawback, though: mouse events are not triggered if the element
 * under the mouse changes not because of mouse moving but because of scrolling.
 * To mitigate this, we install an event listener that removes the tooltip on
 * the scrollable element (we don't do it in this function, as we don't want to
 * install the same listener to the scrollable element multiple times).
 * @param {HTMLElement} owner
 * @param {string} content Either a plain text or innerHTML.
 * @param {{dX: number, dY: number}} offset
 */
utils.registerTooltipOn = (owner, content, offset) => {
  const tooltip = utils.locateSingletonTooltip_();
  // Use mouseenter/mouseleave instead of mouseover/mouseout because the latter
  // has problems with event bubbling:
  // https://www.quirksmode.org/dom/events/mouseover.html
  owner.addEventListener('mouseenter', () => {
    tooltip.innerHTML = content;
    tooltip.style.visibility = 'visible';
    const ownerCoords = utils.getBodyOffset(owner);
    tooltip.style.left = String(ownerCoords.left + offset.dX);
    tooltip.style.top = String(ownerCoords.top + offset.dY);
    const removeTooltip = () => {
      utils.clearSingletonTooltip();
      owner.removeEventListener('mouseleave', removeTooltip);
    };
    owner.addEventListener('mouseleave', removeTooltip);
  });
};

utils.clearSingletonTooltip = () => {
  const tooltip = utils.locateSingletonTooltip_();
  tooltip.innerHTML = '';
  tooltip.style.visibility = 'hidden';
  tooltip.style.left = '0';
  tooltip.style.top = '0';
};

/**
 * We cannot just store #global_tooltip as a property utils.GLOBAL_TOOLTIP,
 * because when utils.js is executed the DOM is not constructed, as utils.js
 * is included by a <script> tag before <body>.
 * @return {HTMLElement}
 */
utils.locateSingletonTooltip_ = () => {
  if (!window.singletonTooltip) {
    const e = /** @type {HTMLElement} */ (
        document.body.querySelector('body > #global_tooltip'));
    if (!e) {
      throw new Error('unable to find #global_tooltip in DOM.');
    }
    window.singletonTooltip = e;
  }
  return window.singletonTooltip;
};

/**
 * If the input string is too long, replace a substring in the
 * middle with ellipsis.
 * @param {string} str
 * @param {number} maxLen Max number of characters.
 * @return {string}
 */
utils.capWidthByMiddleEllipsis = (str, maxLen) => {
  if (str.length <= maxLen) {
    return str;
  }
  const frontLen = 12;
  const ellipsis = '...';
  return str.substr(0, frontLen) + ellipsis +
      str.substr(-(maxLen - (frontLen + ellipsis.length)));
};

utils.logDataStorageToConsole = () => {
  const strings = [
    `url: ${window.location}`,
    'dataStorage = {',
  ];
  for (const [prop, value] of Object.entries(dataStorage)) {
    if (value instanceof Array) {
      strings.push(`  ${prop}: Array[${value.length}],`);
    } else if (value instanceof Map) {
      strings.push(`  ${prop}: Map[${value.size}],`);
    } else if (value instanceof Set) {
      strings.push(`  ${prop}: Set[${value.size}],`);
    } else {
      strings.push(`  ${prop}: ${JSON.stringify(dataStorage[prop])},`);
    }
  }
  strings.push('};');
  console.log(strings.join('\n'));
};

/**
 * @param {string} text
 * @param {string} elementType
 * @param {string} elementId
 * @return {HTMLElement}
 */
utils.makeCopyButton = (text, elementType, elementId) => {
  const icon = utils.makeMaterialIcon('content_copy');
  const copyButtonHolder = document.createElement(elementType);
  copyButtonHolder.classList.add('copy_button');
  copyButtonHolder.id = elementId;
  copyButtonHolder.append(icon);
  copyButtonHolder.addEventListener('click', () => {
    utils.styleButtonClickEffect(copyButtonHolder);
    utils.copyToClipboard(text);
  });
  return copyButtonHolder;
};

/**
 * @param {string=} relpath Path relative to the parent directory of
 *     the current HTML page.
 * @return {string=}
 */
utils.makeAbsPath = (relpath) => {
  if (!relpath) {
    return relpath;  // null, undefined.
  }
  const rootPath = window.location.origin +
      window.location.pathname.split('/').slice(0, -1).join('/');
  // Use URL() so that we have "a/./b" => "a/b", "a/b/../c" => "a/c", etc.
  return (new URL(rootPath + '/' + relpath)).toString();
};
