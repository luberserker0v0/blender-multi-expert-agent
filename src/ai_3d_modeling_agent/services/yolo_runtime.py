"""Ultralytics-backed YOLO runtime integration."""

from ai_3d_modeling_agent.services.model_runtime import LocalModelBackend, LocalModelConfig


class UltralyticsYoloBackend(LocalModelBackend):
    """Load YOLO models through the official Ultralytics Python API."""

    def load(self, config: LocalModelConfig):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "Ultralytics is required for YOLO runtime integration. Install the 'ultralytics' package."
            ) from exc

        task = config.extra_options.get("task")
        return YOLO(str(config.model_path), task=task)
