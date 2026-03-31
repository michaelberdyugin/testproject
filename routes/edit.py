import os
import uuid

from flask import Blueprint, render_template, request, redirect, flash, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Tests, Tests_questions, Tests_answers, TestComments
from helpers import allowed_file, validate_test_name, delete_image, _revert_test_to_review, _create_notification

edit_bp = Blueprint('edit', __name__)


@edit_bp.route('/edit-test/<int:test_id>')
@login_required
def edit_test(test_id):
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого теста!", 'danger')
        return redirect("/tests")
    comments = TestComments.query.filter_by(tc_test_id=test.test_id).order_by(TestComments.tc_created_at.desc()).all()
    return render_template("edit_test.html", test=test, comments=comments)


@edit_bp.route('/edit-test/<int:test_id>/update', methods=["POST"])
@login_required
def update_test(test_id):
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав!", 'danger')
        return redirect("/tests")

    test_name = request.form.get('test_name')
    test_description = request.form.get('test_description')

    if not validate_test_name(test_name):
        flash("Название теста содержит недопустимые символы!", 'danger')
        return redirect(f"/edit-test/{test_id}")
    if test_name != test.test_name and Tests.query.filter_by(test_name=test_name).first():
        flash("Тест с таким названием уже существует!", 'danger')
        return redirect(f"/edit-test/{test_id}")

    if 'test_image' in request.files:
        file = request.files['test_image']
        if file and file.filename != '' and allowed_file(file.filename):
            delete_image(test.test_image, current_app.config['UPLOAD_FOLDER'])
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename))
            test.test_image = image_filename
        elif file.filename != '':
            flash("Недопустимый формат изображения.", "danger")
            return redirect(f"/edit-test/{test_id}")

    test.test_name = test_name
    test.test_description = test_description

    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        comment = request.form.get('moderator_comment', '').strip()
        text = f"Модератор {current_user.username} отредактировал ваш тест '{test.test_name}'"
        if comment:
            text += f". Комментарий: {comment}"
            db.session.add(TestComments(tc_test_id=test.test_id, tc_user_id=current_user.id, tc_comment=comment))
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=text, link=f"/edit-test/{test.test_id}", category='tests')

    was_published = _revert_test_to_review(test, current_user)
    db.session.commit()

    flash("Информация о тесте обновлена!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-test/{test_id}")


@edit_bp.route('/edit-test/<int:test_id>/questions')
@login_required
def edit_test_questions(test_id):
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав!", 'danger')
        return redirect("/tests")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    questions_with_answers = [
        {'question': q, 'answers': Tests_answers.query.filter_by(test_a_question_id=q.test_q_id).all()}
        for q in questions
    ]
    return render_template("edit_test_questions.html", test=test, questions_with_answers=questions_with_answers)


@edit_bp.route('/edit-question/<int:question_id>')
@login_required
def edit_question(question_id):
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    test = Tests.query.get(question.test_q_test_id)
    if not test or (test.test_id_creator != current_user.id and current_user.admin < 1):
        flash("Нет доступа!", 'danger')
        return redirect("/tests")
    answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).all()
    return render_template("edit_question.html", test=test, question=question, answers=answers)


@edit_bp.route('/edit-question/<int:question_id>/update', methods=["POST"])
@login_required
def update_question(question_id):
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    test = Tests.query.get(question.test_q_test_id)
    if not test or (test.test_id_creator != current_user.id and current_user.admin < 1):
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    if 'question_image' in request.files:
        file = request.files['question_image']
        if file and file.filename != '' and allowed_file(file.filename):
            delete_image(question.test_q_image, current_app.config['UPLOAD_FOLDER'])
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            question.test_q_image = filename
        elif file.filename != '':
            flash("Недопустимый формат изображения.", "danger")
            return redirect(f"/edit-question/{question_id}")

    question.test_q_text = request.form.get('question_text')
    was_published = _revert_test_to_review(test, current_user)

    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        comment = request.form.get('moderator_comment', '').strip()
        text = f"Модератор {current_user.username} отредактировал вопрос в вашем тесте \"{test.test_name}\""
        if comment:
            text += f": {comment}"
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=text, link=f"/edit-question/{question_id}")

    db.session.commit()
    flash("Вопрос обновлен!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-question/{question_id}")


@edit_bp.route('/edit-answer/<int:answer_id>/update', methods=["POST"])
@login_required
def update_answer(answer_id):
    answer = Tests_answers.query.get(answer_id)
    if not answer:
        flash("Ответ не найден!", 'danger')
        return redirect("/tests")
    question = Tests_questions.query.get(answer.test_a_question_id)
    test = Tests.query.get(answer.test_a_test_id)
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    answer_text = request.form.get('answer_text')
    is_correct = bool(request.form.get('is_correct'))

    if question.test_q_type in [4, 41]:
        row_text = (request.form.get('row_text') or "").strip()
        if row_text:
            answer.test_a_match = row_text
        is_correct = True

    if question.test_q_type in [1, 2, 11, 21] and answer.test_a_is_correct and not is_correct:
        correct_count = Tests_answers.query.filter_by(
            test_a_question_id=question.test_q_id, test_a_is_correct=True).count()
        if correct_count <= 1:
            flash("Нельзя убрать правильность с последнего правильного ответа!", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")

    answer.test_a_text = answer_text
    answer.test_a_is_correct = is_correct
    was_published = _revert_test_to_review(test, current_user)

    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        comment = request.form.get('moderator_comment', '').strip()
        text = f"Модератор {current_user.username} отредактировал ответ в вашем тесте \"{test.test_name}\""
        if comment:
            text += f": {comment}"
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=text, link=f"/edit-question/{question.test_q_id}", category='tests')

    db.session.commit()
    flash("Ответ обновлен!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-question/{question.test_q_id}")


@edit_bp.route('/delete-question/<int:question_id>', methods=["POST"])
@login_required
def delete_question(question_id):
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    test = Tests.query.get(question.test_q_test_id)
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    Tests_answers.query.filter_by(test_a_question_id=question_id).delete()
    delete_image(question.test_q_image, current_app.config['UPLOAD_FOLDER'])
    db.session.delete(question)
    was_published = _revert_test_to_review(test, current_user)

    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=f"Модератор {current_user.username} удалил вопрос в вашем тесте \"{test.test_name}\"",
                             link=f"/edit-test/{test.test_id}/questions", category='tests')

    db.session.commit()
    flash("Вопрос удален!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-test/{test.test_id}/questions")


@edit_bp.route('/delete-answer/<int:answer_id>', methods=["POST"])
@login_required
def delete_answer(answer_id):
    answer = Tests_answers.query.get(answer_id)
    if not answer:
        flash("Ответ не найден!", 'danger')
        return redirect("/tests")
    question = Tests_questions.query.get(answer.test_a_question_id)
    test = Tests.query.get(answer.test_a_test_id)
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    total = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).count()
    if question.test_q_type in [1, 2, 11, 21]:
        if total <= 2:
            flash("Нельзя удалить ответ! Должно быть минимум 2 варианта.", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")
        if answer.test_a_is_correct:
            correct_count = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id, test_a_is_correct=True).count()
            if correct_count <= 1:
                flash("Нельзя удалить последний правильный ответ!", 'danger')
                return redirect(f"/edit-question/{question.test_q_id}")
    elif question.test_q_type in [3, 31]:
        if total <= 1:
            flash("Нельзя удалить последний ответ!", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")
    elif question.test_q_type in [4, 41]:
        if total <= 2:
            flash("Нельзя удалить пару! Должно быть минимум 2 пары.", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")

    db.session.delete(answer)
    was_published = _revert_test_to_review(test, current_user)

    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=f"Модератор {current_user.username} удалил ответ в вашем тесте \"{test.test_name}\"",
                             link=f"/edit-question/{question.test_q_id}", category='tests')

    db.session.commit()
    flash("Ответ удален!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-question/{question.test_q_id}")


@edit_bp.route('/add-question/<int:test_id>')
@login_required
def add_question(test_id):
    test = Tests.query.get(test_id)
    if not test or (test.test_id_creator != current_user.id and current_user.admin < 1):
        flash("Нет доступа!", 'danger')
        return redirect("/tests")
    return render_template("add_question_type.html", test=test)


@edit_bp.route('/add-question/<int:test_id>/create', methods=["POST"])
@login_required
def create_question(test_id):
    test = Tests.query.get(test_id)
    if not test or (test.test_id_creator != current_user.id and current_user.admin < 1):
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    question_type = int(request.form.get('question_type', 1))
    question_text = request.form.get('question_text')
    if not question_text:
        flash("Введите текст вопроса!", 'danger')
        return redirect(f"/add-question/{test_id}")

    image_filename = None
    if question_type in [11, 21, 31, 41] and 'question_image' in request.files:
        file = request.files['question_image']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения.", "danger")
            return redirect(f"/add-question/{test_id}")

    new_q = Tests_questions(test_q_creator_id=current_user.id, test_q_test_id=test_id,
                            test_q_text=question_text, test_q_type=question_type,
                            test_q_status=test.test_status, test_q_image=image_filename)
    db.session.add(new_q)
    db.session.commit()

    if question_type in [1, 2, 11, 21]:
        a1_text = request.form.get('answer1_text', 'Вариант 1')
        a2_text = request.form.get('answer2_text', 'Вариант 2')
        c1 = bool(request.form.get('is_correct1'))
        c2 = bool(request.form.get('is_correct2'))
        if not c1 and not c2:
            flash("Укажите хотя бы один правильный ответ!", 'danger')
            return redirect(f"/add-question/{test_id}")
        for txt, cor in [(a1_text, c1), (a2_text, c2)]:
            db.session.add(Tests_answers(test_a_creator_id=current_user.id, test_a_test_id=test_id,
                                         test_a_question_id=new_q.test_q_id, test_a_text=txt,
                                         test_a_status=test.test_status, test_a_is_correct=cor))

    elif question_type in [3, 31]:
        db.session.add(Tests_answers(test_a_creator_id=current_user.id, test_a_test_id=test_id,
                                     test_a_question_id=new_q.test_q_id,
                                     test_a_text=request.form.get('answer_text', 'Правильный ответ'),
                                     test_a_status=test.test_status, test_a_is_correct=True))

    elif question_type in [4, 41]:
        pairs = [(request.form.get('row_text', '').strip(), request.form.get('block_text', '').strip()),
                 (request.form.get('row_text2', '').strip(), request.form.get('block_text2', '').strip())]
        if not all(r and b for r, b in pairs):
            db.session.delete(new_q)
            db.session.commit()
            flash("Для типа 'Перетаскивание' нужно заполнить минимум 2 пары!", 'danger')
            return redirect(f"/add-question/{test_id}")
        for rt, bt in pairs:
            db.session.add(Tests_answers(test_a_creator_id=current_user.id, test_a_test_id=test_id,
                                         test_a_question_id=new_q.test_q_id, test_a_text=bt,
                                         test_a_match=rt, test_a_status=test.test_status, test_a_is_correct=True))

    was_published = _revert_test_to_review(test, current_user)
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=f"Модератор {current_user.username} добавил новый вопрос в ваш тест \"{test.test_name}\"",
                             link=f"/edit-question/{new_q.test_q_id}", category='tests')

    db.session.commit()
    flash("Вопрос создан!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-question/{new_q.test_q_id}")


@edit_bp.route('/add-answer/<int:question_id>', methods=["POST"])
@login_required
def add_answer(question_id):
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    test = Tests.query.get(question.test_q_test_id)
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("Нет доступа!", 'danger')
        return redirect("/tests")

    answer_text = request.form.get('answer_text', 'Новый ответ')
    is_correct = bool(request.form.get('is_correct'))
    row_text = None

    if question.test_q_type in [3, 31]:
        is_correct = True
    if question.test_q_type in [4, 41]:
        is_correct = True
        row_text = (request.form.get('row_text') or "").strip()

    db.session.add(Tests_answers(test_a_creator_id=current_user.id, test_a_test_id=test.test_id,
                                 test_a_question_id=question_id, test_a_text=answer_text,
                                 test_a_match=row_text, test_a_status=question.test_q_status,
                                 test_a_is_correct=is_correct))

    was_published = _revert_test_to_review(test, current_user)
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        _create_notification(user_id=test.test_id_creator, sender_id=current_user.id,
                             text=f"Модератор {current_user.username} добавил новый ответ в ваш тест \"{test.test_name}\"",
                             link=f"/edit-question/{question_id}", category='tests')

    db.session.commit()
    flash("Ответ добавлен!" + (" Тест отправлен на повторную проверку." if was_published else ""),
          'warning' if was_published else 'success')
    return redirect(f"/edit-question/{question_id}")
