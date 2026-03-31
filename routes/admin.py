from flask import Blueprint, render_template, request, redirect, flash
from flask_login import login_required, current_user

from extensions import db
from models import User
from helpers import _create_notification

admin_bp = Blueprint('admin', __name__)


def _require_admin():
    if current_user.admin < 2:
        flash("У вас нет доступа!", 'danger')
        return redirect("/")
    return None


@admin_bp.route('/admin_1')
@admin_bp.route('/admin')
@login_required
def admin_1():
    err = _require_admin()
    if err:
        return err
    return render_template("admin_1.html")


@admin_bp.route('/admin/users')
@login_required
def admin_users():
    err = _require_admin()
    if err:
        return err

    q_id = request.args.get('id', '').strip()
    q_name = request.args.get('name', '').strip()
    q_email = request.args.get('email', '').strip()
    q_status = request.args.get('status', '').strip()

    query = User.query
    if q_id:
        try:
            query = query.filter(User.id == int(q_id))
        except ValueError:
            pass
    if q_name:
        query = query.filter(User.username.ilike(f'%{q_name}%'))
    if q_email:
        query = query.filter(User.email.ilike(f'%{q_email}%'))
    if q_status in ('0', '1', '2'):
        query = query.filter(User.admin == int(q_status))

    users = query.order_by(User.id).all()
    return render_template("admin_users.html", users=users,
                           q_id=q_id, q_name=q_name, q_email=q_email, q_status=q_status)


@admin_bp.route('/admin/user/<int:user_id>/update-name', methods=['POST'])
@login_required
def admin_update_username(user_id):
    err = _require_admin()
    if err:
        return err

    user = User.query.get(user_id)
    if not user:
        flash("Пользователь не найден!", 'danger')
        return redirect("/admin/users")

    new_username = request.form.get('username', '').strip()
    if not new_username:
        flash("Имя не может быть пустым!", 'danger')
        return redirect("/admin/users")

    old_username = user.username
    reason = request.form.get('reason', '').strip()
    user.username = new_username

    text = f"Администратор изменил ваше имя пользователя с \"{old_username}\" на \"{new_username}\"."
    if reason:
        text += f" Причина: {reason}"
    _create_notification(user_id=user.id, sender_id=current_user.id, text=text, category='account_changes')

    db.session.commit()
    flash(f"Имя пользователя изменено на \"{new_username}\".", 'success')
    return redirect("/admin/users")


@admin_bp.route('/admin/user/<int:user_id>/update-status', methods=['POST'])
@login_required
def admin_update_status(user_id):
    err = _require_admin()
    if err:
        return err

    if user_id == current_user.id:
        flash("Нельзя изменить свой собственный статус!", 'danger')
        return redirect("/admin/users")

    user = User.query.get(user_id)
    if not user:
        flash("Пользователь не найден!", 'danger')
        return redirect("/admin/users")

    new_status = request.form.get('admin_status')
    if new_status not in ['0', '1', '2']:
        flash("Недопустимый статус!", 'danger')
        return redirect("/admin/users")

    new_status = int(new_status)
    old_status = user.admin
    reason = request.form.get('reason', '').strip()
    status_names = {0: 'Пользователь', 1: 'Модератор', 2: 'Администратор'}
    user.admin = new_status

    text = (f"Администратор изменил ваш статус с \"{status_names[old_status]}\" "
            f"на \"{status_names[new_status]}\".")
    if reason:
        text += f" Причина: {reason}"
    _create_notification(user_id=user.id, sender_id=current_user.id, text=text, category='account_changes')

    db.session.commit()
    flash(f"Статус пользователя \"{user.username}\" изменён на \"{status_names[new_status]}\".", 'success')
    return redirect("/admin/users")


@admin_bp.route('/admin/messages', methods=['GET'])
@login_required
def admin_messages():
    err = _require_admin()
    if err:
        return err
    users = User.query.order_by(User.username).all()
    return render_template("admin_messages.html", users=users)


@admin_bp.route('/admin/messages/send', methods=['POST'])
@login_required
def admin_send_message():
    err = _require_admin()
    if err:
        return err

    text = request.form.get('text', '').strip()
    link = request.form.get('link', '').strip() or None
    target = request.form.get('target')

    if not text:
        flash("Текст сообщения не может быть пустым!", 'danger')
        return redirect("/admin/messages")

    if target == 'all':
        recipients = User.query.all()
    elif target == 'single':
        try:
            user = User.query.get(int(request.form.get('user_id', '')))
        except (ValueError, TypeError):
            user = None
        if not user:
            flash("Пользователь не найден!", 'danger')
            return redirect("/admin/messages")
        recipients = [user]
    elif target == 'multiple':
        try:
            recipients = User.query.filter(
                User.id.in_([int(i) for i in request.form.getlist('user_ids')])).all()
        except (ValueError, TypeError):
            recipients = []
        if not recipients:
            flash("Не выбрано ни одного пользователя!", 'danger')
            return redirect("/admin/messages")
    else:
        flash("Неверный тип получателей!", 'danger')
        return redirect("/admin/messages")

    for user in recipients:
        _create_notification(user_id=user.id, sender_id=current_user.id,
                             text=text, link=link, category='admin_messages')
    db.session.commit()
    flash(f"Сообщение отправлено {len(recipients)} пользователю(-ям).", 'success')
    return redirect("/admin/messages")
