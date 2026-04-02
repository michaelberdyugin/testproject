import time

from flask import Blueprint, render_template, request, redirect, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User
from helpers import _generate_code, _send_verification_code, _start_pending_registration, _clear_pending_registration

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/registration', methods=["GET", "POST"])
def registration():
    if request.method == "GET":
        pending = session.get("pending_reg")
        if pending:
            return render_template("registration.html", show_modal=True,
                                   pending_email=pending.get("email"),
                                   pending_username=pending.get("username"))
        return render_template("registration.html", show_modal=False)

    verification_code = (request.form.get("verification_code") or "").strip()
    if verification_code:
        pending = session.get("pending_reg")
        if not pending:
            flash("Сессия подтверждения истекла. Заполните регистрацию заново.", "warning")
            return redirect("/registration")
        if not check_password_hash(pending["code_hash"], verification_code):
            flash("Неверный код подтверждения.", "danger")
            return render_template("registration.html", show_modal=True,
                                   pending_email=pending.get("email"),
                                   pending_username=pending.get("username"))

        username = pending["username"]
        email = pending["email"]
        password_hash = pending["password_hash"]

        if User.query.filter_by(username=username).first():
            _clear_pending_registration()
            flash("Имя пользователя уже занято. Попробуйте другое.", "danger")
            return redirect("/registration")
        if User.query.filter_by(email=email).first():
            _clear_pending_registration()
            flash("Почта уже используется. Попробуйте другую.", "danger")
            return redirect("/registration")

        new_user = User(username=username, password=password_hash, email=email)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        _clear_pending_registration()
        flash("Почта подтверждена. Регистрация завершена!", "success")
        return redirect("/")

    username = (request.form.get('username') or "").strip()
    email = (request.form.get('email') or "").strip().lower()
    password = request.form.get('password') or ""
    password2 = request.form.get('password2') or ""

    if not username or not email or not password:
        flash("Заполните логин, почту и пароль.", "danger")
        return redirect("/registration")
    if len(username) > 30:
        flash("Имя пользователя не может быть длиннее 30 символов!", "danger")
        return redirect("/registration")
    if "@" not in email or "." not in email:
        flash("Введите корректную почту.", "danger")
        return redirect("/registration")
    if User.query.filter_by(username=username).first():
        flash('Имя пользователя занято!', 'danger')
        return redirect("/registration")
    if User.query.filter_by(email=email).first():
        flash('Эта почта уже используется!', 'danger')
        return redirect("/registration")
    if password2 != password:
        flash('Пароли не совпадают!', 'danger')
        return redirect("/registration")

    _start_pending_registration(username, generate_password_hash(password), email)
    flash("Мы отправили код подтверждения на вашу почту.", "info")
    pending = session.get("pending_reg", {})
    return render_template("registration.html", show_modal=True,
                           pending_email=pending.get("email"),
                           pending_username=pending.get("username"))


@auth_bp.route("/registration/resend", methods=["POST"])
def registration_resend():
    pending = session.get("pending_reg")
    if not pending:
        flash("Сессия подтверждения истекла. Заполните регистрацию заново.", "warning")
        return redirect("/registration")

    now = int(time.time())
    cooldown = 30
    if now - int(pending.get("last_resend_at") or 0) < cooldown:
        flash(f"Повторно отправить код можно через {cooldown - (now - int(pending.get('last_resend_at', 0)))} сек.", "warning")
        return render_template("registration.html", show_modal=True,
                               pending_email=pending.get("email"),
                               pending_username=pending.get("username"))

    code = _generate_code()
    pending["code_hash"] = generate_password_hash(code)
    pending["last_resend_at"] = now
    pending["sent_at"] = now
    session["pending_reg"] = pending
    _send_verification_code(pending["email"], code)
    flash("Код отправлен повторно.", "info")
    return render_template("registration.html", show_modal=True,
                           pending_email=pending.get("email"),
                           pending_username=pending.get("username"))


@auth_bp.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if current_user.is_authenticated:
            flash("Вы уже авторизованы", 'warning')
            return redirect("/")
        return render_template("login.html")
    username = request.form.get('username')
    password = request.form.get('password')
    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User.query.filter_by(email=username).first()
    if user is None:
        flash('Такого пользователя не существует', 'danger')
        return redirect("/login")
    if check_password_hash(user.password, password):
        login_user(user)
        return redirect('/')
    flash("Неверный логин или пароль!", 'danger')
    return render_template("login.html")


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect("/")
