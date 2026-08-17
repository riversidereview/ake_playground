from endfield_pcap.trace_bridge import TraceBridge


def test_scene_info_skills_maps_inst_to_template_for_cast_lines(tmp_path):
    trace_path = tmp_path / "trace.log"
    bridge = TraceBridge(trace_path)
    bridge.id_to_name[100844] = "chr_0019_karin"

    bridge.handle_event(
        {
            "type": "SC_SELF_SCENE_INFO_SKILLS",
            "timestamp_ms": 1_000,
            "owner_inst_id": 100844,
            "owner_templateid": "chr_0019_karin",
            "skills": [
                {
                    "owner_inst_id": 100844,
                    "skill_inst_id": 100849,
                    "template_type": "Skill",
                    "template_str_id": "chr_0019_karin_ultimate_skill",
                    "template_int_id": None,
                },
            ],
        }
    )
    bridge.handle_event(
        {
            "type": "BattleOpSkillStartCast",
            "timestamp_ms": 1_100,
            "seq_id": 307,
            "client_tick_tms": 23928,
            "owner_id": 100844,
            "skill_inst_id": 100849,
        }
    )

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    cast_line = next(line for line in lines if " SKILL_CAST_START " in line)
    assert "skill=chr_0019_karin_ultimate_skill" in cast_line


def test_scene_info_skills_does_not_override_attach_mapping(tmp_path):
    trace_path = tmp_path / "trace.log"
    bridge = TraceBridge(trace_path)
    bridge.id_to_name[100844] = "chr_0019_karin"

    bridge.handle_event(
        {
            "type": "BattleOpSkillAttach",
            "timestamp_ms": 900,
            "src_inst_id": 100844,
            "skill_inst_id": 100849,
            "template_str_id": "chr_0019_karin_combo_skill",
            "skill_source": "Default",
        }
    )
    bridge.handle_event(
        {
            "type": "SC_SELF_SCENE_INFO_SKILLS",
            "timestamp_ms": 1_000,
            "owner_inst_id": 100844,
            "owner_templateid": "chr_0019_karin",
            "skills": [
                {
                    "owner_inst_id": 100844,
                    "skill_inst_id": 100849,
                    "template_type": "Skill",
                    "template_str_id": "chr_0019_karin_ultimate_skill",
                    "template_int_id": None,
                },
            ],
        }
    )

    assert bridge.skill_id_by_inst[100849] == "chr_0019_karin_combo_skill"
