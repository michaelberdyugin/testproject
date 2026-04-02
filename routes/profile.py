import time

from flask import Blueprint, render_template, request, redirect, flash, session
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_mail import Message

from extensions import db, mail
from models import User, UserNotificationSettings, Notifications
from helpers import _generate_code

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
@login_required
def profile():
    settings = UserNotificationSettings.query.filter_by(uns_user_id=current_user.id).first()
    show_email_confirm = request.args.get("show_email_confirm") == "1"
    pending_email = session.get("pending_email", {}).get("new_email") if show_email_confirm else None
    return render_template("profile.html", settings=settings,
                           show_email_confirm=show_email_confirm,
                           pending_new_email=pending_email)


@profile_bp.route('/profile/update-username', methods=['POST'])
@login_required
def profile_update_username():
    new_username = request.form.get('username', '').strip()
    if not new_username:
        flash("Имя не может быть пустым!", 'danger')
        return redirect("/profile")
    if len(new_username) > 30:
        flash("Имя не может быть длиннее 30 символов!", 'danger')
        return redirect("/profile")
    if User.query.filter(User.username == new_username, User.id != current_user.id).first():
        flash("Это имя уже занято!", 'danger')
        return redirect("/profile")
    current_user.username = new_username
    db.session.commit()
    flash("Имя пользователя обновлено.", 'success')
    return redirect("/profile")


@profile_bp.route('/profile/update-email', methods=['POST'])
@login_required
def profile_update_email():
    # Шаг 2: подтверждение кода
    verification_code = (request.form.get("email_verification_code") or "").strip()
    if verification_code:
        pending = session.get("pending_email")
        if not pending or pending.get("user_id") != current_user.id:
            flash("Сессия подтверждения истекла. Попробуйте снова.", "warning")
            return redirect("/profile")
        if not check_password_hash(pending["code_hash"], verification_code):
            flash("Неверный код подтверждения.", "danger")
            return redirect("/profile?show_email_confirm=1")
        new_email = pending["new_email"]
        if User.query.filter(User.email == new_email, User.id != current_user.id).first():
            session.pop("pending_email", None)
            flash("Эта почта уже используется!", "danger")
            return redirect("/profile")
        current_user.email = new_email
        db.session.commit()
        session.pop("pending_email", None)
        flash("Почта успешно обновлена.", "success")
        return redirect("/profile")

    # Шаг 1: запрос новой почты
    new_email = request.form.get('email', '').strip().lower()
    if not new_email or '@' not in new_email or '.' not in new_email:
        flash("Введите корректную почту!", 'danger')
        return redirect("/profile")
    if new_email == current_user.email:
        flash("Это уже ваша текущая почта.", 'warning')
        return redirect("/profile")
    if User.query.filter(User.email == new_email, User.id != current_user.id).first():
        flash("Эта почта уже используется!", 'danger')
        return redirect("/profile")

    code = _generate_code()
    session["pending_email"] = {
        "user_id": current_user.id,
        "new_email": new_email,
        "code_hash": generate_password_hash(code),
        "sent_at": int(time.time()),
    }
    try:
        msg = Message(
            recipients=[new_email],
            subject="Подтверждение смены почты",
            body=f"Ваш код подтверждения для смены почты: {code}\n\nЕсли вы не запрашивали смену — проигнорируйте это письмо."
        )
        mail.send(msg)
        flash(f"Код подтверждения отправлен на {new_email}.", "info")
    except Exception as e:
        print(f"Ошибка отправки кода смены почты: {e}")
        flash("Не удалось отправить код. Проверьте почту и попробуйте снова.", "danger")
        session.pop("pending_email", None)
    return redirect("/profile?show_email_confirm=1")


@profile_bp.route('/profile/update-password', methods=['POST'])
@login_required
def profile_update_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    new_password2 = request.form.get('new_password2', '')
    if not check_password_hash(current_user.password, current_password):
        flash("Неверный текущий пароль!", 'danger')
        return redirect("/profile")
    if len(new_password) < 6:
        flash("Новый пароль должен быть не короче 6 символов!", 'danger')
        return redirect("/profile")
    if new_password != new_password2:
        flash("Пароли не совпадают!", 'danger')
        return redirect("/profile")
    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash("Пароль изменён.", 'success')
    return redirect("/profile")


@profile_bp.route('/profile/notification-settings', methods=['POST'])
@login_required
def profile_notification_settings():
    settings = UserNotificationSettings.query.filter_by(uns_user_id=current_user.id).first()
    if not settings:
        settings = UserNotificationSettings(uns_user_id=current_user.id)
        db.session.add(settings)
    settings.uns_email_tests = bool(request.form.get('email_tests'))
    settings.uns_email_admin_messages = bool(request.form.get('email_admin_messages'))
    settings.uns_email_account_changes = bool(request.form.get('email_account_changes'))
    db.session.commit()
    flash("Настройки уведомлений сохранены.", 'success')
    return redirect("/profile")


@profile_bp.route('/notifications')
@login_required
def notifications():
    user_notifications = Notifications.query.filter_by(
        n_user_id=current_user.id
    ).order_by(Notifications.n_created_at.desc()).all()

    notifications_with_senders = []
    for notif in user_notifications:
        sender = User.query.get(notif.n_sender_id) if notif.n_sender_id else None
        notifications_with_senders.append({'notification': notif, 'sender': sender})

    unread_count = Notifications.query.filter_by(n_user_id=current_user.id, n_is_read=False).count()
    return render_template("notifications.html",
                           notifications=notifications_with_senders,
                           unread_count=unread_count)


@profile_bp.route('/notifications/mark-read/<int:notification_id>', methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notifications.query.get(notification_id)
    if notification and notification.n_user_id == current_user.id:
        notification.n_is_read = True
        db.session.commit()
    return redirect("/notifications")


@profile_bp.route('/notifications/mark-all-read', methods=["POST"])
@login_required
def mark_all_notifications_read():
    Notifications.query.filter_by(n_user_id=current_user.id, n_is_read=False).update({'n_is_read': True})
    db.session.commit()
    flash("Все уведомления отмечены как прочитанные", 'success')
    return redirect("/notifications")
