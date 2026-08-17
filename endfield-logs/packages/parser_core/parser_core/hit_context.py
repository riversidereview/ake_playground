from __future__ import annotations

from collections import defaultdict
from math import log
from typing import Any

from parser_core.battle_log_parser import (
    _ATTR_TYPE_BUFF_LABELS,
    _ATTR_TYPE_TO_EFFECT,
    _BUFF_EFFECT_SKILL_FILTER,
    _BUFF_SKILL_FILTER,
    _DPD_ZONE_BUCKETS,
    _attr_type_applies_to_skill,
    _element_filter_debug_fields,
    _effect_applies_to_damage_element,
    _resolve_character_name,
    _window_matches_packet_uids,
    _window_uid_aliases,
    _window_effects_at_ts,
)


ZONE_LABELS = {
    "atk": "攻击",
    "dmg_inc": "增伤",
    "fragile": "脆弱",
    "vuln_taken": "易伤",
    "amp": "增幅",
    "res": "减抗",
    "combo": "连击",
    "crit": "暴击",
}
ZONE_ORDER = {
    "atk": 0,
    "dmg_inc": 1,
    "fragile": 2,
    "vuln_taken": 3,
    "amp": 4,
    "res": 5,
    "combo": 6,
    "crit": 7,
}


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _dpd_bucket_for_zone(zone: str, dpd_raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dpd_raw:
        return None
    bucket = _DPD_ZONE_BUCKETS.get(zone)
    if bucket is None:
        return None
    side, index = bucket
    values = dpd_raw.get("atk_zones") if side == "atk" else dpd_raw.get("def_zones")
    values = values or []
    if len(values) > index:
        return {"side": side, "index": index, "value": values[index]}
    return None


def _sort_zones(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (ZONE_ORDER.get(str(item.get("zone")), 99), str(item.get("zone"))))


def _record_applicable_effect(
    *,
    window: dict[str, Any],
    effect: dict[str, Any],
    scope: str,
    rdps_credit: float | None = None,
) -> dict[str, Any]:
    source_key = window.get("source_character_key")
    raw_source_key = window.get("raw_source_character_key")
    return {
        "scope": scope,
        "source_character_key": source_key,
        "source_character_name": window.get("source_character_name")
        or _resolve_character_name(source_key)
        or source_key,
        "raw_source_character_key": raw_source_key,
        "raw_source_character_name": window.get("raw_source_character_name")
        or _resolve_character_name(raw_source_key)
        or raw_source_key,
        "raw_source": window.get("raw_source"),
        "target_character_key": window.get("target_character_key"),
        "target_character_name": window.get("target_character_name"),
        "owner_raw": window.get("owner_raw"),
        "event_key": window.get("event_key"),
        "event_name": window.get("event_name"),
        "uid": window.get("uid"),
        "uid_aliases": list(window.get("uid_aliases") or []),
        "start_ts_ms": window.get("start_ts_ms"),
        "start_time": window.get("start_time"),
        "end_ts_ms": window.get("end_ts_ms"),
        "end_time": window.get("end_time"),
        "zone": str(effect.get("zone") or ""),
        "zone_label": ZONE_LABELS.get(str(effect.get("zone") or ""), str(effect.get("zone") or "")),
        "element": str(effect.get("element") or "all"),
        "rate": _round4(float(effect.get("rate") or 0.0)),
        "rdps_credit": _round4(rdps_credit),
    }


def _record_dpd_self_residual(
    *,
    hit: dict[str, Any],
    zone: str,
    rate: float,
) -> dict[str, Any]:
    attacker_key = str(hit.get("character_key") or "")
    attacker_name = str(hit.get("character_name") or _resolve_character_name(attacker_key) or attacker_key)
    return {
        "scope": "self",
        "source_character_key": attacker_key,
        "source_character_name": attacker_name,
        "raw_source_character_key": attacker_key,
        "raw_source_character_name": attacker_name,
        "raw_source": "DPD_RAW",
        "target_character_key": attacker_key,
        "target_character_name": attacker_name,
        "owner_raw": "DPD_RAW",
        "event_key": "__dpd_self_residual__",
        "event_name": "自身基线/未归因（DPD残差）",
        "uid": None,
        "start_ts_ms": None,
        "start_time": None,
        "end_ts_ms": None,
        "end_time": None,
        "zone": zone,
        "zone_label": ZONE_LABELS.get(zone, zone),
        "element": str(hit.get("damage_element") or "all"),
        "rate": _round4(rate),
        "rdps_credit": None,
    }


def _record_baseline_self(
    *,
    hit: dict[str, Any],
    attr_type: int,
    zone: str,
    element: str,
    rate: float,
    final_value: float,
    captured: float,
) -> dict[str, Any]:
    attacker_key = str(hit.get("character_key") or "")
    attacker_name = str(hit.get("character_name") or _resolve_character_name(attacker_key) or attacker_key)
    label = _ATTR_TYPE_BUFF_LABELS.get(attr_type) or ZONE_LABELS.get(zone, zone)
    return {
        "scope": "self",
        "source_character_key": attacker_key,
        "source_character_name": attacker_name,
        "raw_source_character_key": attacker_key,
        "raw_source_character_name": attacker_name,
        "raw_source": "BASELINE",
        "target_character_key": attacker_key,
        "target_character_name": attacker_name,
        "owner_raw": "BASELINE",
        "event_key": f"__baseline_attr_{attr_type}__",
        "event_name": f"自身属性基线（{label} / attrType={attr_type}）",
        "uid": None,
        "start_ts_ms": None,
        "start_time": None,
        "end_ts_ms": None,
        "end_time": None,
        "zone": zone,
        "zone_label": ZONE_LABELS.get(zone, zone),
        "element": element,
        "rate": _round4(rate),
        "rdps_credit": None,
        "baseline_final": _round4(final_value),
        "baseline_captured": _round4(captured),
    }


def build_hit_context(hit: dict[str, Any], buff_windows: list[dict[str, Any]]) -> dict[str, Any]:
    attacker_key = str(hit["character_key"])
    target_enemy_key = str(hit.get("target_enemy_key") or "")
    hit_value = float(hit["hit_value"])
    hit_ts_ms = int(hit["ts_ms"])
    damage_element = hit.get("damage_element")
    damage_school = hit.get("damage_school")

    external_by_zone: dict[str, list[tuple[str, float, dict[str, Any]]]] = defaultdict(list)
    self_by_zone: dict[str, float] = defaultdict(float)
    captured_by_attr_type: dict[int, float] = defaultdict(float)
    contributors_by_zone: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ignored_effects: list[dict[str, Any]] = []
    packet_modifier_uids = hit.get("packet_modifier_uids") if isinstance(hit.get("packet_modifier_uids"), dict) else {}
    attacker_modifier_uids = {str(item) for item in packet_modifier_uids.get("attacker") or [] if str(item)}
    defender_modifier_uids = {str(item) for item in packet_modifier_uids.get("defender") or [] if str(item)}

    for window in buff_windows:
        if not (int(window["start_ts_ms"]) <= hit_ts_ms <= int(window["end_ts_ms"])):
            continue
        skill_family_key = window.get("skill_family_key")
        if skill_family_key and hit.get("skill_family_key") != skill_family_key:
            continue
        skill_filter = _BUFF_SKILL_FILTER.get(str(window.get("event_key") or ""))
        if skill_filter and not skill_filter.search(str(hit.get("skill_key") or "")):
            continue

        applies_to_attacker = window.get("target_character_key") == attacker_key
        applies_to_enemy = bool(target_enemy_key) and window.get("target_character_key") == target_enemy_key
        if not applies_to_attacker and not applies_to_enemy:
            continue

        source_key = window.get("source_character_key")
        if not source_key:
            continue

        window_uid_aliases = _window_uid_aliases(window)
        packet_uid_match = bool(window_uid_aliases & defender_modifier_uids)

        for effect in _window_effects_at_ts(window, hit_ts_ms):
            zone = str(effect.get("zone") or "")
            rate = float(effect.get("rate") or 0.0)
            element = str(effect.get("element") or "all")
            packet_uid_restricted = (
                bool(hit.get("packet_modifier_seen"))
                and applies_to_enemy
                and bool(window_uid_aliases)
                and zone == "vuln_taken"
            )
            if packet_uid_restricted and not packet_uid_match:
                ignored_effects.append(
                    {
                        **_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                        "reason": "packet_defender_uid_suppressed",
                        "reason_group": "packet_modifier_uid_mismatch",
                        "packet_modifier_guard": "defender_uid_selection",
                        "packet_modifier_seen": True,
                        "packet_modifier_uids": {
                            "attacker": sorted(attacker_modifier_uids),
                            "defender": sorted(defender_modifier_uids),
                        },
                        "candidate_uids": sorted(window_uid_aliases),
                    }
                )
                continue
            effect_skill_filter = _BUFF_EFFECT_SKILL_FILTER.get((str(window.get("event_key") or ""), zone))
            if effect_skill_filter and not effect_skill_filter.search(str(hit.get("skill_key") or "")):
                continue
            attr_type = effect.get("attr_type")
            if isinstance(attr_type, int) and not _attr_type_applies_to_skill(
                attr_type,
                str(hit.get("skill_key") or ""),
            ):
                continue
            if rate <= 0:
                continue
            if zone == "crit":
                ignored_effects.append(
                    {
                        **_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                        "reason": "crit_not_allocated",
                    }
                )
                continue
            if not _effect_applies_to_damage_element(element, damage_element, damage_school):
                ignored_effects.append(
                    {
                        **_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                        **_element_filter_debug_fields(element, damage_element, damage_school),
                    }
                )
                continue

            if applies_to_attacker and isinstance(attr_type, int):
                captured_by_attr_type[attr_type] += rate

            scope = "self" if source_key == attacker_key else "external"
            record = _record_applicable_effect(window=window, effect=effect, scope=scope)
            contributors_by_zone[zone].append(record)
            if scope == "self":
                self_by_zone[zone] += rate
            else:
                external_by_zone[zone].append((str(source_key), rate, record))

    for raw_attr_type, final_value in (hit.get("baseline") or {}).items():
        try:
            attr_type = int(raw_attr_type)
            final_rate = float(final_value)
        except (TypeError, ValueError):
            continue
        if attr_type == 2:
            continue
        mapping = _ATTR_TYPE_TO_EFFECT.get(attr_type)
        if mapping is None:
            continue
        zone, element = mapping
        element = str(element or "all")
        if zone == "crit":
            continue
        if not _attr_type_applies_to_skill(attr_type, str(hit.get("skill_key") or "")):
            continue
        if not _effect_applies_to_damage_element(element, damage_element, damage_school):
            continue
        captured = captured_by_attr_type.get(attr_type, 0.0)
        baseline_rate = final_rate - captured
        if baseline_rate <= 0.001:
            continue
        self_by_zone[zone] += baseline_rate
        contributors_by_zone[zone].append(
            _record_baseline_self(
                hit=hit,
                attr_type=attr_type,
                zone=zone,
                element=element,
                rate=baseline_rate,
                final_value=final_rate,
                captured=captured,
            )
        )

    for zone in _DPD_ZONE_BUCKETS:
        dpd_bucket = _dpd_bucket_for_zone(zone, hit.get("dpd_raw"))
        if not dpd_bucket:
            continue
        try:
            bucket_value = float(dpd_bucket.get("value") or 0.0)
        except (TypeError, ValueError):
            continue
        recognized_total = self_by_zone.get(zone, 0.0) + sum(
            rate for _, rate, _ in external_by_zone.get(zone, [])
        )
        residual = (bucket_value - 1.0) - recognized_total
        if abs(residual) <= 0.003:
            continue
        self_by_zone[zone] += residual
        contributors_by_zone[zone].append(
            _record_dpd_self_residual(hit=hit, zone=zone, rate=residual)
        )

    external_multiplier_by_zone: dict[str, float] = {}
    external_sum_by_zone: dict[str, float] = {}
    for zone, contributors in external_by_zone.items():
        external_sum = sum(rate for _, rate, _ in contributors)
        if external_sum <= 0:
            continue
        self_sum = self_by_zone.get(zone, 0.0)
        multiplier = (1.0 + self_sum + external_sum) / (1.0 + self_sum)
        dpd_bucket = _dpd_bucket_for_zone(zone, hit.get("dpd_raw"))
        if dpd_bucket:
            try:
                bucket_value = float(dpd_bucket.get("value") or 0.0)
            except (TypeError, ValueError):
                bucket_value = 0.0
            if bucket_value > 1.0001:
                calibrated = bucket_value / max(1.0, bucket_value - external_sum)
                if calibrated > 1.0001:
                    multiplier = calibrated
        if multiplier <= 1.0:
            continue
        external_sum_by_zone[zone] = external_sum
        external_multiplier_by_zone[zone] = multiplier

    if not external_multiplier_by_zone:
        product_external = 1.0
        attacker_share = hit_value
        external_pool = 0.0
    else:
        product_external = 1.0
        for multiplier in external_multiplier_by_zone.values():
            product_external *= multiplier
        attacker_share = hit_value / product_external if product_external > 0 else hit_value
        external_pool = hit_value - attacker_share

    log_total = sum(log(value) for value in external_multiplier_by_zone.values()) if product_external > 1 else 0.0
    zone_external_share: dict[str, float] = defaultdict(float)
    rdps_contributions: dict[str, float] = defaultdict(float)
    rdps_contributions[attacker_key] += attacker_share

    if log_total > 0 and external_pool > 0:
        for zone, contributors in external_by_zone.items():
            multiplier = external_multiplier_by_zone.get(zone)
            if multiplier is None or multiplier <= 1.0:
                continue
            zone_share = external_pool * (log(multiplier) / log_total)
            zone_external_share[zone] = zone_share
            zone_external_sum = external_sum_by_zone.get(zone, 0.0)
            if zone_external_sum <= 0:
                rdps_contributions[attacker_key] += zone_share
                continue
            for source_key, rate, record in contributors:
                credit = zone_share * (rate / zone_external_sum)
                record["rdps_credit"] = _round4(credit)
                rdps_contributions[source_key] += credit

    zones: list[dict[str, Any]] = []
    for zone in sorted(
        set(self_by_zone) | set(external_by_zone),
        key=lambda key: (ZONE_ORDER.get(key, 99), key),
    ):
        self_rate = self_by_zone.get(zone, 0.0)
        external_rate = external_sum_by_zone.get(
            zone,
            sum(rate for _, rate, _ in external_by_zone.get(zone, [])),
        )
        total_rate = self_rate + external_rate
        dpd_bucket = _dpd_bucket_for_zone(zone, hit.get("dpd_raw"))
        zones.append(
            {
                "zone": zone,
                "zone_label": ZONE_LABELS.get(zone, zone),
                "self_rate": _round4(self_rate),
                "external_rate": _round4(external_rate),
                "total_rate": _round4(total_rate),
                "total_multiplier": _round4(1.0 + total_rate),
                "external_multiplier": _round4(external_multiplier_by_zone.get(zone, 1.0)),
                "zone_external_share": _round4(zone_external_share.get(zone, 0.0)),
                "dpd_bucket": (
                    {
                        "side": dpd_bucket["side"],
                        "index": dpd_bucket["index"],
                        "value": _round4(dpd_bucket["value"]),
                    }
                    if dpd_bucket
                    else None
                ),
                "contributors": sorted(
                    contributors_by_zone.get(zone, []),
                    key=lambda item: (
                        0 if item.get("scope") == "external" else 1,
                        -float(item.get("rate") or 0.0),
                        str(item.get("source_character_name") or ""),
                        str(item.get("event_key") or ""),
                    ),
                ),
            }
        )

    external_sources: dict[str, dict[str, Any]] = {}
    for contributors in external_by_zone.values():
        for source_key, _rate, record in contributors:
            current = external_sources.setdefault(
                source_key,
                {
                    "character_key": source_key,
                    "character_name": record.get("source_character_name") or source_key,
                    "effect_count": 0,
                    "rdps_credit": 0.0,
                },
            )
            current["effect_count"] += 1
            current["rdps_credit"] += float(record.get("rdps_credit") or 0.0)

    external_sources_list = sorted(
        (
            {
                **value,
                "rdps_credit": _round4(value["rdps_credit"]),
            }
            for value in external_sources.values()
        ),
        key=lambda item: (-float(item.get("rdps_credit") or 0.0), str(item.get("character_name") or "")),
    )
    sorted_zones = _sort_zones(zones)
    baseline = hit.get("baseline") if isinstance(hit.get("baseline"), dict) else {}
    return {
        "baseline": {
            "attrs": _baseline_attr_rows(baseline),
        },
        "zones": sorted_zones,
        "ignored_effects": ignored_effects,
        "product_external_multiplier": _round4(product_external),
        "attacker_share": _round4(attacker_share),
        "external_pool": _round4(external_pool),
        "rdps_contributions": [
            {
                "character_key": key,
                "character_name": _resolve_character_name(key) or key,
                "value": _round4(value),
            }
            for key, value in sorted(rdps_contributions.items(), key=lambda item: (-item[1], item[0]))
            if value > 0.0001
        ],
        "external_sources": external_sources_list,
        "zone_summary": " / ".join(
            f"{zone['zone_label']} x{zone['external_multiplier']:.4f}"
            for zone in sorted_zones
            if float(zone.get("external_multiplier") or 1.0) > 1.0001
        ),
        "buff_source_summary": " / ".join(
            f"{source['character_name']} +{source['rdps_credit']:.1f}"
            for source in external_sources_list
            if float(source.get("rdps_credit") or 0.0) > 0.0001
        ),
    }


def explain_hit_context(hit: dict[str, Any], buff_windows: list[dict[str, Any]]) -> dict[str, Any]:
    raw_baseline = hit.get("baseline")
    context = build_hit_context(hit, buff_windows)
    for key, value in context.items():
        if key == "baseline":
            continue
        hit[key] = value
    if raw_baseline is not None:
        hit["baseline"] = raw_baseline
    hit["hit_context"] = context
    return hit


def rdps_contribution_map(hit_context: dict[str, Any]) -> dict[str, float]:
    return {
        str(item.get("character_key") or ""): float(item.get("value") or 0.0)
        for item in hit_context.get("rdps_contributions") or []
        if item.get("character_key") and float(item.get("value") or 0.0) > 0.0001
    }


def _baseline_attr_row(attr_type: int, value: float) -> dict[str, Any]:
    zone = None
    element = None
    mapping = _ATTR_TYPE_TO_EFFECT.get(attr_type)
    if mapping is not None:
        zone, element = mapping
    return {
        "attr_type": attr_type,
        "label": _ATTR_TYPE_BUFF_LABELS.get(attr_type) or ZONE_LABELS.get(str(zone or ""), ""),
        "zone": zone,
        "zone_label": ZONE_LABELS.get(str(zone or ""), str(zone or "")) if zone else None,
        "element": element,
        "value": _round4(value),
    }


def _baseline_attr_rows(baseline: dict[Any, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_attr_type, raw_value in sorted(baseline.items(), key=lambda item: str(item[0])):
        try:
            attr_type = int(raw_attr_type)
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        rows.append(_baseline_attr_row(attr_type, value))
    rows.sort(key=lambda item: int(item["attr_type"]))
    return rows


def _state_window_row(window: dict[str, Any], *, battle_start_ms: int) -> dict[str, Any]:
    start_ts_ms = int(window.get("start_ts_ms") or 0)
    end_ts_ms = int(window.get("end_ts_ms") or start_ts_ms)
    return {
        "event_key": window.get("event_key"),
        "event_name": window.get("event_name"),
        "source_character_key": window.get("source_character_key"),
        "source_character_name": window.get("source_character_name"),
        "target_character_key": window.get("target_character_key"),
        "target_character_name": window.get("target_character_name"),
        "target_player_key": window.get("target_player_key"),
        "target_enemy_key": window.get("target_enemy_key"),
        "target_enemy_name": window.get("target_enemy_name"),
        "owner_raw": window.get("owner_raw"),
        "start_ts_ms_from_start": max(start_ts_ms - battle_start_ms, 0),
        "end_ts_ms_from_start": max(end_ts_ms - battle_start_ms, 0),
        "duration_ms": max(end_ts_ms - start_ts_ms, 1),
        "effects": [
            {
                "zone": effect.get("zone"),
                "zone_label": ZONE_LABELS.get(str(effect.get("zone") or ""), str(effect.get("zone") or "")),
                "element": effect.get("element"),
                "rate": _round4(float(effect.get("rate") or 0.0)),
                "attr_type": effect.get("attr_type"),
                "bb_key": effect.get("bb_key"),
            }
            for effect in window.get("zone_effects") or []
        ],
        "dynamic_effects": [
            {
                "zone": effect.get("zone"),
                "zone_label": ZONE_LABELS.get(str(effect.get("zone") or ""), str(effect.get("zone") or "")),
                "element": effect.get("element"),
                "base_rate": _round4(float(effect.get("base_rate") or 0.0)),
                "tick_rate": _round4(float(effect.get("tick_rate") or 0.0)),
                "max_rate": _round4(float(effect.get("max_rate") or 0.0)),
            }
            for effect in window.get("dynamic_effects") or []
        ],
    }


def build_character_states(
    *,
    roster: list[dict[str, Any]],
    hits: list[dict[str, Any]],
    buff_windows: list[dict[str, Any]],
    battle_start_ms: int,
) -> list[dict[str, Any]]:
    first_baseline_by_character: dict[str, tuple[int, dict[int, float]]] = {}
    for hit in hits:
        character_key = str(hit.get("character_key") or "")
        baseline = hit.get("baseline")
        if not character_key or character_key in first_baseline_by_character or not isinstance(baseline, dict):
            continue
        first_baseline_by_character[character_key] = (int(hit.get("ts_ms") or 0), baseline)

    states: list[dict[str, Any]] = []
    for roster_entry in roster:
        character_key = str(roster_entry.get("character_key") or "")
        if not character_key:
            continue
        baseline_ts_ms, baseline = first_baseline_by_character.get(character_key, (None, {}))
        buffs_received = [
            _state_window_row(window, battle_start_ms=battle_start_ms)
            for window in buff_windows
            if window.get("target_player_key") == character_key
        ]
        buffs_given = [
            _state_window_row(window, battle_start_ms=battle_start_ms)
            for window in buff_windows
            if window.get("source_character_key") == character_key
            and window.get("target_player_key")
            and window.get("target_player_key") != character_key
        ]
        debuffs_applied = [
            _state_window_row(window, battle_start_ms=battle_start_ms)
            for window in buff_windows
            if window.get("source_character_key") == character_key and window.get("target_enemy_key")
        ]
        states.append(
            {
                "character_key": character_key,
                "character_name": roster_entry.get("character_name") or _resolve_character_name(character_key) or character_key,
                "initial_baseline": {
                    "ts_ms_from_start": (
                        max(int(baseline_ts_ms) - battle_start_ms, 0)
                        if baseline_ts_ms is not None
                        else None
                    ),
                    "attrs": _baseline_attr_rows(baseline),
                },
                "buffs_received": buffs_received,
                "buffs_given": buffs_given,
                "debuffs_applied": debuffs_applied,
            }
        )
    return states
