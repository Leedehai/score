// @ts-nocheck

const statusBar = document.getElementById('status_bar');
const shortMessage = document.getElementById('status_bar_short_message');
if (window.errorTaskCount === 0) {
    statusBar.style.backgroundColor = '#f0f7ee'; // Light green
    statusBar.style.borderColor = '#4caf50'; // Dark green
    shortMessage.textContent = 'success';
} else {
    statusBar.style.backgroundColor = '#fbeceb'; // Light red
    statusBar.style.borderColor = '#dc153c'; // Dark red
    shortMessage.textContent = 'error';
}
shortMessage.style.color = statusBar.style.borderColor;

const testDirBreadcumb = document.getElementById('test_directory_breadcumbs');
window.absoluteTestDirectory.split('/').forEach((e, index, array) => {
    if (index < array.length - 5) { return; }
    const component = document.createElement('span');
    component.classList.add('component');
    component.textContent = e;
    testDirBreadcumb.appendChild(component);
    if (index < array.length - 1) {
        const separator = document.createElement('span');
        separator.textContent = '▸';
        testDirBreadcumb.appendChild(separator);
    }
});
