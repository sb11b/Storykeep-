from __future__ import annotations

import unittest

from app.database import parse_database_url


class DatabaseUrlTests(unittest.TestCase):
    def test_local_url_has_no_ssl_and_no_query(self):
        url, connect_args = parse_database_url(
            "postgresql+psycopg2://storykeep:storykeep@127.0.0.1:5432/storykeep"
        )
        self.assertEqual(url.host, "127.0.0.1")
        self.assertEqual(url.port, 5432)
        self.assertEqual(url.username, "storykeep")
        self.assertEqual(url.password, "storykeep")
        self.assertEqual(url.database, "storykeep")
        self.assertEqual(connect_args, {})
        self.assertIsNone(url.query.get("sslmode") if url.query else None)

    def test_railway_public_url_ignores_ssl_query(self):
        raw = (
            "postgresql://user:p%40ss@switchyard.proxy.rlwy.net:12345/railway"
            "?sslmode=verify-full&sslrootcert=/etc/ssl/cert.pem"
        )
        url, connect_args = parse_database_url(raw)
        self.assertEqual(url.host, "switchyard.proxy.rlwy.net")
        self.assertEqual(url.port, 12345)
        self.assertEqual(url.username, "user")
        self.assertEqual(url.password, "p@ss")
        self.assertEqual(url.database, "railway")
        self.assertEqual(connect_args, {"sslmode": "require"})
        rendered = url.render_as_string(hide_password=False)
        self.assertNotIn("sslmode", rendered)
        self.assertNotIn("sslrootcert", rendered)
        self.assertNotIn("verify-full", rendered)

    def test_postgres_scheme_and_default_port(self):
        url, connect_args = parse_database_url("postgres://u:p@db.example.com/app")
        self.assertEqual(url.port, 5432)
        self.assertEqual(url.drivername, "postgresql+psycopg2")
        self.assertEqual(connect_args["sslmode"], "require")


if __name__ == "__main__":
    unittest.main()
