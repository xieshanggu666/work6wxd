"""考试预约与补考管理业务逻辑。

- 管理员：配置考试场次（时段、名额、限考次数）
- 学生：申请正考/补考预约
- 教师：审核预约（通过/驳回）
- 预约状态驱动：开考资格、次数限制、成绩统计、证书发放
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Exam, ExamAttempt, ExamSession, ExamAppointment, User,
)
from app.schemas.appointment import SessionCreate, SessionUpdate, AppointmentCreate

# 仍占用资格的预约状态（不能重复申请、不能重复开考）
ACTIVE_STATUSES = ("pending", "approved")
# 占用名额的预约状态
OCCUPY_STATUSES = ("approved", "completed")
VALID_REVIEW_STATUSES = ("pending",)


# ---------- 场次管理（管理员） ----------
def create_session(db: Session, data: SessionCreate, user_id: int) -> ExamSession:
    exam = db.query(Exam).filter(Exam.id == data.exam_id).first()
    if not exam:
        raise ValueError("考试不存在")
    if data.end_time <= data.start_time:
        raise ValueError("场次结束时间必须晚于开始时间")
    session = ExamSession(
        exam_id=data.exam_id,
        name=data.name.strip(),
        start_time=data.start_time,
        end_time=data.end_time,
        quota=data.quota,
        max_attempts=data.max_attempts,
        created_by=user_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def update_session(db: Session, session: ExamSession, data: SessionUpdate) -> ExamSession:
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ("open", "closed"):
        raise ValueError("场次状态只能为 open/closed")
    for field, value in updates.items():
        setattr(session, field, value)
    if session.end_time <= session.start_time:
        raise ValueError("场次结束时间必须晚于开始时间")
    # 名额不得小于当前已占用名额
    booked = count_session_booked(db, session.id)
    if session.quota < booked:
        raise ValueError(f"名额不能小于已占用名额（{booked} 人）")
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, session: ExamSession) -> None:
    active = (
        db.query(ExamAppointment)
        .filter(
            ExamAppointment.session_id == session.id,
            ExamAppointment.status.in_(ACTIVE_STATUSES),
        )
        .count()
    )
    if active:
        raise ValueError("该场次存在待审核或已通过的预约，无法删除")
    db.delete(session)
    db.commit()


def get_session(db: Session, session_id: int) -> ExamSession | None:
    return db.query(ExamSession).filter(ExamSession.id == session_id).first()


def list_sessions(db: Session, exam_id: int | None = None) -> list[ExamSession]:
    query = db.query(ExamSession)
    if exam_id:
        query = query.filter(ExamSession.exam_id == exam_id)
    return query.order_by(ExamSession.start_time.asc()).all()


def count_session_booked(db: Session, session_id: int) -> int:
    return (
        db.query(ExamAppointment)
        .filter(
            ExamAppointment.session_id == session_id,
            ExamAppointment.status.in_(OCCUPY_STATUSES),
        )
        .count()
    )


def list_sessions_with_booked(db: Session, exam_id: int | None = None) -> list[dict]:
    result = []
    for s in list_sessions(db, exam_id):
        booked = count_session_booked(db, s.id)
        result.append({
            "session": s,
            "exam_title": s.exam.title,
            "booked": booked,
            "remaining": max(0, s.quota - booked),
        })
    return result


# ---------- 学生申请 ----------
def apply_appointment(db: Session, user: User, data: AppointmentCreate) -> ExamAppointment:
    session = get_session(db, data.session_id)
    if not session:
        raise ValueError("考试场次不存在")
    if data.appointment_type not in ("regular", "retake"):
        raise ValueError("预约类型只能为 regular（正考）/ retake（补考）")
    if session.status != "open":
        raise ValueError("该场次已关闭预约")
    now = datetime.now()
    if now > session.end_time:
        raise ValueError("该场次已结束，无法预约")

    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    if not exam or exam.status != "published":
        raise ValueError("考试未发布，暂不能预约")

    # 同一考试存在进行中的预约（待审核/已通过）时禁止重复申请
    existing = (
        db.query(ExamAppointment)
        .filter(
            ExamAppointment.exam_id == session.exam_id,
            ExamAppointment.user_id == user.id,
            ExamAppointment.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if existing:
        raise ValueError("您已有该考试的预约申请，请勿重复提交")

    # 存在未完成的考试记录时禁止再次预约
    in_progress = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == session.exam_id,
            ExamAttempt.user_id == user.id,
            ExamAttempt.status == "in_progress",
        )
        .first()
    )
    if in_progress:
        raise ValueError("您有未完成的考试，请先完成后再申请")

    graded = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == session.exam_id,
            ExamAttempt.user_id == user.id,
            ExamAttempt.status == "graded",
        )
        .order_by(ExamAttempt.submit_time.asc())
        .all()
    )

    if data.appointment_type == "regular":
        if graded:
            raise ValueError("您已参加过该考试，如需重考请申请补考")
        attempt_no = 1
    else:
        if not graded:
            raise ValueError("您尚未参加过该考试，请申请正考预约")
        if graded[-1].is_passed == 1:
            raise ValueError("您已通过该考试，无需补考")
        if len(graded) >= session.max_attempts:
            raise ValueError(f"该场次限考 {session.max_attempts} 次，您的考试次数已用完")
        if not data.reason.strip():
            raise ValueError("补考申请请填写申请理由")
        attempt_no = len(graded) + 1

    # 名额校验（审核通过时会再次校验，防止并发超额）
    if count_session_booked(db, session.id) >= session.quota:
        raise ValueError("该场次名额已满，请选择其他场次")

    appointment = ExamAppointment(
        session_id=session.id,
        exam_id=session.exam_id,
        user_id=user.id,
        appointment_type=data.appointment_type,
        reason=data.reason.strip(),
        attempt_no=attempt_no,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(db: Session, appointment: ExamAppointment, user: User) -> ExamAppointment:
    if appointment.user_id != user.id:
        raise ValueError("无权取消他人的预约")
    if appointment.status not in ACTIVE_STATUSES:
        raise ValueError("当前预约状态不可取消")
    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)
    return appointment


def list_user_appointments(db: Session, user_id: int) -> list[ExamAppointment]:
    return (
        db.query(ExamAppointment)
        .filter(ExamAppointment.user_id == user_id)
        .order_by(ExamAppointment.created_at.desc())
        .all()
    )


# ---------- 教师审核 ----------
def review_appointment(db: Session, appointment: ExamAppointment, reviewer: User,
                       approve: bool, comment: str) -> ExamAppointment:
    if appointment.status not in VALID_REVIEW_STATUSES:
        raise ValueError("该预约已审核，请勿重复操作")
    if approve:
        # 通过时再次校验名额
        if count_session_booked(db, appointment.session_id) >= appointment.session.quota:
            raise ValueError("该场次名额已满，无法通过审核")
        appointment.status = "approved"
    else:
        appointment.status = "rejected"
    appointment.review_by = reviewer.id
    appointment.review_at = datetime.now()
    appointment.review_comment = comment.strip()[:255]
    db.commit()
    db.refresh(appointment)
    return appointment


def list_appointments(db: Session, status: str | None = None,
                      exam_id: int | None = None) -> list[ExamAppointment]:
    query = db.query(ExamAppointment)
    if status:
        query = query.filter(ExamAppointment.status == status)
    if exam_id:
        query = query.filter(ExamAppointment.exam_id == exam_id)
    return query.order_by(ExamAppointment.created_at.desc()).all()


def get_appointment(db: Session, appointment_id: int) -> ExamAppointment | None:
    return db.query(ExamAppointment).filter(ExamAppointment.id == appointment_id).first()


# ---------- 预约状态驱动开考资格 ----------
def exam_requires_appointment(db: Session, exam_id: int) -> bool:
    return db.query(ExamSession).filter(ExamSession.exam_id == exam_id).count() > 0


def check_start_eligibility(db: Session, exam: Exam, user_id: int) -> ExamAppointment | None:
    """
    校验开考资格：
    - 未配置场次：返回 None，沿用旧的单次考试规则
    - 已配置场次：必须存在“已通过”且当前时间位于场次时段内的预约，
      同时校验限考次数（含补考）；否则抛出 ValueError
    """
    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam.id).all()
    if not sessions:
        return None

    appointments = (
        db.query(ExamAppointment)
        .filter(
            ExamAppointment.exam_id == exam.id,
            ExamAppointment.user_id == user_id,
            ExamAppointment.status == "approved",
        )
        .order_by(ExamAppointment.created_at.asc())
        .all()
    )
    if not appointments:
        raise ValueError("该考试需预约审核通过后方可参加，请先在“考试预约”中申请")

    now = datetime.now()
    for appt in appointments:
        session = appt.session
        if session.start_time <= now <= session.end_time:
            used = (
                db.query(ExamAttempt)
                .filter(
                    ExamAttempt.exam_id == exam.id,
                    ExamAttempt.user_id == user_id,
                )
                .count()
            )
            if used >= session.max_attempts:
                raise ValueError(f"该场次限考 {session.max_attempts} 次，您的考试次数已用完")
            return appt
    raise ValueError("当前时间不在已预约场次的考试时段内，请在预约时段内参加考试")


# ---------- 预约驱动的成绩统计 ----------
def exam_appointment_stats(db: Session, exam_id: int) -> dict:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    appointments = (
        db.query(ExamAppointment)
        .filter(ExamAppointment.exam_id == exam_id)
        .all()
    )

    by_status = {"pending": 0, "approved": 0, "rejected": 0, "cancelled": 0, "completed": 0}
    by_type = {"regular": 0, "retake": 0}
    for a in appointments:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_type[a.appointment_type] = by_type.get(a.appointment_type, 0) + 1

    # 经预约参加的考试成绩，按正考/补考分别统计及格率
    appt_map = {a.id: a for a in appointments}
    attempts = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == "graded",
            ExamAttempt.appointment_id.isnot(None),
        )
        .all()
    )
    regular_scores = [
        t for t in attempts
        if (appt := appt_map.get(t.appointment_id)) and appt.appointment_type == "regular"
    ]
    retake_scores = [
        t for t in attempts
        if (appt := appt_map.get(t.appointment_id)) and appt.appointment_type == "retake"
    ]

    def _pass_rate(items: list[ExamAttempt]) -> float:
        if not items:
            return 0.0
        passed = sum(1 for t in items if t.is_passed == 1)
        return round(passed / len(items) * 100, 1)

    session_items = []
    for s in db.query(ExamSession).filter(ExamSession.exam_id == exam_id).order_by(ExamSession.start_time).all():
        booked = count_session_booked(db, s.id)
        completed = sum(1 for a in appointments if a.session_id == s.id and a.status == "completed")
        session_items.append({
            "session_id": s.id,
            "name": s.name,
            "quota": s.quota,
            "booked": booked,
            "remaining": max(0, s.quota - booked),
            "completed": completed,
        })

    return {
        "exam_id": exam_id,
        "total_appointments": len(appointments),
        "by_status": by_status,
        "by_type": by_type,
        "regular_attempts": len(regular_scores),
        "regular_pass_rate": _pass_rate(regular_scores),
        "retake_attempts": len(retake_scores),
        "retake_pass_rate": _pass_rate(retake_scores),
        "sessions": session_items,
    }
