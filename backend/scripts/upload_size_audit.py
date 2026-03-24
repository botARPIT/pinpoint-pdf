#!/usr/bin/env python3
"""Benchmark upload latency/throughput as PDF size grows."""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import statistics
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import httpx


@dataclass
class Result:
    target_mb: float
    actual_mb: float
    trial: int
    status_code: int
    latency_ms: float
    throughput_mbps: float
    doc_id: str
    error: str


def _parse_sizes(raw: str) -> list[float]:
    sizes = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        value = float(item)
        if value <= 0:
            raise ValueError(f"Size must be > 0: {item}")
        sizes.append(value)
    if not sizes:
        raise ValueError("No sizes parsed")
    return sizes


def _build_pdf_bytes(target_bytes: int, marker: str) -> bytes:
    """
    Build a syntactically valid PDF and pad it near target size.

    Padding is added as comment bytes after EOF; upload endpoint only stores bytes.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        f"Upload audit marker={marker} ts={time.time()}\n"
        f"target_bytes={target_bytes}",
    )
    base = doc.tobytes()
    doc.close()

    if len(base) >= target_bytes:
        return base

    pad_len = target_bytes - len(base)
    # Comment-prefixed padding keeps content PDF-like while increasing payload size.
    payload = ("\n%PAD-" + marker + "-").encode("utf-8")
    random_len = max(0, pad_len - len(payload))
    return base + payload + secrets.token_bytes(random_len)


def _write_pdf(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def _iter_trials(sizes_mb: Iterable[float], repeats: int) -> Iterable[tuple[float, int]]:
    for size in sizes_mb:
        for trial in range(1, repeats + 1):
            yield size, trial


def _summarize(results: list[Result]) -> str:
    lines = []
    lines.append("\nSummary by target size")
    lines.append("size_mb | runs | ok | avg_ms | p50_ms | max_ms | avg_MBps")
    lines.append("-" * 62)

    by_size: dict[float, list[Result]] = {}
    for r in results:
        by_size.setdefault(r.target_mb, []).append(r)

    for size in sorted(by_size):
        rows = by_size[size]
        ok = [r for r in rows if r.status_code in (200, 202)]
        latencies = [r.latency_ms for r in ok]
        speeds = [r.throughput_mbps for r in ok]

        if latencies:
            avg_ms = statistics.mean(latencies)
            p50_ms = statistics.median(latencies)
            max_ms = max(latencies)
            avg_mbps = statistics.mean(speeds)
            line = (
                f"{size:7.2f} | {len(rows):4d} | {len(ok):2d} | "
                f"{avg_ms:6.1f} | {p50_ms:6.1f} | {max_ms:6.1f} | {avg_mbps:8.2f}"
            )
        else:
            line = f"{size:7.2f} | {len(rows):4d} |  0 |   n/a |   n/a |   n/a |      n/a"
        lines.append(line)

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit /api/upload performance vs PDF size")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--sizes-mb",
        default="0.5,1,2,5,10",
        help="Comma-separated target sizes in MB",
    )
    parser.add_argument("--repeats", type=int, default=3, help="Trials per size")
    parser.add_argument(
        "--token",
        default=os.getenv("TOKEN", ""),
        help="Bearer token (defaults to TOKEN env var)",
    )
    parser.add_argument(
        "--output",
        default="backend/upload_audit_results.csv",
        help="CSV output path",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout seconds")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Missing token. Provide --token or set TOKEN env var.")
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")

    sizes_mb = _parse_sizes(args.sizes_mb)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[Result] = []
    headers = {"Authorization": f"Bearer {args.token}"}

    with tempfile.TemporaryDirectory(prefix="upload-audit-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout, headers=headers) as client:
            for target_mb, trial in _iter_trials(sizes_mb, args.repeats):
                target_bytes = int(target_mb * 1024 * 1024)
                marker = f"{uuid.uuid4()}-{trial}"
                data = _build_pdf_bytes(target_bytes, marker)
                pdf_path = tmpdir_path / f"audit-{target_mb:.2f}mb-t{trial}.pdf"
                _write_pdf(pdf_path, data)
                actual_mb = _mb(len(data))

                print(f"Uploading size={target_mb:.2f}MB trial={trial} actual={actual_mb:.2f}MB")

                start = time.perf_counter()
                status_code = 0
                doc_id = ""
                error = ""
                try:
                    with pdf_path.open("rb") as fh:
                        resp = client.post(
                            "/api/upload",
                            params={"force_reprocess": "true"},
                            files={"file": (pdf_path.name, fh, "application/pdf")},
                        )
                    status_code = resp.status_code
                    payload = resp.json() if resp.content else {}
                    doc_id = str(payload.get("doc_id", ""))
                    if status_code not in (200, 202):
                        error = str(payload.get("detail", resp.text))[:500]
                except Exception as exc:  # noqa: BLE001
                    status_code = -1
                    error = str(exc)[:500]

                elapsed = time.perf_counter() - start
                latency_ms = elapsed * 1000
                throughput_mbps = (actual_mb / elapsed) if elapsed > 0 else 0.0

                results.append(
                    Result(
                        target_mb=target_mb,
                        actual_mb=actual_mb,
                        trial=trial,
                        status_code=status_code,
                        latency_ms=latency_ms,
                        throughput_mbps=throughput_mbps,
                        doc_id=doc_id,
                        error=error,
                    )
                )

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "target_mb",
                "actual_mb",
                "trial",
                "status_code",
                "latency_ms",
                "throughput_MBps",
                "doc_id",
                "error",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    f"{r.target_mb:.4f}",
                    f"{r.actual_mb:.4f}",
                    r.trial,
                    r.status_code,
                    f"{r.latency_ms:.2f}",
                    f"{r.throughput_mbps:.4f}",
                    r.doc_id,
                    r.error,
                ]
            )

    print(f"\nWrote detailed results to: {output_path}")
    print(_summarize(results))

    failures = [r for r in results if r.status_code not in (200, 202)]
    if failures:
        print(f"\nWARNING: {len(failures)} upload trials failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
