from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---------- 考试场次（管理员配置名额和时段） ----------
class SessionCreate(BaseModel):
    exam_id: int
    name: str = Field(min_length=1, max_length=100)
    start_time: datetime
    end_time: datetime
    quota: int = Field(default=50, ge=1)
    max_attempts: int = Field(default=1, ge=1, le=10)


class SessionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    quota: int | None = Field(default=None, ge=1)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    status: str | None = None  # open/closed


class SessionResponse(ORMModel):
    id: int
    exam_id: int
    name: str
    start_time: datetime
    end_time: datetime
    quota: int
    max_attempts: int
    status: str
    created_at: datetime


class SessionWithBookedResponse(SessionResponse):
    exam_title: str = ""
    booked: int = 0        # 已占用名额（已通过 + 已完成）
    remaining: int = 0     # 剩余名额


# ---------- 考试预约（学生申请、教师审核） ----------
class AppointmentCreate(BaseModel):
    session_id: int
    appointment_type: str = "regular"  # regular=正考 retake=补考
    reason: str = ""


class AppointmentReview(BaseModel):
    approve: bool
    comment: str = ""


class AppointmentResponse(ORMModel):
    id: int
    session_id: int
    exam_id: int
    user_id: int
    appointment_type: str
    status: str
    reason: str
    attempt_no: int
    review_comment: str
    created_at: datetime


class AppointmentDetailResponse(AppointmentResponse):
    exam_title: str = ""
    session_name: str = ""
    session_start_time: datetime | None = None
    session_end_time: datetime | None = None
    username: str = ""
    real_name: str = ""
    review_at: datetime | None = None


# ---------- 预约驱动的统计 ----------
class SessionStatItem(BaseModel):
    session_id: int
    name: str
    quota: int
    booked: int
    remaining: int
    completed: int


class ExamAppointmentStatsResponse(BaseModel):
    exam_id: int
    total_appointments: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    regular_attempts: int = 0
    regular_pass_rate: float = 0.0
    retake_attempts: int = 0
    retake_pass_rate: float = 0.0
    sessions: list[SessionStatItem] = []
