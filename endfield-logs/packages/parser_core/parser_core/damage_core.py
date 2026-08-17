from __future__ import annotations

from typing import Any

from parser_core.battle_log_parser import (
    _attr_type_applies_to_skill,
    _BUFF_EFFECT_SKILL_FILTER,
    _BUFF_SKILL_FILTER,
    _effect_applies_to_damage_element,
    _damage_school_from_element,
    _infer_skill_action_damage_element,
    _infer_skill_damage_element,
    _infer_skill_damage_school,
)

_DAMAGE_TYPE_ELEMENTS = {
    0: "physical",
    2: "fire",
    3: "pulse",
    4: "cryst",
    6: "natural",
}


def normalize_zone(zone: str | None) -> str:
    return str(zone or "").lower()


def damage_element_from_dpd(dpd: dict[str, Any] | None) -> str | None:
    if not isinstance(dpd, dict):
        return None
    raw_value = dpd.get("damage_type", dpd.get("damageType"))
    if raw_value is None:
        return None
    try:
        damage_type = int(str(raw_value), 16) if str(raw_value).lower().startswith("0x") else int(raw_value)
    except (TypeError, ValueError):
        return None
    return _DAMAGE_TYPE_ELEMENTS.get(damage_type)


def infer_damage_element(
    skill_key: str | None,
    character_key: str | None = None,
    *,
    action_id: int | str | None = None,
    damage_unit_index: int | str | None = None,
    dpd: dict[str, Any] | None = None,
) -> str | None:
    # Exact action damage units are authoritative when packet HP rows expose
    # them. DPD damageType can be an internal calculation bucket for proc skills
    # and is only a fallback.
    return (
        _infer_skill_action_damage_element(skill_key, action_id, damage_unit_index)
        or _infer_skill_damage_element(skill_key, character_key)
        or damage_element_from_dpd(dpd)
    )


def infer_damage_school(
    skill_key: str | None,
    character_key: str | None = None,
    *,
    raw_skill_key: str | None = None,
    action_id: int | str | None = None,
    damage_unit_index: int | str | None = None,
) -> str | None:
    action_element = _infer_skill_action_damage_element(skill_key, action_id, damage_unit_index)
    damage_element = action_element or infer_damage_element(
        skill_key,
        character_key,
        action_id=action_id,
        damage_unit_index=damage_unit_index,
    )
    if action_element:
        return _damage_school_from_element(action_element) or _infer_skill_damage_school(
            skill_key,
            character_key,
            raw_skill_key=raw_skill_key,
        )
    return _infer_skill_damage_school(
        skill_key,
        character_key,
        raw_skill_key=raw_skill_key,
    ) or _damage_school_from_element(damage_element)


def effect_applies_to_damage_element(
    effect_element: str | None,
    damage_element: str | None,
    damage_school: str | None = None,
) -> bool:
    return _effect_applies_to_damage_element(effect_element or "all", damage_element, damage_school)


def attr_type_applies_to_skill(attr_type: int | str | None, skill_key: str | None) -> bool:
    try:
        attr_type_int = int(attr_type) if attr_type is not None else None
    except (TypeError, ValueError):
        return True
    return _attr_type_applies_to_skill(attr_type_int, skill_key)


def buff_applies_to_skill(buff_id: str | None, skill_key: str | None) -> bool:
    skill_filter = _BUFF_SKILL_FILTER.get(str(buff_id or ""))
    return not skill_filter or bool(skill_filter.search(str(skill_key or "")))


def buff_effect_applies_to_skill(buff_id: str | None, zone: str | None, skill_key: str | None) -> bool:
    skill_filter = _BUFF_EFFECT_SKILL_FILTER.get((str(buff_id or ""), normalize_zone(zone)))
    return not skill_filter or bool(skill_filter.search(str(skill_key or "")))
