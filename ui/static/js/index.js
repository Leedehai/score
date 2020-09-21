// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the MIT LICENSE.txt file.

/**
 * The starting point, called in an index.html script tag.
 */
function run() {
  utils.logDataStorageToConsole();
  window.uiState = new UIState();
  window.dataState = new DataState();

  // Initialize persistent states.
  window.dataState.testIds = Array.from(dataStorage.testData.keys()).sort();
  if (window.sessionStorage.getItem('random_error')) {  // Demo error effects.
    console.warn(
        'some test results are set to error for demo with P=0.5; to undo: ' +
        'window.sessionStorage.removeItem(\'random_error\') and refresh.');
    window.dataState.testIds.forEach((testId) => {
      const testInfo = dataStorage.testData.get(testId);
      if (testInfo.ok && Math.random() <= 0.5) {
        // @ts-expect-error: testInfo.ok is read-only.
        testInfo.ok = false;
        // @ts-expect-error: testInfo.taskErrorCount is read-only.
        testInfo.taskErrorCount += 1;
        // @ts-expect-error: dataStorage.testErrorCount is read-only.
        dataStorage.testErrorCount += 1;
      }
    });
  }
  window.uiState.allOk = dataStorage.testErrorCount === 0;

  // Page header, status bar, sub status bar.
  configureColorModeControlButtonEvent();
  configureAlternativeSortingButtonEvent(window.uiState);
  configureExplorerViewControlEvents(window.uiState, window.dataState);

  // Build initial page.
  setTrivialTextSlots(dataStorage);
  setStatusBar(
      window.uiState.allOk, dataStorage.masterLogModificationTime,
      dataStorage.wholeTime);
  setTestExecBreadcrumbsAndCopyButton(
      dataStorage.testExecPathComponents, dataStorage.testExecPath,
      /*breadcrumbViewPathSeparator=*/ '〉');
  buildExplorerAndIconsView(window.uiState, window.dataState);
}

function configureColorModeControlButtonEvent() {
  // There are two color mode control buttons. One for light to dark, and one
  // for dark to light. Exactly one button is shown, at the other is hidden.
  // Credit: https://github.com/royalfig/dark-mode-demo/blob/master/main.js
  // License: in static/css/color_mode_button.css.
  utils.querySelectorAll('.color_mode_button').forEach((button) => {
    button.addEventListener('click', (event) => {
      const targetElement = /** @type {HTMLElement} */ (event.currentTarget);
      const elementId = targetElement.id;
      if (elementId === 'enable_light_mode') {
        document.documentElement.setAttribute('data-color-mode', 'light');
        localStorage.setItem('data-color-mode', 'light');
      } else if (elementId === 'enable_dark_mode') {
        document.documentElement.setAttribute('data-color-mode', 'dark');
        localStorage.setItem('data-color-mode', 'dark');
      } else {
        throw new Error(`unrecognized color mode button id ${elementId}.`)
      }
    });
  });
}

/**
 * @param {!UIState} uiState
 */
function configureAlternativeSortingButtonEvent(uiState) {
  const sortTestEntriesBy = /** @type {!Object<string, string|null>} */ ({
    'test id': null,  // Sort by testId (the canonical sort key).
    'processor time': 'avgRumtimeMs',
    'memory footprint': 'avgMaxrssKb',
  });
  const button = utils.querySelector('div#sort_options');
  const selectList = utils.querySelector('.select_options', button);
  utils.querySelectorAll('div.select_item', selectList).forEach((e) => {
    const what = e.textContent;
    e.addEventListener('click', (event) => {
      event.stopPropagation();
      utils.querySelector('#sort_by_what', button).textContent = what;
      if (!sortTestEntriesBy.hasOwnProperty(what)) {
        throw new Error(`no listener for sorting option '${what}'.`);
      }
      selectList.style.display = 'none';  // The drop-down list withdraws.
      // Resort the view elements instead of rebuilding, so that user-related
      // states stored in these elements (e.g. SELECTED, STARRED) can be kept
      // around.
      const compareTestEntries = utils.objectSortingComparerFactory(
          {key: sortTestEntriesBy[what], order: utils.SortOrder.DESCENDING},
          /*fallback=*/ {key: 'testId', order: utils.SortOrder.ASCENDING});
      utils.sortChildren(uiState.explorerView, compareTestEntries);
      utils.sortChildren(
          uiState.iconsView,
          (pa, pb) => compareTestEntries(
              uiState.findTestEntry(/** @type {!PeekIcon} */ (pa)),
              uiState.findTestEntry(/** @type {!PeekIcon} */ (pb))));
      uiState.explorerView.classList.add('view_refreshed');
      setTimeout(() => {
        uiState.explorerView.classList.remove('view_refreshed');
        // The drop-down list won't expand, because #sort_options is no longer
        // under the mouse. Setting it from 'none' to null ensures the list
        // can expand again when user hovers above #sort_options again.
        selectList.style.display = null;
      }, 200);  // The .view_refreshed animation takes this long to complete.
    });
  });
}

/**
 * @param {!UIState} uiState
 * @param {!DataState} dataState
 */
function configureExplorerViewControlEvents(uiState, dataState) {
  const onControlChange = () => {
    buildExplorerAndIconsView(uiState, dataState);
  };
  const searchBar = /** @type {HTMLInputElement} */ (
      utils.querySelector('#entries_search_bar'));
  // Not 'keypress' because it doesn't catch Deletion key.
  searchBar.addEventListener('keyup', () => {
    // Not more succinct: to please the TS linter.
    utils.throttle(onControlChange, 200)();
  });

  const checkboxes = utils.querySelectorAll(
      '#explorer_view_control_checkboxes input[type="checkbox"]');
  if (checkboxes.length !== 2) {
    throw new Error(
        `expecting 2 <input>s under ` +
        `#explorer_view_control_checkboxes, got ${checkboxes.length}.`);
  }
  checkboxes.forEach((element) => {
    element.addEventListener('click', onControlChange);
  });
}

/**
 * @param {!DataStorage} dataStorage
 */
function setTrivialTextSlots(dataStorage) {
  const tabTitle =
      /** @type {HTMLTitleElement} */ (document.head.querySelector('title'));
  tabTitle.textContent = dataStorage.testTitle;

  const logAnchor =
      /** @type {HTMLAnchorElement} */ (
          utils.querySelector('#master_log_link a'));
  logAnchor.href = dataStorage.masterLog;

  const populateBodyTextContent = (mapQueryValue) => {
    for (const [query, value] of Object.entries(mapQueryValue)) {
      const elem = utils.querySelector(query);
      elem.textContent = value;
    }
  };

  populateBodyTextContent({
    'span#test_title': dataStorage.testTitle,
    'div#test_result_stats_total': dataStorage.testData.size,
    'div#test_result_stats_successes':
        dataStorage.testData.size - dataStorage.testErrorCount,
    'div#test_result_stats_errors': dataStorage.testErrorCount,
  });
}

/**
 * @param {boolean} allOk Whether all tests succeeded.
 * @param {string} completeTime A human-friendly time string.
 * @param {number} timeDuration Milliseconds.
 */
function setStatusBar(allOk, completeTime, timeDuration) {
  // The status icon.
  const iconDiv = utils.querySelector('div#status_bar_icon');
  const icon = utils.makeMaterialIcon(allOk ? 'check_circle' : 'error');
  icon.classList.add(allOk ? 'status_bar_ok' : 'status_bar_error');
  iconDiv.append(icon);

  // The main message.
  const messageDiv = utils.querySelector('div#status_bar_status_message');
  messageDiv.textContent = allOk ? 'Success' : 'Error';
  messageDiv.classList.add(allOk ? 'status_bar_ok' : 'status_bar_error');

  // The timing message
  const timingMessageDiv = utils.querySelector('span#test_timing_message');
  const timeStr =
      utils.timeToString(timeDuration, utils.TimeConversionMode.AS_TIME_ELAPSE);
  timingMessageDiv.innerHTML =
      `Complete at ${completeTime} <b> in ${timeStr}</b>`;

  // The color.
  const statusBarDiv = utils.querySelector('div#status_bar');
  statusBarDiv.classList.remove('status_bar_neutral');
  if (allOk) {
    statusBarDiv.classList.add('status_bar_ok');
  } else {
    statusBarDiv.classList.add('status_bar_error');
  }
}

/**
 * @param {!Array<string>} pathComponents
 * @param {string} pathString
 * @param {string} breadcrumbViewPathSeparator
 */
function setTestExecBreadcrumbsAndCopyButton(
    pathComponents, pathString, breadcrumbViewPathSeparator) {
  // Make breadcrumbs view.
  const docFragment = document.createDocumentFragment();
  pathComponents.forEach((part, idx) => {
    const partDiv = document.createElement('div');
    partDiv.textContent = part;
    partDiv.classList.add('breadcrumb_component');
    docFragment.append(partDiv);
    if (idx < pathComponents.length - 1) {
      const delimDiv = document.createElement('div');
      delimDiv.textContent = breadcrumbViewPathSeparator;
      delimDiv.classList.add('breadcrumb_component');
      docFragment.append(delimDiv);
    }
  });
  const breadcrumbsDiv = utils.querySelector('div#test_directory_breadcrumbs');
  breadcrumbsDiv.append(docFragment);

  // Make copy button.
  const copyButton = utils.makeCopyButton(
      pathString, 'div', 'test_directory_breadcrumbs_copy_icon');
  breadcrumbsDiv.append(copyButton);
}

/**
 * @param {!UIState} uiState
 * @return {?RegExp}
 */
function parseExplorerViewSearchBar(uiState) {
  const searchBar = uiState.searchBar;
  const regexParsed = utils.parseRegexNoexcept(searchBar.value);
  if (regexParsed.error) {
    searchBar.classList.add('search_bar_error');
  } else {
    searchBar.classList.remove('search_bar_error');
  }
  return regexParsed.regexp;
}

/**
 * @param {!UIState} uiState
 * @param {!DataState} dataState
 */
function buildExplorerAndIconsView(uiState, dataState) {
  const searchRegex = parseExplorerViewSearchBar(uiState);
  if (!searchRegex) {
    uiState.showSuccessCheckbox.disabled = true;
    uiState.showErrorCheckbox.disabled = true;
    return;
  }
  uiState.showSuccessCheckbox.disabled = false;
  uiState.showErrorCheckbox.disabled = false;
  const showSuccess = uiState.showSuccessCheckbox.checked;
  const showError = uiState.showErrorCheckbox.checked;

  const startTime = Date.now();  // Milliseconds since Unix Epoch.

  const explorerViewToRebuild =
      !window.uiState.explorerView.querySelector('test-entry');
  if (explorerViewToRebuild) {
    const explorerDocFragment = document.createDocumentFragment();
    const iconsDocFragment = document.createDocumentFragment();
    dataState.testIds.forEach((testId, index) => {
      // This index uniquely identifies a test, and is stable. It is not
      // just a mere loop index.
      const entry = buildExplorerAndIconsViewForOneTest(
          index, testId, explorerDocFragment, iconsDocFragment);
      uiState.explorerViewportObserver.observe(entry);
    });
    uiState.explorerView.append(explorerDocFragment);
    uiState.iconsView.append(iconsDocFragment);
  }

  // Refresh visibility on the entries.
  let visibleStats = {successes: 0, errors: 0};
  Array.from(uiState.explorerView.children)
      .forEach(/** @param {!TestEntry} entry */ (entry) => {
        const peekIcon = uiState.findPeekIcon(entry);
        didSetVisibilityForOneTest(
            entry, visibleStats, peekIcon,
            entry.setVisibility(searchRegex, showSuccess, showError));
      });

  // Populate stats message.
  const statsDiv = utils.querySelector('#explorer_view_stats');
  statsDiv.textContent = `Query processed, found ` +
      `${visibleStats.successes + visibleStats.errors} ` +
      `(passed: ${visibleStats.successes}, ` +
      `errors: ${visibleStats.errors}) in ` +
      `${Date.now() - startTime} ms`;
}

/**
 * @param {number} index
 * @param {string} testId
 * @param {DocumentFragment} explorerDocFragment
 * @param {DocumentFragment} iconsDocFragment
 * @return {!TestEntry} The created TestEntry object, if one is created.
 */
function buildExplorerAndIconsViewForOneTest(
    index, testId, explorerDocFragment, iconsDocFragment) {
  const testInfo = dataStorage.testData.get(testId);
  if (!testInfo) {
    throw new Error(`unable to find TestAggregateInfo for ${testId}`);
  }

  // The test entry in #entries_explorer_view.
  const entry = TestEntry.create(index, testId, testInfo);
  explorerDocFragment.append(entry);

  // The peek icon in #entries_peek_icons_view.
  const peekIcon = PeekIcon.create(index, testId, testInfo.ok);
  iconsDocFragment.append(peekIcon);

  entry.addEventListener('click', entryClickListenerFactory(entry));
  peekIcon.addEventListener('click', peekIconClickListenerFactory(peekIcon));

  return entry;
}

/**
 * @param {!TestEntry} entry
 */
function entryClickListenerFactory(entry) {
  return () => {
    const previouslySelectedEntry = window.uiState.selectedTestEntry;
    // If this entry is already marked as SELECTED, clicking it again
    // de-selects it.
    if (previouslySelectedEntry === entry) {
      window.uiState.unsetSelectedEntry();
      return;
    }

    window.uiState.unsetSelectedEntry();
    window.uiState.setSelectedEntry(entry);
    utils.scrollIntoView(window.uiState.findPeekIcon(entry));
  };
}

/**
 * @param {!PeekIcon} peekIcon The peek icon in #entries_peek_icons_view
 *  not the one on each entry element in #entries_explorer_view.
 */
function peekIconClickListenerFactory(peekIcon) {
  return () => {
    if (!peekIcon.hasAttribute(PeekIconAttribute.ENTRY_VISIBLE)) {
      return;
    }

    const entry = window.uiState.findTestEntry(peekIcon);
    const previouslySelectedEntry = window.uiState.selectedTestEntry;
    // If this icon is already marked as SELECTED, clicking it again
    // de-selects it.
    if (previouslySelectedEntry === entry) {
      window.uiState.unsetSelectedEntry();
      return;
    }

    window.uiState.unsetSelectedEntry();
    window.uiState.setSelectedEntry(entry);
    utils.scrollIntoView(entry);
  };
}

/**
 * @param {!TestEntry} entry
 * @param {{successes: number, errors: number}} visibleStats
 * @param {PeekIcon} peekIcon
 * @param {boolean} visible Whether the test passed the visibility controls:
 *   search bar and visibility checkboxes (note: "visible" is unrelated to
 *   whether the entry element is actually in the user view port).
 */
function didSetVisibilityForOneTest(entry, visibleStats, peekIcon, visible) {
  if (!visible) {
    peekIcon.removeAttribute(PeekIconAttribute.ENTRY_VISIBLE);
    return;
  }

  // Entry is visible in #entries_explorer_view.
  peekIcon.setAttribute(PeekIconAttribute.ENTRY_VISIBLE, '');
  if (entry.ok) {
    visibleStats.successes += 1;
  } else {
    visibleStats.errors += 1;
  }
}
