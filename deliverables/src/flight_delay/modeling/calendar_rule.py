"""Pre-registered calendar-feature decision (``experiments/son-test-on-kayit.md`` sections a and b), Val-A ONLY.

Compares two saved runs that differ only in ``--drop-date-features`` (same contract, same parameters, same Val-A rows)
and applies the rule mechanically; Val-B numbers of the runs are never read (the hypothesis came from Val-B).

Rule (direction / majority, no tuned thresholds; strict "<", a tie is not an improvement):
- ArrDel15 (``arr_del15``): drop the calendar features iff the Val-A Brier score of the run WITHOUT them is lower
  in total AND in at least 3 of the 4 Val-A months (Sep - Dec 2025; 3 of 4 = the smallest strict majority).
  Brier is used because it is a proper score that the runs record per month (``segments.month``); log-loss is
  recorded only in total and is reported for information.
- Quantiles (``arr_delay``, one decision for P50 / P80 / P95 and the 0.10 / 0.90 interval models together): drop iff
  the same two conditions hold for BOTH the P80 pinball (the search objective, plan 4.3) and the P95 pinball (the OR
  tail); P50 is recorded per run only in total and is reported for information.
- Otherwise the calendar features stay (the plan's feature list is the default; the burden of proof is on dropping).

Usage (from ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.calendar_rule --with-calendar run-20261120T175822Z --without-calendar run-...
Output: ``experiments/takvim-karari/karar-<UTC>/`` (``takvim-karari.json`` + ``takvim-karari.md``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from flight_delay.modeling import run_models as rm
from flight_delay.modeling import targets as tg
from flight_delay.modeling.matrix import DATE_FEATURES
from flight_delay.modeling.run_baselines import _format
from flight_delay.paths import PROJECT_ROOT

__all__ = ["MONTHS_REQUIRED", "VAL_A_MONTHS", "decide", "main", "render"]

VAL_A_MONTHS = ("9", "10", "11", "12")  # segment labels of Val-A months in the runs (calendar month numbers)
MONTHS_REQUIRED = 3  # of 4: the smallest strict majority
SET = "val_a"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "takvim-karari"


def _month_values(entry: Mapping[str, Any], metric: str) -> dict[str, float | None]:
    rows = {str(r["segment"]): r for r in entry["segments"]["month"]}
    return {m: (rows.get(m) or {}).get(metric) for m in VAL_A_MONTHS}


def _compare(with_entry: Mapping[str, Any], without_entry: Mapping[str, Any], metric: str) -> dict[str, Any]:
    total_with, total_without = with_entry["total"].get(metric), without_entry["total"].get(metric)
    months_with, months_without = _month_values(with_entry, metric), _month_values(without_entry, metric)
    values = [total_with, total_without, *months_with.values(), *months_without.values()]
    if any(v is None for v in values):
        return {"metric": metric, "complete": False, "condition_met": False}
    better = [m for m in VAL_A_MONTHS if float(months_without[m] or 0.0) < float(months_with[m] or 0.0)]
    return {
        "metric": metric,
        "complete": True,
        "total_with_calendar": total_with,
        "total_without_calendar": total_without,
        "total_improves": float(total_without) < float(total_with),
        "months_with_calendar": months_with,
        "months_without_calendar": months_without,
        "months_improving": better,
        "months_required": MONTHS_REQUIRED,
        "condition_met": float(total_without) < float(total_with) and len(better) >= MONTHS_REQUIRED,
    }


def _checks(with_run: Mapping[str, Any], without_run: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    a, b = with_run["metadata"], without_run["metadata"]
    if a["contract"] != b["contract"]:
        problems.append(f"contracts differ: {a['contract']} vs {b['contract']}")
    if with_run["periods"].get(SET) != without_run["periods"].get(SET):
        problems.append("Val-A periods differ")
    if with_run["periods"].get("fit") != without_run["periods"].get("fit"):
        problems.append("fit windows differ")
    dropped_a = set(with_run["features"].get("dropped", []))
    dropped_b = set(without_run["features"].get("dropped", []))
    if dropped_a & set(DATE_FEATURES):
        problems.append("the 'with calendar' run dropped calendar features")
    if dropped_b - dropped_a != set(DATE_FEATURES) or dropped_a - dropped_b:
        problems.append(f"the runs must differ exactly by {list(DATE_FEATURES)}")
    params = {
        key: (with_run["tuning"]["selected"].get(key, {}).get("params"), block.get("params"))
        for key, block in without_run["tuning"]["selected"].items()
    }
    if any(x != y for x, y in params.values()):
        problems.append("the runs use different LightGBM parameters")
    return problems


def decide(with_run: Mapping[str, Any], without_run: Mapping[str, Any]) -> dict[str, Any]:
    """The decision per model family; reads only the Val-A blocks of the two runs."""
    problems = _checks(with_run, without_run)
    families: dict[str, Any] = {}
    classification_a, classification_b = with_run.get("classification", {}), without_run.get("classification", {})
    if tg.ARR_DEL15 in classification_a and tg.ARR_DEL15 in classification_b:
        entry_a = classification_a[tg.ARR_DEL15]["LightGBM"]["sets"][SET]
        entry_b = classification_b[tg.ARR_DEL15]["LightGBM"]["sets"][SET]
        if entry_a["total"].get("n") != entry_b["total"].get("n"):
            problems.append("ArrDel15 Val-A rows differ")
        brier = _compare(entry_a, entry_b, "brier")
        families[tg.ARR_DEL15] = {
            "rule": f"Val-A Brier lower in total AND in >= {MONTHS_REQUIRED} of 4 months",
            "decisive": [brier],
            "information": {
                "log_loss_total": [entry_a["total"].get("log_loss"), entry_b["total"].get("log_loss")],
                "roc_auc_total": [entry_a["total"].get("roc_auc"), entry_b["total"].get("roc_auc")],
                "citl_months": [
                    _month_values(entry_a, "calibration_in_the_large"),
                    _month_values(entry_b, "calibration_in_the_large"),
                ],
            },
            "drop_calendar_features": bool(brier["condition_met"]),
        }
    quantile_a, quantile_b = with_run.get("quantile", {}), without_run.get("quantile", {})
    if tg.ARR_DELAY in quantile_a and tg.ARR_DELAY in quantile_b:
        entry_a = quantile_a[tg.ARR_DELAY]["LightGBM"]["sets"][SET]
        entry_b = quantile_b[tg.ARR_DELAY]["LightGBM"]["sets"][SET]
        if entry_a["total"].get("n") != entry_b["total"].get("n"):
            problems.append("quantile Val-A rows differ")
        decisive = [_compare(entry_a, entry_b, "pinball_q080"), _compare(entry_a, entry_b, "pinball_q095")]
        p50 = [entry_a["total"].get("pinball_q050"), entry_b["total"].get("pinball_q050")]
        families[tg.ARR_DELAY] = {
            "rule": f"Val-A pinball P80 AND P95 each lower in total AND in >= {MONTHS_REQUIRED} of 4 months",
            "decisive": decisive,
            "information": {"pinball_q050_total": p50},
            "drop_calendar_features": all(c["condition_met"] for c in decisive),
        }
    return {
        "with_calendar_run": with_run["metadata"]["run_id"],
        "without_calendar_run": without_run["metadata"]["run_id"],
        "contract": with_run["metadata"]["contract"],
        "set_used": SET,
        "val_b_read": False,
        "problems": problems,
        "valid": not problems,
        "families": families,
    }


def render(decision: Mapping[str, Any]) -> str:
    lines = [
        f"# Takvim özelliği kararı (önceden kayıtlı kural, yalnızca Val-A) – {decision['contract']}",
        "",
        f"- Takvimli: `{decision['with_calendar_run']}` · takvimsiz: `{decision['without_calendar_run']}` · Val-B "
        "okunmadı.",
        f"- Geçerli karşılaştırma: **{'evet' if decision['valid'] else 'HAYIR'}**"
        + (f" ({'; '.join(decision['problems'])})" if decision["problems"] else ""),
        "",
    ]
    for family, block in decision["families"].items():
        verdict = "takvim özellikleri ÇIKARILIR" if block["drop_calendar_features"] else "takvim özellikleri KALIR"
        lines += [f"## {family}: {verdict}", "", f"Kural: {block['rule']}", ""]
        lines += ["| Metrik | Toplam takvimli | Toplam takvimsiz | Eylül | Ekim | Kasım | Aralık | Koşul |"]
        lines += ["|---|---|---|---|---|---|---|---|"]
        for c in block["decisive"]:
            if not c["complete"]:
                lines.append(f"| {c['metric']} | eksik | | | | | | hayır |")
                continue
            cells = [
                f"{_format(c['months_with_calendar'][m], 4)} → {_format(c['months_without_calendar'][m], 4)}"
                for m in VAL_A_MONTHS
            ]
            totals = f"{_format(c['total_with_calendar'], 4)} | {_format(c['total_without_calendar'], 4)}"
            met = "evet" if c["condition_met"] else "hayır"
            lines.append(f"| {c['metric']} | {totals} | " + " | ".join(cells) + f" | {met} |")
        lines += ["", f"Bilgi (karar dışı): `{json.dumps(block['information'])}`", ""]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-registered calendar-feature rule on Val-A (two saved runs).")
    parser.add_argument("--with-calendar", required=True, help="run-<UTC> without --drop-date-features")
    parser.add_argument("--without-calendar", required=True, help="run-<UTC> with --drop-date-features")
    parser.add_argument("--runs-dir", type=Path, default=rm.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(list(argv) if argv is not None else None)
    runs = [
        json.loads((args.runs_dir / run_id / rm.RESULTS_NAME).read_text(encoding="utf-8"))
        for run_id in (args.with_calendar, args.without_calendar)
    ]
    decision = decide(*runs)
    folder = args.output_dir / f"karar-{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}-{decision['contract']}"
    folder.mkdir(parents=True)
    (folder / "takvim-karari.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "takvim-karari.md").write_text(render(decision), encoding="utf-8")
    print(f"Decision: {folder / 'takvim-karari.md'}")
    return 0 if decision["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
