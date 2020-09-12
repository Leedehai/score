// Copyright (c) 2020 Leedehai. All rights reserved.
// Use of this source code is governed under the LICENSE.txt file.

class DetailsPanel extends HTMLElement {
  constructor() {
    super();

    /**
     * @type {string}
     */
    this.testId = '';

    /**
     * @type {?TestEntry}
     */
    this.entry = null;

    /**
     * @type {?TestAggregateInfo}
     */
    this.testInfo = null;
  }

  connectedCallback() {
    const placeholder = utils.querySelector('#entry_details_view #placeholder');
    placeholder.classList.add('hidden');
    this.render_();
  }

  disconnectedCallback() {
    const placeholder = utils.querySelector('#entry_details_view #placeholder');
    placeholder.classList.remove('hidden');
    const iframeView = utils.querySelector('#iframe_view');
    iframeView.classList.remove('iframe_opened');
  }

  /* Custom methods below. */

  /**
   * @param {!TestEntry} entry
   * @param {!TestAggregateInfo} info
   */
  static create(entry, info) {
    const obj = new DetailsPanel();
    // Index vs testId: index is used only by the UI, while testId
    // is used by both the test log and the UI. Like testId, an index
    // can uniquely identify a test, but it takes much less space.
    obj.entry = entry;
    obj.testId = entry.testId;
    obj.testInfo = info;
    obj.setAttribute('test-details-status', info.ok ? '1' : '0');
    return obj;
  }

  /**
   * Builds HTML.
   */
  render_() {
    this.classList.add('test_details_panel');

    this.renderTitleSection_();
    this.renderCommandInvocation_();
    this.renderOverviewSection_();
    this.renderTaskResults_();

    utils.querySelectorAll('a.link_as_non_iframe_button', this).forEach((e) => {
      e.addEventListener('click', () => {
        e.classList.toggle('link_as_button_clicked');
      });
    });
  }

  renderTitleSection_() {
    const section = document.createElement('div');
    section.classList.add('test_details_title');

    const testIdHolder = document.createElement('div');
    testIdHolder.id = 'test_details_id_holder';
    testIdHolder.innerText = this.testId;
    section.append(testIdHolder);

    const copyButton =
        utils.makeCopyButton(this.testId, 'div', 'test_id_copy_icon');
    section.append(copyButton);

    this.append(section);
  }

  renderCommandInvocation_() {
    const section = document.createElement('div');
    section.classList.add('test_details_command');

    const expandButton = document.createElement('a');
    expandButton.id = 'expansion_button';
    expandButton.classList.add('link_as_non_iframe_button');
    expandButton.textContent = 'command invocation';
    section.append(expandButton);
    const copyButton =
        utils.makeCopyButton(this.testInfo.command, 'div', 'copy_command');
    section.append(copyButton);
    const commandArea = document.createElement('pre');
    commandArea.id = 'command_text_area';
    commandArea.textContent = this.testInfo.command;
    section.append(commandArea);

    expandButton.addEventListener('click', () => {
      section.classList.toggle('expanded');
    });

    this.append(section);
  }

  renderOverviewSection_() {
    const section = document.createElement('div');
    section.classList.add('test_details_overview');

    const metadataTable = new TableMaker({id: 'test_metadata'});
    metadataTable.addRow([
      {
        content: 'expected exit:',
        tooltip: 'return code, signal code, timeout, etc.',
      },
      {
        content: this.testInfo.exit.join(' '),
      },
    ]);
    metadataTable.addRow([
      {
        content: 'expected stdout:',
        tooltip: 'if present, compare the actual stdout with its content',
      },
      {
        content: this.testInfo.goldenFile ? 'golden file' : '-',
        iframe: this.testInfo.goldenFile,
      },
    ]);
    metadataTable.addRow([
      {
        content: 'proc. timeout:',
        tooltip: 'allowed max. time on processor',
      },
      {
        content: `${this.testInfo.timeout} ms`,
      },
    ]);
    section.append(metadataTable.finish());

    const aggregateResultTable = new TableMaker({id: 'test_aggregate_result'});
    aggregateResultTable.addRow([
      {
        content: 'proc. runtime:',
        tooltip: 'time on processor (not wall time), std. deviation',
      },
      {
        content: this.testInfo.runtimeStat.map(v => v.toFixed(1)).join(' ± ') +
            ' ms',
      },
    ]);
    aggregateResultTable.addRow([
      {
        content: 'max. rss.:',
        tooltip: 'main memory footprint, std. deviation',
      },
      {
        content:
            this.testInfo.maxrssStat.map(v => v.toFixed(1)).join(' ± ') + ' KB',
      },
    ]);
    aggregateResultTable.addRow([
      {
        content: 'success count:',
        tooltip: 'successful vs total attempts',
        class: this.testInfo.ok ? 'success' : 'error',
      },
      {
        content: `${
            this.testInfo.taskIndexes.length -
            this.testInfo.taskErrorCount} out of ${
            this.testInfo.taskIndexes.length}`,
        class: this.testInfo.ok ? 'success' : 'error',
        id: 'has_status_icon',
      },
    ]);
    section.append(aggregateResultTable.finish());
    utils.querySelector('#has_status_icon', section)
        .append(this.makeStatusIcon_());

    this.append(section);
  }

  renderTaskResults_() {
    const section = document.createElement('div');
    section.classList.add('test_details_tasks');

    const resultTableMaker = new TableMaker({id: 'task_result_table'});
    resultTableMaker.addRow(
        [
          {content: '#'},
          {content: 'result'},
          {content: 'runtime', tooltip: 'time on processor'},
          {content: 'max. rss.', tooltip: 'main memory footprint'},
          {content: 'exit', tooltip: 'how program exited'},
          {content: 'exit ok'},
          {content: 'stdout'},
          {content: 'stdout diff'},
          {content: 'stdout ok'},
          {content: 'timeline', tooltip: 'start/end time vs all tests'},
        ],
        /*isRowHead=*/ true);
    this.testInfo.taskIndexes.forEach((pos, index) => {
      const taskInfo = /** @type {!TaskInfo} */
          (JSON.parse(dataStorage.taskResults[pos].replace(/'/g, '"')));
      const times = taskInfo.timesMs;
      const procWallTimeRatio =
          (times[0] / (times[2] - times[1]) * 100).toFixed(0);
      resultTableMaker.addRow([
        {
          content: String(index + 1),
        },
        {
          content: `<b>${taskInfo.ok ? 'good' : 'bad'}<b>`,
          class: taskInfo.ok ? 'success' : 'error',
        },
        {
          content: `${taskInfo.timesMs[0].toFixed(1)} ms`,
          tooltip: `${procWallTimeRatio}% of wall time`,
        },
        {
          content: `${(taskInfo.maxrssKb / 1024.0).toFixed(1)} MB`,
          tooltip: `${taskInfo.maxrssKb} KB`,
        },
        {
          content: taskInfo.exit.slice(1, 3).join(' '),
        },
        {
          content: taskInfo.exit[0] ? 'yes' : 'no',
          class: taskInfo.exit[0] ? 'success' : 'error',
        },
        {
          content: taskInfo.stdout[1] ? 'stdout' : '-',
          iframe: taskInfo.stdout[1],
        },
        {
          content: taskInfo.stdout[2] ? 'diff' : '-',
          iframe: taskInfo.stdout[2],
        },
        {
          content: taskInfo.stdout[0] ? 'yes' : 'no',
          class: taskInfo.stdout[0] ? 'success' : 'error',
        },
        {
          content: this.makeTimelineHtml_(
              160,
              times[1] - dataStorage.startTime,
              times[2] - dataStorage.startTime,
              dataStorage.wholeTime,
              ),
        },
      ]);
    });
    section.append(resultTableMaker.finish());

    this.append(section);
  }

  /**
   * @return {HTMLElement}
   */
  makeStatusIcon_() {
    const statusIconHolder = document.createElement('div');
    statusIconHolder.id = 'test_details_status_icon';
    const errorIsFlaky = !this.testInfo.ok &&
        this.testInfo.taskErrorCount < this.testInfo.taskIndexes.length;
    const statusIcon = utils.makeMaterialIcon(
        this.testInfo.ok ? 'check_circle_outline' :
                           (errorIsFlaky ? 'flaky' : 'error_outline'));
    statusIconHolder.append(statusIcon);
    return statusIconHolder;
  }

  /**
   * @param {number} length Length in pixels
   * @param {number} start
   * @param {number} end
   * @param {number} whole
   * @return {string}
   */
  makeTimelineHtml_(length, start, end, whole) {
    const PATH_MIN_LEN = 3;  // Pixels
    const xCoords = [0];
    const xStart = Math.min(start / whole * length, length - PATH_MIN_LEN);
    xCoords.push(xStart);
    let xFinish = end / whole * length;
    xFinish =
        (xFinish - xStart >= PATH_MIN_LEN) ? xFinish : (xStart + PATH_MIN_LEN);
    xCoords.push(xFinish);
    xCoords.push(length);
    return `<svg xmlns='http://www.w3.org/2000/svg' ` +
        `width='${length}' height='20'>` +
        `<path d='M${xCoords[0]} 10 L${xCoords[1]} 10'` +
        ` stroke='#cccccc' stroke-width='2'></path>` +
        `<path d='M${xCoords[1]} 10 L${xCoords[2]} 10'` +
        ` stroke='#557ecc' stroke-width='2'></path>` +
        `<path d='M${xCoords[2]} 10 L${xCoords[3]} 10'` +
        ` stroke='#cccccc' stroke-width='2'></path>` +
        `</path></svg>`;
  }
}

// This line has side effect.
window.customElements.define('details-panel', DetailsPanel);

/**
 * @typedef {Object} TableAttributes
 * @property {string|!Array<string>=} class
 * @property {string=} id
 * @property {string=} caption Plain text or HTML string
 *
 * @typedef {Object} CellData
 * @property {string} content Plain text or HTML string
 * @property {string=} tooltip
 * @property {string|!Array<string>=} class
 * @property {string=} id
 * @property {string=} iframe If defined, this behaves as an iframe opener
 */

class TableMaker {
  /**
   * @param {TableAttributes=} attributes
   */
  constructor(attributes) {
    /**
     * @private {HTMLTableElement}
     */
    this.table_ = document.createElement('table');
    if (attributes) {
      if (attributes.class) {
        [].concat(attributes.class).forEach((c) => {
          this.table_.classList.add(c);
        });
      }
      if (attributes.id) {
        this.table_.id = attributes.id;
      }
      if (attributes.caption) {
        const caption = document.createElement('caption');
        caption.innerHTML = attributes.caption;
        this.table_.append(caption);
      }
    }
    /**
     * @private {boolean}
     */
    this.done_ = false;
  }

  /**
   * @param {!Array<!CellData>} rowCells
   * @param {boolean=} isRowHead
   */
  addRow(rowCells, isRowHead) {
    if (this.done_) {
      throw new Error('TableMaker object has already emitted a table');
    }

    /**
     * @param {!Array<CellData>} cells
     * @return {HTMLTableRowElement}
     */
    const makeRowElement = (cells) => {
      const row = document.createElement('tr');
      cells.forEach((cellData) => {
        const e = document.createElement(isRowHead ? 'th' : 'td');
        const span = document.createElement('span');
        span.innerHTML = cellData.content;
        if (cellData.tooltip) {
          utils.registerTooltipOn(span, cellData.tooltip, {dX: 20, dY: 20});
        }
        [].concat(cellData.class || []).forEach((c) => {
          span.classList.add(c);
        });
        if (cellData.id) {
          e.id = cellData.id;
        }
        if (cellData.iframe) {
          configureIframeViewAnchor(span, cellData.iframe);
        }
        e.append(span);
        row.append(e);
      });
      return row;
    };
    this.table_.append(makeRowElement(rowCells));
  }

  /**
   * @return {HTMLTableElement}
   */
  finish() {
    this.done_ = true;
    return this.table_;
  }
}

/**
 * @param {!Event} event
 */
function openFileInIframe(event) {
  console.log(event.target);
}

/**
 * @param {HTMLSpanElement} span
 * @param {string} iframeSrc
 */
function configureIframeViewAnchor(span, iframeSrc) {
  span.classList.add('iframe_opener');
  const detailsView = utils.querySelector('#entry_details_view');
  const iframeView = utils.querySelector('#iframe_view');
  const iframeDescText =
      utils.querySelector('#iframe_desc #desc_text', iframeView);
  const iframeOpenLink =
      utils.querySelector('#iframe_desc a#open_link', iframeView);
  const iframeInsertionPoint =
      utils.querySelector('#iframe_insertion_point', iframeView);
  const closeIframeView = () => {
    span.classList.remove('iframe_opened');
    detailsView.classList.remove('iframe_opened');
    iframeView.classList.remove('iframe_opened');
    iframeInsertionPoint.innerHTML = '';
  };
  span.addEventListener('click', () => {
    const now_opened = span.classList.toggle('iframe_opened');
    // Don't use utils.querySelectorAll() here, because the resultant
    // array might be empty.
    detailsView.querySelectorAll('span.iframe_opened').forEach((e) => {
      if (e !== span) {
        e.classList.remove('iframe_opened');
      }
    });
    if (now_opened) {
      detailsView.classList.add('iframe_opened');
      iframeView.classList.add('iframe_opened');
      iframeDescText.textContent = utils.capWidthByMiddleEllipsis(
          iframeSrc, iframeDescText.scrollWidth / 9);
      iframeOpenLink.setAttribute('href', iframeSrc);
      const copyButton = utils.makeCopyButton(iframeSrc, 'span', 'copy_link');
      // Don't use utils.querySelector() here, because the resultant
      // element might be null.
      const previousCopyButton =
          iframeDescText.parentElement.querySelector('#copy_link');
      if (previousCopyButton) {
        previousCopyButton.remove();  // Clear the previous button.
      }
      iframeDescText.parentElement.insertBefore(copyButton, iframeOpenLink);
      utils.querySelector('#close_iframe', iframeView)
          .addEventListener('click', closeIframeView);
      const iframe = document.createElement('iframe');
      iframe.name = 'raw_file_presenter';
      iframe.id = 'raw_file_presenter';
      iframe.src = iframeSrc;
      iframeInsertionPoint.innerHTML = '';  // Clear the previous file.
      iframeInsertionPoint.append(iframe);
    } else {
      closeIframeView();
    }
  });
}
