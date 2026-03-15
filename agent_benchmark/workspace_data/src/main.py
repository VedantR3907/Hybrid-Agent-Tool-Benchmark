from src.utils import process_order


def main() -> None:
    order = {"id": "SO-1001", "country": "India", "amount": 980}
    result = process_order(order)
    print(result)


if __name__ == "__main__":
    main()
