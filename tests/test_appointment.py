"""
考试预约与补考管理测试。
覆盖：管理员配置场次名额/时段、学生申请、教师审核、
预约状态驱动开考资格、次数限制、成绩统计与证书发放。
"""
from datetime import datetime, timedelta

import pytest

from app.models import Exam, ExamAttempt, ExamQuestion, ExamAppointment
from app.schemas.appointment import SessionCreate, AppointmentCreate
from app.schemas.attempt import ExamSubmitRequest
from app.services import (
    attempt_service, appointment_service, grade_service,
)


def _make_published_exam(db, pass_score=60):
    exam = Exam(title="预约测试考试", subject_id=1, duration_minutes=60,
                total_score=100, pass_score=pass_score, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def _make_session(db, exam, quota=50, max_attempts=2,
                  start_delta_hours=-1, end_delta_hours=24):
    return appointment_service.create_session(db, SessionCreate(
        exam_id=exam.id,
        name="测试场次",
        start_time=datetime.now() + timedelta(hours=start_delta_hours),
        end_time=datetime.now() + timedelta(hours=end_delta_hours),
        quota=quota,
        max_attempts=max_attempts,
    ), user_id=1)


def _apply_and_approve(db, session, user, reviewer, appointment_type="regular", reason=""):
    appt = appointment_service.apply_appointment(db, user, AppointmentCreate(
        session_id=session.id, appointment_type=appointment_type, reason=reason))
    return appointment_service.review_appointment(db, appt, reviewer, approve=True, comment="通过")


# ---------- 场次与名额 ----------
def test_session_create_and_booked_count(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, quota=2)
    assert appointment_service.count_session_booked(db, session.id) == 0

    teacher = make_user("teacher_a", role="teacher")
    s1 = make_user("book_s1")
    s2 = make_user("book_s2")
    _apply_and_approve(db, session, s1, teacher)
    assert appointment_service.count_session_booked(db, session.id) == 1

    # 第二名学生：待审核不占名额，审核通过后占名额
    appt2 = appointment_service.apply_appointment(
        db, s2, AppointmentCreate(session_id=session.id))
    assert appointment_service.count_session_booked(db, session.id) == 1
    appointment_service.review_appointment(db, appt2, teacher, approve=True, comment="通过")
    assert appointment_service.count_session_booked(db, session.id) == 2


def test_session_time_range_validated(db):
    exam = _make_published_exam(db)
    with pytest.raises(ValueError, match="结束时间"):
        appointment_service.create_session(db, SessionCreate(
            exam_id=exam.id, name="非法场次",
            start_time=datetime.now() + timedelta(days=1),
            end_time=datetime.now(),
        ), user_id=1)


# ---------- 学生申请 ----------
def test_apply_regular_is_pending(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    student = make_user("apply_s1")
    appt = appointment_service.apply_appointment(
        db, student, AppointmentCreate(session_id=session.id))
    assert appt.status == "pending"
    assert appt.appointment_type == "regular"
    assert appt.attempt_no == 1


def test_duplicate_apply_blocked(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    student = make_user("dup_s1")
    appointment_service.apply_appointment(
        db, student, AppointmentCreate(session_id=session.id))
    with pytest.raises(ValueError, match="已有"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(session_id=session.id))


def test_closed_session_apply_blocked(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    session.status = "closed"
    db.commit()
    student = make_user("closed_s1")
    with pytest.raises(ValueError, match="关闭预约"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(session_id=session.id))


# ---------- 补考规则 ----------
def test_retake_requires_failed_attempt(db, make_question, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, max_attempts=2)
    teacher = make_user("teacher_b", role="teacher")
    student = make_user("retake_s1")
    q = make_question("single_choice", correct_ids=(1,))
    db.add(ExamQuestion(exam_id=exam.id, question_id=q.id, score=10))
    db.commit()

    # 没考过：不能申请补考
    with pytest.raises(ValueError, match="尚未参加"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(session_id=session.id, appointment_type="retake"))

    # 正考流程：申请 -> 审核 -> 开考 -> 答错（0 分不及格）
    appt = _apply_and_approve(db, session, student, teacher)
    attempt = attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")
    assert attempt.appointment_id == appt.id
    attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "3", "time_spent_seconds": 20},
    ]))
    # 交卷后预约自动完成
    db.refresh(appt)
    assert appt.status == "completed"

    # 补考必须填写理由
    with pytest.raises(ValueError, match="申请理由"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(
                session_id=session.id, appointment_type="retake", reason=""))

    # 不及格可申请补考，attempt_no=2
    retake = appointment_service.apply_appointment(
        db, student, AppointmentCreate(
            session_id=session.id, appointment_type="retake", reason="复习后申请补考"))
    assert retake.attempt_no == 2


def test_retake_blocked_when_passed(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, max_attempts=2)
    student = make_user("passed_s1")
    now = datetime.now()
    db.add(ExamAttempt(exam_id=exam.id, user_id=student.id, start_time=now,
                       submit_time=now, score=90, status="graded", is_passed=1))
    db.commit()
    with pytest.raises(ValueError, match="已通过"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(
                session_id=session.id, appointment_type="retake", reason="想刷分"))


def test_attempt_count_limit(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, max_attempts=1)
    student = make_user("limit_s1")
    now = datetime.now()
    db.add(ExamAttempt(exam_id=exam.id, user_id=student.id, start_time=now,
                       submit_time=now, score=50, status="graded", is_passed=0))
    db.commit()
    with pytest.raises(ValueError, match="次数已用完"):
        appointment_service.apply_appointment(
            db, student, AppointmentCreate(
                session_id=session.id, appointment_type="retake", reason="再考一次"))


# ---------- 教师审核与名额 ----------
def test_review_quota_exhausted(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, quota=1, max_attempts=1)
    teacher = make_user("teacher_c", role="teacher")
    s1, s2 = make_user("quota_s1"), make_user("quota_s2")
    a1 = appointment_service.apply_appointment(
        db, s1, AppointmentCreate(session_id=session.id))
    a2 = appointment_service.apply_appointment(
        db, s2, AppointmentCreate(session_id=session.id))
    appointment_service.review_appointment(db, a1, teacher, approve=True, comment="通过")
    # 名额已满，第二个不能通过，只能驳回
    with pytest.raises(ValueError, match="名额"):
        appointment_service.review_appointment(db, a2, teacher, approve=True, comment="通过")
    appointment_service.review_appointment(db, a2, teacher, approve=False, comment="名额不足")
    assert a2.status == "rejected"


def test_cancel_own_appointment(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    student = make_user("cancel_s1")
    appt = appointment_service.apply_appointment(
        db, student, AppointmentCreate(session_id=session.id))
    appointment_service.cancel_appointment(db, appt, student)
    assert appt.status == "cancelled"


def test_cannot_cancel_others_appointment(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    s1, s2 = make_user("owner_s1"), make_user("other_s2")
    appt = appointment_service.apply_appointment(
        db, s1, AppointmentCreate(session_id=session.id))
    with pytest.raises(ValueError, match="无权"):
        appointment_service.cancel_appointment(db, appt, s2)


# ---------- 预约状态驱动开考资格 ----------
def test_start_without_appointment_blocked(db, make_user):
    exam = _make_published_exam(db)
    _make_session(db, exam)
    student = make_user("noappt_s1")
    with pytest.raises(ValueError, match="需预约"):
        attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")


def test_start_with_approved_appointment_ok(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    teacher = make_user("teacher_d", role="teacher")
    student = make_user("approved_s1")
    appt = _apply_and_approve(db, session, student, teacher)
    attempt = attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")
    assert attempt.appointment_id == appt.id


def test_start_outside_session_window_blocked(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    teacher = make_user("teacher_e", role="teacher")
    student = make_user("window_s1")
    _apply_and_approve(db, session, student, teacher)
    # 审核通过后将场次时段改为已过期（模拟不在预约时段内开考）
    session.start_time = datetime.now() - timedelta(hours=48)
    session.end_time = datetime.now() - timedelta(hours=24)
    db.commit()
    with pytest.raises(ValueError, match="时段"):
        attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")


def test_start_attempt_limit_enforced(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam, max_attempts=1)
    teacher = make_user("teacher_f", role="teacher")
    student = make_user("startlimit_s1")
    _apply_and_approve(db, session, student, teacher)
    now = datetime.now()
    db.add(ExamAttempt(exam_id=exam.id, user_id=student.id, start_time=now,
                       submit_time=now, score=50, status="graded", is_passed=0))
    db.commit()
    with pytest.raises(ValueError, match="次数已用完"):
        attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")


def test_legacy_exam_without_session_allows_once(db, make_user):
    """未配置场次的考试沿用旧规则：可直接参加，不能重复参加"""
    exam = _make_published_exam(db)
    student = make_user("legacy_s1")
    attempt = attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")
    assert attempt.appointment_id is None
    with pytest.raises(ValueError, match="已经参加过"):
        attempt_service.start_exam(db, exam, student.id, "127.0.0.1", "pytest")


# ---------- 成绩统计与证书 ----------
def test_appointment_stats(db, make_question, make_user):
    exam = _make_published_exam(db, pass_score=5)  # 自动评分每题满分 5 分，答对即及格
    session = _make_session(db, exam, quota=10, max_attempts=2)
    teacher = make_user("teacher_g", role="teacher")
    s1, s2 = make_user("stat_s1"), make_user("stat_s2")
    q = make_question("single_choice", correct_ids=(1,))
    db.add(ExamQuestion(exam_id=exam.id, question_id=q.id, score=10))
    db.commit()

    # s1 正考通过；s2 申请后被驳回
    a1 = _apply_and_approve(db, session, s1, teacher)
    attempt = attempt_service.start_exam(db, exam, s1.id, "127.0.0.1", "pytest")
    attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 20},
    ]))
    db.refresh(a1)
    a2 = appointment_service.apply_appointment(
        db, s2, AppointmentCreate(session_id=session.id))
    appointment_service.review_appointment(db, a2, teacher, approve=False, comment="不符合")

    stats = appointment_service.exam_appointment_stats(db, exam.id)
    assert stats["total_appointments"] == 2
    assert stats["by_status"]["completed"] == 1
    assert stats["by_status"]["rejected"] == 1
    assert stats["by_type"]["regular"] == 2
    assert stats["regular_attempts"] == 1
    assert stats["regular_pass_rate"] == 100.0
    assert stats["sessions"][0]["booked"] == 1
    assert stats["sessions"][0]["completed"] == 1


def test_certificate_requires_appointment_for_session_exam(db, make_user):
    exam = _make_published_exam(db)
    session = _make_session(db, exam)
    student = make_user("cert_s1")
    now = datetime.now()

    # 未预约的及格成绩不能发证
    db.add(ExamAttempt(exam_id=exam.id, user_id=student.id, start_time=now,
                       submit_time=now, score=90, status="graded", is_passed=1,
                       appointment_id=None))
    db.commit()
    with pytest.raises(ValueError, match="未预约"):
        grade_service.generate_certificate(db, student.id, exam.id)

    # 持已通过的预约参考并及格 -> 可发证（直接构造已审核通过的补考预约）
    appt = ExamAppointment(session_id=session.id, exam_id=exam.id, user_id=student.id,
                           appointment_type="retake", status="approved", attempt_no=2)
    db.add(appt)
    db.commit()
    db.add(ExamAttempt(exam_id=exam.id, user_id=student.id, start_time=now,
                       submit_time=now, score=95, status="graded", is_passed=1,
                       appointment_id=appt.id))
    db.commit()
    cert = grade_service.generate_certificate(db, student.id, exam.id)
    assert cert.score == 95


def test_retake_passed_best_score_for_rank(db, make_user):
    """补考后排名按每人最高分计算"""
    exam = _make_published_exam(db)
    s1, s2 = make_user("rank_s1"), make_user("rank_s2")
    now = datetime.now()
    # s1 正考 50、补考 90；s2 一次 80
    db.add(ExamAttempt(exam_id=exam.id, user_id=s1.id, start_time=now,
                       submit_time=now, score=50, status="graded", is_passed=0))
    db.add(ExamAttempt(exam_id=exam.id, user_id=s1.id, start_time=now,
                       submit_time=now, score=90, status="graded", is_passed=1))
    db.add(ExamAttempt(exam_id=exam.id, user_id=s2.id, start_time=now,
                       submit_time=now, score=80, status="graded", is_passed=1))
    db.commit()

    rank_info = grade_service.get_user_rank(db, s1.id, exam.id)
    assert rank_info["score"] == 90
    assert rank_info["total"] == 2
    assert rank_info["rank"] == 1

    board = grade_service.get_leaderboard(db, exam.id)
    user_ids = [item["user_id"] for item in board]
    assert sorted(user_ids) == sorted([s1.id, s2.id])
