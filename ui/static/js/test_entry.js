// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the LICENSE.txt file.

/**
 * @enum {string} String, because HTML attribute names are strings.
 */
const TestEntryAttribute = {
  INDEX: 'te-index',  // Static, i.e. value fixed on creation
  STATUS: 'te-status',  // Static, i.e. value fixed on creation
  VISIBLE: 'te-visible',  // Dynamic (passed search and visibility checkboxes)
  SELECTED: 'te-user-selected',  // Dynamic (user clicked the element itself)
  STARRED: 'te-user-starred',  // Dynamic (user clicked the element's star icon)
  IN_VIEW: 'te-in-view',  // Dynamic (in view port, different from VISIBLE)
}

/**
 * @enum {string} String, because HTML attribute values are strings.
 */
const TestStatus = {
  SUCCESS: '1',
  ERROR: '0',
}

/**
 * @enum {number}
 */
const AttributeChange = {
  UPDATING: 0,
  ADDING: 1,
  REMOVING: 2,
}

/**
 * Used to set element height so that even if the element is
 * not rendered, i.e. innerHTML is empty, its height is still
 * taken into account by the layout system, so e.g. the
 * scrollbar thumb : track ratio is computed correctly.
 * @type {string}
 */
// TODO: Get the value from JavaScript, not from DevTools.
// TODO: Set it as a static property in class TestEntry, when static properties
//       becomes part of the standard.
const TEST_ENTRY_INTRINSIC_HEIGHT = '22px';

// TestEntry is a custom element. However, we do not use shadow DOM here, as
// a node that has a shadow DOM requires adding its own CSS nodes. There might
// be a huge number of test entries to create, so we want to be prudent about
// adding nodes. It is recommended the DOM hold no more than a few thousand
// nodes: https://web.dev/dom-size/
class TestEntry extends HTMLElement {
  constructor() {
    super();

    /**
     * @type {string}
     */
    this.testId = '';

    /**
     * @type {boolean}
     */
    this.ok = false;

    /**
     * @type {number} Average processor runtime (not wall time), millisec.
     */
    this.avgRumtimeMs = 0;

    /**
     * @type {number} Average max resident set size, KB.
     */
    this.avgMaxrssKb = 0;

    /**
     * @type {number}
     */
    this.taskCount = 0;

    /**
     * @type {number}
     */
    this.taskErrorCount = 0;
  }

  connectedCallback() {
    // Called when this element is connected to the DOM (not merely appended to
    // another element as a child, but actually becomes a part of the page).

    // NOTE Do mot render the element here. We use lazy-rendering, i.e. build
    // the element's HTML if attribute TestEntryAttribute.IN_VIEW is added,
    // and remove the HTML if that attribute is removed. This way, the document
    // holds much fewer nodes compared with normal rendering (i.e. not lazy).
  }

  static get observedAttributes() {
    return [
      TestEntryAttribute.IN_VIEW,
      TestEntryAttribute.STARRED,
      TestEntryAttribute.SELECTED,
    ];
  }

  attributeChangedCallback(name, oldValue, newValue) {
    // Called when HTML attributes returned by observedAttributes() is changed.
    // the value for a missing attribute is represented by null.
    let change = AttributeChange.UPDATING;
    if (oldValue === null && (typeof newValue === 'string')) {
      change = AttributeChange.ADDING;
    } else if ((typeof oldValue === 'string') && newValue === null) {
      change = AttributeChange.REMOVING;
    }

    switch (name) {
      case TestEntryAttribute.IN_VIEW:
        if (change === AttributeChange.ADDING) {
          this.render_();
        } else if (change === AttributeChange.REMOVING) {
          this.disrender_();
        }
        break;
      case TestEntryAttribute.STARRED:
        const starHolder =
            utils.querySelector('div.test_entry_star_holder', this);
        // The TestEntry innerHTML might be empty (because of lazy-loading).
        // In that case, starHolder is null, and thus we should not set the
        // star. We will let render_() build the starHolder and set the star.
        if (starHolder) {
          if (change === AttributeChange.ADDING) {
            this.maybeSetStar_(starHolder);
          } else if (change === AttributeChange.REMOVING) {
            this.maybeSetStar_(starHolder);
          }
        }
        break;
      case TestEntryAttribute.SELECTED:
        const detailsViewBox = /** @type {HTMLElement} */ (
            utils.querySelector('div#entry_details_view'));
        if (!detailsViewBox) {
          throw new Error('unable to find div#entry_details_view');
        }
        if (change === AttributeChange.ADDING) {
          const detailsPanel =
              DetailsPanel.create(this, dataStorage.testData.get(this.testId));
          detailsViewBox.appendChild(detailsPanel);
        } else if (change === AttributeChange.REMOVING) {
          const detailsPanel = /** @type {!DetailsPanel} */ (
              utils.querySelector('details-panel', detailsViewBox));
          detailsViewBox.removeChild(detailsPanel);
          if (detailsViewBox.querySelector('details-panel')) {
            throw new Error(  // Maybe there were more than one <details-panel>.
                '<details-panel> still exists on div#entry_details_view.')
          }
        }
        break;
      default:
        console.warn(`unhandled attribute change: ${name}.`);
        break;
    }
  }

  /* Custom methods below. */

  /**
   * @param {number} index
   * @param {string} testId
   * @param {!TestAggregateInfo} info
   */
  static create(index, testId, info) {
    const obj = new TestEntry();
    // Index vs testId: index is used only by the UI, while testId
    // is used by both the test log and the UI. Like testId, an index
    // can uniquely identify a test, but it takes much less space.
    obj.setAttribute(TestEntryAttribute.INDEX, String(index));
    obj.testId = testId;
    obj.setAttribute(
        TestEntryAttribute.STATUS,
        info.ok ? TestStatus.SUCCESS : TestStatus.ERROR);
    obj.ok = info.ok;
    obj.avgRumtimeMs = info.runtimeStat[0];
    obj.avgMaxrssKb = info.maxrssStat[0];
    obj.taskCount = info.taskIndexes.length;
    obj.taskErrorCount = info.taskErrorCount;
    obj.style.height = TEST_ENTRY_INTRINSIC_HEIGHT;
    return obj;
  }

  /**
   * @param {!RegExp} searchRegex
   * @param {boolean} showSuccess
   * @param {boolean} showError
   * @return {boolean} Whether it is visible
   */
  setVisibility(searchRegex, showSuccess, showError) {
    const visible = this.testId.search(searchRegex) >= 0 ?
        (this.ok ? showSuccess : showError) :
        false;
    if (visible) {
      this.setAttribute(TestEntryAttribute.VISIBLE, '');
    } else {
      this.removeAttribute(TestEntryAttribute.VISIBLE);
    }
    return visible;
  }

  /**
   * Builds HTML.
   */
  render_() {
    this.classList.add('test_entry_button');

    // Status icon holder and icon.
    const statusIconHolder = document.createElement('div');
    statusIconHolder.classList.add('test_entry_status_icon');
    const errorIsFlaky = !this.ok && this.taskErrorCount < this.taskCount;
    const statusIcon = utils.makeMaterialIcon(
        this.ok ? 'check_circle_outline' :
                  (errorIsFlaky ? 'flaky' : 'error_outline'));
    statusIconHolder.append(statusIcon);
    this.append(statusIconHolder);

    // Test ID string.
    const testIdElem = document.createElement('div');
    testIdElem.classList.add('test_entry_id_text');
    testIdElem.textContent =  // The value 9 was set by trial-and-error.
        utils.capWidthByMiddleEllipsis(this.testId, this.scrollWidth / 9);
    this.append(testIdElem);

    // Star icon holder and icon.
    const starHolder = document.createElement('div');
    starHolder.classList.add('test_entry_star_holder');
    starHolder.addEventListener('click', this.onStarClick_.bind(this));
    this.maybeSetStar_(starHolder);
    this.append(starHolder);

    this.registerTooltip_();
  }

  /**
   * Removes HTML.
   */
  disrender_() {
    this.innerHTML = '';
    // Reset entry height so that even if it is not rendered, its height
    // is still taken into account by the scrollbar.
    this.style.height = TEST_ENTRY_INTRINSIC_HEIGHT;
  }

  /**
   * In fact, tooltips don't always need event handler (you can just set the
   * tooltip's HTML, and arrange its CSS so it is visible only when the owner
   * is being hovered upon: https://www.w3schools.com/css/css_tooltip.asp).
   * However, we chose to build the tooltip in an event handler, because we
   * want to keep the number nodes a TestEntry holds when not hovered at a
   * minimum. Moreover, that CSS-only approach has a bug that is hard to fix
   * is a clear, robust way (see the comment at registerTooltipOn()).
   */
  registerTooltip_() {
    const countTasks = this.ok ?
        `OK (${this.taskCount})` :
        `erred: ${this.taskErrorCount} out of ${this.taskCount}`;
    const tooltipContent = `<b>${this.testId}</b><br>` +
        `${this.avgRumtimeMs.toFixed(1)} ms, ` +
        `${(this.avgMaxrssKb / 1024.0).toFixed(1)} MB<br>` +
        `${countTasks}`;
    utils.registerTooltipOn(this, tooltipContent, {dX: 0, dY: 35});
  }

  /**
   * @param {Element} starHolder
   */
  maybeSetStar_(starHolder) {
    if (!starHolder) {
      throw new Error(
          'the star holder element is not present, probably because ' +
          'TestEntry is not rendered.');
    }
    starHolder.innerHTML = '';
    const starIcon = utils.makeMaterialIcon(null);
    starIcon.classList.add('test_entry_star_icon');
    if (this.hasAttribute(TestEntryAttribute.STARRED)) {
      starIcon.textContent = 'star';  // Full star.
    } else {
      starIcon.textContent = 'star_border';  // Empty star.
    }

    starHolder.append(starIcon);
  }

  /**
   * @param {!Event} event
   */
  onStarClick_(event) {
    // Stop the click event from being delivered to TestEntry itself.
    event.stopPropagation();
    this.toggleAttribute(TestEntryAttribute.STARRED);
  }
}

// This line has side effect.
window.customElements.define('test-entry', TestEntry);

/**
 * Custom HTML attributes for peek icons in #entries_peek_icons_view.
 * @enum {string}
 */
const PeekIconAttribute = {
  // The index that uniquely identify a test entry
  INDEX: 'data-idx',
  // The entry is selected (in which case, this peek icon is selected
  // automatically, and vice versa)
  SELECTED: 'data-slt',
  // The entry passed search and visibility checkboxes
  ENTRY_VISIBLE: 'data-vis',
  // The entry is in the viewport
  ENTRY_IN_VIEW: 'data-ivw',
}

/**
 * Peek icons in #entries_peek_icons_view. Each peek icon represent the test
 * status of a test entry in #entries_explorer_view.
 */
class PeekIcon extends HTMLElement {
  constructor() {
    super();
  }

  /**
   * @param {number} index
   * @param {string} testId
   * @param {boolean} testOk
   */
  static create(index, testId, testOk) {
    const obj = new PeekIcon();
    obj.setAttribute(PeekIconAttribute.INDEX, String(index));
    obj.render_(testId, testOk);
    return obj;
  }

  /* Custom methods below. */

  /**
   * Builds HTML.
   * @param {string} testId
   * @param {boolean} testOk
   */
  render_(testId, testOk) {
    this.classList.add('peek_icon');
    const icon = utils.makeMaterialIcon(null);
    if (testOk) {
      icon.textContent = 'done';
      icon.classList.add('peek_icon_success');
    } else {
      icon.textContent = 'priority_high';
      icon.classList.add('peek_icon_error');
    }
    this.append(icon);
    utils.registerTooltipOn(this, testId, {dX: 20, dY: 20});
  }
}

// This line has side effect.
window.customElements.define('peek-icon', PeekIcon);
