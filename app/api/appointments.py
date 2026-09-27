from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User
from app.schemas.appointment import (
    SessionCreate, SessionUpdate, SessionWithBookedResponse,
    AppointmentCreate, AppointmentReview, AppointmentDetailResponse,
    ExamAppointmentStatsResponse,
)
from app.schemas.common import APIResponse
from app.services import appointment_service

router = APIRouter(prefix="/appointments", tags=["考试预约"])


def _detail(a) -> AppointmentDetailResponse:
    data = AppointmentDetailResponse.model_validate(a)
    data.exam_title = a.exam.title if a.exam else ""
    data.session_name = a.session.name if a.session else ""
    data.session_start_time = a.session.start_time if a.session else None
    data.session_end_time = a.session.end_time if a.session else None
    data.username = a.user.username if a.user else ""
    data.real_name = a.user.real_name if a.user else ""
    return data


def _session_response(session, exam_title: str, booked: int) -> SessionWithBookedResponse:
    return SessionWithBookedResponse(
        id=session.id,
        exam_id=session.exam_id,
        name=session.name,
        start_time=session.start_time,
        end_time=session.end_time,
        quota=session.quota,
        max_attempts=session.max_attempts,
        status=session.status,
        created_at=session.created_at,
        exam_title=exam_title,
        booked=booked,
        remaining=max(0, session.quota - booked),
    )


# ---------- 场次（管理员配置名额和时段） ----------
@router.post("/sessions", response_model=APIResponse[SessionWithBookedResponse])
def create_session(data: SessionCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin"))):
    try:
        session = appointment_service.create_session(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=_session_response(session, session.exam.title, 0))


@router.get("/sessions", response_model=APIResponse[list[SessionWithBookedResponse]])
def list_sessions(exam_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    items = appointment_service.list_sessions_with_booked(db, exam_id)
    return APIResponse(data=[
        _session_response(i["session"], i["exam_title"], i["booked"])
        for i in items
    ])


@router.put("/sessions/{session_id}", response_model=APIResponse[SessionWithBookedResponse])
def update_session(session_id: int, data: SessionUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin"))):
    session = appointment_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="场次不存在")
    try:
        session = appointment_service.update_session(db, session, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    booked = appointment_service.count_session_booked(db, session.id)
    return APIResponse(data=_session_response(session, session.exam.title, booked))


@router.delete("/sessions/{session_id}", response_model=APIResponse)
def delete_session(session_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin"))):
    session = appointment_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="场次不存在")
    try:
        appointment_service.delete_session(db, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=None)


# ---------- 学生：我的预约 ----------
@router.post("", response_model=APIResponse[AppointmentDetailResponse])
def apply(data: AppointmentCreate, db: Session = Depends(get_db),
          user: User = Depends(require_roles("student"))):
    try:
        appointment = appointment_service.apply_appointment(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=_detail(appointment))


@router.get("/my", response_model=APIResponse[list[AppointmentDetailResponse]])
def my_appointments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = appointment_service.list_user_appointments(db, user.id)
    return APIResponse(data=[_detail(a) for a in items])


@router.post("/{appointment_id}/cancel", response_model=APIResponse[AppointmentDetailResponse])
def cancel(appointment_id: int, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    appointment = appointment_service.get_appointment(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="预约不存在")
    try:
        appointment = appointment_service.cancel_appointment(db, appointment, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=_detail(appointment))


# ---------- 教师：审核 ----------
@router.get("", response_model=APIResponse[list[AppointmentDetailResponse]])
def list_appointments(status: str | None = None, exam_id: int | None = None,
                      db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin", "teacher"))):
    items = appointment_service.list_appointments(db, status, exam_id)
    return APIResponse(data=[_detail(a) for a in items])


@router.post("/{appointment_id}/review", response_model=APIResponse[AppointmentDetailResponse])
def review(appointment_id: int, data: AppointmentReview, db: Session = Depends(get_db),
           user: User = Depends(require_roles("admin", "teacher"))):
    appointment = appointment_service.get_appointment(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="预约不存在")
    try:
        appointment = appointment_service.review_appointment(
            db, appointment, user, data.approve, data.comment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=_detail(appointment))


# ---------- 预约驱动的统计 ----------
@router.get("/stats/{exam_id}", response_model=APIResponse[ExamAppointmentStatsResponse])
def appointment_stats(exam_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin", "teacher"))):
    try:
        stats = appointment_service.exam_appointment_stats(db, exam_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return APIResponse(data=ExamAppointmentStatsResponse(**stats))
