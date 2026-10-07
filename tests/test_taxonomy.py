from pipeline.taxonomy import load_taxonomy


def test_taxonomy_loads_by_id():
    taxonomy = load_taxonomy()
    assert taxonomy.version == "v0"
    node = taxonomy.get("incomplete_memory_place_event")
    assert node.parent_id == "incomplete_memory"
    assert "Goa" in node.examples[0] or "café" in node.examples[0].lower()


def test_distinct_non_memory_nodes_exist():
    taxonomy = load_taxonomy()
    ids = taxonomy.ids()
    assert "query_failure_complete_info" in ids
    assert "deleted_locked_partner_sharing" in ids
    assert "backup_sync_storage" in ids
