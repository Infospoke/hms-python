"""Push the generated sample clips at a session, without using a browser.

Useful for checking the endpoint, worker and retention behaviour end to end,
or for re-testing after changing a threshold.

    python scripts/upload_av_samples.py <interview_session_id>
    python scripts/upload_av_samples.py <session_id> --only 02 --api http://127.0.0.1:5002
"""

import argparse
import glob
import json
import os
import sys
import time

import requests

SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "av"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--api", default="http://127.0.0.1:5002")
    ap.add_argument("--only", help="Substring filter, e.g. '02' or 'suspicious'.")
    ap.add_argument("--wait", type=int, default=120,
                    help="Seconds to wait for the worker to finish analysing.")
    args = ap.parse_args()

    clips = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.webm")))
    if args.only:
        clips = [c for c in clips if args.only in os.path.basename(c)]
    if not clips:
        print(f"No sample clips found in {SAMPLES_DIR}. "
              "Run scripts/generate_av_samples.py first.")
        return 1

    api = args.api.rstrip("/")
    expected = {}
    manifest_path = os.path.join(SAMPLES_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            expected = {m["file"]: m["expected_verdict"] for m in json.load(f)}

    print(f"Uploading {len(clips)} clip(s) to session {args.session_id}\n")
    for i, clip in enumerate(clips, start=1):
        name = os.path.basename(clip)
        with open(clip, "rb") as f:
            r = requests.post(
                f"{api}/api/interview/submit-answer-av",
                data={"interview_session_id": args.session_id, "question_index": i},
                files={"clip": (name, f, "video/webm")},
                timeout=300,
            )
        status = "queued" if r.status_code == 202 else f"FAILED {r.status_code}"
        print(f"  Q{i:<3} {name:48} {status}")
        if r.status_code != 202:
            print(f"        {r.text[:200]}")

    print(f"\nWaiting up to {args.wait}s for analysis ...")
    deadline = time.time() + args.wait
    results = []
    while time.time() < deadline:
        time.sleep(3)
        data = requests.get(f"{api}/api/interview/av-analysis",
                            params={"interview_session_id": args.session_id},
                            timeout=60).json()
        results = data.get("results", [])
        if len(results) >= len(clips):
            break

    print(f"\n{len(results)}/{len(clips)} analysed\n")
    print(f"  {'Q':<4}{'verdict':<17}{'speech':<9}{'face':<7}"
          f"{'mouth/speech':<14}{'voices':<8}clip")
    mismatches = 0
    for r in sorted(results, key=lambda x: x["question_index"]):
        idx = r["question_index"]
        clip_name = os.path.basename(clips[idx - 1]) if idx <= len(clips) else "?"
        want = expected.get(clip_name)
        flag = ""
        if want and want != r["verdict"]:
            flag = f"  <- expected {want}"
            mismatches += 1
        print(f"  {idx:<4}{r['verdict']:<17}"
              f"{str(r['speech_seconds']) + 's':<9}"
              f"{format(r['face_coverage'], '.0%'):<7}"
              f"{format(r['mouth_active_ratio_during_speech'], '.0%'):<14}"
              f"{r['distinct_voice_clusters']:<8}"
              f"{'kept' if r['clip_retained'] else 'deleted'}{flag}")
        for reason in r.get("reasons", []):
            print(f"       - {reason}")

    if mismatches:
        print(f"\n  {mismatches} clip(s) did not match the expected verdict.")
        return 1
    print("\n  All clips matched their expected verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
