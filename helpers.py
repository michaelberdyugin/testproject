import random
import re
import time
import uuid
import os

from flask import render_template, request, session
from flask_mail import Message
from werkzeug.security import generate_password_hash

from extensions import db, mail

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_test_name(name):
    pattern = r'^[а-яА-ЯёЁa-zA-Z0-9 _-]+$'
    return bool(re.match(pattern, name))


def save_uploaded_image(file_field, upload_folder):
    """Сохраняет загруженный файл и возвращает имя файла или None."""
    if not file_field or file_field.filename == '':
        return None, None
    if not allowed_file(file_field.filename):
        return None, "Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp"
    ext = file_field.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_field.save(os.path.join(upload_folder, filename))
    return filename, None


def delete_image(filename, upload_folder):
    """Удаляет файл изображения если он существует."""
    if filename:
        try:
            path = os.path.join(upload_folder, filename)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Ошибка при удалении изображения: {e}")


def _generate_code():
    return f"{random.randint(0, 999999):06d}"


def _send_verification_code(email: str, code: str):
    subject = "Код подтверждения регистрации"
    body = f"Ваш код подтверждения: {code}\n\nЕсли вы не регистрировались — просто проигнорируйте это письмо."
    with mail.connect() as conn:
        msg = Message(recipients=[email], body=body, subject=subject)
        conn.send(msg)


def _start_pending_registration(username: str, password_hash: str, email: str):
    code = _generate_code()
    session["pending_reg"] = {
        "username": username,
        "password_hash": password_hash,
        "email": email,
        "code_hash": generate_password_hash(code),
        "sent_at": int(time.time()),
        "last_resend_at": int(time.time()),
    }
    _send_verification_code(email, code)


def _clear_pending_registration():
    session.pop("pending_reg", None)


def _revert_test_to_review(test, user):
    """Переводит опубликованный тест обратно на проверку (не для модераторов)."""
    from models import Tests_questions, Tests_answers
    if user.admin >= 1:
        return False
    if test.test_status == 2:
        test.test_status = 1
        for q in Tests_questions.query.filter_by(test_q_test_id=test.test_id).all():
            if q.test_q_status == 2:
                q.test_q_status = 1
        for a in Tests_answers.query.filter_by(test_a_test_id=test.test_id).all():
            if a.test_a_status == 2:
                a.test_a_status = 1
        return True
    return False


def _calc_are_ready(question):
    """Проверяет готовность вопроса к переходу дальше."""
    from models import Tests_answers
    answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).all()
    count = len(answers)
    if question.test_q_type in [3, 31]:
        return count >= 1
    if question.test_q_type in [4, 41]:
        return count >= 2
    has_correct = any(a.test_a_is_correct for a in answers)
    return count >= 2 and has_correct


def _render_createnext(current_test, last_question):
    """Рендерит createnext.html с правильно вычисленными флагами."""
    from models import Tests_answers
    answers = Tests_answers.query.filter_by(test_a_question_id=last_question.test_q_id).all()
    count = len(answers)
    has_correct = any(a.test_a_is_correct for a in answers)
    if last_question.test_q_type in [3, 31]:
        are_ready = count >= 1
    elif last_question.test_q_type in [4, 41]:
        are_ready = count >= 2
    else:
        are_ready = count >= 2 and has_correct
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_ready,
        has_correct=has_correct,
        answers_count=count
    )


def _create_notification(user_id, sender_id, text, link=None, category=None,
                         test_id=None, is_comment=False):
    """Создаёт уведомление и при необходимости отправляет email."""
    from models import Notifications, User
    notification = Notifications(
        n_user_id=user_id,
        n_sender_id=sender_id,
        n_text=text,
        n_link=link,
        n_test_id=test_id,
        n_is_comment=is_comment
    )
    db.session.add(notification)

    if category:
        user = User.query.get(user_id)
        if user and user.email:
            send_email = False
            if category == 'tests' and user.notif_email_tests:
                send_email = True
            elif category == 'admin_messages' and user.notif_email_admin:
                send_email = True
            elif category == 'account_changes' and user.notif_email_account:
                send_email = True

            if send_email:
                try:
                    body = text
                    if link:
                        body += f"\n\nПерейти: {request.host_url.rstrip('/')}{link}"
                    msg = Message(recipients=[user.email], body=body, subject="Новое уведомление")
                    mail.send(msg)
                except Exception as e:
                    print(f"Ошибка отправки email уведомления: {e}")
