// @ts-nocheck

let gTestStats = { total: 0, success: 0, error: 0, error_but_flaky: 0 };
let gSelectedButton = /* {?HtmlElement} */null;
let gDetailPanelPlaceholder = (function() {
  const div = document.createElement('div');
  div.style = 'position: relative; height: 200px';
  span = document.createElement('span');
  span.style = '\
    position: absolute; left: 38%; top: 10%; \
    font-family: Helvetica, sans-serif; font-size: 16px; font-weight: bold; \
    text-align: center; \
    color: #aaa; \
  ';
  span.innerText = 'Click a test to view details.';
  div.appendChild(span);
  return div;
})();
const gDetailPanel = document.querySelector('.entry_details_view');
replaceView(gDetailPanel, gDetailPanelPlaceholder);

const gTestEntryButtons = document.body.querySelectorAll('.test_entry_button');
gTestEntryButtons.forEach(button => {
    const entryDetail = getEntryDetailFromEntryButton(button);
    button.addEventListener('click', () => {
        const clickedOnSelectedButton = window.gSelectedButton === button;
        if (clickedOnSelectedButton) {
            button.classList.remove('test_entry_detail_displayed');
            window.gSelectedButton = null;
            replaceView(gDetailPanel, gDetailPanelPlaceholder);
        } else {
            if (window.gSelectedButton) {
                window.gSelectedButton.classList.remove('test_entry_detail_displayed');
            }
            window.gSelectedButton = button;
            button.classList.add('test_entry_detail_displayed');
            replaceView(gDetailPanel, makeEntryDetailView(entryDetail));
        }
    });

    const successCountSpan = entryDetail.querySelector('span#success_count');
    const successCount = Number(successCountSpan.textContent);
    const attemptCountSpan = entryDetail.querySelector('span#attempt_count');
    const attemptCount = Number(attemptCountSpan.textContent);
    const flakyErrorAttemptCountSpan = entryDetail.querySelector('span#flaky_error_count');
    const flakyErrorAttemptCount = Number(flakyErrorAttemptCountSpan.textContent);
    const errorAttemptCount = attemptCount - successCount;
    const allErrorsAreKnownFlaky = errorAttemptCount > 0 && flakyErrorAttemptCount === errorAttemptCount;

    const pluralSuffixSpan = entryDetail.querySelector('span#plural_suffix');
    pluralSuffixSpan.textContent = attemptCount > 1 ? 's' : '';

    let entryThemeColor = '';
    let statusSvgIcon = null;
    let statusTextMsg = '';
    let statusClassName = '';
    gTestStats.total += 1;
    if (errorAttemptCount === 0) { // All attempts are definite successes
        entryThemeColor = '#4caf50'; // Green
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        gTestStats.success += 1;
        statusTextMsg = 'success';
        statusClassName = 'status_success';
        button.classList.add('entry_button_passed_test');
        entryDetail.classList.add('entry_detail_passed_test');
    } else if (allErrorsAreKnownFlaky) { // Treat the test status as success
        entryThemeColor = '#9932cc'; // Purple
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        gTestStats.error_but_flaky += 1;
        statusTextMsg = 'all errors are known as flaky';
        statusClassName = 'status_pseudo_success';
        button.classList.add('entry_button_erred_but_flaky_test');
        entryDetail.classList.add('entry_detail_erred_but_flaky_test');
    } else { // Has definite error
        entryThemeColor = '#f03f50'; // Red
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: '#f03f50',
            path: 'M1 1 L14 14 M14 1 L1 14', // Cross mark
        });
        gTestStats.error += 1;
        statusTextMsg = 'error';
        statusClassName = 'status_error';
        button.classList.add('entry_button_erred_test');
        entryDetail.classList.add('entry_detail_erred_test');
    }
    button.classList.add(statusClassName);
    entryDetail.classList.add(statusClassName);
    button.style.borderLeftStyle = 'solid';
    button.style.borderLeftWidth = '5px';
    button.style.borderLeftColor = entryThemeColor;

    const successInfoDiv = entryDetail.querySelector('#success_info');
    successInfoDiv.style.color = entryThemeColor;

    const statusIconSpan = button.querySelector('span#status_icon');
    statusIconSpan.appendChild(statusSvgIcon);
    const statusMsgSpan = button.querySelector('span#status_message');
    statusMsgSpan.textContent = statusTextMsg;
});

// Set innerHTML rather than innerText or textContent, for '&emsp;'.
document.body.querySelector("span#test_results_stats").innerHTML =
    `Total ${gTestStats.total}&emsp;&emsp;&emsp;`
    + `Success ${gTestStats.success}&emsp;&emsp;&emsp;`
    + `Error ${gTestStats.error}&emsp;&emsp;&emsp;`
    + `Flaky ${gTestStats.error_but_flaky}`;

Array.from(document.getElementsByClassName('golden_file_link_span')).forEach(e => {
    const anchorElement = e.querySelector('a#maybe_link');
    if (anchorElement.href.toLowerCase().endsWith('none')) {
        e.removeChild(anchorElement);
        e.textContent = '(none)';
    }
});

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
 * @param {!HTMLElement} contentElement
 */
function copyToClipboard(contentElement) {
    const copyToClipboardImpl = () => {
        navigator.clipboard.writeText(contentElement.textContent);
    };
    try {
        if (navigator.permissions) {
            navigator.permissions.query({ name: 'clipboard-write' }).then(result => {
                if (result.state == 'granted' || result.state == 'prompt') {
                    copyToClipboardImpl();
                }
            }).catch(() => { // Firefox does not fully support the Permission API.
                copyToClipboardImpl();
            });
        } else { // Some others do not support the Permission API at all.
            copyToClipboardImpl();
        }
    } catch (e) { // Safari, uhh..
        if (e instanceof TypeError) {
            window.alert('The copy-text feature encountered a bug.\n\n'
             + 'It needs Clipboard API and Permissions API, features\n'
             + 'required in the Web Standard. Your browser does not\n'
             + 'support them. Consider using another browser.');
        }
    }
}

/**
 * @param {object} param
 * @param {number} param.width
 * @param {number} param.height
 * @param {string} param.path
 * @param {string} param.color
 */
function makeSvgPath({ width, height, path, color }) {
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svgPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    svgPath.setAttribute('d', path);
    svgPath.setAttribute('stroke', color);
    svgPath.setAttribute('stroke-width', 2);
    svgPath.setAttribute('fill', 'transparent');
    svg.appendChild(svgPath);
    return svg;
}

const checkboxShowErrors = document.body.querySelector(
    'input#view_control_visibility_checkbox_errors');
const controlledByShowErrors = document.body.querySelectorAll(
    '.test_entry_button.status_error',
);
const checkboxShowSuccesses = document.body.querySelector(
    'input#view_control_visibility_checkbox_successes');
const controlledByShowSuccesses = document.body.querySelectorAll([
    '.test_entry_button.status_success',
    '.test_entry_button.status_pseudo_success', // known flaky tests which succeeded
].join(','));
const searchBarElement = document.body.querySelector(
  'input.entries_search_bar'
);

/**
 * @param {!HTMLButtonElement} buttonElement
 * @param {boolean} shouldDisplay
 */
function setButtonDisplayState(buttonElement, shouldDisplay) {
    buttonElement.style.display = shouldDisplay ? null : 'none';
    if (!shouldDisplay && window.gSelectedButton === buttonElement) {
      window.gSelectedButton = null;
      buttonElement.classList.remove('test_entry_detail_displayed');
      replaceView(gDetailPanel, gDetailPanelPlaceholder);
    }
};
let displayEntryCriteria = {showSuccesses: true, showErrors: true, descQuery: ''};
function updateDisplayState(updateState) {
    Object.assign(displayEntryCriteria, updateState);
    gTestEntryButtons.forEach(button => {
        const desc = button.querySelector('span#full_description').textContent;
        const isSuccess = button.classList.contains('status_success')
            || button.classList.contains('status_pseudo_success');
        const isError = button.classList.contains('status_error');
        const pickedUpByShowSuccess = displayEntryCriteria.showSuccesses && isSuccess;
        const pickedUpByShowError = displayEntryCriteria.showErrors && isError;
        let pickedUpByDescQuery = true;
        try {
          pickedUpByDescQuery = desc.search(new RegExp(displayEntryCriteria.descQuery)) >= 0;
        } catch (e) { // Invalid Regex
          searchBarElement.style = "color: #f03f50;"; // Red
          console.log(searchBarElement.style);
          return;
        }
        searchBarElement.style = "color: initial;";
        if ((pickedUpByShowSuccess || pickedUpByShowError) && pickedUpByDescQuery) {
            setButtonDisplayState(button, true);
        } else {
            setButtonDisplayState(button, false);
        }
    });
}
const opacitySetter = /** @type {number|null} */ opacity => element => {
    element.style.opacity = opacity;
};
checkboxShowErrors.addEventListener('click', () => {
    updateDisplayState({showErrors: checkboxShowErrors.checked});
});
checkboxShowErrors.addEventListener('mouseenter', () => {
    controlledByShowErrors.forEach(opacitySetter(0.5));
});
checkboxShowErrors.addEventListener('mouseout', () => {
    controlledByShowErrors.forEach(opacitySetter(null));
});
checkboxShowSuccesses.addEventListener('click', () => {
    updateDisplayState({showSuccesses: checkboxShowSuccesses.checked});
});
checkboxShowSuccesses.addEventListener('mouseenter', () => {
    controlledByShowSuccesses.forEach(opacitySetter(0.5));
});
checkboxShowSuccesses.addEventListener('mouseout', () => {
    controlledByShowSuccesses.forEach(opacitySetter(null));
});
searchBarElement.addEventListener('keyup', () => {
  // Not 'keypress' because it doesn't catch Deletion key.
  updateDisplayState({descQuery: searchBarElement.value});
})

/**
 * @param {!HTMLElement} entryDetail
 * @return {!HTMLElement}
 */
function makeEntryDetailView(entryDetail) {
    const invocationExpansion = entryDetail.querySelector('.invocation_expansion');
    const fullHeight = entryDetail.scrollHeight + invocationExpansion.scrollHeight;
    const cloned = entryDetail.cloneNode(/*deep=*/true);
    const invocationButton = cloned.querySelector('.invocation_button');
    if (invocationButton) {
        AddInvocationExpansionListener(invocationButton);
    }
    const stdoutAnchor = cloned.querySelector('.link_stdout');
    if (stdoutAnchor) {
        AddIframeOpenListener(stdoutAnchor);
    }
    cloned.style.maxHeight = fullHeight;
    return cloned;
}

/**
 * @param {!HTMLElement} button Note: not necessarily an HTMLButtonElement
 */
function AddInvocationExpansionListener(button) {
    button.addEventListener('click', () => {
        button.classList.toggle('invocation_expanded');
        const copyButton = getInvocationCopyButtonFromInvocationButton(button);
        const invocationExpansion = getInvocationExpansionFromInvocationButton(button);
        if (invocationExpansion.style.maxHeight) {
            invocationExpansion.style.maxHeight = null; // Not 0
            copyButton.style.visibility = 'hidden';
        } else {
            const h = invocationExpansion.scrollHeight;
            invocationExpansion.style.maxHeight = `${h}px`;
            copyButton.style.visibility = 'visible';
        }
        const contentElement = invocationExpansion.querySelector('#invocation_content');
        copyButton.addEventListener('click', () => {
            copyToClipboard(contentElement);
        });
        copyButton.addEventListener('mousedown', () => {
            contentElement.style.color = 'blue';
        });
        copyButton.addEventListener('mouseup', () => {
            contentElement.style.color = 'black';
        })
    });
};

/**
 * @param {!HTMLAnchorElement} anchorElement
 */
function AddIframeOpenListener(anchorElement) {
    anchorElement.addEventListener('click', (event) => {
        event.preventDefault(); // Don't open a link.
        if (anchorElement.classList.contains('link_stdout_open')) {
          anchorElement.classList.remove('link_stdout_open');
          const iframe = gDetailPanel.querySelector('.test_stdout_iframe');
          gDetailPanel.removeChild(iframe);
        } else {
          anchorElement.classList.add('link_stdout_open');
          const url = anchorElement.href;
          const iframe = document.createElement('iframe');
          iframe.classList.add('test_stdout_iframe');
          iframe.src = url;
          gDetailPanel.appendChild(iframe);
        }
    });
}

/**
 * @param {!HTMLElement} anchorElement
 * @param {!HTMLElement} viewElement
 */
function replaceView(anchorElement, viewElement) {
    anchorElement.textContent = ''; // Remove all child nodes.
    anchorElement.appendChild(viewElement);
}

/**
 * @param {!HTMLElement} button
 * @return {!HTMLElement}
 */
function getEntryDetailFromEntryButton(button) {
    return button.nextElementSibling; // Sync with HTML
}

/**
 * @param {!HTMLElement} button
 * @return {!HTMLElement}
 */
function getInvocationCopyButtonFromInvocationButton(button) {
    return button.nextElementSibling; // Sync with HTML
}

/**
 * @param {!HTMLElement} button
 * @return {!HTMLElement}
 */
function getInvocationExpansionFromInvocationButton(button) {
    return button.nextElementSibling.nextElementSibling; // Sync with HTML
}
