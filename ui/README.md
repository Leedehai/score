# UI

The UI generator [score_ui.py](https://github.com/Leedehai/score/blob/master/score_ui.py)
takes the log produced by the test runner
[score_run.py](https://github.com/Leedehai/score/blob/master/score_run.py) and
produces a static site, with UI assets contained in this directory.

The generated site does not require a server (not even a static file server).
All you need to do is point your browser to the file path of the generated
`index.html`. This constraint limits what the site can do (e.g. load files
dynamically), but is justified by user-friendliness.

The site is built with standard HTML, CSS, and JavaScript, and you do not need
to install any package. A standard-compliant modern web browser is necessary,
though (no Internet Explorer, please).

Internet access to [Google Fonts](https://fonts.googleapis.com) is optional but
highly recommended. If the browser couldn't load the fonts and icons, the UI
might be weird (some bits are missing), but the site is still operational.

Development was done in the Chrome browser, and tested with Firefox.

■
