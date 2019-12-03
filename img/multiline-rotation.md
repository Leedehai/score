# Multiline-rotation

Single-line eliding is achieved with printing the `\r` character.

Multi-line rotation is more sophisticated:
- Move cursor up and clear line by `\033[1A\033[2K`
- Share queue across processes

No errors:

![multiline-roation](multiline-rotation.gif)

With errors:

![multiline-roation](multiline-rotation-err.gif)

###### EOF