from flask import Flask, render_template, request, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_mail import Mail, Message
import random
import time
import uuid
import os
from werkzeug.utils import secure_filename
import secret
import re

app = Flask(__name__)
app.secret_key = secret.key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
db = SQLAlchemy(app)
manager = LoginManager(app)

# Фильтр для подсчета непрочитанных уведомлений
@app.template_filter('get_unread_notifications_count')
def get_unread_notifications_count(user_id):
    """Возвращает количество непрочитанных уведомлений пользователя."""
    return Notifications.query.filter_by(n_user_id=user_id, n_is_read=False).count()

app.config['MAIL_SERVER']='smtp.mail.ru'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'itcube.michael.berdyugin@mail.ru'
app.config['MAIL_DEFAULT_SENDER'] = 'itcube.michael.berdyugin@mail.ru'
app.config['MAIL_PASSWORD'] = secret.mail_password
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'img')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 МБ максимум
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    """Проверяет расширение файла на безопасность."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_test_name(name):
    """
    Проверяет название теста на допустимые символы.
    Разрешены: русские и английские буквы, цифры, пробелы, дефис и подчеркивание.
    """
    pattern = r'^[а-яА-ЯёЁa-zA-Z0-9 _-]+$'
    return bool(re.match(pattern, name))

def create_test_slug(name):
    """
    Создает URL-friendly slug из названия теста.
    Заменяет пробелы на дефисы и приводит к нижнему регистру.
    """
    # Заменяем пробелы на дефисы
    slug = name.strip().replace(' ', '-')
    # Убираем множественные дефисы
    slug = re.sub(r'-+', '-', slug)
    return slug

class User(db.Model, UserMixin):
    """Модель пользователя с логином, паролем и подтверждаемой по почте учётной записью."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    email = db.Column(db.String, unique=True, nullable=False)
    email_confirmed = db.Column(db.Boolean, default=False)
    admin = db.Column(db.Integer, default=0)  # 0 - обычный пользователь, 1 - модератор, 2 - администратор
    current_test_id = db.Column(db.Integer, default=None)  # ID текущего проходимого теста

class Tests(db.Model):
    test_id = db.Column(db.Integer, primary_key=True)
    test_id_creator = db.Column(db.Integer)
    test_name = db.Column(db.String)
    test_description = db.Column(db.String)
    test_status = db.Column(db.Integer)
    test_image= db.Column(db.String)

class Tests_questions(db.Model):
    test_q_id = db.Column(db.Integer, primary_key=True)
    test_q_creator_id = db.Column(db.Integer)
    test_q_test_id = db.Column(db.Integer)
    test_q_text = db.Column(db.String)
    # Тип вопроса:
    # 1 — выбор одного ответа из нескольких вариантов
    # 2 — выбор нескольких ответов
    # 3 — ввод ответа вручную
    # 11 — выбор одного ответа из нескольких вариантов с изображением
    # 21 — выбор нескольких ответов с изображением
    # 31 — ввод ответа вручную с изображением
    test_q_type = db.Column(db.Integer, default=1)
    test_q_status = db.Column(db.Integer)
    test_q_image = db.Column(db.String)

class Tests_answers(db.Model):
    test_a_id = db.Column(db.Integer, primary_key=True)
    test_a_creator_id = db.Column(db.Integer)
    test_a_question_id = db.Column(db.Integer)
    test_a_test_id = db.Column(db.Integer)
    test_a_text = db.Column(db.String)
    test_a_status = db.Column(db.Integer)
    test_a_is_correct = db.Column(db.Boolean)

class Test_scores(db.Model):
    """Модель для хранения оценок тестов пользователями."""
    test_s_id = db.Column(db.Integer, primary_key=True)
    test_s_user_id = db.Column(db.Integer, nullable=False)
    test_s_test_id = db.Column(db.Integer, nullable=False)
    test_s_score = db.Column(db.Integer, nullable=False)  # Оценка от 1 до 5


class Notifications(db.Model):
    """Модель для хранения уведомлений пользователей."""
    n_id = db.Column(db.Integer, primary_key=True)
    n_user_id = db.Column(db.Integer, nullable=False)  # Кому предназначено уведомление
    n_sender_id = db.Column(db.Integer)  # Кто отправил (может быть None для системных уведомлений)
    n_text = db.Column(db.Text, nullable=False)  # Текст уведомления
    n_link = db.Column(db.String)  # Ссылка (например, на тест)
    n_is_read = db.Column(db.Boolean, default=False)  # Прочитано ли
    n_created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Когда создано


class TestComments(db.Model):
    """Модель для хранения комментариев модераторов к тестам."""
    tc_id = db.Column(db.Integer, primary_key=True)
    tc_test_id = db.Column(db.Integer, nullable=False)  # К какому тесту
    tc_user_id = db.Column(db.Integer, nullable=False)  # Кто оставил комментарий
    tc_comment = db.Column(db.Text, nullable=False)  # Текст комментария
    tc_created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Когда создан


def _generate_code():
    """Генерирует 6-значный цифровой код подтверждения в виде строки."""
    return f"{random.randint(0, 999999):06d}"


def _send_verification_code(email: str, code: str):
    """Отправляет на указанный email письмо с кодом подтверждения регистрации."""
    subject = "Код подтверждения регистрации"
    body = f"Ваш код подтверждения: {code}\n\nЕсли вы не регистрировались — просто проигнорируйте это письмо."
    with mail.connect() as conn:
        msg = Message(recipients=[email], body=body, subject=subject)
        conn.send(msg)


def _start_pending_registration(username: str, password_hash: str, email: str):
    """
    Запускает процесс «ожидающей регистрации»:
    сохраняет данные пользователя и хэш кода в session и отправляет код на почту.
    """
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
    """Удаляет из session данные о незавершённой регистрации (если они есть)."""
    session.pop("pending_reg", None)


def _revert_test_to_review(test, user):
    """
    Переводит опубликованный тест обратно на проверку.
    Изменяет статус теста, всех его вопросов и ответов с 2 на 1.
    Модераторы (admin >= 1) могут редактировать без перевода на проверку.
    """
    # Модераторы могут редактировать без перевода на проверку
    if user.admin >= 1:
        return False
    
    if test.test_status == 2:
        # Меняем статус теста
        test.test_status = 1
        
        # Меняем статус всех вопросов
        questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
        for question in questions:
            if question.test_q_status == 2:
                question.test_q_status = 1
        
        # Меняем статус всех ответов
        answers = Tests_answers.query.filter_by(test_a_test_id=test.test_id).all()
        for answer in answers:
            if answer.test_a_status == 2:
                answer.test_a_status = 1
        
        return True
    return False


def _create_notification(user_id, sender_id, text, link=None):
    """
    Создает уведомление для пользователя.
    
    Args:
        user_id: ID пользователя, которому предназначено уведомление
        sender_id: ID отправителя (может быть None для системных уведомлений)
        text: Текст уведомления
        link: Ссылка (опционально)
    """
    notification = Notifications(
        n_user_id=user_id,
        n_sender_id=sender_id,
        n_text=text,
        n_link=link
    )
    db.session.add(notification)
    # Не делаем commit здесь - это сделает вызывающая функция


@app.before_request
def check_must_rate_test():
    """Проверяет, должен ли пользователь оценить тест перед переходом на другие страницы."""
    # Исключаем маршруты, связанные с оценкой теста
    excluded_paths = ['/test/', '/static/', '/logout']
    
    # Проверяем, есть ли флаг обязательной оценки
    if 'must_rate_test' in session and session['must_rate_test']:
        current_path = request.path
        
        # Разрешаем доступ только к страницам результатов и оценки
        if not any(excluded in current_path for excluded in excluded_paths):
            if 'test_result' in session:
                test_name = session['test_result']['test_name']
                if current_path not in [f'/test/{test_name}/result', f'/test/{test_name}/rate']:
                    flash("Пожалуйста, оцените тест перед переходом на другие страницы!", 'warning')
                    return redirect(f"/test/{test_name}/result")

@manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/registration', methods=["POST", "GET"])
def registration():
    if request.method == "GET":
        # Если уже есть незавершённая регистрация в session — сразу показываем модалку ввода кода.
        pending = session.get("pending_reg")
        if pending:
            return render_template(
                "registration.html",
                show_modal=True,
                pending_email=pending.get("email"),
                pending_username=pending.get("username"),
            )
        return render_template("registration.html", show_modal=False)

    # Шаг 2: проверка кода из модалки (если пришло поле verification_code)
    verification_code = (request.form.get("verification_code") or "").strip()
    if verification_code:
        pending = session.get("pending_reg")
        if not pending:
            flash("Сессия подтверждения истекла. Заполните регистрацию заново.", "warning")
            return redirect("/registration")
        if not check_password_hash(pending["code_hash"], verification_code):
            flash("Неверный код подтверждения.", "danger")
            return render_template(
                "registration.html",
                show_modal=True,
                pending_email=pending.get("email"),
                pending_username=pending.get("username"),
            )

        # Код верный — создаём пользователя и авторизуем
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

        new_user = User(
            username=username,
            password=password_hash,  # Обратите внимание: поле называется 'password', а не 'password_hash'
            email=email,
            email_confirmed=True
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        _clear_pending_registration()
        flash("Почта подтверждена. Регистрация завершена!", "success")
        return redirect("/")

    # Шаг 1: старт регистрации (первичная отправка кода на почту)
    username = (request.form.get('username') or "").strip()
    email = (request.form.get('email') or "").strip().lower()
    password = request.form.get('password') or ""
    password2 = request.form.get('password2') or ""

    if not username or not email or not password:
        flash("Заполните логин, почту и пароль.", "danger")
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

    hash_pwd = generate_password_hash(password)
    _start_pending_registration(username, hash_pwd, email)
    flash("Мы отправили код подтверждения на вашу почту.", "info")
    pending = session.get("pending_reg", {})
    return render_template(
        "registration.html",
        show_modal=True,
        pending_email=pending.get("email"),
        pending_username=pending.get("username"),
    )

@app.route("/registration/resend", methods=["POST"])
def registration_resend():
    #Обрабатывает повторную отправку кода подтверждения, с простым ограничением по времени (cooldown).
    pending = session.get("pending_reg")
    if not pending:
        flash("Сессия подтверждения истекла. Заполните регистрацию заново.", "warning")
        return redirect("/registration")

    now = int(time.time())
    last = int(pending.get("last_resend_at") or 0)
    cooldown = 30
    if now - last < cooldown:
        flash(f"Повторно отправить код можно через {cooldown - (now - last)} сек.", "warning")
        return render_template(
            "registration.html",
            show_modal=True,
            pending_email=pending.get("email"),
            pending_username=pending.get("username"),
        )

    code = _generate_code()
    pending["code_hash"] = generate_password_hash(code)
    pending["last_resend_at"] = now
    pending["sent_at"] = now
    session["pending_reg"] = pending
    _send_verification_code(pending["email"], code)
    flash("Код отправлен повторно.", "info")
    return render_template(
        "registration.html",
        show_modal=True,
        pending_email=pending.get("email"),
        pending_username=pending.get("username"),
    )

@app.route('/login', methods=["POST", "GET"])
def login():
    if request.method == "GET":
        if current_user.is_authenticated:
            flash("Вы уже авторизованы", 'warning')
            return redirect("/")
        return render_template("login.html")
    username = request.form.get('username')
    password = request.form.get('password')
    # Ищем по имени или по почте
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

@app.route('/workshop')
@login_required
def workshop():
    """Мастерская тестов - управление своими тестами."""
    # Получаем все тесты пользователя (все статусы)
    user_tests = Tests.query.filter_by(test_id_creator=current_user.id).all()
    
    # Разделяем тесты по статусам
    tests_in_progress = [t for t in user_tests if t.test_status == 0]
    tests_pending = [t for t in user_tests if t.test_status == 1]
    tests_published = [t for t in user_tests if t.test_status == 2]
    
    return render_template("workshop.html", 
                         tests_in_progress=tests_in_progress,
                         tests_pending=tests_pending,
                         tests_published=tests_published)

@app.route('/notifications')
@login_required
def notifications():
    """Страница уведомлений пользователя."""
    # Получаем все уведомления пользователя, отсортированные по дате
    user_notifications = Notifications.query.filter_by(n_user_id=current_user.id).order_by(Notifications.n_created_at.desc()).all()
    
    # Получаем информацию об отправителях
    notifications_with_senders = []
    for notif in user_notifications:
        sender = None
        if notif.n_sender_id:
            sender = User.query.get(notif.n_sender_id)
        notifications_with_senders.append({
            'notification': notif,
            'sender': sender
        })
    
    # Подсчитываем непрочитанные
    unread_count = Notifications.query.filter_by(n_user_id=current_user.id, n_is_read=False).count()
    
    return render_template("notifications.html", 
                         notifications=notifications_with_senders,
                         unread_count=unread_count)

@app.route('/notifications/mark-read/<int:notification_id>', methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Отметить уведомление как прочитанное."""
    notification = Notifications.query.get(notification_id)
    if notification and notification.n_user_id == current_user.id:
        notification.n_is_read = True
        db.session.commit()
    return redirect("/notifications")

@app.route('/notifications/mark-all-read', methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Отметить все уведомления как прочитанные."""
    Notifications.query.filter_by(n_user_id=current_user.id, n_is_read=False).update({'n_is_read': True})
    db.session.commit()
    flash("Все уведомления отмечены как прочитанные", 'success')
    return redirect("/notifications")

@app.route('/create', methods=["GET", "POST"])
@login_required
def create():
    if request.method == "GET":
        return render_template("create.html")
    test_name = request.form.get('test_name')
    test_description = request.form.get('test_description')
    
    # Проверка на допустимые символы в названии
    if not validate_test_name(test_name):
        flash("Название теста содержит недопустимые символы! Разрешены только русские и английские буквы, цифры, пробелы, дефис и подчеркивание.", 'danger')
        return redirect("/create")
    
    test = Tests.query.filter_by(test_name=test_name).first()
    if test:
        flash("Тест с таким названием уже существует, выберите другое!", 'warning')
        return redirect("/create")
    image_filename = None
    if 'test_image' in request.files:
        file = request.files['test_image']

        # Если файл выбран и проходит проверку
        if file and file.filename != '' and allowed_file(file.filename):
            # Генерируем уникальное имя, чтобы файлы не перезаписывались

            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"

            # Сохраняем в static/img/
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect("/create")
    test = Tests(test_name=test_name, test_description=test_description, test_status=0, test_id_creator=current_user.id, test_image=image_filename)
    db.session.add(test)
    db.session.commit()
    # После создания теста переходим к выбору типа следующего вопроса
    return redirect("/createq_0")


@app.route('/createq_0', methods=["GET", "POST"])
@login_required
def createq_0():
    """Выбор типа вопроса для текущего теста."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_0.html", current_test=current_test)

    # POST: пользователь выбрал тип вопроса
    try:
        question_type = int(request.form.get("question_type", "1"))
    except ValueError:
        question_type = 1

    # Проверяем чекбокс "добавить картинку"
    add_image = bool(request.form.get("add_image"))

    # Определяем финальный тип вопроса
    if add_image:
        # Если выбрано добавить картинку, используем типы x.1 (11, 21, 31)
        final_type = question_type * 10 + 1
    else:
        # Обычные типы (1, 2, 3)
        final_type = question_type

    # Перенаправляем на соответствующий маршрут
    if final_type == 1:
        return redirect("/createq_1")
    elif final_type == 2:
        return redirect("/createq_2")
    elif final_type == 3:
        return redirect("/createq_3")
    elif final_type == 11:
        return redirect("/createq_11")
    elif final_type == 21:
        return redirect("/createq_21")
    elif final_type == 31:
        return redirect("/createq_31")
    else:
        flash("Выберите корректный тип вопроса.", "warning")
        return redirect("/createq_0")

@app.route('/createq_3', methods=["GET", "POST"])
@login_required
def createq_3():
    """Создание вопроса типа 3 — ручной ввод ответа."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_3.html", current_test=current_test)

    # POST: создаём вопрос с первым правильным ответом
    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()

    if not test_q:
        flash("Введите текст вопроса!", 'warning')
        return redirect("/createq_3")

    if not test_a:
        flash("Введите хотя бы один правильный ответ!", 'warning')
        return redirect("/createq_3")

    # Создаём вопрос типа 3
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=3,
        test_q_status=0
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём первый правильный ответ (все ответы для типа 3 правильные)
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True
    )
    db.session.add(test_answer)
    db.session.commit()

    flash("Вопрос создан. Можете добавить дополнительные правильные ответы.", 'success')
    return redirect("/createnext")


@app.route('/createq_11', methods=["GET", "POST"])
@login_required
def createq_11():
    """Создание вопроса типа 11 — выбор одного ответа с изображением."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_11.html", current_test=current_test)

    # POST: создаём вопрос с первым ответом и изображением
    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()

    if not test_q:
        flash("Введите текст вопроса!", 'warning')
        return redirect("/createq_11")

    if not test_a:
        flash("Введите текст ответа!", 'warning')
        return redirect("/createq_11")

    # Обработка изображения (идентично функции create)
    image_filename = None
    if 'test_q_image' in request.files:
        file = request.files['test_q_image']

        # Если файл выбран и проходит проверку
        if file and file.filename != '' and allowed_file(file.filename):
            # Генерируем уникальное имя, чтобы файлы не перезаписывались
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"

            # Сохраняем в static/img/
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect("/createq_11")

    # Создаём вопрос типа 11 с изображением
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=11,
        test_q_status=0,
        test_q_image=image_filename
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём первый ответ (правильный для типа 11)
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True
    )
    db.session.add(test_answer)
    db.session.commit()

    flash("Вопрос с изображением создан!", 'success')
    return redirect("/createnext")


@app.route('/createq_21', methods=["GET", "POST"])
@login_required
def createq_21():
    """Создание вопроса типа 21 — выбор нескольких ответов с изображением."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_21.html", current_test=current_test)

    # POST: создаём вопрос с первым ответом и изображением
    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()

    if not test_q:
        flash("Введите текст вопроса!", 'warning')
        return redirect("/createq_21")

    if not test_a:
        flash("Введите текст ответа!", 'warning')
        return redirect("/createq_21")

    # Обработка изображения (идентично функции create)
    image_filename = None
    if 'test_q_image' in request.files:
        file = request.files['test_q_image']

        # Если файл выбран и проходит проверку
        if file and file.filename != '' and allowed_file(file.filename):
            # Генерируем уникальное имя, чтобы файлы не перезаписывались
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"

            # Сохраняем в static/img/
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect("/createq_21")

    # Создаём вопрос типа 21 с изображением
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=21,
        test_q_status=0,
        test_q_image=image_filename
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём первый ответ (правильный для типа 21)
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True
    )
    db.session.add(test_answer)
    db.session.commit()

    flash("Вопрос с изображением создан. Теперь добавьте варианты ответов.", 'success')
    return redirect("/createnext")


@app.route('/createq_31', methods=["GET", "POST"])
@login_required
def createq_31():
    """Создание вопроса типа 31 — ручной ввод ответа с изображением."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_31.html", current_test=current_test)

    # POST: создаём вопрос с первым правильным ответом и изображением
    test_q = (request.form.get('test_question') or "").strip()
    test_a = (request.form.get('test_answer') or "").strip()

    if not test_q:
        flash("Введите текст вопроса!", 'warning')
        return redirect("/createq_31")

    if not test_a:
        flash("Введите хотя бы один правильный ответ!", 'warning')
        return redirect("/createq_31")

    # Обработка изображения (идентично функции create)
    image_filename = None
    if 'test_q_image' in request.files:
        file = request.files['test_q_image']

        # Если файл выбран и проходит проверку
        if file and file.filename != '' and allowed_file(file.filename):
            # Генерируем уникальное имя, чтобы файлы не перезаписывались
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"

            # Сохраняем в static/img/
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect("/createq_31")

    # Создаём вопрос типа 31 с изображением
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=31,
        test_q_status=0,
        test_q_image=image_filename
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём первый правильный ответ (все ответы для типа 31 правильные)
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True
    )
    db.session.add(test_answer)
    db.session.commit()

    flash("Вопрос с изображением создан. Можете добавить дополнительные правильные ответы.", 'success')
    return redirect("/createnext")


@app.route('/tests')
def tests():
    all_tests = Tests.query.filter_by(test_status=2).all()
    return render_template("tests.html", tests=all_tests)

@app.route('/test/<test_name>')
def view_test(test_name):
    """Информационная страница теста перед прохождением."""
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Подсчитываем количество вопросов
    questions_count = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).count()
    
    # Вычисляем среднюю оценку теста
    scores = Test_scores.query.filter_by(test_s_test_id=test.test_id).all()
    average_score = 0
    if scores:
        total_score = sum(score.test_s_score for score in scores)
        average_score = round(total_score / len(scores), 1)
    
    # Проверяем, оценивал ли текущий пользователь этот тест
    user_score = None
    if current_user.is_authenticated:
        user_score = Test_scores.query.filter_by(
            test_s_user_id=current_user.id,
            test_s_test_id=test.test_id
        ).first()
    
    return render_template("test_info.html", test=test, questions_count=questions_count, 
                         average_score=average_score, scores_count=len(scores), user_score=user_score)

@app.route('/test/<test_name>/start')
@login_required
def start_test(test_name):
    """Начало прохождения теста."""
    # Проверяем, не проходит ли пользователь уже другой тест
    if current_user.current_test_id is not None:
        current_test = Tests.query.get(current_user.current_test_id)
        if current_test:
            flash(f"Вы уже проходите тест '{current_test.test_name}'. Завершите его перед началом нового.", 'warning')
            return redirect(f"/test/{current_test.test_name}/take")
    
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Устанавливаем текущий тест для пользователя
    current_user.current_test_id = test.test_id
    db.session.commit()
    
    return redirect(f"/test/{test_name}/take")

@app.route('/test/<test_name>/take')
@login_required
def take_test(test_name):
    """Страница прохождения теста."""
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем, что пользователь проходит именно этот тест
    if current_user.current_test_id != test.test_id:
        flash("Вы не можете проходить этот тест!", 'danger')
        return redirect("/tests")
    
    # Получаем все вопросы теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).all()
    
    # Для каждого вопроса получаем ответы
    questions_with_answers = []
    for question in questions:
        answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id, test_a_status=2).all()
        questions_with_answers.append({
            'question': question,
            'answers': answers
        })
    
    return render_template("take_test.html", test=test, questions_with_answers=questions_with_answers)

@app.route('/test/<test_name>/submit', methods=["POST"])
@login_required
def submit_test(test_name):
    """Обработка отправки ответов на тест."""
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем, что пользователь проходит именно этот тест
    if current_user.current_test_id != test.test_id:
        flash("Вы не можете отправить ответы на этот тест!", 'danger')
        return redirect("/tests")
    
    # Получаем все вопросы теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).all()
    
    correct_answers = 0
    total_questions = len(questions)
    
    for question in questions:
        question_key = f"question_{question.test_q_id}"
        
        if question.test_q_type in [1, 11]:  # Один правильный ответ (с изображением или без)
            user_answer_id = request.form.get(question_key)
            if user_answer_id:
                answer = Tests_answers.query.get(int(user_answer_id))
                if answer and answer.test_a_is_correct:
                    correct_answers += 1
        
        elif question.test_q_type in [2, 21]:  # Несколько правильных ответов (с изображением или без)
            user_answer_ids = request.form.getlist(question_key)
            correct_answer_ids = [str(a.test_a_id) for a in Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).all()]
            
            if set(user_answer_ids) == set(correct_answer_ids):
                correct_answers += 1
        
        elif question.test_q_type in [3, 31]:  # Ручной ввод (с изображением или без)
            user_answer = (request.form.get(question_key) or "").strip().lower()
            correct_answers_list = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).all()
            
            # Проверяем, совпадает ли ответ с одним из правильных
            if any(user_answer == answer.test_a_text.strip().lower() for answer in correct_answers_list):
                correct_answers += 1
    
    # Вычисляем процент правильных ответов
    percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    
    # Сохраняем результат в сессии для отображения на странице результатов
    session['test_result'] = {
        'test_name': test_name,
        'test_id': test.test_id,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'percentage': percentage
    }
    
    return redirect(f"/test/{test_name}/result")

@app.route('/test/<test_name>/result')
@login_required
def test_result(test_name):
    """Страница результатов теста с обязательной оценкой."""
    # Проверяем, есть ли результат в сессии
    if 'test_result' not in session:
        flash("Результат теста не найден!", 'danger')
        return redirect("/tests")
    
    result = session['test_result']
    
    # Проверяем, что результат для правильного теста
    if result['test_name'] != test_name:
        flash("Неверный результат теста!", 'danger')
        return redirect("/tests")
    
    test = Tests.query.get(result['test_id'])
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем, есть ли уже оценка от этого пользователя
    existing_score = Test_scores.query.filter_by(
        test_s_user_id=current_user.id,
        test_s_test_id=result['test_id']
    ).first()
    
    # Устанавливаем флаг, что пользователь должен оценить тест
    session['must_rate_test'] = True
    
    return render_template("test_result.html", test=test, result=result, existing_score=existing_score)

@app.route('/test/<test_name>/rate', methods=["POST"])
@login_required
def rate_test(test_name):
    """Обработка оценки теста пользователем."""
    # Проверяем, есть ли результат в сессии
    if 'test_result' not in session:
        flash("Результат теста не найден!", 'danger')
        return redirect("/tests")
    
    result = session['test_result']
    
    # Проверяем, что результат для правильного теста
    if result['test_name'] != test_name:
        flash("Неверный результат теста!", 'danger')
        return redirect("/tests")
    
    try:
        score = int(request.form.get('score', 0))
        if score < 1 or score > 5:
            flash("Оценка должна быть от 1 до 5!", 'danger')
            return redirect(f"/test/{test_name}/result")
    except ValueError:
        flash("Неверная оценка!", 'danger')
        return redirect(f"/test/{test_name}/result")
    
    # Проверяем, есть ли уже оценка от этого пользователя для этого теста
    existing_score = Test_scores.query.filter_by(
        test_s_user_id=current_user.id,
        test_s_test_id=result['test_id']
    ).first()
    
    if existing_score:
        # Обновляем существующую оценку
        existing_score.test_s_score = score
        flash_message = f"Ваша оценка обновлена! Результат: {result['correct_answers']} из {result['total_questions']} ({result['percentage']:.1f}%)"
    else:
        # Создаем новую оценку
        test_score = Test_scores(
            test_s_user_id=current_user.id,
            test_s_test_id=result['test_id'],
            test_s_score=score
        )
        db.session.add(test_score)
        flash_message = f"Спасибо за оценку! Ваш результат: {result['correct_answers']} из {result['total_questions']} ({result['percentage']:.1f}%)"
    
    # Очищаем current_test_id у пользователя
    current_user.current_test_id = None
    db.session.commit()
    
    # Очищаем результат из сессии и флаг обязательной оценки
    session.pop('test_result', None)
    session.pop('must_rate_test', None)
    
    flash(flash_message, 'success')
    return redirect("/tests")
    
    correct_answers = 0
    total_questions = len(questions)
    
    for question in questions:
        question_key = f"question_{question.test_q_id}"
        
        if question.test_q_type in [1, 11]:  # Один правильный ответ (с изображением или без)
            user_answer_id = request.form.get(question_key)
            if user_answer_id:
                answer = Tests_answers.query.get(int(user_answer_id))
                if answer and answer.test_a_is_correct:
                    correct_answers += 1
        
        elif question.test_q_type in [2, 21]:  # Несколько правильных ответов (с изображением или без)
            user_answer_ids = request.form.getlist(question_key)
            correct_answer_ids = [str(a.test_a_id) for a in Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).all()]
            
            if set(user_answer_ids) == set(correct_answer_ids):
                correct_answers += 1
        
        elif question.test_q_type in [3, 31]:  # Ручной ввод (с изображением или без)
            user_answer = (request.form.get(question_key) or "").strip().lower()
            correct_answers_list = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).all()
            
            # Проверяем, совпадает ли ответ с одним из правильных
            if any(user_answer == answer.test_a_text.strip().lower() for answer in correct_answers_list):
                correct_answers += 1
    
    # Вычисляем процент правильных ответов
    percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    
    flash(f"Тест завершен! Правильных ответов: {correct_answers} из {total_questions} ({percentage:.1f}%)", 'success')
    return redirect(f"/test/{test_name}")


@app.route('/createq_1', methods=["GET", "POST"])  # ✅ Добавили POST
@login_required
def createq():
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        # Тип 1: выбор одного ответа из нескольких вариантов
        return render_template("createq_1.html", current_test=current_test)

    # ✅ POST-обработка
    test_q = request.form.get('test_question')
    test_a = request.form.get('test_answer')

    if not test_q or not test_a:
        flash("Заполните вопрос и ответ!", 'warning')
        return redirect("/createq")

    # Создаём вопрос
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=1,
        test_q_status=0
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём ответ
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=1
    )
    db.session.add(test_answer)
    db.session.commit()

    flash("Вопрос и ответ добавлены!", 'success')
    return redirect("/createnext")


@app.route('/createq_2', methods=["GET", "POST"])
@login_required
def createq_2():
    """Создание вопроса типа 2 — выбор нескольких ответов."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Сначала создайте тест!", 'warning')
        return redirect("/create")

    if request.method == "GET":
        return render_template("createq_2.html", current_test=current_test)

    # POST: создаём вопрос без вариантов ответа
    test_q = (request.form.get('test_question') or "").strip()

    if not test_q:
        flash("Введите текст вопроса!", 'warning')
        return redirect("/createq_2")

    test_a = request.form.get('test_answer')

    # Создаём вопрос
    test_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_text=test_q,
        test_q_test_id=current_test.test_id,
        test_q_type=2,
        test_q_status=0
    )
    db.session.add(test_question)
    db.session.commit()

    # Создаём ответ
    test_answer = Tests_answers(
        test_a_text=test_a,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=test_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=1
    )
    db.session.add(test_answer)
    db.session.commit()


    flash("Вопрос создан. Теперь добавьте варианты ответов.", 'success')
    return redirect("/createnext")


@app.route('/createnext')
@login_required
def createnext():
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден или уже завершён!", 'warning')
        return redirect("/tests")

    # ✅ Получаем последний созданный вопрос ТОЛЬКО для текущего теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        # Нет ни одного вопроса — можно создавать первый, но пока блокируем переход дальше
        return render_template(
            "createnext.html",
            current_test=current_test,
            last_question=None,
            are_2_questions=False
        )

    # ✅ Считаем количество ответов для последнего вопроса текущего теста
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )
@app.route('/addanswer', methods=["GET", "POST"])
@login_required
def addanswer():
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # ✅ Получаем последний вопрос ТОЛЬКО этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 1:
        flash("Добавление ответов через эту страницу доступно только для вопросов типа 'выбор одного ответа'.", 'warning')
        return redirect("/createnext")

    # ✅ Считаем количество ответов для этого вопроса
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    are_2_questions = answers_count >= 2

    if request.method == "GET":
        return render_template(
            "addanswer_1.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем ответ
    answer_text = request.form.get('answer_text')
    # Чекбокс даёт либо "on", либо None — приводим к bool
    is_correct = bool(request.form.get('is_correct'))

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=is_correct
    )
    db.session.add(test_answer)
    db.session.commit()

    # После добавления ответа пересчитаем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Ответ добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/addanswer_2', methods=["GET", "POST"])
@login_required
def addanswer_2():
    """Добавление вариантов ответа для вопросов типа 2 (несколько правильных ответов)."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # Берём последний вопрос этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 2:
        flash("Эта страница предназначена только для вопросов с выбором нескольких ответов.", 'warning')
        return redirect("/createnext")

    # Считаем количество уже существующих ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    are_2_questions = answers_count >= 2

    if request.method == "GET":
        return render_template(
            "addanswer_2.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем новый вариант ответа
    answer_text = (request.form.get('answer_text') or "").strip()
    is_correct = bool(request.form.get('is_correct'))

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer_2")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=is_correct
    )
    db.session.add(test_answer)
    db.session.commit()

    # Пересчитываем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Вариант ответа добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/addanswer_3', methods=["GET", "POST"])
@login_required
def addanswer_3():
    """Добавление правильных ответов для вопросов типа 3 (ручной ввод)."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # Берём последний вопрос этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 3:
        flash("Эта страница предназначена только для вопросов с ручным вводом ответа.", 'warning')
        return redirect("/createnext")

    # Считаем количество уже существующих ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    are_2_questions = answers_count >= 2

    if request.method == "GET":
        return render_template(
            "addanswer_3.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем новый правильный ответ (все ответы для типа 3 правильные)
    answer_text = (request.form.get('answer_text') or "").strip()

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer_3")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True  # Все ответы для типа 3 правильные
    )
    db.session.add(test_answer)
    db.session.commit()

    # Пересчитываем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Правильный ответ добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/finish-test', methods=["GET", "POST"])
@login_required
def finish_test():
    """Завершает создание теста: меняет статус на 1 у теста, вопросов и ответов."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден или уже завершён!", 'warning')
        return redirect("/tests")

    # ✅ Проверяем, есть ли хотя бы один вопрос
    questions_count = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).count()

    if questions_count == 0:
        flash("Нельзя завершить тест без вопросов!", 'danger')
        return redirect("/createnext")

    # ✅ Меняем статус теста на "готов" (1)
    current_test.test_status = 1

    # ✅ Меняем статус у ВСЕХ вопросов этого теста
    questions = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).all()
    for question in questions:
        question.test_q_status = 1

    # ✅ Меняем статус у ВСЕХ ответов этого теста
    answers = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id
    ).all()
    for answer in answers:
        answer.test_a_status = 1

    db.session.commit()

    flash("Тест отправлен на проверку модераторам!", 'success')
    return redirect("/tests")

@app.route('/delete-test', methods=["GET", "POST"])
@login_required
def delete_test():
    """Удаляет текущий тест со всеми вопросами и ответами."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден или уже завершён!", 'warning')
        return redirect("/tests")

    # ✅ Получаем все вопросы этого теста
    questions = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).all()

    # ✅ Удаляем все ответы, связанные с вопросами этого теста
    for question in questions:
        Tests_answers.query.filter_by(
            test_a_question_id=question.test_q_id
        ).delete()

    # ✅ Удаляем изображения вопросов (если есть)
    for question in questions:
        if question.test_q_image:
            try:
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], question.test_q_image)
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as e:
                print(f"Ошибка при удалении изображения вопроса: {e}")

    # ✅ Удаляем все вопросы этого теста
    for question in questions:
        db.session.delete(question)

    # ✅ Удаляем изображение теста (если есть)
    if current_test.test_image:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], current_test.test_image)
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception as e:
            print(f"Ошибка при удалении изображения: {e}")

    # ✅ Удаляем сам тест
    db.session.delete(current_test)
    db.session.commit()

    flash("Тест успешно удалён!", 'success')
    return redirect("/tests")

@app.route('/moderator_1')
@login_required
def moderator_1():
    """Страница модератора - доступна при admin >= 1."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    return render_template("moderator_1.html")

@app.route('/moderator_2')
@login_required
def moderator_2():
    """Страница с тестами на проверке - доступна при admin >= 1."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    # Показываем тесты со статусом 1 (на проверке)
    pending_tests = Tests.query.filter_by(test_status=1).all()
    return render_template("moderator_2.html", tests=pending_tests)

@app.route('/moderator/manage')
@login_required
def moderator_manage_tests():
    """Страница управления всеми тестами - доступна при admin >= 1."""
    if current_user.admin <= 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    # Показываем все тесты (кроме тех, что в разработке)
    all_tests = Tests.query.filter(Tests.test_status.in_([1, 2])).all()
    return render_template("moderator_manage.html", tests=all_tests)

@app.route('/moderator/review/<test_name>')
@login_required
def moderator_review_test(test_name):
    """Просмотр теста модератором для проверки."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")
    
    # Получаем все вопросы теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=1).all()
    
    # Для каждого вопроса получаем ответы
    questions_with_answers = []
    for question in questions:
        answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id, test_a_status=1).all()
        questions_with_answers.append({
            'question': question,
            'answers': answers
        })
    
    return render_template("moderator_review_test.html", test=test, questions_with_answers=questions_with_answers)

@app.route('/moderator/approve/<test_name>', methods=["POST"])
@login_required
def moderator_approve_test(test_name):
    """Одобрение теста модератором - меняет статус на 2."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")
    
    # Меняем статус теста на 2 (опубликован)
    test.test_status = 2
    
    # Меняем статус у всех вопросов этого теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=1).all()
    for question in questions:
        question.test_q_status = 2
    
    # Меняем статус у всех ответов этого теста
    answers = Tests_answers.query.filter_by(test_a_test_id=test.test_id, test_a_status=1).all()
    for answer in answers:
        answer.test_a_status = 2
    
    # Создаем уведомление для автора теста
    _create_notification(
        user_id=test.test_id_creator,
        sender_id=current_user.id,
        text=f"Модератор {current_user.username} одобрил ваш тест \"{test.test_name}\"! Тест опубликован.",
        link=f"/test-info/{test.test_name}"
    )
    
    db.session.commit()
    
    flash(f"Тест '{test_name}' успешно одобрен и опубликован!", 'success')
    return redirect("/moderator_2")

@app.route('/moderator/delete/<test_name>', methods=["POST"])
@login_required
def moderator_delete_test(test_name):
    """Удаление теста модератором."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    
    test = Tests.query.filter_by(test_name=test_name, test_status=1).first()
    if not test:
        flash("Тест не найден или уже проверен!", 'danger')
        return redirect("/moderator_2")
    
    # Получаем все вопросы этого теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    
    # Удаляем все ответы
    for question in questions:
        Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).delete()
    
    # Удаляем изображения вопросов
    for question in questions:
        if question.test_q_image:
            try:
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], question.test_q_image)
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as e:
                print(f"Ошибка при удалении изображения вопроса: {e}")
    
    # Удаляем все вопросы
    for question in questions:
        db.session.delete(question)
    
    # Удаляем изображение теста
    if test.test_image:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], test.test_image)
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception as e:
            print(f"Ошибка при удалении изображения теста: {e}")
    
    # Удаляем сам тест
    db.session.delete(test)
    db.session.commit()
    
    flash(f"Тест '{test_name}' успешно удалён!", 'success')
    return redirect("/moderator_2")

@app.route('/moderator/delete-any/<test_name>', methods=["POST"])
@login_required
def moderator_delete_any_test(test_name):
    """Удаление любого теста модератором (из управления тестами)."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2])).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator/manage")
    
    # Получаем все вопросы этого теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    
    # Удаляем все ответы
    for question in questions:
        Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).delete()
    
    # Удаляем все оценки теста
    Test_scores.query.filter_by(test_s_test_id=test.test_id).delete()
    
    # Удаляем изображения вопросов
    for question in questions:
        if question.test_q_image:
            try:
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], question.test_q_image)
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as e:
                print(f"Ошибка при удалении изображения вопроса: {e}")
    
    # Удаляем все вопросы
    for question in questions:
        db.session.delete(question)
    
    # Удаляем изображение теста
    if test.test_image:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], test.test_image)
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception as e:
            print(f"Ошибка при удалении изображения теста: {e}")
    
    # Удаляем сам тест
    db.session.delete(test)
    db.session.commit()
    
    flash(f"Тест '{test_name}' успешно удалён!", 'success')
    return redirect("/moderator/manage")

@app.route('/moderator/view/<test_name>')
@login_required
def moderator_view_test(test_name):
    """Просмотр любого теста модератором для управления."""
    if current_user.admin < 1:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    
    test = Tests.query.filter_by(test_name=test_name).filter(Tests.test_status.in_([1, 2])).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/moderator/manage")
    
    # Получаем все вопросы теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    
    # Для каждого вопроса получаем ответы
    questions_with_answers = []
    for question in questions:
        answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).all()
        questions_with_answers.append({
            'question': question,
            'answers': answers
        })
    
    return render_template("moderator_view_test.html", test=test, questions_with_answers=questions_with_answers)

@app.route('/edit-test/<int:test_id>')
@login_required
def edit_test(test_id):
    """Страница редактирования теста."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа: владелец или модератор
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого теста!", 'danger')
        return redirect("/tests")
    
    # Получаем комментарии модераторов к тесту
    comments = TestComments.query.filter_by(tc_test_id=test.test_id).order_by(TestComments.tc_created_at.desc()).all()
    
    return render_template("edit_test.html", test=test, comments=comments)

@app.route('/edit-test/<int:test_id>/update', methods=["POST"])
@login_required
def update_test(test_id):
    """Обновление информации о тесте."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого теста!", 'danger')
        return redirect("/tests")
    
    test_name = request.form.get('test_name')
    test_description = request.form.get('test_description')
    
    # Проверка на допустимые символы в названии
    if not validate_test_name(test_name):
        flash("Название теста содержит недопустимые символы! Разрешены только русские и английские буквы, цифры, пробелы, дефис и подчеркивание.", 'danger')
        return redirect(f"/edit-test/{test_id}")
    
    # Проверяем, не занято ли новое название другим тестом
    if test_name != test.test_name:
        existing_test = Tests.query.filter_by(test_name=test_name).first()
        if existing_test:
            flash("Тест с таким названием уже существует!", 'danger')
            return redirect(f"/edit-test/{test_id}")
    
    # Обработка изображения
    if 'test_image' in request.files:
        file = request.files['test_image']
        if file and file.filename != '' and allowed_file(file.filename):
            # Удаляем старое изображение
            if test.test_image:
                try:
                    old_img_path = os.path.join(app.config['UPLOAD_FOLDER'], test.test_image)
                    if os.path.exists(old_img_path):
                        os.remove(old_img_path)
                except Exception as e:
                    print(f"Ошибка при удалении старого изображения: {e}")
            
            # Сохраняем новое изображение
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            test.test_image = image_filename
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect(f"/edit-test/{test_id}")
    
    # Обновляем данные теста
    test.test_name = test_name
    test.test_description = test_description
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        comment = request.form.get('moderator_comment', '').strip()
        notification_text = f"Модератор {current_user.username} отредактировал ваш тест '{test.test_name}'"
        if comment:
            notification_text += f". Комментарий: {comment}"
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-test/{test.test_id}"
        )
        # Сохраняем комментарий если есть
        if comment:
            test_comment = TestComments(
                tc_test_id=test.test_id,
                tc_user_id=current_user.id,
                tc_comment=comment
            )
            db.session.add(test_comment)
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    db.session.commit()
    
    if was_published:
        flash("Информация о тесте обновлена! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Информация о тесте обновлена!", 'success')
    return redirect(f"/edit-test/{test_id}")

@app.route('/edit-test/<int:test_id>/questions')
@login_required
def edit_test_questions(test_id):
    """Страница редактирования вопросов теста."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого теста!", 'danger')
        return redirect("/tests")
    
    # Получаем все вопросы теста
    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id).all()
    
    # Для каждого вопроса получаем ответы
    questions_with_answers = []
    for question in questions:
        answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).all()
        questions_with_answers.append({
            'question': question,
            'answers': answers
        })
    
    return render_template("edit_test_questions.html", test=test, questions_with_answers=questions_with_answers)

@app.route('/edit-question/<int:question_id>')
@login_required
def edit_question(question_id):
    """Страница редактирования вопроса."""
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    
    test = Tests.query.get(question.test_q_test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого вопроса!", 'danger')
        return redirect("/tests")
    
    # Получаем ответы на вопрос
    answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).all()
    
    return render_template("edit_question.html", test=test, question=question, answers=answers)

@app.route('/edit-question/<int:question_id>/update', methods=["POST"])
@login_required
def update_question(question_id):
    """Обновление вопроса."""
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    
    test = Tests.query.get(question.test_q_test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого вопроса!", 'danger')
        return redirect("/tests")
    
    question_text = request.form.get('question_text')
    
    # Обработка изображения вопроса
    if 'question_image' in request.files:
        file = request.files['question_image']
        if file and file.filename != '' and allowed_file(file.filename):
            # Удаляем старое изображение
            if question.test_q_image:
                try:
                    old_img_path = os.path.join(app.config['UPLOAD_FOLDER'], question.test_q_image)
                    if os.path.exists(old_img_path):
                        os.remove(old_img_path)
                except Exception as e:
                    print(f"Ошибка при удалении старого изображения: {e}")
            
            # Сохраняем новое изображение
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            question.test_q_image = image_filename
        elif file.filename != '':
            flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
            return redirect(f"/edit-question/{question_id}")
    
    # Обновляем текст вопроса
    question.test_q_text = question_text
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        moderator_comment = request.form.get('moderator_comment', '').strip()
        notification_text = f"Модератор {current_user.username} отредактировал вопрос в вашем тесте \"{test.test_name}\""
        if moderator_comment:
            notification_text += f": {moderator_comment}"
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-question/{question_id}"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Вопрос обновлен! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Вопрос обновлен!", 'success')
    return redirect(f"/edit-question/{question_id}")

@app.route('/edit-answer/<int:answer_id>/update', methods=["POST"])
@login_required
def update_answer(answer_id):
    """Обновление ответа с проверкой минимального количества правильных ответов."""
    answer = Tests_answers.query.get(answer_id)
    if not answer:
        flash("Ответ не найден!", 'danger')
        return redirect("/tests")
    
    question = Tests_questions.query.get(answer.test_a_question_id)
    test = Tests.query.get(answer.test_a_test_id)
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для редактирования этого ответа!", 'danger')
        return redirect("/tests")
    
    answer_text = request.form.get('answer_text')
    is_correct = bool(request.form.get('is_correct'))
    
    # Для типов 1, 2, 11, 21 - проверяем, что не убираем последний правильный ответ
    if question.test_q_type in [1, 2, 11, 21]:
        if answer.test_a_is_correct and not is_correct:
            # Проверяем, есть ли другие правильные ответы
            correct_answers_count = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).count()
            
            if correct_answers_count <= 1:
                flash("Нельзя убрать правильность с последнего правильного ответа! Должен быть хотя бы один правильный вариант.", 'danger')
                return redirect(f"/edit-question/{question.test_q_id}")
    
    # Обновляем ответ
    answer.test_a_text = answer_text
    answer.test_a_is_correct = is_correct
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        moderator_comment = request.form.get('moderator_comment', '').strip()
        notification_text = f"Модератор {current_user.username} отредактировал ответ в вашем тесте \"{test.test_name}\""
        if moderator_comment:
            notification_text += f": {moderator_comment}"
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-question/{question.test_q_id}"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Ответ обновлен! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Ответ обновлен!", 'success')
    return redirect(f"/edit-question/{question.test_q_id}")

@app.route('/delete-question/<int:question_id>', methods=["POST"])
@login_required
def delete_question(question_id):
    """Удаление вопроса."""
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    
    test = Tests.query.get(question.test_q_test_id)
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для удаления этого вопроса!", 'danger')
        return redirect("/tests")
    
    # Удаляем все ответы на вопрос
    Tests_answers.query.filter_by(test_a_question_id=question_id).delete()
    
    # Удаляем изображение вопроса
    if question.test_q_image:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], question.test_q_image)
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception as e:
            print(f"Ошибка при удалении изображения: {e}")
    
    # Удаляем вопрос
    db.session.delete(question)
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        notification_text = f"Модератор {current_user.username} удалил вопрос в вашем тесте \"{test.test_name}\""
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-test/{test.test_id}/questions"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Вопрос удален! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Вопрос удален!", 'success')
    return redirect(f"/edit-test/{test.test_id}/questions")

@app.route('/delete-answer/<int:answer_id>', methods=["POST"])
@login_required
def delete_answer(answer_id):
    """Удаление ответа с проверкой минимального количества."""
    answer = Tests_answers.query.get(answer_id)
    if not answer:
        flash("Ответ не найден!", 'danger')
        return redirect("/tests")
    
    question = Tests_questions.query.get(answer.test_a_question_id)
    test = Tests.query.get(answer.test_a_test_id)
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для удаления этого ответа!", 'danger')
        return redirect("/tests")
    
    # Подсчитываем количество ответов на вопрос
    total_answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id).count()
    
    # Для типов 1, 2, 11, 21 - нельзя удалить если останется меньше 2 ответов
    if question.test_q_type in [1, 2, 11, 21]:
        if total_answers <= 2:
            flash("Нельзя удалить ответ! Должно быть минимум 2 варианта ответа.", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")
        
        # Нельзя удалить последний правильный ответ
        if answer.test_a_is_correct:
            correct_answers_count = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id,
                test_a_is_correct=True
            ).count()
            
            if correct_answers_count <= 1:
                flash("Нельзя удалить последний правильный ответ! Должен быть хотя бы один правильный вариант.", 'danger')
                return redirect(f"/edit-question/{question.test_q_id}")
    
    # Для типов 3, 31 - нельзя удалить если это последний ответ
    elif question.test_q_type in [3, 31]:
        if total_answers <= 1:
            flash("Нельзя удалить последний ответ! Должен быть хотя бы один правильный вариант ответа.", 'danger')
            return redirect(f"/edit-question/{question.test_q_id}")
    
    # Удаляем ответ
    db.session.delete(answer)
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        notification_text = f"Модератор {current_user.username} удалил ответ в вашем тесте \"{test.test_name}\""
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-question/{question.test_q_id}"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Ответ удален! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Ответ удален!", 'success')
    return redirect(f"/edit-question/{question.test_q_id}")

@app.route('/add-question/<int:test_id>')
@login_required
def add_question(test_id):
    """Страница выбора типа нового вопроса."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для добавления вопросов в этот тест!", 'danger')
        return redirect("/tests")
    
    return render_template("add_question_type.html", test=test)

@app.route('/add-question/<int:test_id>/create', methods=["POST"])
@login_required
def create_question(test_id):
    """Создание нового вопроса."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для добавления вопросов в этот тест!", 'danger')
        return redirect("/tests")
    
    question_type = int(request.form.get('question_type', 1))
    question_text = request.form.get('question_text')
    
    if not question_text:
        flash("Введите текст вопроса!", 'danger')
        return redirect(f"/add-question/{test_id}")
    
    # Обработка изображения для типов 11, 21, 31
    image_filename = None
    if question_type in [11, 21, 31]:
        if 'question_image' in request.files:
            file = request.files['question_image']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                image_filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            elif file.filename != '':
                flash("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, gif, webp", "danger")
                return redirect(f"/add-question/{test_id}")
    
    # Создаем вопрос
    new_question = Tests_questions(
        test_q_creator_id=current_user.id,
        test_q_test_id=test_id,
        test_q_text=question_text,
        test_q_type=question_type,
        test_q_status=test.test_status,  # Наследуем статус теста
        test_q_image=image_filename
    )
    db.session.add(new_question)
    db.session.commit()
    
    # Создаем минимальные ответы в зависимости от типа
    if question_type in [1, 2, 11, 21]:
        # Для типов с вариантами - создаем 2 пустых ответа
        answer1_text = request.form.get('answer1_text', 'Вариант 1')
        answer2_text = request.form.get('answer2_text', 'Вариант 2')
        is_correct1 = bool(request.form.get('is_correct1'))
        is_correct2 = bool(request.form.get('is_correct2'))
        
        # Проверяем, что хотя бы один ответ правильный
        if not is_correct1 and not is_correct2:
            is_correct1 = True  # Делаем первый ответ правильным по умолчанию
        
        answer1 = Tests_answers(
            test_a_creator_id=current_user.id,
            test_a_test_id=test_id,
            test_a_question_id=new_question.test_q_id,
            test_a_text=answer1_text,
            test_a_status=test.test_status,
            test_a_is_correct=is_correct1
        )
        answer2 = Tests_answers(
            test_a_creator_id=current_user.id,
            test_a_test_id=test_id,
            test_a_question_id=new_question.test_q_id,
            test_a_text=answer2_text,
            test_a_status=test.test_status,
            test_a_is_correct=is_correct2
        )
        db.session.add(answer1)
        db.session.add(answer2)
    
    elif question_type in [3, 31]:
        # Для типов с ручным вводом - создаем 1 правильный ответ
        answer_text = request.form.get('answer_text', 'Правильный ответ')
        
        answer = Tests_answers(
            test_a_creator_id=current_user.id,
            test_a_test_id=test_id,
            test_a_question_id=new_question.test_q_id,
            test_a_text=answer_text,
            test_a_status=test.test_status,
            test_a_is_correct=True
        )
        db.session.add(answer)
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        notification_text = f"Модератор {current_user.username} добавил новый вопрос в ваш тест \"{test.test_name}\""
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-question/{new_question.test_q_id}"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Вопрос создан! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Вопрос создан! Теперь вы можете отредактировать его.", 'success')
    return redirect(f"/edit-question/{new_question.test_q_id}")

@app.route('/add-answer/<int:question_id>', methods=["POST"])
@login_required
def add_answer(question_id):
    """Добавление нового ответа к вопросу."""
    question = Tests_questions.query.get(question_id)
    if not question:
        flash("Вопрос не найден!", 'danger')
        return redirect("/tests")
    
    test = Tests.query.get(question.test_q_test_id)
    
    # Проверяем права доступа
    if test.test_id_creator != current_user.id and current_user.admin < 1:
        flash("У вас нет прав для добавления ответов!", 'danger')
        return redirect("/tests")
    
    answer_text = request.form.get('answer_text', 'Новый ответ')
    is_correct = bool(request.form.get('is_correct'))
    
    # Для типов 3 и 31 (ручной ввод) все ответы автоматически правильные
    if question.test_q_type in [3, 31]:
        is_correct = True
    
    # Создаем новый ответ
    new_answer = Tests_answers(
        test_a_creator_id=current_user.id,
        test_a_test_id=test.test_id,
        test_a_question_id=question_id,
        test_a_text=answer_text,
        test_a_status=question.test_q_status,
        test_a_is_correct=is_correct
    )
    db.session.add(new_answer)
    
    # Если тест был опубликован, переводим его на проверку
    was_published = _revert_test_to_review(test, current_user)
    
    # Если модератор редактирует чужой тест, создаем уведомление
    if current_user.admin >= 1 and test.test_id_creator != current_user.id:
        notification_text = f"Модератор {current_user.username} добавил новый ответ в ваш тест \"{test.test_name}\""
        _create_notification(
            user_id=test.test_id_creator,
            sender_id=current_user.id,
            text=notification_text,
            link=f"/edit-question/{question_id}"
        )
    
    db.session.commit()
    
    if was_published:
        flash("Ответ добавлен! Тест отправлен на повторную проверку модератором.", 'warning')
    else:
        flash("Ответ добавлен!", 'success')
    return redirect(f"/edit-question/{question_id}")

@app.route('/admin_1')
@app.route('/admin')
@login_required
def admin_1():
    """Главная панель администратора."""
    if current_user.admin < 2:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")
    return render_template("admin_1.html")


@app.route('/admin/users')
@login_required
def admin_users():
    """Список пользователей для администратора с поиском."""
    if current_user.admin < 2:
        flash("У вас нет доступа к этой странице!", 'danger')
        return redirect("/")

    q_id     = request.args.get('id', '').strip()
    q_name   = request.args.get('name', '').strip()
    q_email  = request.args.get('email', '').strip()
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


@app.route('/admin/user/<int:user_id>/update-name', methods=['POST'])
@login_required
def admin_update_username(user_id):
    """Изменение имени пользователя администратором."""
    if current_user.admin < 2:
        flash("У вас нет доступа!", 'danger')
        return redirect("/")

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

    notification_text = f"Администратор изменил ваше имя пользователя с \"{old_username}\" на \"{new_username}\"."
    if reason:
        notification_text += f" Причина: {reason}"

    _create_notification(
        user_id=user.id,
        sender_id=current_user.id,
        text=notification_text
    )

    db.session.commit()
    flash(f"Имя пользователя изменено на \"{new_username}\".", 'success')
    return redirect("/admin/users")


@app.route('/admin/user/<int:user_id>/update-status', methods=['POST'])
@login_required
def admin_update_status(user_id):
    """Изменение статуса (admin) пользователя администратором."""
    if current_user.admin < 2:
        flash("У вас нет доступа!", 'danger')
        return redirect("/")

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

    notification_text = (
        f"Администратор изменил ваш статус с \"{status_names[old_status]}\" "
        f"на \"{status_names[new_status]}\"."
    )
    if reason:
        notification_text += f" Причина: {reason}"

    _create_notification(
        user_id=user.id,
        sender_id=current_user.id,
        text=notification_text
    )

    db.session.commit()
    flash(f"Статус пользователя \"{user.username}\" изменён на \"{status_names[new_status]}\".", 'success')
    return redirect("/admin/users")


@app.route('/admin/messages', methods=['GET'])
@login_required
def admin_messages():
    """Страница отправки сообщений администратором."""
    if current_user.admin < 2:
        flash("У вас нет доступа!", 'danger')
        return redirect("/")
    users = User.query.order_by(User.username).all()
    return render_template("admin_messages.html", users=users)


@app.route('/admin/messages/send', methods=['POST'])
@login_required
def admin_send_message():
    """Отправка сообщения пользователям."""
    if current_user.admin < 2:
        flash("У вас нет доступа!", 'danger')
        return redirect("/")

    text = request.form.get('text', '').strip()
    link = request.form.get('link', '').strip() or None
    target = request.form.get('target')  # 'all', 'single', 'multiple'

    if not text:
        flash("Текст сообщения не может быть пустым!", 'danger')
        return redirect("/admin/messages")

    if target == 'all':
        recipients = User.query.all()
    elif target == 'single':
        user_id = request.form.get('user_id', '').strip()
        try:
            user = User.query.get(int(user_id))
        except (ValueError, TypeError):
            user = None
        if not user:
            flash("Пользователь не найден!", 'danger')
            return redirect("/admin/messages")
        recipients = [user]
    elif target == 'multiple':
        user_ids = request.form.getlist('user_ids')
        try:
            recipients = User.query.filter(User.id.in_([int(i) for i in user_ids])).all()
        except (ValueError, TypeError):
            recipients = []
        if not recipients:
            flash("Не выбрано ни одного пользователя!", 'danger')
            return redirect("/admin/messages")
    else:
        flash("Неверный тип получателей!", 'danger')
        return redirect("/admin/messages")

    for user in recipients:
        _create_notification(
            user_id=user.id,
            sender_id=current_user.id,
            text=text,
            link=link
        )

    db.session.commit()
    flash(f"Сообщение отправлено {len(recipients)} пользователю(-ям).", 'success')
    return redirect("/admin/messages")

@app.route('/addanswer_11', methods=["GET", "POST"])
@login_required
def addanswer_11():
    """Добавление ответов для вопросов типа 11 (выбор одного ответа с изображением)."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # Берём последний вопрос этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 11:
        flash("Эта страница предназначена только для вопросов с выбором одного ответа и изображением.", 'warning')
        return redirect("/createnext")

    if request.method == "GET":
        return render_template(
            "addanswer_11.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем ответ
    answer_text = request.form.get('answer_text')
    # Чекбокс даёт либо "on", либо None — приводим к bool
    is_correct = bool(request.form.get('is_correct'))

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer_11")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=is_correct
    )
    db.session.add(test_answer)
    db.session.commit()

    # После добавления ответа пересчитаем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Ответ добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/addanswer_21', methods=["GET", "POST"])
@login_required
def addanswer_21():
    """Добавление вариантов ответа для вопросов типа 21 (несколько правильных ответов с изображением)."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # Берём последний вопрос этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 21:
        flash("Эта страница предназначена только для вопросов с выбором нескольких ответов и изображением.", 'warning')
        return redirect("/createnext")

    if request.method == "GET":
        return render_template(
            "addanswer_21.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем новый вариант ответа
    answer_text = (request.form.get('answer_text') or "").strip()
    is_correct = bool(request.form.get('is_correct'))

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer_21")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=is_correct
    )
    db.session.add(test_answer)
    db.session.commit()

    # Пересчитываем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Вариант ответа добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/addanswer_31', methods=["GET", "POST"])
@login_required
def addanswer_31():
    """Добавление правильных ответов для вопросов типа 31 (ручной ввод с изображением)."""
    current_test = Tests.query.filter_by(
        test_id_creator=current_user.id,
        test_status=0
    ).first()

    if not current_test:
        flash("Тест не найден!", 'danger')
        return redirect("/create")

    # Берём последний вопрос этого теста
    last_question = Tests_questions.query.filter_by(
        test_q_test_id=current_test.test_id
    ).order_by(Tests_questions.test_q_id.desc()).first()

    if not last_question:
        flash("Сначала создайте вопрос!", 'warning')
        return redirect("/createq_0")

    if last_question.test_q_type != 31:
        flash("Эта страница предназначена только для вопросов с ручным вводом ответа и изображением.", 'warning')
        return redirect("/createnext")

    if request.method == "GET":
        return render_template(
            "addanswer_31.html",
            question=last_question,
            current_test=current_test
        )

    # POST: сохраняем новый правильный ответ (все ответы для типа 31 правильные)
    answer_text = (request.form.get('answer_text') or "").strip()

    if not answer_text:
        flash("Введите текст ответа!", 'warning')
        return redirect("/addanswer_31")

    test_answer = Tests_answers(
        test_a_text=answer_text,
        test_a_creator_id=current_user.id,
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id,
        test_a_status=0,
        test_a_is_correct=True  # Все ответы для типа 31 правильные
    )
    db.session.add(test_answer)
    db.session.commit()

    # Пересчитываем количество ответов
    answers_count = Tests_answers.query.filter_by(
        test_a_test_id=current_test.test_id,
        test_a_question_id=last_question.test_q_id
    ).count()
    
    # Для типов 3, 4, 31 (ручной ввод) достаточно 1 ответа, для остальных нужно минимум 2
    if last_question.test_q_type in [3, 31]:
        are_2_questions = answers_count >= 1
    else:
        are_2_questions = answers_count >= 2

    flash("Правильный ответ добавлен!", 'success')
    return render_template(
        "createnext.html",
        current_test=current_test,
        last_question=last_question,
        are_2_questions=are_2_questions
    )


@app.route('/logout')
def logout():
    logout_user()
    return redirect("/")


@app.route('/profile')
@login_required
def profile():
    return render_template("profile.html")


@app.route('/profile/update-username', methods=['POST'])
@login_required
def profile_update_username():
    new_username = request.form.get('username', '').strip()
    if not new_username:
        flash("Имя не может быть пустым!", 'danger')
        return redirect("/profile")
    if User.query.filter(User.username == new_username, User.id != current_user.id).first():
        flash("Это имя уже занято!", 'danger')
        return redirect("/profile")
    current_user.username = new_username
    db.session.commit()
    flash("Имя пользователя обновлено.", 'success')
    return redirect("/profile")


@app.route('/profile/update-email', methods=['POST'])
@login_required
def profile_update_email():
    new_email = request.form.get('email', '').strip().lower()
    if not new_email or '@' not in new_email:
        flash("Введите корректную почту!", 'danger')
        return redirect("/profile")
    if User.query.filter(User.email == new_email, User.id != current_user.id).first():
        flash("Эта почта уже используется!", 'danger')
        return redirect("/profile")
    current_user.email = new_email
    db.session.commit()
    flash("Почта обновлена.", 'success')
    return redirect("/profile")


@app.route('/profile/update-password', methods=['POST'])
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

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()
