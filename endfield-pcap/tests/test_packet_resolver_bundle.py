from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_bundle_builder_module():
    script_path = ROOT / "infra" / "scripts" / "build_packet_resolver_bundle.py"
    spec = importlib.util.spec_from_file_location("endfield_test_packet_resolver_bundle", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_best_available_bundle_merges_local_buff_numeric_map_into_canonical_export(tmp_path: Path) -> None:
    module = _load_bundle_builder_module()
    packet_root = tmp_path / "packet_semantics"
    packet_root.mkdir()
    (packet_root / "buff_numeric_map.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mappings": {
                    "3055": {
                        "canonical_buff_id": "buff_wpn_lance_0007_dmgup",
                        "role": "utility",
                    },
                    "3057": {
                        "canonical_buff_id": "buff_wpn_lance_0007_dmgup2",
                        "role": "effect",
                        "effects": [
                            {
                                "zone": "dmg_inc",
                                "element": "physical",
                                "bb_key": "dmg_up2",
                            }
                        ],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (packet_root / "skill_numeric_map.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mappings": {
                    "chr_0028_wulfa_skill_2257": {
                        "canonical_skill_id": "chr_0028_wulfa_combo_2_skill",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (packet_root / "actor_fingerprint_map.json").write_text(
        json.dumps(
            {
                "version": 1,
                "characters": {
                    "chr_0028_wulfa": {
                        "strong_skill_ids": ["2257"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    canonical_export = tmp_path / "canonical_export_bundle.json"
    canonical_export.write_text(
        json.dumps(
            {
                "version": 7,
                "resolver": {
                    "sources": {"canonical_seed": "canonical_export_bundle.json"},
                    "buffs": {
                        "by_numeric": {
                            "1": {"canonical_buff_id": "buff_existing", "role": "effect"},
                            "3057": {"canonical_buff_id": "stale_canonical_mapping"},
                        }
                    },
                    "skills": {
                        "by_owner_numeric": {
                            "chr_0023_antal_skill_2257": "chr_0023_antal_stale_skill",
                        },
                        "by_numeric_unique": {
                            "2257": "chr_0023_antal_stale_skill",
                        },
                        "strong_owner_by_numeric": {
                            "2257": "chr_0023_antal",
                        },
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = module.build_best_available_bundle(packet_root, canonical_export)

    by_numeric = bundle["buffs"]["by_numeric"]
    assert by_numeric["1"]["canonical_buff_id"] == "buff_existing"
    assert by_numeric["3055"]["canonical_buff_id"] == "buff_wpn_lance_0007_dmgup"
    assert by_numeric["3057"]["canonical_buff_id"] == "buff_wpn_lance_0007_dmgup2"
    assert by_numeric["3057"]["effects"][0]["bb_key"] == "dmg_up2"
    skills = bundle["skills"]
    assert skills["by_owner_numeric"]["chr_0028_wulfa_skill_2257"] == "chr_0028_wulfa_combo_2_skill"
    assert skills["by_numeric_unique"]["2257"] == "chr_0028_wulfa_combo_2_skill"
    assert skills["strong_owner_by_numeric"]["2257"] == "chr_0028_wulfa"
    assert bundle["sources"]["canonical_export_bundle"] == str(canonical_export.resolve())
    assert bundle["sources"]["buff_numeric_map"] == "buff_numeric_map.json"
    assert bundle["sources"]["skill_numeric_map"] == "skill_numeric_map.json"
    assert bundle["sources"]["actor_fingerprint_map"] == "actor_fingerprint_map.json"
