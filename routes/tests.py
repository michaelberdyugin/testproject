import random
import json

from flask import Blueprint, render_template, request, redirect, flash, session
from flask_login import login_required, current_user

from extensions import db
from models import Tests, Tests_questions, Tests_answers, Test_scores, TestReport, User, get_category_choices, TestDetailedResults
from helpers import _create_notification

tests_bp = Blueprint('tests', __name__)
COMPLAINT_THRESHOLD = 3


@tests_bp.route('/tests')
def tests():
    q_name = request.args.get('name', '').strip()
    q_author = request.args.get('author', '').strip()
    q_cat = request.args.get('cat', '').strip()
    sort = request.args.get('sort', '')

    query = Tests.query.filter_by(test_status=2)
    if q_name:
        query = query.filter(Tests.test_name.ilike(f'%{q_name}%'))
    if q_cat:
        try:
            query = query.filter(Tests.test_cat_id == int(q_cat))
        except ValueError:
            pass

    all_tests = query.all()

    creators = {}
    avg_scores = {}
    for test in all_tests:
        user = User.query.get(test.test_id_creator)
        creators[test.test_id] = user.username if user else "—"
        scores = Test_scores.query.filter_by(test_s_test_id=test.test_id).all()
        avg_scores[test.test_id] = round(sum(s.test_s_score for s in scores) / len(scores), 1) if scores else None

    if q_author:
        all_tests = [t for t in all_tests if q_author.lower() in creators[t.test_id].lower()]

    if sort == 'rating':
        all_tests.sort(key=lambda t: avg_scores[t.test_id] or 0, reverse=True)

    categories = get_category_choices()
    cat_map = {c['cat_id']: c['cat_name'] for c in categories}

    return render_template("tests.html", tests=all_tests, creators=creators, avg_scores=avg_scores,
                           q_name=q_name, q_author=q_author, q_cat=q_cat, sort=sort,
                           categories=categories, cat_map=cat_map)


@tests_bp.route('/test/<test_name>')
def view_test(test_name):
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    questions_count = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).count()
    scores = Test_scores.query.filter_by(test_s_test_id=test.test_id).all()
    average_score = round(sum(s.test_s_score for s in scores) / len(scores), 1) if scores else 0

    user_score = None
    active_test = None
    if current_user.is_authenticated:
        user_score = Test_scores.query.filter_by(
            test_s_user_id=current_user.id, test_s_test_id=test.test_id
        ).first()
        if current_user.current_test_id and current_user.current_test_id != test.test_id:
            active_test = Tests.query.get(current_user.current_test_id)

    return render_template("test_info.html", test=test, questions_count=questions_count,
                           average_score=average_score, scores_count=len(scores),
                           user_score=user_score, active_test=active_test)


@tests_bp.route('/test/<test_name>/report-complaint', methods=['POST'])
@login_required
def report_test_complaint(test_name):
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден или недоступен для жалобы.", 'danger')
        return redirect("/tests")

    if test.test_id_creator == current_user.id:
        flash("Нельзя отправить жалобу на собственный тест.", 'warning')
        return redirect(f"/test/{test_name}")

    text = (request.form.get('complaint_text') or "").strip()
    if not text:
        flash("Опишите причину жалобы.", 'warning')
        return redirect(f"/test/{test_name}")

    existing = TestReport.query.filter_by(
        tr_test_id=test.test_id, tr_user_id=current_user.id, tr_type='complaint', tr_resolved=False
    ).first()
    if existing:
        flash("Вы уже отправляли жалобу на этот тест.", 'info')
        return redirect(f"/test/{test_name}")

    db.session.add(TestReport(
        tr_test_id=test.test_id,
        tr_user_id=current_user.id,
        tr_type='complaint',
        tr_text=text
    ))

    unique_complaints = db.session.query(TestReport.tr_user_id).filter_by(
        tr_test_id=test.test_id, tr_type='complaint', tr_resolved=False
    ).distinct().count()

    if unique_complaints >= COMPLAINT_THRESHOLD and test.test_status == 2:
        # Отправляем уведомление модераторам, но НЕ меняем статус теста
        for mod in User.query.filter(User.admin >= 1).all():
            _create_notification(
                user_id=mod.id,
                sender_id=current_user.id,
                text=(
                    f"Тест \"{test.test_name}\" получил {unique_complaints} жалобы. "
                    f"Требуется внимание модератора."
                ),
                link="/moderator/reported",
                category='tests'
            )
        flash("Жалоба отправлена. Модераторы уведомлены о большом количестве жалоб.", 'success')
    else:
        flash("Жалоба отправлена. Спасибо за обратную связь.", 'success')

    db.session.commit()
    return redirect(f"/test/{test_name}")


@tests_bp.route('/test/<test_name>/report-error', methods=['POST'])
@login_required
def report_test_error(test_name):
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден или недоступен.", 'danger')
        return redirect("/tests")

    if test.test_id_creator == current_user.id:
        flash("Вы автор этого теста. Используйте редактирование для исправлений.", 'info')
        return redirect(f"/test/{test_name}")

    text = (request.form.get('error_text') or "").strip()
    if not text:
        flash("Опишите найденную ошибку.", 'warning')
        return redirect(f"/test/{test_name}")

    db.session.add(TestReport(
        tr_test_id=test.test_id,
        tr_user_id=current_user.id,
        tr_type='error',
        tr_text=text
    ))
    _create_notification(
        user_id=test.test_id_creator,
        sender_id=current_user.id,
        text=f"Пользователь сообщил об ошибке в тесте \"{test.test_name}\": {text}",
        link=f"/edit-test/{test.test_id}",
        category='tests'
    )
    db.session.commit()
    flash("Сообщение об ошибке отправлено автору теста.", 'success')
    return redirect(f"/test/{test_name}")


@tests_bp.route('/test/<test_name>/start')
@login_required
def start_test(test_name):
    if current_user.current_test_id is not None:
        current_test = Tests.query.get(current_user.current_test_id)
        if current_test:
            flash(f"Вы уже проходите тест '{current_test.test_name}'. Завершите его перед началом нового.", 'warning')
            return redirect(f"/test/{current_test.test_name}/take")

    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    current_user.current_test_id = test.test_id
    db.session.commit()
    return redirect(f"/test/{test_name}/take")


@tests_bp.route('/test/<test_name>/take')
@login_required
def take_test(test_name):
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    if current_user.current_test_id != test.test_id:
        flash("Вы не можете проходить этот тест!", 'danger')
        return redirect("/tests")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).all()
    questions_with_answers = []
    for question in questions:
        answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id, test_a_status=2).all()
        if question.test_q_type in [1, 2, 11, 21]:
            random.shuffle(answers)
        questions_with_answers.append({'question': question, 'answers': answers})

    return render_template("take_test.html", test=test, questions_with_answers=questions_with_answers)


@tests_bp.route('/test/<test_name>/submit', methods=["POST"])
@login_required
def submit_test(test_name):
    test = Tests.query.filter_by(test_name=test_name, test_status=2).first()
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    if current_user.current_test_id != test.test_id:
        flash("Вы не можете отправить ответы на этот тест!", 'danger')
        return redirect("/tests")

    questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).all()
    correct_answers = 0
    total_questions = len(questions)
    user_answers = {}

    for question in questions:
        question_key = f"question_{question.test_q_id}"
        user_answers[question.test_q_id] = {
            'question_text': question.test_q_text,
            'question_type': question.test_q_type,
            'user_input': None,
            'correct': False,
            'correct_answers': [],
            'user_answers': []
        }

        if question.test_q_type in [1, 11]:
            user_answer_id = request.form.get(question_key)
            if user_answer_id:
                answer = Tests_answers.query.get(int(user_answer_id))
                user_answers[question.test_q_id]['user_answers'] = [user_answer_id]
                if answer and answer.test_a_is_correct:
                    correct_answers += 1
                    user_answers[question.test_q_id]['correct'] = True

        elif question.test_q_type in [2, 21]:
            user_answer_ids = request.form.getlist(question_key)
            correct_ids = [str(a.test_a_id) for a in Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id, test_a_is_correct=True).all()]
            user_answers[question.test_q_id]['user_answers'] = user_answer_ids
            if set(user_answer_ids) == set(correct_ids):
                correct_answers += 1
                user_answers[question.test_q_id]['correct'] = True

        elif question.test_q_type in [3, 31]:
            user_answer = (request.form.get(question_key) or "").strip().lower()
            correct_list = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id, test_a_is_correct=True).all()
            user_answers[question.test_q_id]['user_input'] = user_answer
            if any(user_answer == a.test_a_text.strip().lower() for a in correct_list):
                correct_answers += 1
                user_answers[question.test_q_id]['correct'] = True

        elif question.test_q_type in [4, 41]:
            pairs = Tests_answers.query.filter_by(
                test_a_question_id=question.test_q_id, test_a_status=2).all()
            user_matches = {}
            all_correct = True
            for p in pairs:
                user_match = (request.form.get(f"match_{p.test_a_id}") or "").strip()
                user_matches[p.test_a_id] = user_match
                if user_match != p.test_a_match.strip():
                    all_correct = False
            user_answers[question.test_q_id]['user_input'] = user_matches
            if pairs and all_correct:
                correct_answers += 1
                user_answers[question.test_q_id]['correct'] = True

    percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    session['test_result'] = {
        'test_name': test_name,
        'test_id': test.test_id,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'percentage': percentage,
        'user_answers': user_answers,
        'show_answers': test.show_answers_after_test
    }
    return redirect(f"/test/{test_name}/result")


@tests_bp.route('/test/<test_name>/result')
@login_required
def test_result(test_name):
    if 'test_result' not in session:
        flash("Результат теста не найден!", 'danger')
        return redirect("/tests")

    result = session['test_result']
    if result['test_name'] != test_name:
        flash("Неверный результат теста!", 'danger')
        return redirect("/tests")

    test = Tests.query.get(result['test_id'])
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    existing_score = Test_scores.query.filter_by(
        test_s_user_id=current_user.id, test_s_test_id=result['test_id']).first()

    # Получаем детальную информацию о вопросах и ответах, если нужно показать ответы
    detailed_results = None
    if result.get('show_answers', True):
        detailed_results = []
        questions = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).all()
        for question in questions:
            answers = Tests_answers.query.filter_by(test_a_question_id=question.test_q_id, test_a_status=2).all()
            # Ключи в user_answers сохранены как строки в сессии, поэтому преобразуем question.test_q_id в строку
            user_answer_data = result.get('user_answers', {}).get(str(question.test_q_id), {})
            
            detailed_results.append({
                'question': question,
                'answers': answers,
                'user_answer_data': user_answer_data
            })

    session['must_rate_test'] = True
    return render_template("test_result.html", test=test, result=result, 
                          existing_score=existing_score, detailed_results=detailed_results,
                          show_answers=result.get('show_answers', True))


@tests_bp.route('/test/<test_name>/simple-rate')
@login_required
def simple_rate(test_name):
    """Простая страница для оценки теста (чтобы выйти из debug)"""
    if 'test_result' not in session:
        flash("Результат теста не найден!", 'danger')
        return redirect("/tests")

    result = session['test_result']
    if result['test_name'] != test_name:
        flash("Неверный результат теста!", 'danger')
        return redirect("/tests")

    test = Tests.query.get(result['test_id'])
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/tests")

    return render_template("simple_rate_form.html", test=test)


@tests_bp.route('/test/<test_name>/rate', methods=["POST"])
@login_required
def rate_test(test_name):
    if 'test_result' not in session:
        flash("Результат теста не найден!", 'danger')
        return redirect("/tests")

    result = session['test_result']
    if result['test_name'] != test_name:
        flash("Неверный результат теста!", 'danger')
        return redirect("/tests")

    try:
        score = int(request.form.get('score', 0))
        if score < 1 or score > 5:
            raise ValueError
    except ValueError:
        flash("Оценка должна быть от 1 до 5!", 'danger')
        return redirect(f"/test/{test_name}/result")

    existing_score = Test_scores.query.filter_by(
        test_s_user_id=current_user.id, test_s_test_id=result['test_id']).first()

    if existing_score:
        existing_score.test_s_score = score
        msg = f"Ваша оценка обновлена! Результат: {result['correct_answers']} из {result['total_questions']} ({result['percentage']:.1f}%)"
    else:
        db.session.add(Test_scores(
            test_s_user_id=current_user.id,
            test_s_test_id=result['test_id'],
            test_s_score=score
        ))
        msg = f"Спасибо за оценку! Ваш результат: {result['correct_answers']} из {result['total_questions']} ({result['percentage']:.1f}%)"

    # Сохраняем детальные результаты, если автор теста включил показ ответов
    test = Tests.query.get(result['test_id'])
    if test and test.show_answers_after_test:
        db.session.add(TestDetailedResults(
            tdr_test_id=result['test_id'],
            tdr_user_id=current_user.id,
            tdr_correct_answers=result['correct_answers'],
            tdr_total_questions=result['total_questions'],
            tdr_percentage=result['percentage'],
            tdr_user_answers=json.dumps(result.get('user_answers', {}))
        ))

    current_user.current_test_id = None
    db.session.commit()
    session.pop('test_result', None)
    session.pop('must_rate_test', None)
    flash(msg, 'success')
    return redirect("/tests")


@tests_bp.route('/test/<int:test_id>/results')
@login_required
def view_test_results(test_id):
    """Просмотр результатов прохождения теста автором."""
    test = Tests.query.get(test_id)
    if not test:
        flash("Тест не найден!", 'danger')
        return redirect("/workshop")
    
    # Проверяем, что текущий пользователь - автор теста
    if test.test_id_creator != current_user.id:
        flash("Вы не являетесь автором этого теста!", 'danger')
        return redirect("/workshop")
    
    # Получаем автора теста
    author = User.query.get(test.test_id_creator)
    
    # Получаем количество вопросов
    questions_count = Tests_questions.query.filter_by(test_q_test_id=test.test_id, test_q_status=2).count()
    
    # Параметры поиска и пагинации
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Запрос результатов
    query = TestDetailedResults.query.filter_by(tdr_test_id=test_id)
    
    # Поиск по имени пользователя
    if search_query:
        query = query.join(User).filter(User.username.ilike(f'%{search_query}%'))
    
    # Сортировка по дате (новые сначала)
    query = query.order_by(TestDetailedResults.tdr_created_at.desc())
    
    # Пагинация
    total_results = query.count()
    results = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total_results + per_page - 1) // per_page
    
    # Статистика
    all_results = TestDetailedResults.query.filter_by(tdr_test_id=test_id).all()
    if all_results:
        avg_percentage = sum(r.tdr_percentage for r in all_results) / len(all_results)
        best_percentage = max(r.tdr_percentage for r in all_results)
        worst_percentage = min(r.tdr_percentage for r in all_results)
    else:
        avg_percentage = best_percentage = worst_percentage = 0
    
    return render_template("test_results_view.html", 
                          test=test, 
                          author=author,
                          questions_count=questions_count,
                          results=results,
                          total_results=total_results,
                          avg_percentage=avg_percentage,
                          best_percentage=best_percentage,
                          worst_percentage=worst_percentage,
                          search_query=search_query,
                          page=page,
                          total_pages=total_pages)