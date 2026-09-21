"""Create disposable interview sessions for testing audio/visual proctoring.

Manual testing needs a session id that passes the /submit-answer-av lookup,
which means a job -> application -> session -> analysis chain must exist. This
builds a self-contained one and can tear the whole thing down again, so real
candidate records are never touched.

Everything it creates is prefixed so it is obvious in the database and safe to
delete: the job is `ZZ-TEST-AVPROCTOR`, applicants are named "AVTest", and the
job is left unsubmitted and closed so it should not surface in normal job
listings.

    python scripts/seed_test_sessions.py --create          # make 3 sessions
    python scripts/seed_test_sessions.py --create -n 5     # make 5
    python scripts/seed_test_sessions.py --list            # show what exists
    python scripts/seed_test_sessions.py --delete          # remove all of it
"""

import argparse
import hashlib
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from sqlmodel import Session, select  # noqa: E402

from app import models  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.utils import timezone_utils  # noqa: E402

JOB_CODE = "ZZ-TEST-AVPROCTOR"
JOB_TITLE = "ZZ TEST - AV Proctoring Harness"
NAME_TAG = "AVTest"

# Deliberately ordinary interview questions - the point is to have something
# plausible to read aloud while testing, long enough to produce the 3+ seconds
# of speech the detector needs before it will judge an answer at all.
QUESTIONS = [
    {
        "question_id": 1,
        "question": "Walk me through a project you have worked on recently. "
                    "What was your specific role, and what did you build?",
        "expected_time": "2-3 mins",
        "difficulty_level": "easy",
        "question_type": "experience",
    },
    {
        "question_id": 2,
        "question": "Describe a bug that took you a long time to track down. "
                    "How did you eventually find the cause?",
        "expected_time": "2-3 mins",
        "difficulty_level": "medium",
        "question_type": "technical",
    },
    {
        "question_id": 3,
        "question": "How do you decide when a piece of code needs tests, and "
                    "what do you choose not to test?",
        "expected_time": "2-3 mins",
        "difficulty_level": "medium",
        "question_type": "technical",
    },
    {
        "question_id": 4,
        "question": "Tell me about a time you disagreed with a technical "
                    "decision on your team. What did you do?",
        "expected_time": "2-3 mins",
        "difficulty_level": "medium",
        "question_type": "situational",
    },
    {
        "question_id": 5,
        "question": "What part of your current tech stack would you replace if "
                    "you could, and what would you replace it with?",
        "expected_time": "2-3 mins",
        "difficulty_level": "hard",
        "question_type": "technical",
    },
]


def get_or_create_job(session: Session) -> int:
    job = session.exec(
        select(models.CreateJobDetails).where(
            models.CreateJobDetails.job_code == JOB_CODE
        )
    ).first()
    if job:
        return job.job_id

    job = models.CreateJobDetails(
        job_title=JOB_TITLE,
        job_code=JOB_CODE,
        location="Test",
        country="India",
        openings=0,
        work_mode="Remote",
        employment_type="Full Time",
        skills_must_have="testing",
        min_experience=0,
        max_experience=1,
        additional_notes="Disposable job created by scripts/seed_test_sessions.py "
                         "for AV proctoring tests. Safe to delete.",
        # Unsubmitted and closed, so it should stay out of normal job listings.
        submit=False,
        is_open=False,
        created_by="av-proctoring-test",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    print(f"  created test job job_id={job.job_id} ({JOB_CODE})")
    return job.job_id


def create_session(session: Session, job_id: int, index: int) -> dict:
    now = timezone_utils.get_ist_now()

    application = models.JobApplications(
        first_name=NAME_TAG,
        last_name=f"Candidate{index:02d}",
        email=f"avtest.candidate{index:02d}@example.invalid",
        ph_no="0000000000",
        job_id=job_id,
        created_date=now,
        current_stage="AI Interview",
        stage_entry_date=now,
        privacy_policy=True,
        contact_future_opportunities=False,
        rejected=False,
        in_person_interviews=False,
    )
    session.add(application)
    session.commit()
    session.refresh(application)

    # tb_interview_sessions.application_id carries a second foreign key onto
    # tb_resume_analysis.application_id that the SQLModel definitions do not
    # declare, so a resume-analysis row has to exist before the session will
    # insert. Values are placeholders - nothing here feeds AV proctoring.
    session.add(
        models.ResumeAnalysis(
            application_id=application.id,
            job_id=job_id,
            candidate_name=f"{application.first_name} {application.last_name}",
            email=application.email,
            contact_number=application.ph_no,
            final_score=75.0,
            skills_match=75.0,
            experience_score=75.0,
            education_score=75.0,
            keywords_match=75.0,
            overall_fit=75.0,
            growth_potential=75.0,
            recommendation_decision="Shortlisted",
            recommendation_reason="Seeded test record for AV proctoring.",
            recommendation_confidence="medium",
            skill_match_percentage=75.0,
            experience_level="mid",
            education_level="graduate",
            salary_expectation_alignment="aligned",
            onboarding_priority="medium",
            processing_time=0.0,
            file_path="seeded/test/no-resume.pdf",
            file_size=0.0,
            word_count=0,
            status="Shortlisted",
        )
    )
    session.commit()

    session_uuid = str(uuid.uuid4())
    exit_password = hashlib.sha256(session_uuid.encode()).hexdigest()

    interview_session = models.InterviewSessions(
        application_id=application.id,
        interview_session_id=session_uuid,
        question_type="AI",
        created_date=now,
        scheduled_time=now,
        is_scheduled=True,
        schedule_email_sent=False,
        status=models.InterviewSessionStatusEnum.scheduled,
        exam_exit_password=exit_password,
        interview_scheduled_datetime=now + timedelta(minutes=5),
        job_id=job_id,
        min_pass_percentage=70,
        acceptable_score_range="50",
        questions_status=True,
        move_to_schedule=True,
        move_to_schedule_datetime=now,
        scheduled_by="av-proctoring-test",
        interview_link=f"http://localhost:8080/av_test.html?session={session_uuid}",
    )
    # Committed before the analysis row: tb_interview_analysis has a foreign
    # key onto tb_interview_sessions.interview_session_id, and these are plain
    # Field-level FKs with no ORM relationship, so SQLModel will not order the
    # two inserts for us.
    session.add(interview_session)
    session.commit()

    # /submit-answer-av looks up InterviewAnalysis, so it must exist and be
    # in_progress - a completed interview rejects further submissions.
    analysis = models.InterviewAnalysis(
        application_id=application.id,
        interview_session_id=session_uuid,
        status=models.StatusEnum.in_progress,
        questions=QUESTIONS,
        total_score=0.0,
        recommendation="",
        analysis_completed=False,
        final_decision="",
        email_sent=False,
        is_deleted=False,
        job_id=job_id,
        interview_started_datetime=now,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)

    return {
        "session_id": session_uuid,
        "application_id": application.id,
        "analysis_id": analysis.id,
        "candidate": f"{NAME_TAG} Candidate{index:02d}",
    }


def find_test_data(session: Session):
    job = session.exec(
        select(models.CreateJobDetails).where(
            models.CreateJobDetails.job_code == JOB_CODE
        )
    ).first()
    if not job:
        return None, [], []
    apps = session.exec(
        select(models.JobApplications).where(
            models.JobApplications.job_id == job.job_id
        )
    ).all()
    app_ids = [a.id for a in apps]
    sessions = []
    if app_ids:
        sessions = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id.in_(app_ids)
            )
        ).all()
    return job, apps, sessions


def do_create(count: int):
    with Session(engine) as session:
        job_id = get_or_create_job(session)
        created = [create_session(session, job_id, i + 1) for i in range(count)]

    print(f"\n  {len(created)} test session(s) ready:\n")
    for c in created:
        print(f"    {c['session_id']}   {c['candidate']}  "
              f"(application_id={c['application_id']})")
    print("\n  Paste a session id into av_test.html, or:")
    print(f"    curl \"http://127.0.0.1:5002/api/interview/av-analysis"
          f"?interview_session_id={created[0]['session_id']}\"")
    print(f"\n  Remove all of it again with:")
    print("    python scripts/seed_test_sessions.py --delete")


def do_list():
    with Session(engine) as session:
        job, apps, sessions = find_test_data(session)
        if not job:
            print("  No test data found.")
            return
        print(f"  job_id={job.job_id} ({JOB_CODE})")
        print(f"  {len(apps)} application(s), {len(sessions)} session(s)\n")
        for s in sessions:
            app = next((a for a in apps if a.id == s.application_id), None)
            av_rows = session.exec(
                select(models.AnswerAVAnalysis).where(
                    models.AnswerAVAnalysis.interview_session_id
                    == s.interview_session_id
                )
            ).all()
            name = f"{app.first_name} {app.last_name}" if app else "?"
            verdicts = ", ".join(sorted({r.verdict for r in av_rows})) or "none yet"
            print(f"    {s.interview_session_id}   {name:22} "
                  f"clips analysed: {len(av_rows):2}  [{verdicts}]")


def do_delete():
    from app.services import minio_helper as aws_helper

    with Session(engine) as session:
        job, apps, sessions = find_test_data(session)
        if not job:
            print("  Nothing to delete.")
            return

        session_ids = [s.interview_session_id for s in sessions]
        app_ids = [a.id for a in apps]

        analyses = []
        if session_ids:
            analyses = session.exec(
                select(models.InterviewAnalysis).where(
                    models.InterviewAnalysis.interview_session_id.in_(session_ids)
                )
            ).all()
        analysis_ids = [a.id for a in analyses]

        # AV rows first, deleting any clip still parked in MinIO with them.
        av_rows = []
        if session_ids:
            av_rows = session.exec(
                select(models.AnswerAVAnalysis).where(
                    models.AnswerAVAnalysis.interview_session_id.in_(session_ids)
                )
            ).all()
        clips_removed = 0
        for row in av_rows:
            if row.clip_path:
                if aws_helper.delete_s3_object(row.clip_path).get("success"):
                    clips_removed += 1
            session.delete(row)

        # Then anything hanging off the analyses.
        for model in (models.ProctoringLogs, models.QNA_Analysis):
            if not analysis_ids:
                break
            for row in session.exec(
                select(model).where(model.interview_analysis_id.in_(analysis_ids))
            ).all():
                session.delete(row)

        # Committed in dependency order. These are plain Field-level foreign
        # keys with no ORM relationships, so SQLAlchemy will not sequence the
        # deletes itself and would otherwise try to remove a parent first.
        session.commit()

        for row in analyses:
            session.delete(row)
        session.commit()

        for row in sessions:
            session.delete(row)
        session.commit()

        # Everything else keyed on the application, including the
        # resume-analysis row the session FK required.
        if app_ids:
            for model in (
                models.AIInterviewQuestions,
                models.EvaluationSummary,
                models.ResumeAnalysis,
                models.ResumeLogs,
            ):
                for row in session.exec(
                    select(model).where(model.application_id.in_(app_ids))
                ).all():
                    session.delete(row)
            session.commit()

        for row in apps:
            session.delete(row)
        session.commit()

        session.delete(job)
        session.commit()

    print(f"  Deleted: 1 job, {len(apps)} application(s), {len(sessions)} session(s), "
          f"{len(analyses)} analysis row(s), {len(av_rows)} AV row(s), "
          f"{clips_removed} MinIO clip(s).")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--delete", action="store_true")
    ap.add_argument("-n", "--count", type=int, default=3)
    args = ap.parse_args()

    from app.core.config import _load_interview_configs
    _load_interview_configs()

    if args.create:
        do_create(args.count)
    elif args.list:
        do_list()
    else:
        do_delete()


if __name__ == "__main__":
    main()
