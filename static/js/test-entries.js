// @ts-nocheck

let test_stats = { total: 0, success: 0, error: 0, error_but_flaky: 0 };
Array.from(document.getElementsByClassName('test_entry_button')).forEach(button => {
    const entryExpansion = getEntryExpansionFromEntryButton(button);
    button.addEventListener('click', () => {
        button.classList.toggle('test_entry_expanded');
        if (entryExpansion.style.maxHeight) {
            setEntryExpansionState(entryExpansion, false);
        } else {
            setEntryExpansionState(entryExpansion, true);
        }
    });

    const successCountSpan = entryExpansion.querySelector('span#success_count');
    const successCount = Number(successCountSpan.textContent);
    const attemptCountSpan = entryExpansion.querySelector('span#attempt_count');
    const attemptCount = Number(attemptCountSpan.textContent);
    const flakyErrorAttemptCountSpan = entryExpansion.querySelector('span#flaky_error_count');
    const flakyErrorAttemptCount = Number(flakyErrorAttemptCountSpan.textContent);
    const errorAttemptCount = attemptCount - successCount;
    const allErrorsAreKnownFlaky = errorAttemptCount > 0 && flakyErrorAttemptCount === errorAttemptCount;

    const pluralSuffixSpan = entryExpansion.querySelector('span#plural_suffix');
    pluralSuffixSpan.textContent = attemptCount > 1 ? 's' : '';

    let entryThemeColor = '';
    let statusSvgIcon = null;
    let statusTextMsg = '';
    let statusClassName = '';
    test_stats.total += 1;
    if (errorAttemptCount === 0) { // All attempts are definite successes
        entryThemeColor = '#4caf50'; // Green
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        test_stats.success += 1;
        statusTextMsg = 'success';
        statusClassName = 'status_success';
        button.classList.add('entry_button_passed_test');
        entryExpansion.classList.add('entry_expansion_passed_test');
    } else if (allErrorsAreKnownFlaky) { // Treat the test status as success
        entryThemeColor = '#9932cc'; // Purple
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        test_stats.error_but_flaky += 1;
        statusTextMsg = 'all errors are known as flaky';
        statusClassName = 'status_pseudo_success';
        button.classList.add('entry_button_erred_but_flaky_test');
        entryExpansion.classList.add('entry_expansion_erred_but_flaky_test');
    } else { // Has definite error
        entryThemeColor = '#f03f50'; // Red
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: '#f03f50',
            path: 'M1 1 L14 14 M14 1 L1 14', // Cross mark
        });
        test_stats.error += 1;
        statusTextMsg = 'error';
        statusClassName = 'status_error';
        button.classList.add('entry_button_erred_test');
        entryExpansion.classList.add('entry_expansion_erred_test');
    }
    button.classList.add(statusClassName);
    entryExpansion.classList.add(statusClassName);
    button.style.borderLeftStyle = 'solid';
    button.style.borderLeftWidth = '5px';
    button.style.borderLeftColor = entryThemeColor;

    const successInfoDiv = entryExpansion.querySelector('#success_info');
    successInfoDiv.style.color = entryThemeColor;

    const statusIconSpan = button.querySelector('span#status_icon');
    statusIconSpan.appendChild(statusSvgIcon);
    const statusMsgSpan = button.querySelector('span#status_message');
    statusMsgSpan.textContent = statusTextMsg;
});

// Set innerHTML rather than innerText or textContent, for '&emsp;'.
document.body.querySelector("span#test_results_stats").innerHTML =
    `Total ${test_stats.total}&emsp;&emsp;&emsp;`
    + `Success ${test_stats.success}&emsp;&emsp;&emsp;`
    + `Error ${test_stats.error}&emsp;&emsp;&emsp;`
    + `Flaky ${test_stats.error_but_flaky}`;

Array.from(document.getElementsByClassName('golden_file_link_span')).forEach(e => {
    const anchorElement = e.querySelector('a#maybe_link');
    if (anchorElement.href.toLowerCase().endsWith('none')) {
        e.removeChild(anchorElement);
        e.textContent = '(none)';
    }
});

Array.from(document.getElementsByClassName('invocation_button')).forEach(button => {
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
            contentElement.style.borderStyle = 'solid';
        });
        copyButton.addEventListener('mouseup', () => {
            contentElement.style.borderStyle = 'none';
        })
    });
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
const controlledByShowErrors = document.body.querySelectorAll([
    '.test_entry_button.status_error',
    '.test_entry_expansion.status_error',
].join(','));
checkboxShowErrors.addEventListener('click', () => {
    controlledByShowErrors.forEach(e => {
        e.style.display = checkboxShowErrors.checked ? null : 'none';
     });
});
checkboxShowErrors.addEventListener('mouseenter', () => {
    controlledByShowErrors.forEach(e => {
        e.style.opacity = 0.5;
     });
});
checkboxShowErrors.addEventListener('mouseout', () => {
    controlledByShowErrors.forEach(e => {
        e.style.opacity = null;
     });
});

const checkboxShowSuccesses = document.body.querySelector(
    'input#view_control_visibility_checkbox_successes');
const controlledByShowSuccesses = document.body.querySelectorAll([
    '.test_entry_button.status_success',
    '.test_entry_expansion.status_success',
    '.test_entry_button.status_pseudo_success',
    '.test_entry_expansion.status_pseudo_success',
].join(','));
checkboxShowSuccesses.addEventListener('click', () => {
    controlledByShowSuccesses.forEach(e => {
        e.style.display = checkboxShowSuccesses.checked ? null : 'none';
     });
});
checkboxShowSuccesses.addEventListener('mouseenter', () => {
    controlledByShowSuccesses.forEach(e => {
        e.style.opacity = 0.5;
     });
});
checkboxShowSuccesses.addEventListener('mouseout', () => {
    controlledByShowSuccesses.forEach(e => {
        e.style.opacity = null;
     });
});

const buttonExpandOrCollapseAll = document.body.querySelector(
    'a#view_control_expand_or_collapse_button');
buttonExpandOrCollapseAll.addEventListener('click', () => {
    const strExpandAll = 'expand all'; // The string should be synced with the HTML
    const strCollapseAll = 'collapse all';
    const testEntryButtons = document.body.querySelectorAll('.test_entry_button');
    const dT = 500 / (testEntryButtons.length + 1); // Milliseconds
    if (buttonExpandOrCollapseAll.textContent === strExpandAll) {
        testEntryButtons.forEach(async (button, idx) => {
            await sleepTimeout((testEntryButtons.length - idx - 1) * dT);
            button.classList.add('test_entry_expanded');
            const entryExpansion = getEntryExpansionFromEntryButton(button);
            setEntryExpansionState(entryExpansion, true);
        });
        buttonExpandOrCollapseAll.textContent = strCollapseAll;
    } else { // strCollapseAll
        testEntryButtons.forEach(async (button, idx) => {
            await sleepTimeout(idx * dT);
            button.classList.remove('test_entry_expanded');
            const entryExpansion = getEntryExpansionFromEntryButton(button);
            setEntryExpansionState(entryExpansion, false);
        });
        buttonExpandOrCollapseAll.textContent = strExpandAll;
    }
});

/**
 * Expand or collapse a test entry.
 * @param {!HTMLElement} entryExpansion
 * @param {boolean} doExpand true: expand, false: collapse
 */
function setEntryExpansionState(entryExpansion, doExpand) {
    const invocationExpansion = entryExpansion.querySelector('.invocation_expansion');
    if (doExpand) {
        const h = entryExpansion.scrollHeight + invocationExpansion.scrollHeight;
        entryExpansion.style.maxHeight = `${h}px`;
    } else {
        entryExpansion.style.maxHeight = null; // Not 0
        invocationExpansion.style.maxHeight = null; // Not 0
    }
}

/**
 * @param {!HTMLElement} button
 * @return {!HTMLElement}
 */
function getEntryExpansionFromEntryButton(button) {
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

/**
 * @param {number} milliseconds
 * @return {!Promise}
 */
async function sleepTimeout(milliseconds) {
    return new Promise(resolve => {
        setTimeout(resolve, milliseconds);
    });
}
