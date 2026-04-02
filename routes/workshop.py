import os
import uuid

from flask import Blueprint, render_template, request, redirect, flash, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Tests, Tests_questions, Tests_answers, Test_scores
from helpers import (allowed_file, validate_test_name, delete_image,
                     _render_createnext, _calc_are_ready)

workshop_bp = Blueprint('workshop', __name__)


def _get_current_test():
    return Tests.query.filter_by(test_id_creator=current_user.id, test_status=0).first()


def _get_last_question(test):
    return Tests_questions.query.filter_by(
        test_q_test_id=test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()


@workshop_bp.route('/workshop')
@login_required
def workshop():
    user_tests = Tests.query.filter_by(test_id_creator=current_user.id).all()
    return render_template("workshop.html",
                           tests_in_progress=[t for t in user_tests if t.test_status == 0],
                           tests_pending=[t for t in user_tests if t.test_status == 1],
                           tests_published=[t for t in user_tests if t.test_status == 2])


@workshop_bp.route('/create', methods=["GET", "POST"])
@login_required
def create():
    if request.method == "GET":
        return render_template("create.html")

    test_name = request.form.get('test_name')
    test_description = request.form.get('test_description')

    if not validate_test_name(test_name):
        flash("Название теста содержит недопустимые символы!", 'danger')
        return redirect("/create")
    if Tests.query.filter_by(test_name=test_name).first():
        flash("Тест с таким названием уже существует!", 'warning')
        return redirect("/create")

    image_filename = None
    if 'test_image' in request.files:
        file = request.files['test_image']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения.", "danger")
            return redirect("/create")

    test = Tests(test_name=test_name, test_description=test_description,
                 test_status=0, test_id_creator=current_user.id, test_image=image_filename)
    db.session.add(test)
    db.session.commit()
    return redirect("/createq_0")


@workshop_bp.route('/createq_0', methods=["GET", "POST"])
@login_required
def createq_0():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_0.html", current_test=current_test)

    try:
        question_type = int(request.form.get("question_type", "1"))
    except ValueError:
        question_type = 1

    final_type = question_type * 10 + 1 if bool(request.form.get("add_image")) else question_type
    routes = {1: "/createq_1", 2: "/createq_2", 3: "/createq_3", 4: "/createq_4",
              11: "/createq_11", 21: "/createq_21", 31: "/createq_31", 41: "/createq_41"}
    if final_type in routes:
        return redirect(routes[final_type])
    flash("Выберите корректный тип вопроса.", "warning")
    return redirect("/createq_0")


def _save_question_image(redirect_url):
    """Обрабатывает загрузку изображения вопроса. Возвращает (filename, error_response)."""
    if 'test_q_image' not in request.files:
        return None, None
    file = request.files['test_q_image']
    if not file or file.filename == '':
        return None, None
    if not allowed_file(file.filename):
        flash("Недопустимый формат изображения.", "danger")
        return None, redirect(redirect_url)
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
    return filename, None


@workshop_bp.route('/createq_1', methods=["GET", "POST"])
@login_required
def createq():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template("createq_1.html", current_test=current_test)

    test_q = request.form.get('test_question')
    test_a = request.form.get('test_answer')
    is_correct = bool(request.form.get('is_correct'))
    if not test_q or not test_a:
        flash("Заполните вопрос и ответ!", 'warning')
        return redirect("/createq_1")

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=1, test_q_status=0)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=test_a, test_a_creator_id=current_user.id,
                                 test_a_test_id=current_test.test_id, test_a_question_id=q.test_q_id,
                                 test_a_status=0, test_a_is_correct=is_correct))
    db.session.commit()
    flash("Вопрос и ответ добавлены!", 'success')
    return redirect("/createnext")


@workshop_bp.route('/createq_2', methods=["GET", "POST"])
@login_required
def createq_2():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template("createq_2.html", current_test=current_test)

    test_q = (request.form.get('test_question') or "").strip()
    test_a = request.form.get('test_answer')
    is_correct = bool(request.form.get('is_correct'))
    if not test_q or not test_a:
        flash("Заполните вопрос и ответ!", 'warning')
        return redirect("/createq_2")

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=2, test_q_status=0)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=test_a, test_a_creator_id=current_user.id,
                                 test_a_test_id=current_test.test_id, test_a_question_id=q.test_q_id,
                                 test_a_status=0, test_a_is_correct=is_correct))
    db.session.commit()
    flash("Вопрос создан.", 'success')
    return redirect("/createnext")


@workshop_bp.route('/createq_3', methods=["GET", "POST"])
@login_required
def createq_3():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template("createq_3.html", current_test=current_test)

    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()
    if not test_q or not test_a:
        flash("Заполните вопрос и ответ!", 'warning')
        return redirect("/createq_3")

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=3, test_q_status=0)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=test_a, test_a_creator_id=current_user.id,
                                 test_a_test_id=current_test.test_id, test_a_question_id=q.test_q_id,
                                 test_a_status=0, test_a_is_correct=True))
    db.session.commit()
    flash("Вопрос создан.", 'success')
    return redirect("/createnext")


def _createq_with_image(q_type, template, redirect_url):
    """Общая логика для createq_11, createq_21, createq_31."""
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template(template, current_test=current_test)

    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()
    is_correct = bool(request.form.get('is_correct')) if q_type in [11, 21] else True

    if not test_q or not test_a:
        flash("Заполните вопрос и ответ!", 'warning')
        return redirect(redirect_url)

    image_filename, err = _save_question_image(redirect_url)
    if err:
        return err

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=q_type,
                        test_q_status=0, test_q_image=image_filename)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=test_a, test_a_creator_id=current_user.id,
                                 test_a_test_id=current_test.test_id, test_a_question_id=q.test_q_id,
                                 test_a_status=0, test_a_is_correct=is_correct))
    db.session.commit()
    flash("Вопрос создан!", 'success')
    return redirect("/createnext")


@workshop_bp.route('/createq_11', methods=["GET", "POST"])
@login_required
def createq_11():
    return _createq_with_image(11, "createq_11.html", "/createq_11")


@workshop_bp.route('/createq_21', methods=["GET", "POST"])
@login_required
def createq_21():
    return _createq_with_image(21, "createq_21.html", "/createq_21")


@workshop_bp.route('/createq_31', methods=["GET", "POST"])
@login_required
def createq_31():
    return _createq_with_image(31, "createq_31.html", "/createq_31")


@workshop_bp.route('/createq_4', methods=["GET", "POST"])
@login_required
def createq_4():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template("createq_4.html", current_test=current_test)

    test_q = (request.form.get('test_question') or "").strip()
    row_text = (request.form.get('row_text') or "").strip()
    block_text = (request.form.get('block_text') or "").strip()
    if not test_q or not row_text or not block_text:
        flash("Заполните все поля!", 'warning')
        return redirect("/createq_4")

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=4, test_q_status=0)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=block_text, test_a_match=row_text,
                                 test_a_creator_id=current_user.id, test_a_test_id=current_test.test_id,
                                 test_a_question_id=q.test_q_id, test_a_status=0, test_a_is_correct=True))
    db.session.commit()
    flash("Вопрос создан. Добавьте остальные пары.", 'success')
    return redirect("/createnext")


@workshop_bp.route('/createq_41', methods=["GET", "POST"])
@login_required
def createq_41():
    current_test = _get_current_test()
    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")
    if request.method == "GET":
        return render_template("createq_41.html", current_test=current_test)

    test_q = (request.form.get('test_question') or "").strip()
    row_text = (request.form.get('row_text') or "").strip()
    block_text = (request.form.get('block_text') or "").strip()
    if not test_q or not row_text or not block_text:
        flash("Заполните все поля!", 'warning')
        return redirect("/createq_41")

    image_filename, err = _save_question_image("/createq_41")
    if err:
        return err

    q = Tests_questions(test_q_creator_id=current_user.id, test_q_text=test_q,
                        test_q_test_id=current_test.test_id, test_q_type=41,
                        test_q_status=0, test_q_image=image_filename)
    db.session.add(q)
    db.session.commit()
    db.session.add(Tests_answers(test_a_text=block_text, test_a_match=row_text,
                                 test_a_creator_id=current_user.id, test_a_test_id=current_test.test_id,
                                 test_a_question_id=q.test_q_id, test_a_status=0, test_a_is_correct=True))
    db.session.commit()
    flash("Вопрос создан. Добавьте остальные пары.", 'success')
    return redirect("/createnext")


@workshop_bp.route('/createnext')
@login_required
def createnext():
    current_test = _get_current_test()
    if not current_test:
        flash("Тест не найден или уже завершён!", 'warning')
        return redirect("/tests")

    last_question = _get_last_question(current_test)
    if not last_question:
        return render_template("createnext.html", current_test=current_test,
                               last_question=None, are_2_questions=False)

    are_2_questions = _calc_are_ready(last_question)
    has_correct = Tests_answers.query.filter_by(
        test_a_question_id=last_question.test_q_id, test_a_is_correct=True).first() is not None

    return render_template("createnext.html", current_test=current_test,
                           last_question=last_question, are_2_questions=are_2_questions,
                           has_correct=has_correct)


def _addanswer_route(q_type, template, redirect_url, is_correct_forced=None):
    """Общая логика для всех addanswer маршрутов."""
    current_test = _get_current_test()
    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    last_question = _get_last_question(current_test)
    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != q_type:
        flash("Неверный тип вопроса.", 'warning')
        return redirect("/createnext")

    if request.method == "GET":
        return render_template(template, question=last_question, current_test=current_test)

    if q_type in [4, 41]:
        row_text = (request.form.get('row_text') or "").strip()
        block_text = (request.form.get('block_text') or "").strip()
        if not row_text or not block_text:
            flash("Введите текст блока 1 и блока 2!", 'warning')
            return redirect(redirect_url)
        db.session.add(Tests_answers(test_a_text=block_text, test_a_match=row_text,
                                     test_a_creator_id=current_user.id, test_a_test_id=current_test.test_id,
                                     test_a_question_id=last_question.test_q_id,
                                     test_a_status=0, test_a_is_correct=True))
        db.session.commit()
        flash("Пара добавлена!", 'success')
    else:
        answer_text = (request.form.get('answer_text') or "").strip()
        if not answer_text:
            flash("Введите текст ответа!", 'warning')
            return redirect(redirect_url)
        is_correct = is_correct_forced if is_correct_forced is not None else bool(request.form.get('is_correct'))
        db.session.add(Tests_answers(test_a_text=answer_text, test_a_creator_id=current_user.id,
                                     test_a_test_id=current_test.test_id,
                                     test_a_question_id=last_question.test_q_id,
                                     test_a_status=0, test_a_is_correct=is_correct))
        db.session.commit()
        flash("Ответ добавлен!", 'success')

    return _render_createnext(current_test, last_question)


@workshop_bp.route('/addanswer', methods=["GET", "POST"])
@login_required
def addanswer():
    return _addanswer_route(1, "addanswer_1.html", "/addanswer")


@workshop_bp.route('/addanswer_2', methods=["GET", "POST"])
@login_required
def addanswer_2():
    return _addanswer_route(2, "addanswer_2.html", "/addanswer_2")


@workshop_bp.route('/addanswer_3', methods=["GET", "POST"])
@login_required
def addanswer_3():
    return _addanswer_route(3, "addanswer_3.html", "/addanswer_3", is_correct_forced=True)


@workshop_bp.route('/addanswer_11', methods=["GET", "POST"])
@login_required
def addanswer_11():
    return _addanswer_route(11, "addanswer_11.html", "/addanswer_11")


@workshop_bp.route('/addanswer_21', methods=["GET", "POST"])
@login_required
def addanswer_21():
    return _addanswer_route(21, "addanswer_21.html", "/addanswer_21")


@workshop_bp.route('/addanswer_31', methods=["GET", "POST"])
@login_required
def addanswer_31():
    return _addanswer_route(31, "addanswer_31.html", "/addanswer_31", is_correct_forced=True)


@workshop_bp.route('/addanswer_4', methods=["GET", "POST"])
@login_required
def addanswer_4():
    return _addanswer_route(4, "addanswer_4.html", "/addanswer_4")


@workshop_bp.route('/addanswer_41', methods=["GET", "POST"])
@login_required
def addanswer_41():
    return _addanswer_route(41, "addanswer_41.html", "/addanswer_41")


@workshop_bp.route('/finish-test', methods=["GET", "POST"])
@login_required
def finish_test():
    current_test = _get_current_test()
    if not current_test:
        flash("Тест не найден или уже завершён!", 'warning')
        return redirect("/tests")

    if Tests_questions.query.filter_by(test_q_test_id=current_test.test_id).count() == 0:
        flash("Нельзя завершить тест без вопросов!", 'danger')
        return redirect("/createnext")

    for q in Tests_questions.query.filter_by(test_q_test_id=current_test.test_id).all():
        if q.test_q_type in [1, 2, 11, 21]:
            if not Tests_answers.query.filter_by(test_a_question_id=q.test_q_id, test_a_is_correct=True).first():
                flash(f"Вопрос «{q.test_q_text[:50]}» не имеет ни одного правильного ответа!", 'danger')
                return redirect("/createnext")

    current_test.test_status = 1
    for q in Tests_questions.query.filter_by(test_q_test_id=current_test.test_id).all():
        q.test_q_status = 1
    for a in Tests_answers.query.filter_by(test_a_test_id=current_test.test_id).all():
        a.test_a_status = 1
    db.session.commit()

    flash("Тест отправлен на проверку модераторам!", 'success')
    return redirect("/tests")


@workshop_bp.route('/delete-test', methods=["GET", "POST"])
@login_required
def delete_test():
    current_test = _get_current_test()
    if not current_test:
        flash("Тест не найден!", 'warning')
        return redirect("/tests")
    _delete_test_data(current_test)
    flash("Тест успешно удалён!", 'success')
    return redirect("/tests")


@workshop_bp.route('/workshop/delete-test/<int:test_id>', methods=["POST"])
@login_required
def workshop_delete_test(test_id):
    test = Tests.query.filter_by(test_id=test_id, test_id_creator=current_user.id).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/workshop")
    _delete_test_data(test)
    flash(f"Тест «{test.test_name}» удалён.", 'success')
    return redirect("/workshop")


def _delete_test_data(test):
    """Удаляет тест со всеми вопросами, ответами и изображениями."""
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
