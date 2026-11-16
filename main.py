
import json
import os
import time

DB_FILE = "data.db"

# Custom in-memory index: [key, value, expiration]
records = []


def find_key(key):
    for index, record in enumerate(records):
        if record[0] == key:
            return index
    return -1


def update_index(key, value, expiration=None):
    index = find_key(key)

    if index == -1:
        records.append([key, value, expiration])
    else:
        records[index] = [key, value, expiration]


def remove_index(key):
    index = find_key(key)
    if index != -1:
        records.pop(index)


def get_record(key):
    index = find_key(key)

    if index == -1:
        return None

    record = records[index]
    expiration = record[2]

    if expiration is not None and time.time() >= expiration:
        return None

    return record


def append_log(entry):
    with open(DB_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")
        file.flush()
        os.fsync(file.fileno())


def load_database():
    open(DB_FILE, "a", encoding="utf-8").close()

    with open(DB_FILE, "r", encoding="utf-8") as file:
        for line in file:
            try:
                entry = json.loads(line)

                if not isinstance(entry, list):
                    continue

                if len(entry) == 4 and entry[0] == "SET":
                    update_index(entry[1], entry[2], entry[3])

                elif len(entry) == 3 and entry[0] == "EXPIRE":
                    index = find_key(entry[1])
                    if index != -1:
                        records[index][2] = entry[2]

                elif len(entry) == 2 and entry[0] == "DEL":
                    remove_index(entry[1])

                elif len(entry) == 2:
                    
                    update_index(entry[0], entry[1])

            except (ValueError, TypeError, IndexError):
                continue


def set_key(key, value, show_output=True):
    append_log(["SET", key, value, None])
    update_index(key, value)

    if show_output:
        print("OK")


def get_key(key):
    record = get_record(key)
    if record is None:
        print("NULL")
    else:
        print(record[1])


def delete_key(key):
    if get_record(key) is None:
        print("0")
        return

    append_log(["DEL", key])
    remove_index(key)
    print("1")


def exists_key(key):
    print("1" if get_record(key) is not None else "0")


def mset_keys(pairs):
    entries = []

    for index in range(0, len(pairs), 2):
        entries.append(["SET", pairs[index], pairs[index + 1], None])

    with open(DB_FILE, "a", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry) + "\n")
        file.flush()
        os.fsync(file.fileno())

    for entry in entries:
        update_index(entry[1], entry[2])

    print("OK")


def mget_keys(keys):
    for key in keys:
        get_key(key)


def expire_key(key, seconds):
    if get_record(key) is None:
        print("0")
        return

    expiration = time.time() + seconds
    append_log(["EXPIRE", key, expiration])

    index = find_key(key)
    records[index][2] = expiration
    print("1")


def ttl_key(key):
    record = get_record(key)

    if record is None:
        print("-2")
        return

    if record[2] is None:
        print("-1")
        return

    remaining = int(record[2] - time.time())
    print(max(0, remaining))


def range_keys(start, end):
    matches = []

    for record in records:
        key = record[0]
        if start <= key <= end and get_record(key) is not None:
            matches.append(record)

    matches.sort(key=lambda record: record[0])

    for record in matches:
        print(record[0], record[1])


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

        elif action == "DEL" and len(parts) == 2:
            delete_key(parts[1])

        elif action == "EXISTS" and len(parts) == 2:
            exists_key(parts[1])

        elif action == "MSET" and len(parts) >= 3 and len(parts) % 2 == 1:
            mset_keys(parts[1:])

        elif action == "MGET" and len(parts) >= 2:
            mget_keys(parts[1:])

        elif action == "EXPIRE" and len(parts) == 3:
            try:
                expire_key(parts[1], int(parts[2]))
            except ValueError:
                print("ERROR")

        elif action == "TTL" and len(parts) == 2:
            ttl_key(parts[1])

        elif action == "RANGE" and len(parts) == 3:
            range_keys(parts[1], parts[2])

        elif action == "EXIT" and len(parts) == 1:
            break

        else:
            print("ERROR")


if __name__ == "__main__":
    main()
