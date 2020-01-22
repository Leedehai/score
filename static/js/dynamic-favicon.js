// @ts-nocheck

// Set favicon based on browser light/dark theme.
const matcher = window.matchMedia('(prefers-color-scheme: dark)');
function onUpdate() {
    const prevIcon = document.querySelector('link#favicon');
    if (prevIcon) {
        prevIcon.remove();
    }

    const icon = document.createElement('link');
    icon.rel = 'icon';
    icon.id = 'favicon';
    icon.href = matcher.matches ? 'static/img/check_logo_dark.png'
                                : 'static/img/check_logo_light.png';
    document.head.append(icon);
}
matcher.addListener(onUpdate);
onUpdate();
