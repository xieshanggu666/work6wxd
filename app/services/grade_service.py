import random
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Exam, ExamAttempt, ExamAnswer, Question, GradeRecord, QuestionStatistics, Certificate,
)


def calculate_exam_stats(db: Session, exam_id: int) -> dict:
    """考试整体统计：平均分、最高/最低分、及格率、分数分布"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    graded = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "graded")
        .all()
    )
    if not graded:
        return {
            "exam_id": exam_id, "attempt_count": 0,
            "avg_score": 0, "max_score": 0, "min_score": 0,
            "pass_rate": 0, "distribution": {},
        }

    scores = [a.score for a in graded]
    passed = [s for s in scores if s >= exam.pass_score]
    distribution = {
        "0-59": len([s for s in scores if s < 60]),
        "60-69": len([s for s in scores if 60 <= s < 70]),
        "70-79": len([s for s in scores if 70 <= s < 80]),
        "80-89": len([s for s in scores if 80 <= s < 90]),
        "90-100": len([s for s in scores if s >= 90]),
    }
    return {
        "exam_id": exam_id,
        "attempt_count": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1),
        "max_score": max(scores),
        "min_score": min(scores),
        "pass_rate": round(len(passed) / len(scores) * 100, 1),
        "distribution": distribution,
    }


def calculate_question_stats(db: Session, question_id: int) -> QuestionStatistics:
    """单题统计：正确率、实际难度(1-正确率)、区分度(高分组-低分组正确率)"""
    answers = (
        db.query(ExamAnswer)
        .filter(ExamAnswer.question_id == question_id)
        .all()
    )
    if not answers:
        return QuestionStatistics(question_id=question_id)

    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct == 1)

    # 区分度：取全部成绩中的高分组(前27%)与低分组(后27%)比较该题正确率
    attempt_ids = {a.attempt_id for a in answers}
    attempts = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.id.in_(attempt_ids), ExamAttempt.status == "graded")
        .order_by(ExamAttempt.score.desc())
        .all()
    )
    n = len(attempts)
    high_n = max(1, int(n * 0.27))
    high_ids = {a.id for a in attempts[:high_n]}
    low_ids = {a.id for a in attempts[-high_n:]}

    high_correct = sum(1 for a in answers if a.attempt_id in high_ids and a.is_correct == 1)
    low_correct = sum(1 for a in answers if a.attempt_id in low_ids and a.is_correct == 1)
    discrimination = high_correct / high_n - low_correct / high_n

    stats = QuestionStatistics(
        question_id=question_id,
        total_attempts=total,
        correct_count=correct,
        wrong_count=total - correct,
        average_score=round(sum(a.score for a in answers) / total, 2),
        difficulty_actual=round(1 - correct / total, 2),
        discrimination_actual=round(discrimination, 2),
    )
    existing = (
        db.query(QuestionStatistics)
        .filter(QuestionStatistics.question_id == question_id)
        .first()
    )
    if existing:
        existing.total_attempts = stats.total_attempts
        existing.correct_count = stats.correct_count
        existing.wrong_count = stats.wrong_count
        existing.average_score = stats.average_score
        existing.difficulty_actual = stats.difficulty_actual
        existing.discrimination_actual = stats.discrimination_actual
        stats = existing
    else:
        db.add(stats)
    db.commit()
    db.refresh(stats)
    return stats


def get_user_rank(db: Session, user_id: int, exam_id: int) -> dict:
    """
    获取用户在某次考试中的名次与百分位。
    名次规则：分数高于该用户的已交卷人数 + 1（同分同名次）。
    """
    user_attempt = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "graded",
        )
        .first()
    )
    if not user_attempt:
        raise ValueError("尚未完成该考试")

    higher = (
        db.query(func.count(ExamAttempt.id))
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.score > user_attempt.score,
        )
        .scalar()
    )
    total = (
        db.query(func.count(ExamAttempt.id))
        .filter(ExamAttempt.exam_id == exam_id)
        .scalar()
    )

    rank = higher + 1
    percentile = round(100 * (1 - higher / total), 1) if total else 0.0

    record = GradeRecord(
        attempt_id=user_attempt.id,
        user_id=user_id,
        exam_id=exam_id,
        score=user_attempt.score,
        rank=rank,
        percentile=percentile,
    )
    db.add(record)
    db.commit()
    return {"user_id": user_id, "exam_id": exam_id, "score": user_attempt.score,
            "rank": rank, "total": total, "percentile": percentile}


def get_leaderboard(db: Session, exam_id: int, limit: int = 20) -> list[dict]:
    attempts = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "graded")
        .order_by(ExamAttempt.score.desc(), ExamAttempt.submit_time.asc())
        .limit(limit)
        .all()
    )
    result = []
    prev_score = None
    prev_rank = 0
    for i, a in enumerate(attempts, start=1):
        if a.score != prev_score:
            rank = i
            prev_rank = i
            prev_score = a.score
        else:
            rank = prev_rank
        result.append({
            "user_id": a.user_id,
            "username": a.user.username,
            "real_name": a.user.real_name,
            "score": a.score,
            "rank": rank,
            "submit_time": a.submit_time,
        })
    return result


def generate_certificate(db: Session, user_id: int, exam_id: int) -> Certificate:
    """通过考试后生成证书，编号唯一"""
    attempt = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "graded",
        )
        .first()
    )
    if not attempt or attempt.is_passed != 1:
        raise ValueError("未通过考试，无法生成证书")

    existing = (
        db.query(Certificate)
        .filter(Certificate.user_id == user_id, Certificate.exam_id == exam_id)
        .first()
    )
    if existing:
        return existing

    cert_no = f"CERT-{exam_id}-{user_id}-{random.randint(1000, 9999)}"
    cert = Certificate(
        user_id=user_id,
        exam_id=exam_id,
        certificate_no=cert_no,
        score=attempt.score,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def list_certificates(db: Session, user_id: int):
    return db.query(Certificate).filter(Certificate.user_id == user_id).all()
