from endfield_pcap.loadout_static import infer_weapon_refine_from_source_skills


def test_infer_weapon_refine_from_source_skills_matches_passive_blackboard_values() -> None:
    source_skills = [
        {
            "skill_int_id": 1249,
            "level": 9,
            "blackboard": {"atk": 0.39},
        },
        {
            "skill_int_id": 1241,
            "level": 9,
            "blackboard": {"agi": 156},
        },
        {
            "skill_int_id": 2668,
            "level": 4,
            "blackboard": {
                "cd": 0.1,
                "cryst_dmg_up": 0.256,
                "cryst_dmg_up2": 0.32,
                "duration": 20,
                "duration2": 20,
                "spell_damage_taken_up": 0.096,
                "spell_dmg_taken_up": 0.12,
            },
        },
    ]

    assert infer_weapon_refine_from_source_skills("wpn_pistol_0011", source_skills) == 0


def test_infer_weapon_refine_from_source_skills_uses_passive_level_hint_when_values_overlap() -> None:
    source_skills = [
        {
            "skill_int_id": 2443,
            "level": 1,
            "blackboard": {"wisd": 16},
        },
        {
            "skill_int_id": 2444,
            "level": 2,
            "blackboard": {"atk": 0.072},
        },
        {
            "skill_int_id": 2217,
            "level": 9,
            "blackboard": {
                "atk_up": 0.224,
                "duration": 20,
                "hp_up": 0.28,
                "lv": 9,
                "ower_char_type": "#",
                "team_char_type": "#",
            },
        },
    ]

    assert infer_weapon_refine_from_source_skills("wpn_funnel_0005", source_skills) == 5


def test_infer_weapon_refine_from_source_skills_ignores_character_potential_hint() -> None:
    source_skills = [
        {
            "skill_int_id": 1391,
            "level": 5,
            "potential_lv": 5,
            "blackboard": {"mainattr": 71},
        },
        {
            "skill_int_id": 2253,
            "level": 9,
            "potential_lv": 5,
            "blackboard": {"atk": 0, "physpell": 78},
        },
        {
            "skill_int_id": 2228,
            "level": 4,
            "potential_lv": 5,
            "blackboard": {
                "duration": 15,
                "lv": 4,
                "second_attr_up": 0.16,
                "spell_damage_taken_up": 0.144,
            },
        },
    ]

    assert infer_weapon_refine_from_source_skills("wpn_funnel_0008", source_skills) == 0
