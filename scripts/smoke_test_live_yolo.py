"""Smoke test live Blender MCP capture plus multi-view YOLO perception."""

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.blender.mcp_adapter import BlenderMcpAdapter
from ai_3d_modeling_agent.perception.yolo_provider import (
    BlenderCaptureYoloPerceptionProvider,
    YoloProviderConfig,
)
from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient
from ai_3d_modeling_agent.services.model_runtime import LocalModelLoader
from ai_3d_modeling_agent.services.yolo_runtime import UltralyticsYoloBackend


DEFAULT_BLENDER_MCP_COMMAND = "uv"
DEFAULT_BLENDER_MCP_ARGS = ["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"]
DEFAULT_BLENDER_MCP_CWD = "C:\\blender_mcp\\mcp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test live Blender capture plus YOLO inference.")
    parser.add_argument("--yolo-model-path", required=True, help="Path to a local YOLO model file.")
    parser.add_argument(
        "--viewpoint",
        action="append",
        dest="viewpoints",
        help="Repeatable viewpoint. Defaults to front, side, top.",
    )
    parser.add_argument(
        "--yolo-confidence-threshold",
        type=float,
        default=0.25,
        help="Confidence threshold for YOLO predict.",
    )
    parser.add_argument(
        "--primary-target-part",
        default="apple_body",
        help="Primary target part used for missing-part and bbox metric logic.",
    )
    parser.add_argument(
        "--capture-prefix",
        default="live_yolo_smoke",
        help="Prefix used for saved capture files.",
    )
    parser.add_argument(
        "--blender-mcp-command",
        default=DEFAULT_BLENDER_MCP_COMMAND,
        help="Command used to launch the Blender MCP stdio server.",
    )
    parser.add_argument(
        "--blender-mcp-cwd",
        default=DEFAULT_BLENDER_MCP_CWD,
        help="Working directory used to launch the Blender MCP stdio server.",
    )
    parser.add_argument(
        "--blender-mcp-arg",
        action="append",
        dest="blender_mcp_args",
        help="Repeatable argument passed to the Blender MCP stdio server.",
    )
    return parser


def build_client(args: argparse.Namespace) -> SdkMCPClient:
    return SdkMCPClient(
        McpClientConfig(
            command=args.blender_mcp_command,
            args=list(args.blender_mcp_args or DEFAULT_BLENDER_MCP_ARGS),
            cwd=args.blender_mcp_cwd,
        )
    )


def pretty_print(label: str, value) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def summarize_detections(observed_by_viewpoint: dict) -> dict:
    summary = {}
    for viewpoint, result in observed_by_viewpoint.items():
        detections = sorted(
            [
                {
                    "part_name": item.part_name,
                    "confidence": item.confidence,
                    "bbox_center_ratio": list(item.bbox_center_ratio),
                    "bbox_xyxy": list(item.bbox_xyxy),
                    "viewpoint": item.viewpoint,
                }
                for item in result.detections
            ],
            key=lambda item: item["confidence"],
            reverse=True,
        )
        summary[viewpoint] = {
            "detected_parts": list(result.detected_parts),
            "missing_critical_parts": list(result.missing_critical_parts),
            "detection_count": len(detections),
            "detections_by_confidence": detections,
        }
    return summary


def write_annotated_images(capture_paths: dict, observed_by_viewpoint: dict) -> dict:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise ImportError("Pillow is required to draw detection boxes.") from exc

    annotated_paths = {}
    font = ImageFont.load_default()
    for viewpoint, capture_path in capture_paths.items():
        image = Image.open(capture_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        detections = getattr(observed_by_viewpoint.get(viewpoint), "detections", []) or []

        for item in detections:
            bbox = list(item.bbox_xyxy)
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(round(value)) for value in bbox]
            label = f"{item.part_name} {item.confidence:.3f}"
            draw.rectangle((x1, y1, x2, y2), outline=(255, 64, 64), width=3)

            text_bbox = draw.textbbox((x1, y1), label, font=font)
            text_x1, text_y1, text_x2, text_y2 = text_bbox
            label_box = (
                text_x1,
                max(0, text_y1 - 2),
                text_x2 + 4,
                text_y2 + 2,
            )
            draw.rectangle(label_box, fill=(255, 64, 64))
            draw.text((x1 + 2, max(0, y1 - 12)), label, fill=(255, 255, 255), font=font)

        capture_path_obj = Path(capture_path)
        annotated_path = capture_path_obj.with_name(f"{capture_path_obj.stem}_annotated{capture_path_obj.suffix}")
        image.save(annotated_path)
        annotated_paths[viewpoint] = str(annotated_path)

    return annotated_paths


def main() -> int:
    args = build_parser().parse_args()
    viewpoints = list(args.viewpoints or ["front", "side", "top"])
    capture_dir = REPO_ROOT / "data" / "runtime" / "captures"

    client = build_client(args)
    adapter = BlenderMcpAdapter(
        client=client,
        session_id="live-yolo-smoke",
        capture_output_dir=capture_dir,
    )
    provider = BlenderCaptureYoloPerceptionProvider(
        config=YoloProviderConfig(
            model_path=Path(args.yolo_model_path),
            primary_target_part=args.primary_target_part,
            emit_bbox_metrics=True,
            viewpoints=viewpoints,
            confidence_threshold=args.yolo_confidence_threshold,
            capture_name_prefix=args.capture_prefix,
            class_name_map={args.primary_target_part: args.primary_target_part},
        ),
        object_ops=adapter,
        loader=LocalModelLoader(UltralyticsYoloBackend()),
    )

    try:
        provider.load_model()
        observed_by_viewpoint = {}
        for viewpoint in viewpoints:
            capture_name = f"{args.capture_prefix}_{viewpoint}.png"
            capture_path = Path(adapter.capture_view(capture_name, viewpoint=viewpoint))
            observed_by_viewpoint[viewpoint] = provider._observe_image(capture_path, viewpoint=viewpoint)
        merged = provider.merge_view_results(observed_by_viewpoint)
    except Exception as exc:
        print("\n=== smoke_error ===")
        print(str(exc))
        return 1

    capture_paths = {
        viewpoint: str(capture_dir / f"{args.capture_prefix}_{viewpoint}.png")
        for viewpoint in viewpoints
    }
    per_view_summary = {
        viewpoint: result.to_dict()
        for viewpoint, result in observed_by_viewpoint.items()
    }
    confidence_summary = summarize_detections(observed_by_viewpoint)
    annotated_paths = write_annotated_images(capture_paths, observed_by_viewpoint)

    pretty_print("capture_paths", capture_paths)
    pretty_print("annotated_capture_paths", annotated_paths)
    pretty_print("per_view_results", per_view_summary)
    pretty_print("per_view_confidence_summary", confidence_summary)
    pretty_print("merged_result", merged.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
