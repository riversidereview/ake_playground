from endfield_pcap.trace_bridge import TraceBridge


def test_skill_cast_line_keeps_skill_source(tmp_path):
    trace_path = tmp_path / "trace.log"
    bridge = TraceBridge(trace_path)
    bridge.id_to_name[100616] = "chr_0028_wulfa"

    bridge.handle_event(
        {
            "type": "BattleOpSkillAttach",
            "timestamp_ms": 1_000,
            "src_inst_id": 100616,
            "skill_inst_id": 23001,
            "template_str_id": "chr_0028_wulfa_power_attack",
            "skill_source": "PowerAttack",
        }
    )
    bridge.handle_event(
        {
            "type": "BattleOpSkillStartCast",
            "timestamp_ms": 1_100,
            "seq_id": 42,
            "client_tick_tms": 3200,
            "owner_id": 100616,
            "skill_inst_id": 23001,
        }
    )

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    cast_line = next(line for line in lines if " SKILL_CAST_START " in line)
    assert "skill=chr_0028_wulfa_power_attack" in cast_line
    assert "skillSource=PowerAttack" in cast_line


def test_modify_poise_value_writes_poise_trace(tmp_path):
    trace_path = tmp_path / "trace.log"
    bridge = TraceBridge(trace_path)
    bridge.id_to_name[100616] = "chr_0028_wulfa"

    bridge.handle_event(
        {
            "type": "BattleOpModifyPoiseValue",
            "timestamp_ms": 1_200,
            "seq_id": 43,
            "client_tick_tms": 3300,
            "modify_type": "PoiseDamage",
            "owner_type": "Skill",
            "value": 5.0,
            "cur_poise_value": 15.0,
            "attacker_inst_id": 100616,
            "template_type": "Skill",
            "template_str_id": "chr_0028_wulfa_power_attack",
            "orig_template_type": "Skill",
            "orig_template_str_id": "chr_0028_wulfa_power_attack",
            "action_id": 117,
        }
    )

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    poise_line = next(line for line in lines if " POISE_V1 " in line)
    assert "type=PoiseDamage" in poise_line
    assert "value=5" in poise_line
    assert "cur=15" in poise_line
    assert "attacker=chr_0028_wulfa" in poise_line
    assert "source=chr_0028_wulfa_power_attack" in poise_line
