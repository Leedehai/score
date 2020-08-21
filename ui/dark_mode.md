# Supporting dark mode
> Using vanilla HTML, CSS, JavaScript, on a static site.

Credit: [Ryan Feigenbaum](https://ryanfeigenbaum.com/dark-mode/).

Developers [love dark mode](https://web.dev/prefers-color-scheme/), especially
during the night. Supporting dark mode on the page is not only beneficial, but
also arguably imperative, given that human eyes don't handle sudden change in
brightness well.

## Feature request

- Have a predefined mapping color values between light and dark modes.
- User can toggle between light and dark modes.
- The initial color mode on page load respects user's setting, and if not
found, the system preference.

## Browser support

In modern browsers, there are several features to take advantage of:

- HTML custom attributes [`data-*`](https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/data-*)
- CSS custom properties [`--*`](https://developer.mozilla.org/en-US/docs/Web/CSS/--*)
- media query
[`prefers-color-scheme`](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme)
in JavaScript Web API [`window.matchMedia`](https://developer.mozilla.org/en-US/docs/Web/API/Window/matchMedia)
and in CSS [`@media`](https://developer.mozilla.org/en-US/docs/Web/CSS/Media_Queries/Using_media_queries).


## Let's do it

### Step 1

In the `<html>` tag, add custom attribute `data-color-mode` and its default
value `light`.

```html
<html data-color-mode="light">
  <head>
    <title>Play with color modes</title>
    ... css, javascript ...
  </head>
  <body>
    <div>This is a test.</div>
  </body>
</html>
```

### Step 2

Use CSS custom properties to define color schemes for both the light and dark
modes.

Name the colors in a way that is agnostic to the color mode, e.g. avoid
adjectives like "light" or "dark", because while a dark shade of color appears
salient in light mode, it would be inconspicuous in dark mode.

Use the `:root` pseudo-element so that the custom properties can be applied to
any element. Use the attribute selector `[data-color-mode="..."]` to specify
the color mode.

```css
:root[data-color-mode="light"] {
  --bg-color: #fff;
  --fg-color: #000;
  --red: #f9e9e7;
  --red-bold: #c84031;
  --green: #e9f4eb;
  --green-bold: #3c7d40;
  --yellow: #faf4df;
  --yellow-bold: #eeac3c;
}

:root[data-color-mode="dark"] {
  --bg-color: #202124;
  --fg-color: #e8eaed;
  --red: #554141;
  --red-bold: #e49086;
  --green: #414f46;
  --green-bold: #91c699;
  --yellow: #59533d;
  --yellow-bold: #f7d575;
}
```

You can apply the color schemes in your CSS definitions, like this:

```css
body {
  background-color: var(--bg-color);
  color: var(--fg-color);
  border-color: var(--green);
  border-style: solid;
  border-width: 1px;
  font-family: 'Open Sans', 'Helvetica', sans-serif;
  font-size: 16px;
  margin: 0;
}
```

### Step 3

Implement UI widgets to toggle between the two color modes. For a prettier
appearance, I used [SVG](https://developer.mozilla.org/en-US/docs/Web/SVG)
to render a sun and a moon. Arrange HTML and CSS so that only one toggle is
shown on page: in light mode, the moon; in dark mode, the sun.

HTML:

```html
<!-- Define the SVG -->
<svg style="display: none;">
    <symbol viewBox="0 0 24 24" id="color_mode_control_icon_sun">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
    </symbol>
    <symbol viewBox="0 0 24 24" id="color_mode_control_icon_moon">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
    </symbol>
</svg>

<!-- The toggles -->
<button class="color_mode_button hidden_in_light_mode" id="enable_light_mode">
    <svg>
        <title>Light mode</title>
        <use href="#color_mode_control_icon_sun"></use>
    </svg>
</button>
<button class="color_mode_button hidden_in_dark_mode" id="enable_dark_mode">
    <svg>
        <title>Dark mode</title>
        <use href="#color_mode_control_icon_moon"></use>
    </svg>
</button>
```

CSS:

```css
:root[data-color-mode="light"] .hidden_in_light_mode {
  display: none;
}

:root[data-color-mode="dark"] .hidden_in_dark_mode {
  display: none;
}

.color_mode_button {
  display: flex;
  align-items: right;
  justify-content: right;
  padding: 5px;
  margin: 0 auto 1.5rem;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1;
  color: var(--fg-color);
  cursor: pointer;
  background: none;
  border: none;
  border-radius: 50px;
}

.color_mode_button svg {
  width: 1.5em;
  height: 1.5em;
  fill: none;
  stroke: var(--fg-color);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5px;
}

.color_mode_button#enable_dark_mode:hover svg,
.color_mode_button#enable_dark_mode:focus svg {
  outline: none;
  fill: var(--blue-bold);
}

.color_mode_button#enable_light_mode:hover svg,
.color_mode_button#enable_light_mode:focus svg {
  outline: none;
  fill: var(--yellow-bold);
}
```

JavaScript:

```js
document.querySelectorAll('.color_mode_button').forEach((button) => {
  button.addEventListener('click', (event) => {
    const targetElement = /** @type {HTMLElement} */ (event.currentTarget);
    const elementId = targetElement.id;
    if (elementId === 'enable_light_mode') {
      document.documentElement.setAttribute('data-color-mode', 'light');
      // localStorage.setItem('data-color-mode', 'light');
    } else if (elementId === 'enable_dark_mode') {
      document.documentElement.setAttribute('data-color-mode', 'dark');
      // localStorage.setItem('data-color-mode', 'dark');
    } else {
      throw new Error(`unrecognized color mode button id ${elementId}.`)
    }
  });
});
```

You are almost there! Check out the effects in your browser.

### Step 4

We want the browser to remember what color mode the user has set, so after a
reload the page can stay in that color mode. To do that, we use the browser's
[`localStorage`](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage).

Uncomment the lines containing `localStorage.setItem(...)` in the JavaScript
snippet above, **and** add JavaScript:

```js
// Assuming the default color mode is 'light' in Step 1.
if (localStorage.getItem('data-color-mode') === 'dark') {
  document.documentElement.setAttribute('data-color-mode', 'dark');
}
```

### Step 5

We also want the color mode to have a proper initial value that takes the
system preference into account. To do that, we use media query
[`prefers-color-scheme`](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme)
using the Web API
[`matchMedia`](https://developer.mozilla.org/en-US/docs/Web/API/Window/matchMedia).

Replace the JavaScript added in the previous step with this:

```js
// Assuming the default color mode is 'light' in Step 1.
const matcher = window.matchMedia('(prefers-color-scheme: dark)');
if (localStorage.getItem('data-color-mode') === 'dark' ||
    (matcher.matches && !localStorage.getItem('data-color-mode'))) {
  document.documentElement.setAttribute('data-color-mode', 'dark');
}
```

Done.

### (bonus) Color-mode-aware favicon

We want the icon shown in the browser tab be aware of the system preference
of color mode as well. To do that, you need to have two versions of icon
images ready, and put embed this JavaScript snippet on the page:

```js
const matcher = window.matchMedia('(prefers-color-scheme: dark)');
function onUpdate() {
  const prevIcon = document.querySelector('link#favicon');
  if (prevIcon) {
    prevIcon.remove();
  }
  const icon = document.createElement('link');
  icon.rel = 'icon';
  icon.id = 'favicon';
  icon.href = matcher.matches ? 'favicon_for_dark_mode.png' :
                                'favicon_for_light_mode.png';
  document.head.append(icon);
}
matcher.addListener(onUpdate);
onUpdate();
```

■
