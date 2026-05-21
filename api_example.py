import requests

BASE_URL = "http://127.0.0.1:5000"

# Сессия сохраняет cookies между запросами (нужно для авторизации)
session = requests.Session()


def login():
    username = input("Имя пользователя: ").strip()
    password = input("Пароль: ").strip()

    r = session.post(f"{BASE_URL}/api/auth/login", json={
        "username": username,
        "password": password
    })
    data = r.json()
    if data.get("ok"):
        print("Вход выполнен успешно!")
    else:
        print(f"Ошибка: {data.get('error')}")


def list_tests():
    r = session.get(f"{BASE_URL}/api/tests")
    data = r.json()
    if not data.get("ok"):
        print(f"Ошибка: {data.get('error')}")
        return
    tests = data["items"]
    if not tests:
        print("Тестов нет.")
        return
    for test in tests:
        print(f"\n[{test['id']}] {test['test_name']} (оценка: {test['score']})")
        print(f"  {test['test_description']}")
        for qid, q in test["questions"].items():
            print(f"  Вопрос {qid} ({q['question_type']}): {q['question_text']}")


def list_tests_admin():
    r = session.get(f"{BASE_URL}/api/tests/admin")
    data = r.json()
    if not data.get("ok"):
        print(f"Ошибка: {data.get('error')}")
        return
    tests = data["items"]
    if not tests:
        print("Тестов нет.")
        return
    for test in tests:
        print(f"\n[{test['id']}] {test['test_name']} (оценка: {test['score']})")
        print(f"  {test['test_description']}")
        for qid, q in test["questions"].items():
            print(f"  Вопрос {qid} (тип {q['question_type']}): {q['question_text']}")
            for aid, a in q["answers"].items():
                if "answer_is_correct" in a:
                    correct = "✅" if a["answer_is_correct"] else "❌"
                    print(f"    [{aid}] {correct} {a['answer_text']}")
                elif "answer_block_1" in a:
                    print(f"    [{aid}] {a['answer_block_1']} → {a['answer_block_2']}")
                else:
                    print(f"    [{aid}] {a['answer_text']}")


def main():
    while True:
        print("1 - просмотр всех тестов")
        print("2 - вход")
        print("3 - просмотр всех тестов с ответами (только для администраторов/модераторов)")
        variant = int(input("Выберите действие: "))

        if variant == 1:
            list_tests()
        elif variant == 2:
            login()
        elif variant == 3:
            list_tests_admin()
        else:
            print("Неизвестный вариант")


if __name__ == "__main__":
    main()
