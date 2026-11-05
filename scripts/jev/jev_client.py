"""Minimal client for TypeSafe's Jev model (System One API).

Jev answers typed questions about the state we send and returns calibrated
probabilities. Code in the calling script makes every decision.

- The key comes from TYPESAFE_API_KEY. It only goes into the Authorization
  header. It is never printed or logged.
- A failed call raises JevError. Callers treat that as "could not check",
  never as "no".
- The model is pinned (thresholds were measured on this version). Set
  JEV_MODEL to try another.
- Every request and answer can be appended to a JSONL log for audit.

Only send public material: everything here is public repository content.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import httpx

URL = "https://api.typesafe.ai/v1/systemone"
PINNED_MODEL = "jev-1.14.0"
PRICE_PER_MTOK = 0.042  # input tokens; output is free


class JevError(RuntimeError):
    """The question could not be answered. Not a "no"."""


class Jev:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        log_path: Path | None = None,
        timeout: float = 90.0,
        retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model or os.environ.get("JEV_MODEL") or PINNED_MODEL
        self._key = api_key or os.environ.get("TYPESAFE_API_KEY") or ""
        if not self._key:
            raise JevError("TYPESAFE_API_KEY is not set")
        self.log_path = log_path
        self.retries = retries
        self.input_tokens = 0
        self.requests = 0
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Jev":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def cost_usd(self) -> float:
        return self.input_tokens / 1e6 * PRICE_PER_MTOK

    def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        """One request. Returns {"model": str, "noul": {qid: p}, "raw": response}."""
        payload = {"model": self.model, "state": state, "questions": questions}
        last = ""
        for attempt in range(self.retries + 1):
            try:
                r = self._http.post(URL, json=payload, headers={"Authorization": f"Bearer {self._key}"})
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if r.status_code == 200:
                    break
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code != 429 and r.status_code < 500:
                    raise JevError(last)
            if attempt < self.retries:
                time.sleep(min(2 ** attempt, 20))
        else:
            raise JevError(f"no answer after {self.retries + 1} attempts ({last})")

        try:
            resp = r.json()
            noul = {qid: float(a["noul"]) for qid, a in resp["answers"].items() if a.get("noul") is not None}
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise JevError(f"unexpected response: {type(e).__name__}: {e}") from e
        bad = [qid for qid, p in noul.items() if not (math.isfinite(p) and 0.0 <= p <= 1.0)]
        if bad:
            raise JevError(f"probability out of range for {sorted(bad)}")
        missing = set(questions) - set(noul)
        if missing:
            raise JevError(f"no answer for {sorted(missing)}")
        self.requests += 1
        self.input_tokens += int((resp.get("usage") or {}).get("input_tokens") or 0)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"payload": payload, "model": resp.get("model"), "noul": noul},
                                    ensure_ascii=False) + "\n")
        return {"model": resp.get("model", self.model), "noul": noul, "raw": resp}
