"""Re-point answers whose audio was wrongly declared missing.

The analysis worker used to overwrite answer_text with the literal string
"Audio file missing" when a fetch failed, destroying the only pointer to the
recording. When the failure was transient - most often a second worker running
against the same database but a different MinIO - the audio is still sitting in
the bucket and the answer is recoverable.

This finds those rows, locates their audio by the session id and question index
encoded in the object name, re-points answer_text at it and clears the error so
the worker picks it up again.

    python scripts/recover_missing_answer_audio.py                       # dry run
    python scripts/recover_missing_answer_audio.py --apply
    python scripts/recover_missing_answer_audio.py --minio-host 172.16.1.100:9000 --apply

Run it where the audio actually lives, or pass --minio-host.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

BROKEN_MARKERS = ("Audio file missing", "Error in audio processing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Write the changes. Without this it only reports.")
    ap.add_argument("--session", help="Limit to one interview_session_id.")
    ap.add_argument("--minio-host", help="Override MINIO_HOST, e.g. 172.16.1.100:9000.")
    args = ap.parse_args()

    from app.core.config import _load_interview_configs
    _load_interview_configs()

    from app.core import config as consts
    from app.services import minio_helper as mh

    if args.minio_host:
        consts.MINIO_HOST = args.minio_host
        mh._minio_client = None
        print(f"Using MinIO at {args.minio_host}\n")

    from sqlmodel import Session, select
    from app.db.session import engine
    from app import models

    # Index every answer-audio object by (session_id, question_index).
    client = mh.get_minio_client()
    available = {}
    for obj in client.list_objects(
        consts.INFOSPOKE_S3_BUCKET_NAME, prefix="ai-interviews/audio/", recursive=True
    ):
        name = obj.object_name.rsplit("/", 1)[-1]
        # audio_<session-uuid>_<question_index>_<timestamp><ext>
        if not name.startswith("audio_"):
            continue
        stem = name[len("audio_"):]
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        session_id, q_index = parts[0], parts[1]
        try:
            available[(session_id, int(q_index))] = obj.object_name
        except ValueError:
            continue

    print(f"{len(available)} answer-audio object(s) present in MinIO\n")

    with Session(engine) as session:
        stmt = select(models.QNA_Analysis).where(
            models.QNA_Analysis.is_deleted == False  # noqa: E712
        )
        rows = session.exec(stmt).all()

        broken = []
        for row in rows:
            text = (row.answer_text or "").strip()
            state = row.ai_analysis if isinstance(row.ai_analysis, dict) else {}
            if text in BROKEN_MARKERS or state.get("status") in (
                "error", "audio_fetch_failed"
            ):
                broken.append(row)

        if args.session:
            keep = set(
                r.id for r in session.exec(
                    select(models.InterviewAnalysis).where(
                        models.InterviewAnalysis.interview_session_id == args.session
                    )
                ).all()
            )
            broken = [r for r in broken if r.interview_analysis_id in keep]

        if not broken:
            print("No broken answers found.")
            return 0

        # Map each broken row back to its interview session.
        analysis_ids = {r.interview_analysis_id for r in broken}
        sessions_by_analysis = {
            a.id: a.interview_session_id
            for a in session.exec(
                select(models.InterviewAnalysis).where(
                    models.InterviewAnalysis.id.in_(analysis_ids)
                )
            ).all()
        }

        recovered, unrecoverable = [], []
        for row in broken:
            sid = sessions_by_analysis.get(row.interview_analysis_id)
            state = row.ai_analysis if isinstance(row.ai_analysis, dict) else {}
            # Newer failures record the path directly; older ones lost it and
            # must be matched by session id plus question index.
            key = state.get("audio_path") or available.get((sid, row.question_id))
            if key and key in available.values():
                recovered.append((row, key, sid))
            else:
                unrecoverable.append((row, sid))

        print(f"{len(broken)} broken answer(s): "
              f"{len(recovered)} recoverable, {len(unrecoverable)} not\n")

        for row, key, sid in recovered:
            print(f"  RECOVER  row={row.id} session={sid[:8]} Q{row.question_id}")
            print(f"           was: {(row.answer_text or '')[:52]!r}")
            print(f"           ->   AUDIO_PENDING:{key.rsplit('/',1)[-1]}")
        for row, sid in unrecoverable:
            print(f"  NO AUDIO row={row.id} session={sid[:8] if sid else '?'} "
                  f"Q{row.question_id} - audio is genuinely gone")

        if not args.apply:
            print("\nDry run. Re-run with --apply to write these changes.")
            return 0

        for row, key, _ in recovered:
            row.answer_text = f"AUDIO_PENDING:{key}"
            row.ai_analysis = None  # clears the error so the worker re-claims it
            session.add(row)
        session.commit()

    print(f"\nRe-pointed {len(recovered)} answer(s). The analysis worker will "
          "pick them up on its next poll.")
    print("Make sure exactly ONE worker is running against this database, and "
          "that it can reach the MinIO holding the audio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
