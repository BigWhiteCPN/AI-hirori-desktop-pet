# Room Assets

Put transparent PNG room assets in this folder. The app reads `room_layout.json` when it starts, and you can press `Ctrl+O` in the app to reload the layout and images.

Recommended files:

- `background.png` - full room background, drawn behind everything.
- `window.png` - back wall window.
- `bookshelf.png` - back furniture.
- `bed.png` - bed/rest area.
- `rug.png` - floor rug/walking area.
- `desk.png` - writing desk. Default `z` is in front of the Live2D model.
- `toybox.png` - play area item. Default `z` is in front of the Live2D model.

Layout coordinates are normalized:

- `x`, `y`: top-left position from `0.0` to `1.0`.
- `w`: width relative to the room window width.
- `h`: optional height relative to the room window height. If omitted, the PNG aspect ratio is preserved.
- `z`: layer order. Objects below `model_z` are behind the Live2D character; objects at or above `model_z` are drawn in front.
- `anchor`: optional. Use `top_left`, `center`, `bottom_left`, or `bottom_center`.
- `shadow`: optional. `true` adds a soft contact shadow under the object so it sits better in the room.
- `shadow_opacity`: optional. Use values like `0.12` to `0.24`.
- `remove_checkerboard`: optional. Set `true` on an object only when the PNG accidentally contains a gray/white checkerboard background instead of real transparency.

Activity coordinates under `activities` control where the Live2D model stands in each state. Use `x`, `y`, and `scale`; walking can use `x_min` and `x_max`.

If a checkerboard appears in the app, the image is not truly transparent. Prefer exporting a real PNG with alpha. As a fallback, add `"remove_checkerboard": true` to that object in `room_layout.json`.
