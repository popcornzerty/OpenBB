"""Construit l'univers européen validé à partir du seed d'indices.

Chaque symbole du seed est réellement interrogé : ceux qui ne répondent pas
sont écartés et listés en fin d'exécution. Le fichier produit
(``data/universe_eu.csv``) ne contient donc que des tickers vérifiés, avec
leur pays de siège et leur verdict PEA.

    python scripts/build_universe.py [--concurrency 6] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pea.eligibility import Eligibility  # noqa: E402
from app.pea.universe import (  # noqa: E402
    UniverseEntry,
    describe,
    load_seed,
    save_universe,
)


async def _describe_one(
    symbol: str, name: str, index: str, semaphore: asyncio.Semaphore, attempts: int = 3
) -> tuple[UniverseEntry | None, str | None]:
    async with semaphore:
        last_error = ""
        for attempt in range(attempts):
            try:
                entry = await describe(symbol, name_hint=name, index=index)
                return entry, None
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
                if attempt < attempts - 1:
                    # Yahoo limite le débit : on laisse retomber la pression.
                    await asyncio.sleep(1.5 * (attempt + 1))
        return None, last_error


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0, help="0 = tout le seed")
    args = parser.parse_args()

    seed = load_seed()
    if args.limit:
        seed = seed[: args.limit]
    print(f"Seed : {len(seed)} symboles")

    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.time()
    results = await asyncio.gather(
        *(_describe_one(sym, name, index, semaphore) for sym, name, index in seed)
    )

    entries: list[UniverseEntry] = []
    failures: list[tuple[str, str]] = []
    for (symbol, _, _), (entry, error) in zip(seed, results, strict=True):
        if entry is None:
            failures.append((symbol, error or "inconnu"))
        else:
            entries.append(entry)

    path = save_universe(entries)
    elapsed = time.time() - started

    eligible = sum(1 for e in entries if e.pea_status == Eligibility.ELIGIBLE.value)
    non_eligible = sum(1 for e in entries if e.pea_status == Eligibility.NON_ELIGIBLE.value)
    unknown = sum(1 for e in entries if e.pea_status == Eligibility.UNKNOWN.value)

    print(f"\nÉcrit  : {path}  ({len(entries)} valeurs, {elapsed:.0f}s)")
    print(f"  PEA éligibles     : {eligible}")
    print(f"  PEA non éligibles : {non_eligible}")
    print(f"  Indéterminés      : {unknown}")

    if non_eligible:
        print("\nNon éligibles (siège hors EEE) :")
        for entry in sorted(entries, key=lambda e: e.symbol):
            if entry.pea_status == Eligibility.NON_ELIGIBLE.value:
                print(f"  {entry.symbol:<14} {entry.name[:34]:<34} {entry.country_label}")

    if unknown:
        print("\nIndéterminés (pays du siège non résolu) :")
        for entry in sorted(entries, key=lambda e: e.symbol):
            if entry.pea_status == Eligibility.UNKNOWN.value:
                print(f"  {entry.symbol:<14} {entry.name[:34]:<34} {entry.country_label!r}")

    if failures:
        print(f"\nSymboles écartés ({len(failures)}) :")
        for symbol, error in failures:
            print(f"  {symbol:<14} {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
