// @ts-nocheck

Array.from(document.getElementsByClassName('test_entry_button')).forEach(button => {
    const entryExpansion = button.nextElementSibling;
    button.addEventListener('click', event => {
        const thisButton = event.target;
        thisButton.classList.toggle('test_entry_expanded');
        const invocationExpansion = entryExpansion
            .getElementsByClassName('invocation_expansion')[0];
        if (entryExpansion.style.maxHeight) {
            entryExpansion.style.maxHeight = null; // Not 0
            invocationExpansion.style.maxHeight = null; // Not 0
        } else {
            const h = entryExpansion.scrollHeight + invocationExpansion.scrollHeight;
            entryExpansion.style.maxHeight = `${h}px`;
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
    if (errorAttemptCount === 0) { // All attempts are definite successes
        entryThemeColor = '#4caf50'; // Green
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        statusTextMsg = 'success';
        button.classList.add('entry_button_passed_test');
        entryExpansion.classList.add('entry_expansion_passed_test');
    } else if (allErrorsAreKnownFlaky) { // Treat the test status as success
        entryThemeColor = '#9932cc'; // Purple
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: entryThemeColor,
            path: 'M0.5 9 L6.5 13.7 L14.5 1.5', // Check mark
        });
        statusTextMsg = 'all errors are known as flaky';
        button.classList.add('entry_button_erred_but_flaky_test');
        entryExpansion.classList.add('entry_expansion_erred_but_flaky_test');
    } else { // Has definite error
        entryThemeColor = '#f03f50'; // Red
        statusSvgIcon = makeSvgPath({
            width: 15, height: 15, color: '#f03f50',
            path: 'M1 1 L14 14 M14 1 L1 14', // Cross mark
        });
        statusTextMsg = 'error';
        button.classList.add('entry_button_erred_test');
        entryExpansion.classList.add('entry_expansion_erred_test');
    }
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

Array.from(document.getElementsByClassName('golden_file_link_span')).forEach(e => {
    const anchorElement = e.querySelector('a#maybe_link');
    if (anchorElement.href.toLowerCase().endsWith('none')) {
        e.removeChild(anchorElement);
        e.textContent = '(none)';
    }
});

Array.from(document.getElementsByClassName('invocation_button')).forEach(button => {
    button.addEventListener('click', event => {
        const thisButton = event.target;
        thisButton.classList.toggle('invocation_expanded');
        const copyButton = thisButton.nextElementSibling;
        const invocationExpansion = thisButton.nextElementSibling.nextElementSibling;
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
 * @param {HTMLElement} contentElement
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
