import requests


BASE_URL = "http://127.0.0.1:5000"


def main():
    print("1 - просмотр всех тестов, 2 - регистрация, 3 - просмотр всех тестов с ответами(только для зарегестрированных администраторов или модераторов)")
    variant = int(input())
    if variant == 1:
        r = requests.get(f"{BASE_URL}/api/tests")
        print(r)
        print("tests list:", r.status_code, r.json())
    elif variant == 2:
        pass


if __name__ == "__main__":
    main()

