
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MAIN_FILE = Path(__file__).resolve().parents[1] / "main.py"


class TestKeyValueStore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def run_database(self, commands):
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
        output = self.run_database([
            "GET missing",
            "EXIT",
        ])
        self.assertEqual(output, ["NULL"])

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
            "EXIT",
        ])
        self.assertEqual(output, ["OK", "1", "1", "0"])

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
        self.assertEqual(output, ["OK", "1", "NULL", "-2"])

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
                "apple red",
                "banana yellow",
                "cherry pink",
            ],
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
        self.assertEqual(output, ["OK", "OK", "OK", "NULL"])

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
            ["OK", "OK", "Siya", "major CS", "name Siya"],
        )

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
        self.assertEqual(output, ["OK", "OK", "NULL"])

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
        self.assertEqual(output, ["Algorithms", "Database"])

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
        self.assertEqual(output, ["NULL"])


if __name__ == "__main__":
    unittest.main()
