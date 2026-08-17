from __future__ import annotations

from pathlib import Path

from endfield_pcap.rdps_audit import audit_trace, audit_trace_batch, format_audit_markdown, format_batch_audit_markdown


ROOT = Path(__file__).resolve().parents[1]


def _loadout_lines(*, aglina_suit: str = "{}") -> list[str]:
    return [
        "[09:59:59.000] SQUAD size=4 members=[chr_0004_pelica chr_0013_aglina chr_0027_tangtang chr_0028_wulfa]",
        "[09:59:59.000] LOADOUT slot=0 char=chr_0004_pelica weaponTemplate=wpn_funnel_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
        f"[09:59:59.000] LOADOUT slot=1 char=chr_0013_aglina weaponTemplate=wpn_funnel_0005 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={{}} equips={{}} equipSuit={aglina_suit}",
        "[09:59:59.000] LOADOUT slot=2 char=chr_0027_tangtang weaponTemplate=wpn_pistol_0011 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
        "[09:59:59.000] LOADOUT slot=3 char=chr_0028_wulfa weaponTemplate=wpn_sword_0022 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
    ]


def _write_trace(tmp_path: Path, name: str, lines: list[str]) -> Path:
    trace = tmp_path / name
    trace.write_text("\n".join(lines), encoding="utf-8")
    return trace


def test_audit_accepts_static_table_and_mechanism_buff_ids(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "numeric-buffs.dat",
        [
            *_loadout_lines(aglina_suit="{[suit_usp02]=3}"),
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="2268" uid=1 owner=eny_0051_rodin src=chr_0004_pelica dur=8.75 lifeT=8.75 passed=0.00 enh=1',
            "[10:00:00.100]   BB[1]: spell_resistance_decrease=0.233551 duration=8.75 final_spell_resistance_decrease=0.310623 count=1 extra_scaling=1.33",
            '[10:00:00.200] BUFF_START #2 id="327" uid=2 owner=eny_0051_rodin src=chr_0013_aglina dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.200]   BB[2]: def_decrease=0.0406473 max_def_decrease=0.135491 duration=15 def_decrease_tick=0.00948438 start_def_decrease=0.0406473 count=1",
            '[10:00:00.300] BUFF_START #3 id="buff_equipsuit_usp_02_dmgup" uid=3 owner=chr_0004_pelica src=chr_0013_aglina dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.300]   BB[3]: hp_up=1000 dmg_up=0.16 duration=15",
            '[10:00:00.400] BUFF_START #4 id="1645" uid=4 owner=chr_0027_tangtang src=chr_0013_aglina dur=20.00 lifeT=20.00 passed=0.00 enh=1',
            "[10:00:00.400]   BB[4]: atk_up=0.224 duration=20 lv=9",
            '[10:00:00.500] HP_V2 #4 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0027_tangtang_attack1" hits=1 src=chr_0027_tangtang tgt=eny_0051_rodin atk=chr_0027_tangtang seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    assert audit["hard_blockers"] == []
    buffs = audit["buffs"]
    assert buffs["unresolved_rdps_effect_ids"] == []
    assert dict(buffs["accepted_static_table_ids"])["2268"] == 1
    assert dict(buffs["accepted_static_table_ids"])["327"] == 1
    accepted = {row[0]: row for row in buffs["accepted_packet_mapped_ids"]}
    assert accepted["2268"][2] == "buff_common_pulse_pulse_conduct_triggered_do"
    assert accepted["1645"][2] == "buff_wpn_funnel_0005_atk_up"
    assert accepted["buff_equipsuit_usp_02_dmgup"][2] == "buff_equipsuit_usp_02_AddAttack"
    proof = audit["damage"]["per_hit_rdps"]["rdps_proof"]
    assert proof["external_credit_evidence_ok"] is True
    assert proof["external_contribution_rows"] >= 1
    assert {
        (row["source_character_key"], row["event_key"], row["zone"])
        for row in proof["external_credit_by_buff"]
    } >= {("chr_0013_aglina", "buff_wpn_funnel_0005_atk_up", "atk")}
    trust = audit["damage"]["per_hit_rdps"]["rdps_trust_audit"]
    assert trust["ok"] is True
    assert trust["accepted_effect_buff_count"] >= 1
    assert any(row["event_key"] == "buff_wpn_funnel_0005_atk_up" for row in trust["accepted_rows"])
    markdown = format_audit_markdown(audit)
    assert "## rDPS 可信度审计" in markdown
    assert "白名单命中并进入外部 rDPS 窗口" in markdown


def test_audit_blocks_unresolved_rdps_effect_buff(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "unknown-rdps-buff.dat",
        [
            *_loadout_lines(),
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="999999" uid=1 owner=eny_0051_rodin src=chr_0004_pelica dur=5.00 lifeT=5.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[1]: dmg_up=0.2 duration=5",
            '[10:00:00.500] HP_V2 #2 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0027_tangtang_attack1" hits=1 src=chr_0027_tangtang tgt=eny_0051_rodin atk=chr_0027_tangtang seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is False
    assert "unresolved_rdps_effect_buff" in audit["hard_blockers"]
    assert dict(audit["buffs"]["rdps_relevant_unresolved_after_equipment"]) == {"999999": 1}
    trust = audit["damage"]["per_hit_rdps"]["rdps_trust_audit"]
    assert trust["blocker_count"] >= 1


def test_audit_blocks_unresolved_potential_external_rdps_buff(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "unknown-external-buff.dat",
        [
            *_loadout_lines(),
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="999998" uid=1 owner=eny_0051_rodin src=chr_0004_pelica dur=5.00 lifeT=5.00 passed=0.00 enh=1',
            '[10:00:00.500] HP_V2 #2 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0027_tangtang_attack1" hits=1 src=chr_0027_tangtang tgt=eny_0051_rodin atk=chr_0027_tangtang seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is False
    assert "unresolved_potential_rdps_buff" in audit["hard_blockers"]
    assert dict(audit["buffs"]["rdps_potential_unresolved_after_equipment"]) == {"999998": 1}


def test_audit_accepts_lizhiyan_elemental_fragile_children_and_wrappers(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "lizhiyan-fragile.dat",
        [
            "[09:59:59.000] SQUAD size=4 members=[chr_0032_lizhiyan chr_0017_yvonne chr_0025_ardelia chr_0004_pelica]",
            "[09:59:59.000] LOADOUT slot=0 char=chr_0032_lizhiyan weaponTemplate=wpn_funnel_0002 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={[0]=1 [1]=2 [2]=3 [3]=4} equips={} equipSuit={[suit_combo_cd01]=3}",
            "[09:59:59.000] LOADOUT slot=1 char=chr_0017_yvonne weaponTemplate=wpn_pistol_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={[0]=5 [1]=6 [2]=7 [3]=8} equips={} equipSuit={[suit_combo_cd01]=3}",
            "[09:59:59.000] LOADOUT slot=2 char=chr_0025_ardelia weaponTemplate=wpn_funnel_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={[0]=9 [1]=10 [2]=11 [3]=12} equips={} equipSuit={[suit_combo_cd01]=3}",
            "[09:59:59.000] LOADOUT slot=3 char=chr_0004_pelica weaponTemplate=wpn_funnel_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={[0]=13 [1]=14 [2]=15 [3]=16} equips={} equipSuit={[suit_combo_cd01]=3}",
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="2918" uid=parent owner=eny_0051_rodin src=chr_0032_lizhiyan dur=6.00 lifeT=6.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[parent]: rate=0.2 duration_vul=6 isWisd=1",
            '[10:00:00.200] BUFF_START #2 id="4024" uid=cryst owner=eny_0051_rodin src=chr_0032_lizhiyan dur=6.00 lifeT=6.00 passed=0.00 enh=1',
            "[10:00:00.200]   BB[cryst]: rate=0.2 duration=6",
            '[10:00:00.300] BUFF_START #3 id="4025" uid=natural owner=eny_0051_rodin src=chr_0032_lizhiyan dur=6.00 lifeT=6.00 passed=0.00 enh=1',
            "[10:00:00.300]   BB[natural]: rate=0.2 duration=6",
            '[10:00:00.500] HP_V2 #4 hit=120 cum=120 raw=120.00 packetFinalValue=120.0 pHP=5000 eHP=899880 skill="chr_0017_yvonne_ult_attack1_projhit" hits=1 src=chr_0017_yvonne tgt=eny_0051_rodin atk=chr_0017_yvonne seg=0 shared=2 critFlag=0 critDmg=0.5000',
            '[10:00:00.700] HP_V2 #5 hit=110 cum=230 raw=110.00 packetFinalValue=110.0 pHP=5000 eHP=899770 skill="chr_0025_ardelia_remain_loop_sheep" hits=1 src=chr_0025_ardelia tgt=eny_0051_rodin atk=chr_0025_ardelia seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    assert audit["hard_blockers"] == []
    credited = {
        (row["event_key"], row["zone"])
        for row in audit["damage"]["per_hit_rdps"]["rdps_proof"]["external_credit_by_buff"]
    }
    assert ("buff_common_affixes_vulnerable_crystal_lizhiyan_child", "fragile") in credited
    assert ("buff_common_affixes_vulnerable_natural_lizhiyan_child", "fragile") in credited
    assert ("buff_chr_0032_lizhiyan_combo_skill_spell_vulnerable", "fragile") not in credited


def test_audit_accepts_20260716_weapon_rdps_effects(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "weapon-effects-20260716.dat",
        [
            "[09:59:59.000] SQUAD size=4 members=[chr_0032_lizhiyan chr_0017_yvonne chr_0025_ardelia chr_0004_pelica]",
            "[09:59:59.000] LOADOUT slot=0 char=chr_0032_lizhiyan weaponTemplate=wpn_funnel_0016 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[09:59:59.000] LOADOUT slot=1 char=chr_0017_yvonne weaponTemplate=wpn_funnel_0018 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[09:59:59.000] LOADOUT slot=2 char=chr_0025_ardelia weaponTemplate=wpn_lance_0016 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[09:59:59.000] LOADOUT slot=3 char=chr_0004_pelica weaponTemplate=wpn_sword_0026 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="3723" uid=will_atk owner=eny_0051_rodin src=chr_0032_lizhiyan dur=4.00 lifeT=4.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[will_atk]: spell_dmg_taken_up=0.12 duration=4",
            '[10:00:00.110] BUFF_START #2 id="3724" uid=will_dmg owner=eny_0051_rodin src=chr_0032_lizhiyan dur=4.00 lifeT=4.00 passed=0.00 enh=1',
            "[10:00:00.110]   BB[will_dmg]: spell_dmg_taken_up2=0.08 duration=4",
            '[10:00:00.120] BUFF_START #3 id="3606" uid=link owner=chr_0025_ardelia src=chr_0017_yvonne dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.120]   BB[link]: atk_up2=0.16 duration=15",
            '[10:00:00.130] BUFF_START #4 id="3607" uid=gold owner=chr_0017_yvonne src=chr_0025_ardelia dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.130]   BB[gold]: spell_dmg_up=0.16 duration=15",
            '[10:00:00.140] BUFF_START #5 id="3740" uid=celebration owner=chr_0017_yvonne src=chr_0004_pelica dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.140]   BB[celebration]: dmg_up=0.12 phy_spell_up=20 def_up=20 hp_up=20 duration=15",
            '[10:00:00.500] HP_V2 #6 hit=120 cum=120 raw=120.00 packetFinalValue=120.0 pHP=5000 eHP=899880 skill="chr_0017_yvonne_ult_attack1_projhit" hits=1 src=chr_0017_yvonne tgt=eny_0051_rodin atk=chr_0017_yvonne seg=0 shared=2 critFlag=0 critDmg=0.5000',
            '[10:00:00.700] HP_V2 #7 hit=110 cum=230 raw=110.00 packetFinalValue=110.0 pHP=5000 eHP=899770 skill="chr_0025_ardelia_remain_loop_sheep" hits=1 src=chr_0025_ardelia tgt=eny_0051_rodin atk=chr_0025_ardelia seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    assert audit["hard_blockers"] == []
    credited = {
        (row["event_key"], row["zone"])
        for row in audit["damage"]["per_hit_rdps"]["rdps_proof"]["external_credit_by_buff"]
    }
    assert credited >= {
        ("buff_wpn_funnel_0016_will_atk", "vuln_taken"),
        ("buff_wpn_funnel_0016_will_dmg", "vuln_taken"),
        ("buff_wpn_funnel_0018_layer_teammates", "atk"),
        ("buff_wpn_lance_0016_dmgup", "dmg_inc"),
        ("buff_wpn_sword_0026_celebration", "dmg_inc"),
    }


def test_audit_accepts_trial_numeric_effects_with_stale_previous_loadout(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "trial-stale-loadout.dat",
        [
            *_loadout_lines(),
            "[09:59:59.500] SQUAD size=4 members=[chr_0032_lizhiyan chr_0017_yvonne chr_0019_karin chr_0006_wolfgd]",
            "[10:00:00.000] OFFICIAL_TIMER_START source=SC_GAME_MECHANICS_SYNC_CHALLENGE_START gameId=dung_lizhiyan_chartrial challengeStartTs=1000",
            "[10:00:00.100] GAME_TIMER_START seq=1 source=PacketBattleState startMs=1000 expireMs=0 official=1",
            '[10:00:00.200] BUFF_START #1 id="3724" uid=will_dmg owner=eny_0063_agmelee2 src=chr_0032_lizhiyan dur=25.00 lifeT=25.00 passed=0.00 enh=1',
            "[10:00:00.200] BB[will_dmg]: spell_dmg_taken_up2=0.084 duration4=25 duration_dynamic=25",
            '[10:00:00.250] BUFF_START #2 id="1407" uid=team_dmg owner=chr_0017_yvonne src=chr_0019_karin dur=15.00 lifeT=15.00 passed=0.00 enh=1',
            "[10:00:00.250] BB[team_dmg]: dmg_up=0.16 duration=15",
            '[10:00:00.950] HP_V2 #3 hit=1000 cum=1000 raw=1000.00 packetFinalValue=1000.0 pHP=5000 eHP=900000 skill="chr_0017_yvonne_ult_attack1_projhit" hits=1 src=chr_0017_yvonne tgt=eny_0063_agmelee2 atk=chr_0017_yvonne seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=PacketBattleState elapsedMs=900 startMs=1000 endMs=1900 expireMs=0 sane=1 official=1",
            "[10:00:01.100] OFFICIAL_TIMER_END source=SC_GAME_MECHANICS_SYNC_CHALLENGE_COMPLETE gameId=dung_lizhiyan_chartrial isPass=1 passTime=1000",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    per_hit = audit["damage"]["per_hit_rdps"]
    assert per_hit["parsed_hit_count"] == per_hit["expected_hit_count"] == 1
    assert per_hit["rdps_trust_audit"]["ok"] is True
    credited = {
        (row["source_character_key"], row["event_key"])
        for row in per_hit["rdps_proof"]["external_credit_by_buff"]
    }
    assert ("chr_0032_lizhiyan", "buff_wpn_funnel_0016_will_dmg") in credited
    assert ("chr_0019_karin", "buff_equipsuit_combosuit_01_adddamage") in credited


def test_audit_accepts_mifu_self_weapon_effects_as_non_rdps(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "mifu-self-weapon-buffs.dat",
        [
            "[10:00:00.000] SQUAD size=4 members=[chr_0031_mifu chr_0005_chen chr_0029_pograni chr_0015_lifeng]",
            "[10:00:00.000] LOADOUT slot=0 char=chr_0031_mifu weaponTemplate=wpn_claym_0017 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=1 char=chr_0005_chen weaponTemplate=wpn_sword_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=2 char=chr_0029_pograni weaponTemplate=wpn_lance_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=3 char=chr_0015_lifeng weaponTemplate=wpn_lance_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="3061" uid=1 owner=chr_0031_mifu src=chr_0031_mifu dur=20.00 lifeT=20.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[1]: duration=20 phy_spell_up=42",
            '[10:00:00.200] BUFF_START #2 id="3062" uid=2 owner=chr_0031_mifu src=chr_0031_mifu dur=30.00 lifeT=30.00 passed=0.00 enh=1',
            "[10:00:00.200]   BB[2]: duration2=30 phy_dmg_up_mult=0.21",
            '[10:00:00.500] HP_V2 #1 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0031_mifu_skill_2412" hits=1 src=chr_0031_mifu tgt=eny_0051_rodin atk=chr_0031_mifu seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    assert audit["hard_blockers"] == []
    accepted_non_rdps = dict(audit["buffs"]["accepted_known_non_rdps_ids"])
    assert accepted_non_rdps["3061"] == 1
    assert accepted_non_rdps["3062"] == 1
    assert dict(audit["buffs"]["rdps_relevant_unresolved_after_equipment"]) == {}


def test_audit_accepts_beacon_of_duty_team_fire_physical_buff(tmp_path: Path) -> None:
    trace = _write_trace(
        tmp_path,
        "beacon-of-duty-buffs.dat",
        [
            "[10:00:00.000] SQUAD size=4 members=[chr_0023_antal chr_0006_wolfgd chr_0016_laevat chr_0028_wulfa]",
            "[10:00:00.000] LOADOUT slot=0 char=chr_0023_antal weaponTemplate=wpn_lance_0007 weaponLv=90 refine=5 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=1 char=chr_0006_wolfgd weaponTemplate=wpn_pistol_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=2 char=chr_0016_laevat weaponTemplate=wpn_sword_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] LOADOUT slot=3 char=chr_0028_wulfa weaponTemplate=wpn_sword_0001 weaponLv=1 refine=0 break=0 attachedGem=0 equipInsts={} equips={} equipSuit={}",
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="3055" uid=1 owner=chr_0023_antal src=chr_0023_antal dur=20.00 lifeT=20.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[1]: dmg_up=0.224 duration=20",
            '[10:00:00.200] BUFF_START #2 id="3057" uid=2 owner=chr_0006_wolfgd src=chr_0023_antal dur=30.00 lifeT=30.00 passed=0.00 enh=1',
            "[10:00:00.200]   BB[2]: dmg_up2=0.112 duration2=30",
            '[10:00:00.500] HP_V2 #1 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0006_wolfgd_attack1" hits=1 src=chr_0006_wolfgd tgt=eny_0051_rodin atk=chr_0006_wolfgd seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    audit = audit_trace(trace, root=ROOT)

    assert audit["ok"] is True
    assert audit["hard_blockers"] == []
    accepted_non_rdps = dict(audit["buffs"]["accepted_known_non_rdps_ids"])
    assert accepted_non_rdps["3055"] == 1
    accepted = {row[0]: row for row in audit["buffs"]["accepted_packet_mapped_ids"]}
    assert accepted["3057"][2] == "buff_wpn_lance_0007_dmgup2"
    assert dict(audit["buffs"]["rdps_relevant_unresolved_after_equipment"]) == {}
    proof = audit["damage"]["per_hit_rdps"]["rdps_proof"]
    assert {
        (row["source_character_key"], row["event_key"], row["zone"])
        for row in proof["external_credit_by_buff"]
    } >= {
        ("chr_0023_antal", "buff_wpn_lance_0007_dmgup2", "dmg_inc"),
    }


def test_batch_audit_summarizes_trusted_and_blocked_files(tmp_path: Path) -> None:
    trusted = _write_trace(
        tmp_path,
        "trusted.dat",
        [
            *_loadout_lines(aglina_suit="{[suit_usp02]=3}"),
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.400] BUFF_START #4 id="1645" uid=4 owner=chr_0027_tangtang src=chr_0013_aglina dur=20.00 lifeT=20.00 passed=0.00 enh=1',
            "[10:00:00.400]   BB[4]: atk_up=0.224 duration=20 lv=9",
            '[10:00:00.500] HP_V2 #4 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0027_tangtang_attack1" hits=1 src=chr_0027_tangtang tgt=eny_0051_rodin atk=chr_0027_tangtang seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )
    blocked = _write_trace(
        tmp_path,
        "blocked.dat",
        [
            *_loadout_lines(),
            "[10:00:00.000] GAME_TIMER_START seq=1 source=ChallengeStart startMs=0 expireMs=0",
            '[10:00:00.100] BUFF_START #1 id="999999" uid=1 owner=eny_0051_rodin src=chr_0004_pelica dur=5.00 lifeT=5.00 passed=0.00 enh=1',
            "[10:00:00.100]   BB[1]: dmg_up=0.2 duration=5",
            '[10:00:00.500] HP_V2 #2 hit=100 cum=100 raw=100.00 packetFinalValue=100.0 pHP=5000 eHP=900000 skill="chr_0027_tangtang_attack1" hits=1 src=chr_0027_tangtang tgt=eny_0051_rodin atk=chr_0027_tangtang seg=0 shared=2 critFlag=0 critDmg=0.5000',
            "[10:00:01.000] GAME_TIMER_END seq=1 source=ChallengeComplete elapsedMs=1000 startMs=0 endMs=1000 expireMs=0 sane=1",
        ],
    )

    batch = audit_trace_batch([trusted, blocked], root=ROOT)

    assert batch["ok"] is False
    assert batch["summary"]["trace_count"] == 2
    assert batch["summary"]["ok_count"] == 1
    assert batch["summary"]["failed_count"] == 1
    assert dict(batch["hard_blockers"])["unresolved_rdps_effect_buff"] == 1
    markdown = format_batch_audit_markdown(batch)
    assert "## Files" in markdown
    assert "Strict Block 聚合" in markdown
