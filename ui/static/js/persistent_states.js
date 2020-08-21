// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the LICENSE.txt file.

/**
 * Persistent info related to the UI.
 */
class UIState {
  constructor() {
    /**
     * @type {boolean}
     */
    this.allOk = false;

    /**
     * The RegExp used to select the currently rendered entries.
     * @type {?RegExp}
     */
    this.exploreSearchRegex = null;

    /**
     * The selected (not starred) test entry element.
     * @type {?TestEntry}
     */
    this.selectedTestEntry = null;

    /**
     * @type {HTMLDivElement}
     */
    this.explorerView = /** @type {HTMLDivElement} */ (
        utils.querySelector('#entries_explorer_view'));
    if (this.explorerView.children.length !== 0) {
      throw new Error('#entries_explorer_view should hold 0 child on startup.')
    }
    this.explorerView.addEventListener('scroll', () => {
      utils.clearSingletonTooltip();
    });

    /**
     * @type {HTMLDivElement}
     */
    this.iconsView = /** @type {HTMLDivElement} */ (
        utils.querySelector('#entries_peek_icons_view'));
    if (this.iconsView.children.length !== 0) {
      throw new Error(
          '#entries_peek_icons_view should hold 0 child on startup.')
    }
    this.iconsView.addEventListener('scroll', () => {
      utils.clearSingletonTooltip();
    });

    /**
     * @type {HTMLInputElement}
     */
    this.searchBar = /** @type {HTMLInputElement} */ (
        utils.querySelector('input#entries_search_bar'));
    if (!this.searchBar) {
      throw new Error('unable to find the search bar.')
    }

    /**
     * @type {HTMLInputElement}
     */
    this.showSuccessCheckbox =
        /** @type {HTMLInputElement} */ (utils.querySelector(
            'input#view_control_visibility_checkbox_successes'));
    if (!this.showSuccessCheckbox) {
      throw new Error('unable to find the checkbox that show successes.');
    }

    /**
     * @type {HTMLInputElement}
     */
    this.showErrorCheckbox = /** @type {HTMLInputElement} */ (
        utils.querySelector('input#view_control_visibility_checkbox_errors'));
    if (!this.showErrorCheckbox) {
      throw new Error('unable to find the checkbox that show errors.');
    }

    /**
     * @type {IntersectionObserver}
     */
    this.explorerViewportObserver = new IntersectionObserver(
        this.handleExplorerViewIntersection_.bind(this), {
          root: this.explorerView,  // The viewport element of the observed
          rootMargin: '1%',  // Grow the root bounding box by 1%
          threshold: 0  // Visible amount of item shown in relation to root
        });
  }

  /**
   * @param {!PeekIcon} icon
   * @return {!TestEntry}
   */
  findTestEntry(icon) {
    const testIndex = icon.getAttribute(PeekIconAttribute.INDEX);  // string
    const entry = utils.querySelector(
        `test-entry[${TestEntryAttribute.INDEX}='${testIndex}']`,
        this.explorerView);
    if (!entry) {
      throw new Error(`unable to find a test entry with index ${testIndex}`);
    }
    return /** @type {!TestEntry} */ (entry);
  }

  /**
   * @param {!TestEntry} entry
   * @return {!PeekIcon}
   */
  findPeekIcon(entry) {
    const testIndex = entry.getAttribute(TestEntryAttribute.INDEX);  // string
    const peekIcon = utils.querySelector(
        `peek-icon[${PeekIconAttribute.INDEX}='${testIndex}']`, this.iconsView);
    if (!peekIcon) {
      throw new Error(`unable to find a peek icon with index ${testIndex}`);
    }
    return /** @type {!PeekIcon} */ (peekIcon);
  }

  unsetSelectedEntry() {
    if (!this.selectedTestEntry) {
      return;
    }
    this.findPeekIcon(this.selectedTestEntry)
        .removeAttribute(PeekIconAttribute.SELECTED);
    this.selectedTestEntry.removeAttribute(TestEntryAttribute.SELECTED);
    this.selectedTestEntry = null;
  }

  /**
   * @param {!TestEntry} entry
   */
  setSelectedEntry(entry) {
    if (this.selectedTestEntry) {
      throw new Error(
          'you should explicitly unset a selected entry before setting a new one.')
    }
    this.findPeekIcon(entry).setAttribute(PeekIconAttribute.SELECTED, '');
    entry.setAttribute(TestEntryAttribute.SELECTED, '');
    this.selectedTestEntry = entry;
  }

  /**
   * @param {!Array<!IntersectionObserverEntry>} intersectedEntries
   */
  handleExplorerViewIntersection_(intersectedEntries) {
    intersectedEntries.forEach((intersectedEntry) => {
      const entry = /** @type {!TestEntry} */ (intersectedEntry.target);
      const peekIcon = this.findPeekIcon(entry);
      if (intersectedEntry.isIntersecting) {
        entry.setAttribute(TestEntryAttribute.IN_VIEW, '');
        peekIcon.setAttribute(PeekIconAttribute.ENTRY_IN_VIEW, '');
      } else {
        entry.removeAttribute(TestEntryAttribute.IN_VIEW);
        peekIcon.removeAttribute(PeekIconAttribute.ENTRY_IN_VIEW);
      }
    });
  }
}

/**
 * Persistent info related to the data.
 */
class DataState {
  constructor() {
    /**
     * Sorted test ID strings from dataStorage data.
     * @type {!Array<string>}
     */
    this.testIds = [];
  }
}
