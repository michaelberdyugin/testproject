from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user
from werkzeug.security import check_password_hash


def init_api(app, db, Tests, User, Tests_answers, Tests_questions, Test_scores) -> None:
    """
    Подключает API в существующее Flask-приложение.
    """

    api_bp = Blueprint("api", __name__, url_prefix="/api")

    def _json_error(message: str, status: int = 400):
        return jsonify({"ok": False, "error": message}), status

    def _require_admin():
        if not current_user.is_authenticated:
            return _json_error("Authentication required", 401)
        if getattr(current_user, "admin", 0) == 0:
            return _json_error("Admin privileges required", 403)
        return None

    def _answers_to_dict(answers, question_type):
        result = {}
        for answer in answers:
            if question_type in [1, 2, 11, 21]:
                result[str(answer.test_a_id)] = {
                    "answer_text": answer.test_a_text,
                    "answer_is_correct": answer.test_a_is_correct
                }
            elif question_type in [3, 31]:
                result[str(answer.test_a_id)] = {
                    "answer_text": answer.test_a_text
                }
            elif question_type in [4, 41]:
                result[str(answer.test_a_id)] = {
                    "answer_block_1": answer.test_a_match,
                    "answer_block_2": answer.test_a_text
                }
        return result

    def _questions_to_dict_no_admin(questions):
        result = {}
        for question in questions:
            result[str(question.test_q_id)] = {
                "question_text": question.test_q_text,
                "question_type": question.test_q_type,
                "question_image": question.test_q_image
            }
        return result

    def _questions_to_dict_admin(questions, answers_all):
        result = {}
        for question in questions:
            q_answers = [a for a in answers_all if a.test_a_question_id == question.test_q_id]
            result[str(question.test_q_id)] = {
                "question_text": question.test_q_text,
                "question_type": question.test_q_type,
                "question_image": question.test_q_image,
                "answers": _answers_to_dict(q_answers, question.test_q_type)
            }
        return result

    def _test_to_dict_no_admin(test, questions_all, scores_all):
        questions = [q for q in questions_all if q.test_q_test_id == test.test_id]
        scores = [s for s in scores_all if s.test_s_test_id == test.test_id]
        average_score = round(sum(s.test_s_score for s in scores) / len(scores), 1) if scores else 0
        return {
            "id": test.test_id,
            "test_name": test.test_name,
            "test_description": test.test_description,
            "questions": _questions_to_dict_no_admin(questions),
            "score": average_score
        }

    def _test_to_dict_admin(test, questions_all, scores_all, answers_all):
        questions = [q for q in questions_all if q.test_q_test_id == test.test_id]
        scores = [s for s in scores_all if s.test_s_test_id == test.test_id]
        average_score = round(sum(s.test_s_score for s in scores) / len(scores), 1) if scores else 0
        return {
            "id": test.test_id,
            "test_name": test.test_name,
            "test_description": test.test_description,
            "questions": _questions_to_dict_admin(questions, answers_all),
            "score": average_score
        }

    @api_bp.get("/tests")
    def list_tests_no_admin():
        tests = Tests.query.filter_by(test_status=2).order_by(Tests.test_id.desc()).all()
        questions_all = Tests_questions.query.all()
        scores_all = Test_scores.query.all()
        return jsonify({
            "ok": True,
            "items": [_test_to_dict_no_admin(t, questions_all, scores_all) for t in tests]
        })

    @api_bp.get("/tests/admin")
    def list_tests_admin():
        err = _require_admin()
        if err is not None:
            return err
        tests = Tests.query.order_by(Tests.test_id.desc()).all()
        questions_all = Tests_questions.query.all()
        scores_all = Test_scores.query.all()
        answers_all = Tests_answers.query.all()
        return jsonify({
            "ok": True,
            "items": [_test_to_dict_admin(t, questions_all, scores_all, answers_all) for t in tests]
        })

    @api_bp.post("/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = payload.get("username")
        password = payload.get("password")

        if not username or not password:
            return _json_error("username and password are required", 400)

        user = User.query.filter_by(username=username).first()
        if user is None:
            return _json_error("User not found", 404)
        if not check_password_hash(user.password, password):
            return _json_error("Invalid credentials", 401)

        login_user(user)
        return jsonify({"ok": True, "message": "Login successful"})

    # Регистрируем blueprint в приложение
    app.register_blueprint(api_bp)
