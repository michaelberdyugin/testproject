from datetime import datetime
from flask_login import UserMixin
from extensions import db

DEFAULT_CATEGORIES = ["Образование", "Развлекательные", "Другое"]


def get_category_choices():
    """Возвращает категории в формате для шаблонов (id + name)."""
    return [{'cat_id': c.cat_id, 'cat_name': c.cat_name} for c in TestCategory.query.order_by(TestCategory.cat_name).all()]


class User(db.Model, UserMixin):
    """Модель пользователя."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    admin = db.Column(db.Integer, default=0)  # 0 — пользователь, 1 — модератор, 2 — администратор
    current_test_id = db.Column(db.Integer, default=None)
    # Настройки email-уведомлений (перенесены из UserNotificationSettings)
    notif_email_tests = db.Column(db.Boolean, default=True)
    notif_email_admin = db.Column(db.Boolean, default=True)
    notif_email_account = db.Column(db.Boolean, default=True)


class Tests(db.Model):
    test_id = db.Column(db.Integer, primary_key=True)
    test_id_creator = db.Column(db.Integer)
    test_name = db.Column(db.String)
    test_description = db.Column(db.String)
    test_status = db.Column(db.Integer)
    test_image = db.Column(db.String)
    test_cat_id = db.Column(db.Integer, default=None)  # ссылка на TestCategory.cat_id или None
    show_answers_after_test = db.Column(db.Boolean, default=True)  # показывать правильные ответы после завершения теста


class TestCategory(db.Model):
    __tablename__ = 'test_category'
    cat_id = db.Column(db.Integer, primary_key=True)
    cat_name = db.Column(db.String, unique=True, nullable=False)


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
    test_a_match = db.Column(db.String)   # для типа 4/41
    test_a_status = db.Column(db.Integer)
    test_a_is_correct = db.Column(db.Boolean)


class Test_scores(db.Model):
    test_s_id = db.Column(db.Integer, primary_key=True)
    test_s_user_id = db.Column(db.Integer, nullable=False)
    test_s_test_id = db.Column(db.Integer, nullable=False)
    test_s_score = db.Column(db.Integer, nullable=False)


class Notifications(db.Model):
    """
    Уведомления пользователей.
    Также используется для комментариев модераторов к тестам:
    если n_test_id заполнен — это комментарий к тесту, отображается в истории правок.
    """
    n_id = db.Column(db.Integer, primary_key=True)
    n_user_id = db.Column(db.Integer, nullable=False)   # получатель
    n_sender_id = db.Column(db.Integer)                  # отправитель
    n_text = db.Column(db.Text, nullable=False)
    n_link = db.Column(db.String)
    n_is_read = db.Column(db.Boolean, default=False)
    n_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    n_test_id = db.Column(db.Integer, default=None)      # если это комментарий к тесту
    n_is_comment = db.Column(db.Boolean, default=False)  # True = комментарий модератора (показывать в истории)


class TestComments(db.Model):
    __tablename__ = 'test_comments'
    
    tc_id = db.Column(db.Integer, primary_key=True)
    tc_test_id = db.Column(db.Integer, db.ForeignKey('tests.test_id', ondelete='CASCADE'), nullable=False)
    tc_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    tc_comment = db.Column(db.Text, nullable=False)
    tc_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    user = db.relationship('User', backref='test_comments')
    test = db.relationship('Tests', backref='test_comments')


class TestReport(db.Model):
    __tablename__ = 'test_report'
    
    tr_id = db.Column(db.Integer, primary_key=True)
    tr_test_id = db.Column(db.Integer, db.ForeignKey('tests.test_id', ondelete='CASCADE'), nullable=False)
    tr_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    tr_type = db.Column(db.String(20), nullable=False)  # complaint | error
    tr_text = db.Column(db.Text, nullable=False)
    tr_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tr_resolved = db.Column(db.Boolean, default=False)
    
    # Связи
    user = db.relationship('User', backref='test_reports')
    test = db.relationship('Tests', backref='test_reports')


class TestDetailedResults(db.Model):
    """Детальные результаты прохождения тестов для просмотра авторами."""
    __tablename__ = 'test_detailed_results'
    
    tdr_id = db.Column(db.Integer, primary_key=True)
    tdr_test_id = db.Column(db.Integer, db.ForeignKey('tests.test_id', ondelete='CASCADE'), nullable=False)
    tdr_user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    tdr_correct_answers = db.Column(db.Integer, nullable=False)
    tdr_total_questions = db.Column(db.Integer, nullable=False)
    tdr_percentage = db.Column(db.Float, nullable=False)
    tdr_user_answers = db.Column(db.Text)  # JSON с ответами пользователя
    tdr_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    user = db.relationship('User', backref='detailed_results')
    test = db.relationship('Tests', backref='detailed_results')
