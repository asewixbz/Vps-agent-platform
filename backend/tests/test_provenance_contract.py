from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import memory_graph


class ProvenanceContractTests(TestCase):
    def setUp(self) -> None:
        self.settings = object()
        self.records = {
            "root": {
                "id": "root",
                "kind": "runtime_summary",
                "scope_type": "runtime_run",
                "scope_id": "run-1",
                "title": "Root Run",
                "summary": "Root summary",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "child": {
                "id": "child",
                "kind": "contact_dossier",
                "scope_type": "contact",
                "scope_id": "contact-1",
                "title": "Child Record",
                "summary": "Child summary",
                "updated_at": "2026-01-01T01:00:00Z",
            },
            "grandchild": {
                "id": "grandchild",
                "kind": "project_dossier",
                "scope_type": "project",
                "scope_id": "project-1",
                "title": "Grandchild Record",
                "summary": "Grandchild summary",
                "updated_at": "2026-01-01T02:00:00Z",
            },
        }
        self.artifacts = {
            "root": [
                {
                    "id": "a1",
                    "artifact_type": "file",
                    "artifact_ref": "artifact://root-note",
                    "label": "root note",
                }
            ],
            "child": [
                {
                    "id": "a2",
                    "artifact_type": "file",
                    "artifact_ref": "artifact://child-note",
                    "label": "child note",
                }
            ],
            "grandchild": [
                {
                    "id": "a3",
                    "artifact_type": "file",
                    "artifact_ref": "artifact://grand-note",
                    "label": "grand note",
                }
            ],
        }
        self.links = {
            "root": [
                {
                    "id": "l1",
                    "source_type": "memory_record",
                    "source_id": "root",
                    "target_type": "memory_record",
                    "target_id": "child",
                    "relation_type": "updates",
                    "note": "root to child",
                    "created_at": "2026-01-01T00:30:00Z",
                },
                {
                    "id": "l2",
                    "source_type": "artifact",
                    "source_id": "artifact://root-note",
                    "target_type": "memory_record",
                    "target_id": "root",
                    "relation_type": "references",
                    "note": "root artifact",
                    "created_at": "2026-01-01T00:45:00Z",
                },
            ],
            "child": [
                {
                    "id": "l3",
                    "source_type": "memory_record",
                    "source_id": "child",
                    "target_type": "memory_record",
                    "target_id": "grandchild",
                    "relation_type": "updates",
                    "note": "child to grandchild",
                    "created_at": "2026-01-01T01:30:00Z",
                },
                {
                    "id": "l4",
                    "source_type": "artifact",
                    "source_id": "artifact://child-note",
                    "target_type": "memory_record",
                    "target_id": "child",
                    "relation_type": "references",
                    "note": "child artifact",
                    "created_at": "2026-01-01T01:45:00Z",
                },
            ],
            "grandchild": [
                {
                    "id": "l5",
                    "source_type": "artifact",
                    "source_id": "artifact://grand-note",
                    "target_type": "memory_record",
                    "target_id": "grandchild",
                    "relation_type": "references",
                    "note": "grand artifact",
                    "created_at": "2026-01-01T02:30:00Z",
                }
            ],
        }

    def _get_memory_record(self, settings: object, memory_record_id: str) -> dict[str, object] | None:
        return self.records.get(memory_record_id)

    def _list_memory_record_artifacts(self, settings: object, memory_record_id: str) -> list[dict[str, object]]:
        return list(self.artifacts.get(memory_record_id, []))

    def _record_links(self, settings: object, record_id: str, *, limit: int) -> list[dict[str, object]]:
        return list(self.links.get(record_id, []))

    @patch("app.memory_graph.get_memory_record")
    @patch("app.memory_graph.list_memory_record_artifacts")
    @patch("app.memory_graph._memory_record_links_for_record")
    def test_build_memory_record_provenance_sections(self, mock_links, mock_artifacts, mock_get_record) -> None:
        mock_get_record.side_effect = self._get_memory_record
        mock_artifacts.side_effect = self._list_memory_record_artifacts
        mock_links.side_effect = self._record_links

        provenance = memory_graph.build_memory_record_provenance(self.settings, memory_record_id="root", limit=10, depth=3)

        self.assertIsNotNone(provenance)
        self.assertEqual(provenance["root"]["id"], "root")
        self.assertEqual(provenance["root"]["section"], "root")
        self.assertEqual([record["id"] for record in provenance["one_hop"]], ["child"])
        self.assertEqual([record["id"] for record in provenance["transitive"]], ["grandchild"])
        self.assertEqual(provenance["artifact_only"]["artifact_count"], 3)
        self.assertEqual(provenance["traversal"]["one_hop_record_count"], 1)
        self.assertEqual(provenance["traversal"]["transitive_record_count"], 1)
        self.assertEqual(provenance["summary"]["one_hop_record_count"], 1)
        self.assertEqual(provenance["summary"]["transitive_record_count"], 1)
        self.assertEqual(provenance["artifact_only"]["refs"], [
            "artifact://root-note",
            "artifact://child-note",
            "artifact://grand-note",
        ])

    @patch("app.memory_graph.find_runtime_snapshot")
    @patch("app.memory_graph.build_memory_record_provenance")
    def test_build_runtime_run_provenance_wraps_snapshot(self, mock_build_provenance, mock_find_snapshot) -> None:
        mock_find_snapshot.return_value = self.records["root"]
        mock_build_provenance.return_value = {
            "root": {**self.records["root"], "section": "root", "depth": 0, "artifact_count": 1, "artifacts": self.artifacts["root"]},
            "one_hop": [],
            "transitive": [],
            "artifact_only": {"artifacts": [], "links": [], "refs": []},
        }

        provenance = memory_graph.build_runtime_run_provenance(self.settings, runtime_run_id="run-1", limit=10, depth=2)

        self.assertEqual(provenance["runtime_run_id"], "run-1")
        self.assertEqual(provenance["memory_snapshot"]["id"], "root")
        self.assertEqual(provenance["provenance"]["root"]["id"], "root")
        mock_build_provenance.assert_called_once_with(self.settings, memory_record_id="root", limit=10, depth=2)
