import os

from flask import Blueprint, render_template, request, redirect, flash, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Tests, Tests_questions, Tests_answers, Test_scores
from helpers import _create_notification, delete_image

moderator_bp = Blueprint('moderator', __name__)


def _require_mod():
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    return None


def _delete_test_full(test):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    for q in questions:
        Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).delete()
        delete_image(q.test_q_image, upload_folder)
        db.session.delete(q)
    delete_image(test.test_image, upload_folder)
    Test_scores.query.filter_by(test_s_test_id=test.test_id).delete()
    db.session.delete(test)
    db.session.commit()


@moderator_bp.route('/moderator_1')
@login_required
def moderator_1():
    err = _require_mod()
    if err:
        return err
    return render_template("moderator_1.html")


@moderator_bp.route('/moderator_2')
@login_required
def moderator_2():
    err = _require_mod()
    if err:
        return err
    pending_tests = Tests.query.filter_by(test_status=1).all()
    return render_template("moderator_2.html", tests=pending_tests)


@moderator_bp.route('/moderator/manage')
@login_required
def moderator_manage_tests():
    if current_user.admin <= 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    all_tests = Tests.query.filter(Tests.test_status.in_([1, 2])).all()
    return render_template("moderator_manage.html", tests=all_tests)


@moderator_bp.route('/moderator/review/<test_name>')
@login_required
def moderator_review_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=1).all()
    questions_with_answers = [
        {'question': q, 'answers': Tests_answers.query.filter_by(test_a_question_id=q.test_q_id, test_a_status=1).all()}
        for q in questions
    ]
    return render_template("moderator_review_test.html", test=test, questions_with_answers=questions_with_answers)


@moderator_bp.route('/moderator/approve/<test_name>', methods=["POST"])
@login_required
def moderator_approve_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")

    test.test_status = 2
    for q in Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=1).all():
        q.test_q_status = 2
    for a in Tests_answers.query.filter_by(test_a_test_id=test.test_id, test_a_status=1).all():
        a.test_a_status = 2

    _create_notification(
        user_id=test.test_id_creator, sender_id=current_user.id,
        text=f"Модератор {current_user.username} одобрил ваш тест \"{test.test_name}\"! Тест опубликован.",
        link=f"/test/{test.test_name}", category='tests'
    )
    db.session.commit()
    flash(f"Тест '{test_name}' успешно одобрен и опубликован!", 'success')
    return redirect("/moderator_2")


@moderator_bp.route('/moderator/delete/<test_name>', methods=["POST"])
@login_required
def moderator_delete_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator_2")
    _delete_test_full(test)
    flash(f"Тест '{test_name}' успешно удалён!", 'success')
    return redirect("/moderator_2")


@moderator_bp.route('/moderator/delete-any/<test_name>', methods=["POST"])
@login_required
def moderator_delete_any_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2])).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator/manage")
    _delete_test_full(test)
    flash(f"Тест '{test_name}' успешно удалён!", 'success')
    return redirect("/moderator/manage")


@moderator_bp.route('/moderator/view/<test_name>')
@login_required
def moderator_view_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2])).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator/manage")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    questions_with_answers = [
        {'question': q, 'answers': Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).all()}
        for q in questions
    ]
    return render_template("moderator_view_test.html", test=test, questions_with_answers=questions_with_answers)
