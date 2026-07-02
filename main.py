import requests
def main():
    print(requests.get("https://httpbin.org/status/200"))


if __name__ == "__main__":
    main()
