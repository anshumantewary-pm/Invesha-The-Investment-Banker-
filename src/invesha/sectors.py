"""Sector reference data: trading multiples, unlevered beta and typical operating ranges.

These are indicative screening ranges (rules of thumb), not live market data for a
particular region or date. Override any of them in the model inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from invesha.core import InputError

Range = tuple[float, float]
Multiples = tuple[float, float, float]  # low, mid, high


@dataclass(frozen=True)
class Sector:
    key: str
    name: str
    ev_ebitda: Multiples
    ev_revenue: Multiples
    pe: Multiples
    unlevered_beta: float
    ebitda_margin: Range
    growth: Range
    arr_multiple: Multiples  # for startups (EV / annual recurring revenue)


SECTORS: dict[str, Sector] = {
    s.key: s
    for s in (
        Sector(
            "technology",
            "Technology / SaaS",
            (14, 20, 28),
            (3.0, 6.0, 10.0),
            (25, 35, 50),
            1.15,
            (0.15, 0.35),
            (0.15, 0.40),
            (4.0, 8.0, 14.0),
        ),
        Sector(
            "fintech",
            "Fintech / financial services",
            (12, 17, 24),
            (2.5, 4.5, 8.0),
            (20, 28, 40),
            1.20,
            (0.10, 0.30),
            (0.15, 0.35),
            (3.0, 6.0, 10.0),
        ),
        Sector(
            "consumer",
            "Consumer goods / FMCG",
            (14, 18, 24),
            (1.8, 3.0, 5.0),
            (30, 40, 55),
            0.70,
            (0.12, 0.22),
            (0.06, 0.15),
            (2.0, 3.5, 6.0),
        ),
        Sector(
            "retail",
            "Retail / e-commerce",
            (8, 12, 18),
            (0.6, 1.2, 2.5),
            (20, 30, 45),
            0.95,
            (0.05, 0.12),
            (0.08, 0.25),
            (1.5, 3.0, 5.0),
        ),
        Sector(
            "manufacturing",
            "Manufacturing / industrials",
            (8, 11, 15),
            (0.9, 1.5, 2.4),
            (16, 24, 32),
            0.90,
            (0.10, 0.20),
            (0.05, 0.12),
            (1.5, 2.5, 4.0),
        ),
        Sector(
            "healthcare",
            "Healthcare / pharma",
            (12, 16, 22),
            (2.0, 3.5, 5.5),
            (22, 32, 45),
            0.80,
            (0.15, 0.28),
            (0.08, 0.16),
            (3.0, 5.0, 8.0),
        ),
        Sector(
            "logistics",
            "Logistics / transport",
            (7, 10, 14),
            (0.6, 1.1, 1.8),
            (15, 22, 30),
            0.95,
            (0.07, 0.14),
            (0.06, 0.14),
            (1.5, 2.5, 4.0),
        ),
        Sector(
            "energy",
            "Energy / renewables",
            (7, 10, 13),
            (1.5, 3.0, 5.0),
            (12, 18, 25),
            0.75,
            (0.25, 0.60),
            (0.05, 0.15),
            (2.0, 3.0, 5.0),
        ),
        Sector(
            "infrastructure",
            "Infrastructure / utilities",
            (8, 11, 14),
            (2.0, 4.0, 6.0),
            (14, 20, 26),
            0.60,
            (0.30, 0.65),
            (0.04, 0.10),
            (2.0, 3.0, 5.0),
        ),
        Sector(
            "real_estate",
            "Real estate",
            (12, 16, 22),
            (4.0, 7.0, 10.0),
            (15, 22, 32),
            0.85,
            (0.35, 0.60),
            (0.05, 0.12),
            (2.0, 4.0, 6.0),
        ),
        Sector(
            "telecom",
            "Telecom / media",
            (6, 8, 11),
            (1.5, 2.5, 3.5),
            (14, 20, 28),
            0.75,
            (0.25, 0.45),
            (0.03, 0.10),
            (2.0, 3.0, 4.5),
        ),
        Sector(
            "services",
            "Business services / consulting",
            (10, 14, 18),
            (1.2, 2.0, 3.2),
            (20, 28, 38),
            0.95,
            (0.12, 0.22),
            (0.08, 0.18),
            (2.0, 3.0, 5.0),
        ),
        Sector(
            "chemicals",
            "Specialty chemicals",
            (10, 14, 20),
            (1.5, 2.5, 4.0),
            (20, 30, 42),
            0.95,
            (0.15, 0.25),
            (0.08, 0.16),
            (2.0, 3.0, 5.0),
        ),
    )
}


def get_sector(key: str) -> Sector:
    try:
        return SECTORS[str(key).strip().lower()]
    except KeyError:
        raise InputError(f"unknown sector {key!r}; choose from {', '.join(SECTORS)}") from None
