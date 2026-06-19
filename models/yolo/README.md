# YOLO Local Models

Put local YOLO model files in this directory.

Recommended examples:

- `yolo26s.pt`
- `yolo26n.pt`
- `yolo26s-seg.pt`

This folder is intended for manually downloaded local model weights used by:

- `scripts/smoke_test_live_yolo.py`
- optional YOLO validation paths in the Python runtime

Example path:

- `repo/models/yolo/yolo26s.pt`

Note: `models/` is ignored by git. Keep downloaded weights local or publish
them through a separate model/artifact store.
