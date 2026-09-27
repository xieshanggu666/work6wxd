from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExamSession(Base):
    """考试场次：管理员配置的考试时段、名额与限考次数（含补考）"""
    __tablename__ = "exam_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, default=50)          # 名额
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)    # 每人限考次数（1=仅正考，2=正考+1次补考）
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/closed
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    exam = relationship("Exam")
    appointments: Mapped[list["ExamAppointment"]] = relationship(
        "ExamAppointment", back_populates="session", cascade="all, delete-orphan"
    )


class ExamAppointment(Base):
    """考试预约：学生申请（正考/补考）-> 教师审核 -> 状态驱动开考资格、次数、证书"""
    __tablename__ = "exam_appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("exam_sessions.id"), nullable=False, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    appointment_type: Mapped[str] = mapped_column(String(20), default="regular")  # regular=正考 retake=补考
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending/approved/rejected/cancelled/completed
    reason: Mapped[str] = mapped_column(Text, default="")
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)  # 第几次考试（1=正考，2+=补考）
    review_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    session: Mapped[ExamSession] = relationship("ExamSession", back_populates="appointments")
    exam = relationship("Exam")
    user = relationship("User")
