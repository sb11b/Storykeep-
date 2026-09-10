from __future__ import annotations

import unittest

from app.database import parse_database_url


class DatabaseUrlTests(unittest.TestCase):
    def test_local_url_has_no_ssl(self):
        row = parse_database_url(
            "postgresql+psycopg2://storykeep:storykeep@127.0.0.1:5432/storykeep"
        )
        self.assertEqual(row.host, "127.0.0.1")
        self.assertEqual(row.port, 5432)
        self.assertEqual(row.user, "storykeep")
        self.assertEqual(row.password, "storykeep")
        self.assertEqual(row.database, "storykeep")
        self.assertEqual(row.connect_args, {})

    def test_docker_compose_db_host_has_no_ssl(self):
        row = parse_database_url("postgresql://storykeep:storykeep@db:5432/storykeep")
        self.assertEqual(row.host, "db")
        self.assertEqual(row.connect_args, {})

    def test_railway_private_dns_has_no_ssl(self):
        row = parse_database_url("postgresql://u:p@postgres.railway.internal:5432/railway")
        self.assertEqual(row.host, "postgres.railway.internal")
        self.assertEqual(row.connect_args, {})

    def test_railway_public_proxy_ignores_url_ssl_query(self):
        raw = (
            "postgresql://user:p%40ss@switchyard.proxy.rlwy.net:12345/railway"
            "?sslmode=verify-full&sslrootcert=/etc/ssl/cert.pem"
        )
        row = parse_database_url(raw)
        self.assertEqual(row.host, "switchyard.proxy.rlwy.net")
        self.assertEqual(row.port, 12345)
        self.assertEqual(row.user, "user")
        self.assertEqual(row.password, "p@ss")
        self.assertEqual(row.database, "railway")
        self.assertEqual(row.connect_args, {"sslmode": "require"})
        rendered = row.url.render_as_string(hide_password=False)
        self.assertNotIn("sslmode", rendered)
        self.assertNotIn("sslrootcert", rendered)
        self.assertNotIn("verify-full", rendered)

    def test_postgres_scheme_and_default_port(self):
        row = parse_database_url("postgres://u:p@db.example.com/app")
        self.assertEqual(row.port, 5432)
        self.assertEqual(row.url.drivername, "postgresql+psycopg2")
        self.assertEqual(row.connect_args["sslmode"], "require")


if __name__ == "__main__":
    unittest.main()
