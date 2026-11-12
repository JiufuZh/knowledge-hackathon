"""Measure evidence and repeat behavior that the public organizer score omits."""
import argparse
import ctypes
import json
import sys
import time
from collections import Counter
from pathlib import Path


def peak_mib():
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                        ("peak_working_set", ctypes.c_size_t),
                        ("other_sizes", ctypes.c_size_t * 7)]

        info = Counters()
        info.cb = ctypes.sizeof(info)
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = wintypes.HANDLE
        read_counters = ctypes.windll.psapi.GetProcessMemoryInfo
        read_counters.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        read_counters.restype = wintypes.BOOL
        if read_counters(current_process(), ctypes.byref(info), info.cb):
            return round(info.peak_working_set / 2**20, 1)
        return None
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (2**20 if sys.platform == "darwin" else 1024), 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True, type=Path,
                        help="Local participant folder containing harness/ and eval/")
    args = parser.parse_args()
    kit = args.kit.resolve()
    sys.path.insert(0, str(kit / "harness"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from run_eval import load_snapshots
    from solution import build

    snapshots = load_snapshots(kit / "snapshots")
    questions = [json.loads(line) for line in (kit / "eval" / "public_eval.jsonl")
                 .read_text(encoding="utf-8").splitlines() if line.strip()]
    pages = {(s.snapshot_id, p.url): p.markdown for s in snapshots for p in s.pages}
    dates = {s.snapshot_id: s.taken_on for s in snapshots}
    system = build()
    start = time.perf_counter()
    for snapshot in snapshots:
        system.ingest(snapshot)
    counts = Counter({"uncited_confident_answers": 0, "sources_after_cutoff": 0,
                      "missing_or_unverifiable_quotes": 0, "reverse_order_repeat_mismatches": 0})
    report = {"ingest_seconds": round(time.perf_counter() - start, 3)}

    def check(source, cutoff=None):
        page = pages.get((source.snapshot_id, source.url), "")
        counts["source_records_checked"] += 1
        if not source.quote or source.quote not in page:
            counts["missing_or_unverifiable_quotes"] += 1
        if cutoff and dates.get(source.snapshot_id, "9999") > cutoff:
            counts["sources_after_cutoff"] += 1

    previous = {}
    for repeat in (False, True):
        samples = []
        for item in (reversed(questions) if repeat else questions):
            start = time.perf_counter()
            answer = system.answer(item["question"], item.get("as_of"))
            samples.append(time.perf_counter() - start)
            if repeat:
                counts["reverse_order_repeat_mismatches"] += (previous[item["id"]] != answer)
                continue
            previous[item["id"]] = answer
            counts["uncited_confident_answers"] += bool(answer.confident and not answer.sources)
            for source in answer.sources:
                check(source, item.get("as_of"))
        ordered = sorted(samples)
        report["repeat_p95_ms" if repeat else "first_pass_p95_ms"] = round(
            1000 * ordered[min(len(ordered) - 1, int(.95 * len(ordered)))], 2)
    disagreements = system.conflicts()
    counts["reported_conflicts_and_changes"] = len(disagreements)
    for item in disagreements:
        for source in item.sources:
            check(source)
    report.update(counts)
    report["peak_process_mib_including_kit"] = peak_mib()
    print(json.dumps(report, indent=2))
    if any(counts[k] for k in ("uncited_confident_answers", "sources_after_cutoff",
                               "missing_or_unverifiable_quotes", "reverse_order_repeat_mismatches")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
