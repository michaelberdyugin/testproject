from datetime import datetime
from flask_login import UserMixin
from extensions import db


class User(db.Model, UserMixin):
    """Модель пользователя с логином, паролем и почтой."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    admin = db.Column(db.Integer, default=0)  # 0 - обычный, 1 - модератор, 2 - администратор
    current_test_id = db.Column(db.Integer, default=None)


class Tests(db.Model):
    test_id = db.Column(db.Integer, primary_key=True)
    test_id_creator = db.Column(db.Integer)
    test_name = db.Column(db.String)
    test_description = db.Column(db.String)
    test_status = db.Column(db.Integer)
    test_image = db.Column(db.String)


class Tests_questions(db.Model):
    test_q_id = db.Column(db.Integer, primary_key=True)
    test_q_creator_id = db.Column(db.Integer)
    test_q_test_id = db.Column(db.Integer)
    test_q_text = db.Column(db.String)
    # 1 — один ответ, 2 — несколько, 3 — ввод, 4 — перетаскивание
    # 11/21/31/41 — то же с изображением
    test_q_type = db.Column(db.Integer, default=1)
    test_q_status = db.Column(db.Integer)
    test_q_image = db.Column(db.String)


class Tests_answers(db.Model):
    test_a_id = db.Column(db.Integer, primary_key=True)
    test_a_creator_id = db.Column(db.Integer)
    test_a_question_id = db.Column(db.Integer)
    test_a_test_id = db.Column(db.Integer)
    test_a_text = db.Column(db.String)
    test_a_match = db.Column(db.String)   # для типа 4/41: блок 1 (к чему перетаскивают)
    test_a_status = db.Column(db.Integer)
    test_a_is_correct = db.Column(db.Boolean)


class Test_scores(db.Model):
    test_s_id = db.Column(db.Integer, primary_key=True)
    test_s_user_id = db.Column(db.Integer, nullable=False)
    test_s_test_id = db.Column(db.Integer, nullable=False)
    test_s_score = db.Column(db.Integer, nullable=False)


class Notifications(db.Model):
    n_id = db.Column(db.Integer, primary_key=True)
    n_user_id = db.Column(db.Integer, nullable=False)
    n_sender_id = db.Column(db.Integer)
    n_text = db.Column(db.Text, nullable=False)
    n_link = db.Column(db.String)
    n_is_read = db.Column(db.Boolean, default=False)
    n_created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TestComments(db.Model):
    tc_id = db.Column(db.Integer, primary_key=True)
    tc_test_id = db.Column(db.Integer, nullable=False)
    tc_user_id = db.Column(db.Integer, nullable=False)
    tc_comment = db.Column(db.Text, nullable=False)
    tc_created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserNotificationSettings(db.Model):
    uns_id = db.Column(db.Integer, primary_key=True)
    uns_user_id = db.Column(db.Integer, nullable=False, unique=True)
    uns_email_tests = db.Column(db.Boolean, default=True)
    uns_email_admin_messages = db.Column(db.Boolean, default=True)
    uns_email_account_changes = db.Column(db.Boolean, default=True)
