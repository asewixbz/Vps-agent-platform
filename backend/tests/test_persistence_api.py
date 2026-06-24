from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.persistence_api as persistence_api
from app.persistence_migrations import ensure_persistence_schema, get_schema_metadata, list_schema_metadata
from app.settings import Settings
from app.store import init_db


class PersistenceApiTests(TestCase):
    def _settings(self, tmpdir: str) -> Settings:
        return Settings(
            db_path=str(Path(tmpdir) / "app.db"),
            work_dir=str(Path(tmpdir) / "work"),
            default_timeout_seconds=5,
            require_approval_for_draft=False,
        )

    def test_persistence_schema_snapshot_is_seeded_and_queryable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            init_db(settings)
            seeded = ensure_persistence_schema(settings)

            with patch.object(persistence_api, "settings", settings):
                layers = persistence_api.persistence_layers()
                snapshot = persistence_api.persistence_schema()

            direct = get_schema_metadata(settings)
            all_rows = list_schema_metadata(settings)

            self.assertEqual(layers["schema_name"], "persistence")
            self.assertEqual(layers["schema_metadata_contract"]["schema_name"], "persistence")
            self.assertEqual(snapshot["schema_name"], "persistence")
            self.assertTrue(snapshot["present"])
            self.assertEqual(snapshot["current"]["schema_name"], "persistence")
            self.assertEqual(snapshot["current"]["schema_version"], 1)
            self.assertEqual(snapshot["current"]["metadata"]["versioning_model"], "single-row upsert")
            self.assertEqual(snapshot["current"]["metadata"]["schema_name"], "persistence")
            self.assertEqual(seeded["schema_name"], "persistence")
            self.assertEqual(seeded["schema_version"], 1)
            self.assertEqual(direct["schema_name"], "persistence")
            self.assertEqual(direct["schema_version"], 1)
            self.assertEqual(len(all_rows), 1)
            self.assertEqual(all_rows[0]["schema_name"], "persistence")
            self.assertEqual(all_rows[0]["metadata"]["migration_path"][0], "introduce persistence adapter boundary")
