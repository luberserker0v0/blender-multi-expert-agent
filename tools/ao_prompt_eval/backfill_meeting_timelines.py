from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_meeting_probe import build_meeting_timeline, render_meeting_timeline, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill meeting_timeline files for existing AO prompt eval runs.")
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    count = 0
    for request_path in sorted(args.run_root.glob("*/*/request.json")):
        case_dir = request_path.parent
        request = json.loads(request_path.read_text(encoding="utf-8-sig"))
        response_text = (case_dir / "response.txt").read_text(encoding="utf-8-sig", errors="replace")
        response = {
            "messageId": request.get("response_message_id", ""),
            "text": response_text,
            "parts": [{"type": "text", "text": response_text}] if response_text.strip() else [],
        }
        timeline = build_meeting_timeline(
            request=request,
            response=response,
            response_text=response_text,
            before_state={"sessions": [], "children_by_session": {}, "events": [], "errors": []},
            after_state={"sessions": [], "children_by_session": {}, "events": [], "errors": []},
        )
        write_json(case_dir / "meeting_timeline.json", timeline)
        (case_dir / "meeting_timeline.md").write_text(render_meeting_timeline(timeline), encoding="utf-8-sig")
        count += 1
    print(f"wrote {count} meeting timeline files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
