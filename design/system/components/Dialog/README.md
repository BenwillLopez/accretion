# Dialog

A modal card for a short task: add the source, more ways to install, the download screen, picking an installer.

## Use
- A native `<dialog>` opened with `showModal()`: `surface`, `line` edge, `radius-2xl`, at most `form-max` wide, 22px padding; the page behind gets `scrim` and a 4px blur.
- Title in `section-title`, one `muted` sentence saying what to do, then the choices, then actions with one primary. Close is a ghost button at the end.
- Choose-one options use the segmented `.seg` grid; a link to copy goes in a `.url` well (`code` style on `raised`, select-all).
- The preview shows it inline; on the page it floats over the scrim.
