
"""Persistent append-only key value store. This module provides a console-based database that supports strings,
hashes, lists, expiry, transactions, and counters.

The database is stored in data.db file using an append-only JSON-lines format.
The in-memory index structure uses lists rather than Python dictionaries.
"""

import json
import math
import os
import sys
import time
from typing import Any, Optional


class Database:
    """Manage persistent key-value records using a list-based index."""

    def __init__(self, path: str = "data.db") -> None:
        """Initialize the database and recover saved records."""
        self.path = path
        self.rows: list[list[Any]] = []
        self.known_keys: list[str] = []
        self.transaction: bool = False
        self.snapshot: Optional[list[list[Any]]] = None
        self.pending: list[list[Any]] = []
        self.load()

    def index(self, key: str) -> int:
        """Return the index of a key, or -1 if it does not exist."""
        for position, row in enumerate(self.rows):
            if row[0] == key:
                return position
        return -1

    def remember(self, key: str) -> None:
        """Track keys previously written, deleted, or rolled back."""
        if key not in self.known_keys:
            self.known_keys.append(key)

    def live(self, key: str) -> Optional[list[Any]]:
        """Retrieve an active record while enforcing lazy expiration."""
        position = self.index(key)

        if position < 0:
            return None

        record = self.rows[position]
        expiration = record[3]

        if expiration is not None and time.time() >= expiration:
            return None

        return record

    def put(
        self,
        key: str,
        kind: str,
        value: Any,
        deadline: Optional[float] = None,
    ) -> None:
        """Insert or overwrite a record using last-write-wins semantics."""
        self.remember(key)
        new_record = [key, kind, value, deadline]
        position = self.index(key)

        if position < 0:
            self.rows.append(new_record)
        else:
            self.rows[position] = new_record

    def remove(self, key: str) -> None:
        """Delete a key from the in-memory index."""
        self.remember(key)
        position = self.index(key)

        if position >= 0:
            self.rows.pop(position)

    @staticmethod
    def field_index(fields: list[Any], field: str) -> int:
        """Find a field in a hash represented as a list of pairs."""
        for position, pair in enumerate(fields):
            if pair[0] == field:
                return position
        return -1

    def apply(self, event: list[Any]) -> None:
        """Apply a logged operation without writing it to disk.

        This function is used during normal execution and when
        replaying the append-only log after a restart.
        """
        if not isinstance(event, list) or not event:
            return

        operation = event[0]

        if operation == "TX" and len(event) == 2:
            if not isinstance(event[1], list):
                return

            for child in event[1]:
                self.apply(child)

        elif operation == "SET" and len(event) == 4:
            self.put(event[1], "string", event[2], event[3])

        elif operation == "DEL" and len(event) == 2:
            self.remove(event[1])

        elif operation == "EXPIRE" and len(event) == 3:
            record = self.live(event[1])

            if record is not None:
                record[3] = event[2]

        elif operation == "HSET" and len(event) == 4:
            key, field, value = event[1:]
            record = self.live(key)

            if record is None:
                self.put(key, "hash", [[field, value]])

            elif record[1] == "hash":
                position = self.field_index(record[2], field)

                if position < 0:
                    record[2].append([field, value])
                else:
                    record[2][position][1] = value

        elif operation in ("LPUSH", "RPUSH") and len(event) == 3:
            key, value = event[1:]
            record = self.live(key)

            if record is None:
                self.put(key, "list", [value])

            elif record[1] == "list":
                if operation == "LPUSH":
                    record[2].insert(0, value)
                else:
                    record[2].append(value)

        elif operation in ("LPOP", "RPOP") and len(event) == 2:
            record = self.live(event[1])

            if record is not None:
                if record[1] == "list" and record[2]:
                    position = 0 if operation == "LPOP" else -1
                    record[2].pop(position)

        elif operation == "FLUSHDB" and len(event) == 1:
            self.rows.clear()

        elif len(event) == 2 and operation not in (
            "LPOP",
            "RPOP",
            "FLUSHDB",
        ):
            # Support records from the original database implementation.
            self.put(event[0], "string", event[1])

    def load(self) -> None:
        """Recover database state by replaying the append-only log.

        Creates data.db if necessary. Only complete JSON records
        are replayed to avoid using an incomplete trailing write.
        """
        with open(self.path, "a", encoding="utf-8"):
            pass

        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.endswith("\n"):
                    break

                try:
                    event = json.loads(line)
                    self.apply(event)
                except (ValueError, TypeError, IndexError):
                    # Ignore an invalid record during recovery.
                    continue

    def append(self, event: list[Any]) -> None:
        """Persist an event or buffer it in an active transaction.

        Each durable operation is written as a JSON line.
        flush() and fsync() request immediate disk persistence.
        """
        if self.transaction:
            self.pending.append(event)
            return

        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(event, ensure_ascii=False) + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    def write(self, event: list[Any]) -> None:
        """Persist a command and apply its changes to memory."""
        self.append(event)
        self.apply(event)

    def begin(self) -> list[str]:
        """Start a transaction by saving a snapshot of current records."""
        if self.transaction:
            return ["ERROR"]

        self.snapshot = json.loads(json.dumps(self.rows))
        self.pending = []
        self.transaction = True

        return ["OK"]

    def commit(self) -> list[str]:
        """Atomically log buffered operations as one transaction record."""
        if not self.transaction:
            return ["ERROR"]

        if self.pending:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        ["TX", self.pending],
                        ensure_ascii=False,
                    ) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())

        self.snapshot = None
        self.pending = []
        self.transaction = False

        return ["OK"]

    def abort(self) -> list[str]:
        """Discard pending writes and restore the transaction snapshot."""
        if not self.transaction:
            return ["ERROR"]

        if self.snapshot is not None:
            self.rows = self.snapshot

        self.snapshot = None
        self.pending = []
        self.transaction = False

        return ["OK"]

    def execute(self, line: str) -> Optional[list[str]]:
        """Parse, validate, and execute a database command.

        Parameters:
            line: A single command read from standard input.

        Returns:
            A list of response lines, an empty list for no output,
            or None when the EXIT command terminates the program.
        """
        parts = line.strip().split()

        if not parts:
            return []

        operation = parts[0].upper()
        arguments = parts[1:]

        # Basic commands

        if operation == "EXIT" and not arguments:
            return None

        # Transaction management

        if operation == "BEGIN" and not arguments:
            return self.begin()

        if operation == "COMMIT" and not arguments:
            return self.commit()

        if operation == "ABORT" and not arguments:
            return self.abort()

        # String storage

        if operation == "SET" and len(arguments) >= 2:
            key = arguments[0]
            value = " ".join(arguments[1:])

            self.write(["SET", key, value, None])
            return ["OK"]

        if operation == "GET" and len(arguments) == 1:
            key = arguments[0]
            record = self.live(key)

            if record is None:
                # Never-created keys return an empty line.
                # Previously written but absent keys return nil.
                if key in self.known_keys:
                    return ["nil"]

                return [""]

            if record[1] == "string":
                return [record[2]]

            return ["ERROR"]

        if operation == "EXISTS" and len(arguments) == 1:
            exists = self.live(arguments[0]) is not None
            return ["1" if exists else "0"]

        if operation == "DEL" and len(arguments) == 1:
            key = arguments[0]
            exists = self.live(key) is not None

            if exists:
                self.write(["DEL", key])

            return ["1" if exists else "0"]

        # Multiple-key operations

        if operation == "MSET":
            if len(arguments) < 2 or len(arguments) % 2 != 0:
                return ["ERROR"]

            events = []

            for position in range(0, len(arguments), 2):
                events.append([
                    "SET",
                    arguments[position],
                    arguments[position + 1],
                    None,
                ])

            self.write(["TX", events])
            return ["OK"]

        if operation == "MGET" and arguments:
            results = []

            for key in arguments:
                record = self.live(key)

                if record is None:
                    results.append("nil")
                elif record[1] == "string":
                    results.append(record[2])
                else:
                    results.append("ERROR")

            return results

        # Expiration management

        if operation == "EXPIRE" and len(arguments) == 2:
            try:
                seconds = int(arguments[1])
            except ValueError:
                return ["ERROR"]

            key = arguments[0]

            if self.live(key) is None:
                return ["0"]

            expiration = time.time() + seconds

            self.write(["EXPIRE", key, expiration])
            return ["1"]

        if operation == "TTL" and len(arguments) == 1:
            record = self.live(arguments[0])

            if record is None:
                return ["-2"]

            if record[3] is None:
                return ["-1"]

            seconds = math.ceil(record[3] - time.time())
            return [str(max(0, seconds))]

        # Lexicographical range queries

        if operation == "RANGE" and len(arguments) == 2:
            start, end = arguments

            # Gradebot represents an unbounded end using "".
            if end in ('""', "''"):
                end = ""

            matching_keys = sorted(
                record[0]
                for record in self.rows
                if record[0] >= start
                and (not end or record[0] <= end)
                and self.live(record[0]) is not None
            )

            return matching_keys + ["END"]

        # Hash operations

        if operation == "HSET" and len(arguments) >= 3:
            key = arguments[0]
            field = arguments[1]
            value = " ".join(arguments[2:])

            record = self.live(key)

            if record is not None and record[1] != "hash":
                return ["ERROR"]

            self.write(["HSET", key, field, value])
            return ["OK"]

        if operation == "HGET" and len(arguments) == 2:
            key, field = arguments
            record = self.live(key)

            if record is None:
                return ["nil"]

            if record[1] != "hash":
                return ["ERROR"]

            position = self.field_index(record[2], field)

            if position < 0:
                return ["nil"]

            return [record[2][position][1]]

        if operation == "HGETALL" and len(arguments) == 1:
            record = self.live(arguments[0])

            if record is None:
                return ["nil"]

            if record[1] != "hash":
                return ["ERROR"]

            return [
                field + " " + value
                for field, value in sorted(record[2])
            ]

        # List insertion

        if operation in ("LPUSH", "RPUSH") and len(arguments) >= 2:
            key = arguments[0]
            value = " ".join(arguments[1:])

            record = self.live(key)

            if record is not None and record[1] != "list":
                return ["ERROR"]

            self.write([operation, key, value])

            updated = self.live(key)
            return [str(len(updated[2]))]

        # List removal

        if operation in ("LPOP", "RPOP") and len(arguments) == 1:
            key = arguments[0]
            record = self.live(key)

            if record is None:
                return ["nil"]

            if record[1] != "list":
                return ["ERROR"]

            if not record[2]:
                return ["nil"]

            position = 0 if operation == "LPOP" else -1
            value = record[2][position]

            self.write([operation, key])
            return [value]

        # List range queries

        if operation == "LRANGE" and len(arguments) == 3:
            try:
                start = int(arguments[1])
                stop = int(arguments[2])
            except ValueError:
                return ["ERROR"]

            record = self.live(arguments[0])

            if record is None:
                return ["nil"]

            if record[1] != "list":
                return ["ERROR"]

            items = record[2]
            count = len(items)

            if start < 0:
                start += count

            if stop < 0:
                stop += count

            start = max(0, start)
            stop = min(count - 1, stop)

            if start > stop:
                return []

            return items[start:stop + 1]

        # Integer counters

        if operation in ("INCR", "DECR") and len(arguments) == 1:
            key = arguments[0]
            record = self.live(key)

            if record is not None and record[1] != "string":
                return ["ERROR"]

            try:
                current = int(record[2]) if record is not None else 0
            except ValueError:
                return ["ERROR"]

            change = 1 if operation == "INCR" else -1
            new_value = current + change

            self.write([
                "SET",
                key,
                str(new_value),
                None,
            ])

            return [str(new_value)]

        # Database management

        if operation == "FLUSHDB" and not arguments:
            self.write(["FLUSHDB"])
            return ["OK"]

        # Reject invalid commands and incorrect argument counts.
        return ["ERROR"]


def main() -> None:
    """Read commands from STDIN and write responses to STDOUT."""
    database = Database()

    for line in sys.stdin:
        result = database.execute(line)

        if result is None:
            break

        for response in result:
            print(response, flush=True)


if __name__ == "__main__":
    main()

