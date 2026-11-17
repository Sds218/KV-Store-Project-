
"""Automated tests for the  persistent key-value database.

Tests validate command execution , transactions,
expiration, hashes, lists, counters, and database management.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MAIN_FILE = Path(__file__).resolve().parents[1] / "main.py"


class TestKeyValueStore(unittest.TestCase):
    """Black-box tests for the key-value store CLI."""

    def setUp(self):
        """Create an isolated temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def run_database(self, commands):
        """Run database commands and capture output."""
        result = subprocess.run(
            [sys.executable, str(MAIN_FILE)],
            input="\n".join(commands) + "\n",
            text=True,
            capture_output=True,
            cwd=self.temp_dir.name,
            timeout=10,
            check=True,
        )

        self.assertEqual(result.stderr, "")
        return result.stdout.strip().splitlines()

    def test_set_get(self):
        output = self.run_database([
            "SET name Siya",
            "GET name",
            "EXIT",
        ])
        self.assertEqual(output, ["OK", "Siya"])

    def test_overwrite(self):
        output = self.run_database([
            "SET city Denton",
            "SET city Dallas",
            "GET city",
            "EXIT",
        ])
        self.assertEqual(output, ["OK", "OK", "Dallas"])

    def test_missing_key(self):
        """A never-created key returns a blank response."""
        output = self.run_database([
            "GET missing",
            "EXIT",
        ])
        self.assertEqual(output, [])

    def test_persistence(self):
        self.run_database([
            "SET university UNT",
            "EXIT",
        ])

        output = self.run_database([
            "GET university",
            "EXIT",
        ])
        self.assertEqual(output, ["UNT"])

        database_file = Path(self.temp_dir.name) / "data.db"
        self.assertTrue(database_file.exists())

    def test_delete_exists(self):
        output = self.run_database([
            "SET name Siya",
            "EXISTS name",
            "DEL name",
            "EXISTS name",
            "GET name",
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["OK", "1", "1", "0", "nil"],
        )

    def test_multiple_keys(self):
        output = self.run_database([
            "MSET a 10 b 20 c 30",
            "MGET a b c",
            "EXIT",
        ])
        self.assertEqual(output, ["OK", "10", "20", "30"])

    def test_expiration(self):
        output = self.run_database([
            "SET temporary hello",
            "EXPIRE temporary 0",
            "GET temporary",
            "TTL temporary",
            "EXIT",
        ])
        self.assertEqual(output, ["OK", "1", "nil", "-2"])

    def test_range(self):
        output = self.run_database([
            "SET apple red",
            "SET banana yellow",
            "SET cherry pink",
            "RANGE apple cherry",
            "EXIT",
        ])

        self.assertEqual(
            output,
            [
                "OK",
                "OK",
                "OK",
                "apple",
                "banana",
                "cherry",
                "END",
            ],
        )

    def test_range_unbounded(self):
        output = self.run_database([
            "SET d 4",
            "SET e 5",
            'RANGE d ""',
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["OK", "OK", "d", "e", "END"],
        )

    def test_transaction_commit(self):
        self.run_database([
            "BEGIN",
            "SET student Siya",
            "COMMIT",
            "EXIT",
        ])

        output = self.run_database([
            "GET student",
            "EXIT",
        ])
        self.assertEqual(output, ["Siya"])

    def test_transaction_abort(self):
        output = self.run_database([
            "BEGIN",
            "SET student Siya",
            "ABORT",
            "GET student",
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["OK", "OK", "OK", "nil"],
        )

    def test_hashes(self):
        output = self.run_database([
            "HSET student name Siya",
            "HSET student major CS",
            "HGET student name",
            "HGETALL student",
            "EXIT",
        ])

        self.assertEqual(
            output,
            [
                "OK",
                "OK",
                "Siya",
                "major CS",
                "name Siya",
            ],
        )

    def test_hash_persistence(self):
        self.run_database([
            "HSET student major CS",
            "EXIT",
        ])

        output = self.run_database([
            "HGET student major",
            "EXIT",
        ])
        self.assertEqual(output, ["CS"])

    def test_lists(self):
        output = self.run_database([
            "LPUSH subjects Algorithms",
            "RPUSH subjects Database",
            "LRANGE subjects 0 -1",
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["1", "2", "Algorithms", "Database"],
        )

    def test_list_persistence(self):
        self.run_database([
            "LPUSH subjects Algorithms",
            "RPUSH subjects Database",
            "EXIT",
        ])

        output = self.run_database([
            "LRANGE subjects 0 -1",
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["Algorithms", "Database"],
        )

    def test_list_pop(self):
        output = self.run_database([
            "RPUSH items first",
            "RPUSH items second",
            "RPUSH items third",
            "LPOP items",
            "RPOP items",
            "LRANGE items 0 -1",
            "EXIT",
        ])

        self.assertEqual(
            output,
            ["1", "2", "3", "first", "third", "second"],
        )

    def test_list_pop_persistence(self):
        self.run_database([
            "RPUSH items first",
            "RPUSH items second",
            "LPOP items",
            "EXIT",
        ])

        output = self.run_database([
            "LRANGE items 0 -1",
            "EXIT",
        ])

        self.assertEqual(output, ["second"])

    def test_counters(self):
        output = self.run_database([
            "INCR count",
            "INCR count",
            "DECR count",
            "GET count",
            "EXIT",
        ])

        self.assertEqual(output, ["1", "2", "1", "1"])

    def test_flushdb(self):
        output = self.run_database([
            "SET name Siya",
            "FLUSHDB",
            "GET name",
            "EXIT",
        ])

        self.assertEqual(output, ["OK", "OK", "nil"])

    def test_flushdb_persistence(self):
        self.run_database([
            "SET name Siya",
            "FLUSHDB",
            "EXIT",
        ])

        output = self.run_database([
            "GET name",
            "EXIT",
        ])

        self.assertEqual(output, ["nil"])


if __name__ == "__main__":
    unittest.main()
