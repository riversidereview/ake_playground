from upload_domain import ParsedBattleCandidate, ValidationStatus


def test_upload_domain_exports() -> None:
    candidate = ParsedBattleCandidate(
        local_id="candidate-1",
        dungeon_name="Dungeon",
        boss_name="Boss",
        validation_status=ValidationStatus.PASS,
    )
    assert candidate.validation_status == ValidationStatus.PASS

