import os

from flask import Blueprint, render_template, request, redirect, flash, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Tests, Tests_questions, Tests_answers, Test_scores, TestReport, TestDetailedResults
from helpers import _create_notification, delete_image
from routes.tests import COMPLAINT_THRESHOLD

moderator_bp = Blueprint('moderator', __name__)


def _require_mod():
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    return None


def _has_enough_complaints(test_id):
    """Проверяет, есть ли у теста >= COMPLAINT_THRESHOLD уникальных жалоб."""
    unique_complaints = db.session.query(TestReport.tr_user_id).filter_by(
        tr_test_id=test_id, tr_type='complaint', tr_resolved=False
    ).distinct().count()
    return unique_complaints >= COMPLAINT_THRESHOLD

def _delete_test_full(test):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    for q in questions:
        Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).delete()
        delete_image(q.test_q_image, upload_folder)
        db.session.delete(q)
    delete_image(test.test_image, upload_folder)
    Test_scores.query.filter_by(test_s_test_id=test.test_id).delete()
    # Детальные результаты, жалобы и комментарии удалятся автоматически благодаря каскадному удалению
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


@moderator_bp.route('/moderator/reported')
@login_required
def moderator_reported_tests():
    err = _require_mod()
    if err:
        return err
    
    # Находим все тесты с жалобами (независимо от статуса)
    all_tests_with_complaints = db.session.query(Tests).join(
        TestReport, Tests.test_id == TestReport.tr_test_id
    ).filter(
        TestReport.tr_type == 'complaint',
        TestReport.tr_resolved == False
    ).distinct().all()
    
    # Фильтруем только те, у которых >= 3 уникальных жалоб
    reported_tests = []
    report_counts = {}
    
    for test in all_tests_with_complaints:
        unique_complaints = db.session.query(TestReport.tr_user_id).filter_by(
            tr_test_id=test.test_id, tr_type='complaint', tr_resolved=False
        ).distinct().count()
        
        if unique_complaints >= COMPLAINT_THRESHOLD:
            reported_tests.append(test)
            report_counts[test.test_id] = unique_complaints
    
    return render_template("moderator_reported.html", tests=reported_tests, report_counts=report_counts)


@moderator_bp.route('/moderator/manage')
@login_required
def moderator_manage_tests():
    if current_user.admin <= 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    all_tests = Tests.query.filter(Tests.test_status.in_([1, 2, 3])).all()
    return render_template("moderator_manage.html", tests=all_tests)


@moderator_bp.route('/moderator/review/<test_name>')
@login_required
def moderator_review_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator_2")
    
    # Проверяем, можно ли просматривать этот тест
    # Можно просматривать если: статус 1, статус 3, или статус 2 с достаточным количеством жалоб
    can_review = (
        test.test_status in [1, 3] or 
        (test.test_status == 2 and _has_enough_complaints(test.test_id))
    )
    
    if not can_review:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    questions_with_answers = [
        {'question': q, 'answers': Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).all()}
        for q in questions
    ]
    back_url = "/moderator/reported" if (test.test_status == 3 or _has_enough_complaints(test.test_id)) else "/moderator_2"
    return render_template("moderator_review_test.html", test=test, questions_with_answers=questions_with_answers, back_url=back_url)


@moderator_bp.route('/moderator/approve/<test_name>', methods=["POST"])
@login_required
def moderator_approve_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator_2")
    
    # Проверяем, можно ли одобрять этот тест
    # Можно одобрять если: статус 1, статус 3, или статус 2 с достаточным количеством жалоб
    can_approve = (
        test.test_status in [1, 3] or 
        (test.test_status == 2 and _has_enough_complaints(test.test_id))
    )
    
    if not can_approve:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")

    previous_status = test.test_status
    test.test_status = 2
    for q in Tests_questions.query.filter_by(test_q_test_id=test.test_id).all():
        q.test_q_status = 2
    for a in Tests_answers.query.filter_by(test_a_test_id=test.test_id).all():
        a.test_a_status = 2

    # Если тест был с жалобами (статус 3 или статус 2 с жалобами), помечаем жалобы как решенные
    if previous_status == 3 or _has_enough_complaints(test.test_id):
        TestReport.query.filter_by(
            tr_test_id=test.test_id, tr_type='complaint', tr_resolved=False
        ).update({'tr_resolved': True})

    _create_notification(
        user_id=test.test_id_creator, sender_id=current_user.id,
        text=f"Модератор {current_user.username} одобрил ваш тест \"{test.test_name}\"! Тест опубликован.",
        link=f"/test/{test.test_name}", category='tests'
    )
    db.session.commit()
    flash(f"Тест '{test_name}' успешно одобрен и опубликован!", 'success')
    # Редиректим в reported если тест был с жалобами (статус 3 или статус 2 с жалобами)
    from_reported = previous_status == 3 or _has_enough_complaints(test.test_id)
    return redirect("/moderator/reported" if from_reported else "/moderator_2")


@moderator_bp.route('/moderator/delete/<test_name>', methods=["POST"])
@login_required
def moderator_delete_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator_2")
    
    # Проверяем, можно ли удалять этот тест
    # Можно удалять если: статус 1, статус 3, или статус 2 с достаточным количеством жалоб
    can_delete = (
        test.test_status in [1, 3] or 
        (test.test_status == 2 and _has_enough_complaints(test.test_id))
    )
    
    if not can_delete:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator_2")
    
    back_to_reported = test.test_status == 3 or _has_enough_complaints(test.test_id)
    _delete_test_full(test)
    flash(f"Тест '{test_name}' успешно удалён!", 'success')
    return redirect("/moderator/reported" if back_to_reported else "/moderator_2")


@moderator_bp.route('/moderator/delete-any/<test_name>', methods=["POST"])
@login_required
def moderator_delete_any_test(test_name):
    err = _require_mod()
    if err:
        return err
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2, 3])).first()
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
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2, 3])).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator/manage")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    questions_with_answers = [
        {'question': q, 'answers': Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).all()}
        for q in questions
    ]
    return render_template("moderator_view_test.html", test=test, questions_with_answers=questions_with_answers)
