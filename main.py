
import json
import os
import time

DB_FILE = "data.db"


records = []

transaction_active = False
transaction_backup = []
transaction_log = []


def find_key(key):
    for index, record in enumerate(records):
        if record[0] == key:
            return index
    return -1


def update_index(key, value, expiration=None):
    index = find_key(key)
    new_record = [key, value, expiration]

    if index == -1:
        records.append(new_record)
    else:
        records[index] = new_record


def remove_index(key):
    index = find_key(key)

    if index != -1:
        records.pop(index)


def get_record(key):
    index = find_key(key)

    if index == -1:
        return None

    record = records[index]

    if record[2] is not None and time.time() >= record[2]:
        return None

    return record


def copy_records():
    return json.loads(json.dumps(records))


def append_log(entry):
    with open(DB_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")
        file.flush()
        os.fsync(file.fileno())


def save_operation(entry):
    if transaction_active:
        transaction_log.append(entry)
    else:
        append_log(entry)


def find_field(fields, field):
    for index, item in enumerate(fields):
        if item[0] == field:
            return index
    return -1


def apply_hset(key, field, value):
    record = get_record(key)

    if record is None:
        update_index(key, ["HASH", [[field, value]]])
        return

    if not isinstance(record[1], list):
        return

    if record[1][0] != "HASH":
        return

    fields = record[1][1]
    index = find_field(fields, field)

    if index == -1:
        fields.append([field, value])
    else:
        fields[index][1] = value


def apply_push(key, value, left):
    record = get_record(key)

    if record is None:
        update_index(key, ["LIST", [value]])
        return

    if not isinstance(record[1], list):
        return

    if record[1][0] != "LIST":
        return

    items = record[1][1]

    if left:
        items.insert(0, value)
    else:
        items.append(value)


def apply_entry(entry):
    if not isinstance(entry, list) or not entry:
        return

    action = entry[0]

    if action == "TX" and len(entry) == 2:
        for operation in entry[1]:
            apply_entry(operation)

    elif action == "SET" and len(entry) == 4:
        update_index(entry[1], entry[2], entry[3])

    elif action == "DEL" and len(entry) == 2:
        remove_index(entry[1])

    elif action == "EXPIRE" and len(entry) == 3:
        index = find_key(entry[1])

        if index != -1:
            records[index][2] = entry[2]

    elif action == "HSET" and len(entry) == 4:
        apply_hset(entry[1], entry[2], entry[3])

    elif action == "LPUSH" and len(entry) == 3:
        apply_push(entry[1], entry[2], True)

    elif action == "RPUSH" and len(entry) == 3:
        apply_push(entry[1], entry[2], False)

    elif action == "FLUSHDB" and len(entry) == 1:
        records.clear()

    elif len(entry) == 2:
        # Compatibility with the original SET log format
        update_index(entry[0], entry[1])


def load_database():
    records.clear()

    # Create the database file if it does not exist
    with open(DB_FILE, "a", encoding="utf-8"):
        pass

    with open(DB_FILE, "r", encoding="utf-8") as file:
        for line in file:
            try:
                entry = json.loads(line)
                apply_entry(entry)
            except (ValueError, TypeError, IndexError):
                continue


# Basic key-value operations

def set_key(key, value):
    entry = ["SET", key, value, None]
    save_operation(entry)
    update_index(key, value)
    print("OK")


def get_key(key):
    record = get_record(key)

    if record is None:
        print("NULL")
    elif isinstance(record[1], list):
        print("ERROR")
    else:
        print(record[1])


def delete_key(key):
    record = get_record(key)

    if record is None:
        print("0")
        return

    save_operation(["DEL", key])
    remove_index(key)
    print("1")


def exists_key(key):
    if get_record(key) is None:
        print("0")
    else:
        print("1")


# Multiple key operations

def mset_keys(pairs):
    operations = []

    for index in range(0, len(pairs), 2):
        operations.append([
            "SET",
            pairs[index],
            pairs[index + 1],
            None
        ])

    save_operation(["TX", operations])

    for operation in operations:
        apply_entry(operation)

    print("OK")


def mget_keys(keys):
    for key in keys:
        get_key(key)


# Expiration commands

def expire_key(key, seconds):
    record = get_record(key)

    if record is None:
        print("0")
        return

    expiration = time.time() + seconds

    save_operation(["EXPIRE", key, expiration])
    record[2] = expiration

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


# Range queries

def range_keys(start, end):
    matches = []

    for record in records:
        key = record[0]

        if start <= key <= end and get_record(key) is not None:
            matches.append(record)

    matches.sort(key=lambda item: item[0])

    for record in matches:
        if isinstance(record[1], list):
            print(record[0], json.dumps(record[1]))
        else:
            print(record[0], record[1])


# Transactions

def begin_transaction():
    global transaction_active
    global transaction_backup
    global transaction_log

    if transaction_active:
        print("ERROR")
        return

    transaction_backup = copy_records()
    transaction_log = []
    transaction_active = True

    print("OK")


def commit_transaction():
    global transaction_active
    global transaction_backup
    global transaction_log

    if not transaction_active:
        print("ERROR")
        return

    if transaction_log:
        append_log(["TX", transaction_log])

    transaction_active = False
    transaction_backup = []
    transaction_log = []

    print("OK")


def abort_transaction():
    global transaction_active
    global transaction_backup
    global transaction_log

    if not transaction_active:
        print("ERROR")
        return

    records.clear()
    records.extend(transaction_backup)

    transaction_active = False
    transaction_backup = []
    transaction_log = []

    print("OK")


# Hash operations

def hset_key(key, field, value):
    record = get_record(key)

    if record is not None:
        if not isinstance(record[1], list):
            print("ERROR")
            return

        if record[1][0] != "HASH":
            print("ERROR")
            return

    save_operation(["HSET", key, field, value])
    apply_hset(key, field, value)

    print("OK")


def hget_key(key, field):
    record = get_record(key)

    if record is None:
        print("NULL")
        return

    if not isinstance(record[1], list):
        print("ERROR")
        return

    if record[1][0] != "HASH":
        print("ERROR")
        return

    fields = record[1][1]
    index = find_field(fields, field)

    if index == -1:
        print("NULL")
    else:
        print(fields[index][1])


def hgetall_key(key):
    record = get_record(key)

    if record is None:
        print("NULL")
        return

    if not isinstance(record[1], list):
        print("ERROR")
        return

    if record[1][0] != "HASH":
        print("ERROR")
        return

    fields = sorted(record[1][1], key=lambda item: item[0])

    for field, value in fields:
        print(field, value)


# List operations

def push_key(key, value, left):
    record = get_record(key)

    if record is not None:
        if not isinstance(record[1], list):
            print("ERROR")
            return

        if record[1][0] != "LIST":
            print("ERROR")
            return

    action = "LPUSH" if left else "RPUSH"

    save_operation([action, key, value])
    apply_push(key, value, left)

    record = get_record(key)
    print(len(record[1][1]))


def lrange_key(key, start, stop):
    record = get_record(key)

    if record is None:
        print("NULL")
        return

    if not isinstance(record[1], list):
        print("ERROR")
        return

    if record[1][0] != "LIST":
        print("ERROR")
        return

    items = record[1][1]
    length = len(items)

    if start < 0:
        start += length

    if stop < 0:
        stop += length

    start = max(0, start)
    stop = min(stop, length - 1)

    if start > stop:
        print("NULL")
        return

    for item in items[start:stop + 1]:
        print(item)


# Counter operations

def change_counter(key, amount):
    record = get_record(key)

    if record is None:
        current = 0
    else:
        if not isinstance(record[1], str):
            print("ERROR")
            return

        try:
            current = int(record[1])
        except ValueError:
            print("ERROR")
            return

    result = current + amount

    save_operation(["SET", key, str(result), None])
    update_index(key, str(result))

    print(result)


# Database management

def flush_database():
    save_operation(["FLUSHDB"])
    records.clear()

    print("OK")


# Command-line interface

def main():
    load_database()

    while True:
        try:
            command = input().strip()
        except (EOFError, KeyboardInterrupt):
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

        elif action == "BEGIN" and len(parts) == 1:
            begin_transaction()

        elif action == "COMMIT" and len(parts) == 1:
            commit_transaction()

        elif action == "ABORT" and len(parts) == 1:
            abort_transaction()

        elif action == "HSET" and len(parts) >= 4:
            hset_key(parts[1], parts[2], " ".join(parts[3:]))

        elif action == "HGET" and len(parts) == 3:
            hget_key(parts[1], parts[2])

        elif action == "HGETALL" and len(parts) == 2:
            hgetall_key(parts[1])

        elif action == "LPUSH" and len(parts) >= 3:
            push_key(parts[1], " ".join(parts[2:]), True)

        elif action == "RPUSH" and len(parts) >= 3:
            push_key(parts[1], " ".join(parts[2:]), False)

        elif action == "LRANGE" and len(parts) == 4:
            try:
                lrange_key(parts[1], int(parts[2]), int(parts[3]))
            except ValueError:
                print("ERROR")

        elif action == "INCR" and len(parts) == 2:
            change_counter(parts[1], 1)

        elif action == "DECR" and len(parts) == 2:
            change_counter(parts[1], -1)

        elif action == "FLUSHDB" and len(parts) == 1:
            flush_database()

        elif action == "EXIT" and len(parts) == 1:
            break

        else:
            print("ERROR")


if __name__ == "__main__":
    main()
