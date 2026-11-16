
import json
import os

DB_FILE = "data.db"

records = []


def find_key(key):
    for index, record in enumerate(records):
        if record[0] == key:
            return index
    return -1


def update_index(key, value):
    index = find_key(key)

    if index == -1:
        records.append([key, value])
    else:
        records[index][1] = value


def load_database():
    if not os.path.exists(DB_FILE):
        open(DB_FILE, "a", encoding="utf-8").close()
        return

    with open(DB_FILE, "r", encoding="utf-8") as file:
        for line in file:
            try:
                key, value = json.loads(line)
                update_index(key, value)
            except (ValueError, TypeError):
                continue


def set_key(key, value):
    with open(DB_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps([key, value]) + "\n")
        file.flush()
        os.fsync(file.fileno())

    update_index(key, value)
    print("OK")


def get_key(key):
    index = find_key(key)

    if index == -1:
        print("NULL")
    else:
        print(records[index][1])


def main():
    load_database()

    while True:
        try:
            command = input().strip()
        except EOFError:
            break

        if not command:
            continue

        parts = command.split()
        action = parts[0].upper()

        if action == "SET" and len(parts) >= 3:
            set_key(parts[1], " ".join(parts[2:]))

        elif action == "GET" and len(parts) == 2:
            get_key(parts[1])

        elif action == "EXIT":
            break

        else:
            print("ERROR")


if __name__ == "__main__":
    main()
