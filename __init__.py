import random
import secret

from flask import Flask, render_template, request, redirect, flash, session
from flask_login import current_user

from extensions import db, manager, mail
from models import Notifications

app = Flask(__name__)
app.secret_key = secret.key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
app.config['MAIL_SERVER'] = 'smtp.mail.ru'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'itcube.michael.berdyugin@mail.ru'
app.config['MAIL_DEFAULT_SENDER'] = 'itcube.michael.berdyugin@mail.ru'
app.config['MAIL_PASSWORD'] = secret.mail_password
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['UPLOAD_FOLDER'] = 'static/img'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db.init_app(app)
manager.init_app(app)
mail.init_app(app)

# --- Загрузчик пользователя ---
from models import User

@manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)

# --- Jinja-фильтры ---
@app.template_filter('get_unread_notifications_count')
def get_unread_notifications_count(user_id):
    return Notifications.query.filter_by(n_user_id=user_id, n_is_read=False).count()

@app.template_filter('shuffle_list')
def shuffle_list_filter(lst):
    import copy
    result = copy.copy(list(lst))
    random.shuffle(result)
    return result

@app.template_filter('from_json')
def from_json_filter(json_str):
    import json
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return {}

# --- Before request ---
@app.before_request
def check_must_rate_test():
    excluded_paths = ['/test/', '/static/', '/logout']
    if session.get('must_rate_test') and 'test_result' in session:
        current_path = request.path
        if not any(p in current_path for p in excluded_paths):
            test_name = session['test_result']['test_name']
            if current_path not in [f'/test/{test_name}/result', f'/test/{test_name}/rate']:
                flash("Пожалуйста, оцените тест перед переходом на другие страницы!", 'warning')
                return redirect(f"/test/{test_name}/result")

# --- Главная ---
@app.route('/')
def index():
    return render_template("index.html")

# --- Blueprints ---
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.tests import tests_bp
from routes.workshop import workshop_bp
from routes.edit import edit_bp
from routes.moderator import moderator_bp
from routes.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(tests_bp)
app.register_blueprint(workshop_bp)
app.register_blueprint(edit_bp)
app.register_blueprint(moderator_bp)
app.register_blueprint(admin_bp)

# Добавляем алиасы endpoint'ов без префикса blueprint для совместимости с url_for в шаблонах
for _endpoint, _view in list(app.view_functions.items()):
    if '.' in _endpoint:
        _short = _endpoint.split('.', 1)[1]
        if _short not in app.view_functions:
            app.view_functions[_short] = _view
# Добавляем алиасы в url_map
import werkzeug.routing as _wr
for _rule in list(app.url_map.iter_rules()):
    if '.' in _rule.endpoint:
        _short = _rule.endpoint.split('.', 1)[1]
        if not any(r.endpoint == _short for r in app.url_map.iter_rules()):
            _new_rule = _wr.Rule(_rule.rule, methods=_rule.methods, endpoint=_short)
            app.url_map.add(_new_rule)

# --- API ---
from models import Tests, Tests_answers, Tests_questions, Test_scores
from api import init_api
init_api(app, db, Tests, User, Tests_answers, Tests_questions, Test_scores)


def _ensure_base_data():
    """Создает таблицы и базовые категории при необходимости."""
    from models import DEFAULT_CATEGORIES, TestCategory

    db.create_all()
    try:
        if not TestCategory.query.first():
            for name in DEFAULT_CATEGORIES:
                db.session.add(TestCategory(cat_name=name))
            db.session.commit()
    except Exception:
        db.session.rollback()


with app.app_context():
    _ensure_base_data()


if __name__ == "__main__":
    app.run()
