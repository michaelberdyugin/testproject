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

    def _test_to_dict_no_admin(tests, tests_questions, tests_scores) -> dict[str, Any]:
        average_score = 0
        if tests_scores:
            total_score = sum(score.test_s_score for score in tests_scores)
            average_score = round(total_score / len(tests_scores), 1)
        return {
            "id": tests.test_id,
            "test_name": tests.test_name,
            "test_description": tests.test_description,
            "questions": _questions_to_dict_no_admin(tests_questions, tests.test_id),
            "score": average_score
        }

    def _questions_to_dict_no_admin(tests_questions, test_id):
        questions = dict()
        for question in tests_questions:
            if tests_questions.test_q_creator_id != test_id:
                continue
            questions.update({f"{question.test_q_id}": {"question_text": tests_questions.test_q_text, "question_type": tests_questions.test_q_type, "question_image": getattr(tests_questions, "test_q_image", None)}})
        return questions

    @api_bp.get("/tests")
    def list_tests_no_admin():
        tests = Tests.query.order_by(Tests.date.desc()).all()
        tests_questions = Tests_questions.query.order_by(Tests_questions.date.desc()).all()
        tests_scores = Test_scores.query.order_by(Test_scores.date.desc()).all()
        return jsonify({"ok": True, "items": [_test_to_dict_no_admin(a, tests_questions, tests_scores) for a in tests if tests.test_status == 2]})

    def _test_to_dict_admin(tests, tests_questions, tests_scores, tests_answers) -> dict[str, Any]:
        err = _require_admin()
        if err is not None:
            return err
        average_score = 0
        if tests_scores:
            total_score = sum(score.test_s_score for score in tests_scores)
            average_score = round(total_score / len(tests_scores), 1)
        return {
            "id": tests.test_id,
            "test_name": tests.test_name,
            "test_description": tests.test_description,
            "questions": _questions_to_dict_admin(tests_questions, tests.test_id, tests_answers),
            "score": average_score
        }

    def _questions_to_dict_admin(tests_questions, test_id, tests_answers ):
        err = _require_admin()
        if err is not None:
            return err
        questions = dict()
        for question in tests_questions:
            if tests_questions.test_q_creator_id != test_id:
                continue
            questions.update({f"{question.test_q_id}": {"question_text": tests_questions.test_q_text, "question_type": tests_questions.test_q_type,"answers": _answers_to_dict(tests_answers, test_id, tests_questions.test_q_type),"question_image": getattr(tests_questions, "test_q_image", None)}})
        return questions

    def _answers_to_dict(tests_answers, test_id, question_type):
        err = _require_admin()
        if err is not None:
            return err
        answers = dict()
        for answer in tests_answers:
            if tests_answers.test_a_creator_id != test_id:
                continue
            if question_type in [1, 2, 11, 21]:
                answers.update({f"{answer.test_a_id}": {"answer_text": answer.test_a_text, "answer_is_correct": answer.test_a_is_correct}})
            elif question_type in [3, 31]:
                answers.update({f"{answer.test_a_id}": {"answer_text": answer.test_a_text}})
            elif question_type in [4, 41]:
                answers.update({f"{answer.test_a_id}": {"answer_block_1": answers.test_a_match, "answer_blok_2": answers.test_a_text}})


    @api_bp.get("/tests/admin")
    def list_tests_admin():
        err = _require_admin()
        if err is not None:
            return err
        tests = Tests.query.order_by(Tests.date.desc()).all()
        tests_questions = Tests_questions.query.order_by(Tests_questions.date.desc()).all()
        tests_scores = Test_scores.query.order_by(Test_scores.date.desc()).all()
        tests_answers = Tests_answers.query.order_by(Tests_answers.date.desc()).all()
        return jsonify({"ok": True, "items": [_test_to_dict_admin(a, tests_questions, tests_scores, tests_answers) for a in tests if tests.test_status == 2]})

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

    def _require_admin():
        if not current_user.is_authenticated:
            return _json_error("Authentication required", 401)
        if getattr(current_user, "admin", 0) == 0:
            return _json_error("Admin privileges required", 403)
        return None

    # Регистрируем blueprint в приложение
    app.register_blueprint(api_bp)

