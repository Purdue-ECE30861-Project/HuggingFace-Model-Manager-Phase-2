#from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, override

from src.backend_server.model.dependencies import DependencyBundle
from src.backend_server.utils.hf_api import hfAPI
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


# ---- Canonicalization & rules ----


class DBManager:
    pass
ALIASES = {
    "acc": "accuracy", "top1-acc": "top-1-accuracy", "top1_accuracy": "top-1-accuracy",
    "top5-acc": "top-5-accuracy", "top5_accuracy": "top-5-accuracy",
    "rouge-l": "rouge_l", "rougeL": "rouge_l", "rougeLsum": "rouge_lsum",
    "sacrebleu": "bleu", "ppl": "perplexity",
    "f1-score": "f1", "macro_f1": "f1_macro", "micro_f1": "f1_micro",
}

# Metrics where larger is better (we'll clamp to [0,1]; if >1 assume % and divide by 100)
UP_METRICS = {
    "accuracy", "top-1-accuracy", "top-5-accuracy",
    "precision", "recall", "f1", "f1_macro", "f1_micro",
    "exact_match", "map", "ap", "bleu", "meteor", "chrf",
    "rouge1", "rouge2", "rouge_l", "rouge_lsum",
    "pearson", "spearman", "mcc",
}

# Metrics where smaller is better
DOWN_METRICS = {
    "wer", "cer", "perplexity", "loss", "rmse", "mae", "mape",
    "error_rate", "per_word_error", "char_error_rate",
}

def _canon(name: str) -> str:
    n = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    # normalize some hyphen/underscore variants
    n = n.replace("__", "_")
    # re-map known aliases (apply on dashed variant too)
    dashed = n.replace("_", "-")
    if dashed in ALIASES:
        return ALIASES[dashed]
    if n in ALIASES:
        return ALIASES[n]
    # restore standard forms we list in sets above
    return dashed.replace("-", "_")

def _as_fraction(x: float) -> float:
    """Interpret value as fraction in [0,1], but if clearly a percent (e.g. >1.5), divide by 100."""
    try:
        v = float(x)
    except Exception:
        return math.nan
    if v > 1.5:
        v = v / 100.0
    return max(0.0, min(1.0, v))

def _normalize_metric(name: str, value: Any) -> Optional[float]:
    """
    Convert a metric value to a 0..1 score. Returns None if cannot normalize.
    Heuristics:
      - UP_METRICS: clamp to [0,1] (auto-percent handling)
      - Correlations/MCC: map from [-1,1] -> [0,1]
      - DOWN_METRICS: invert with simple transforms
    """
    m = _canon(name)

    # Try numeric
    try:
        v = float(value)
    except Exception:
        return None

    # Correlation-like in [-1,1]
    if m in {"pearson", "spearman", "mcc"}:
        # If someone reported percent, scale back
        if abs(v) > 1.0 and abs(v) <= 100.0:
            v = v / 100.0
        v = max(-1.0, min(1.0, v))
        return (v + 1.0) / 2.0

    if m in UP_METRICS:
        return _as_fraction(v)

    if m in DOWN_METRICS:
        # Interpret as a rate if it looks like percent/rate
        if m in {"wer", "cer", "error_rate", "char_error_rate", "per_word_error"}:
            r = _as_fraction(v)
            return 1.0 - r  # lower error -> higher score

        if m == "perplexity":
            # Compress heavy tail; PPL ~1 is great, 10 ok, 100 poor
            v = max(1.0, v)
            return 1.0 / (1.0 + math.log10(v))  # 1→1.0, 10→0.5, 100→~0.33

        # Generic loss/RMSE/MAE/MAPE: decreasing returns
        if v < 0:
            v = abs(v)
        return 1.0 / (1.0 + v)  # 0→1.0, 1→0.5, 3→0.25, etc.

    # Unknown metric: try to guess if it's a percentage/rate
    # If in [0,1] or looks like percent -> treat as UP
    f = _as_fraction(v)
    if not math.isnan(f):
        return f #what the fuck is all this bullshit it cannot be this deep

    return None

def _iter_model_index(resp: Dict[str, Any]):
        """
        Yields (task, dataset, metric_name, value) from a HF models API response
        (expects ?expand[]=cardData) or from a dict that is already a model-index.
        """
        # Accept response dict with data.cardData.model-index / model_index
        mi = None
        if isinstance(resp, dict):
            data = resp.get("data") or {}
            card = data.get("cardData") or {}
            mi = card.get("model-index") or card.get("model_index") or resp.get("model-index") or resp.get("model_index")

        if not mi:
            return  # nothing to yield

        for entry in mi:
            for res in entry.get("results", []):
                task = (res.get("task") or {}).get("type")
                d = (res.get("dataset") or {})
                dataset = d.get("name") or d.get("type") or d.get("config") or None
                for m in res.get("metrics", []):
                    mname = m.get("type") or m.get("name")
                    val = m.get("value")
                    if mname is not None and val is not None:
                        yield task, dataset, mname, val

_PROMPT = """You are evaluating PERFORMANCE CLAIMS (benchmarks) for a given model on huggingface. Given a url you need to assess the trustworthiness of the benchmarks and \
    whether these are high quality metrics compared to other models of similar use cases. \
Rate on this discrete scale and reply with ONLY one number: 1.0, 0.5, or 0.0. \
1.0: Benchmarks are accurate and reflect the performance of the model\
0.5: Benchmarks are slightly overexaggerated statistics but the model still performs well\
0.0: Benchmarks are completely inaccurate and cannot be trusted for this model."""


class PerformanceClaims(MetricStd[float]):
    metric_name = "performance_claims"

    def __init__(self, metric_weight=0.2):
        super().__init__(metric_weight)
        self.benchmarks = benchmarks={"batch size": 64, "accuracy": 0.0, "time": 0.0}
        self.benchmarks = benchmarks

    def evaluate(self, url: str) -> float:
        api = hfAPI()
        modelinfo = json.loads(api.get_info(url, printCLI=False))
        try:
            model_index = modelinfo["data"]
        except (KeyError, TypeError):
            model_index = None

        if not model_index:
            prompt = _PROMPT + url
            response = self.llm.main(prompt)
            if "1.0" in response:
                score = 1.0
            elif "0.5" in response:
                score = 0.5
            else:
                score = 0.0
        else:
            score = self.score_model_performance(model_index)
        return score

    def score_model_performance(self, resp):
        """
        Returns (score_0_to_1, breakdown).
        Heuristic: normalize each metric to [0,1], average metrics per (task,dataset),
        then average those group scores. If no metrics, returns (None, {}).
        """
        per_group: Dict[Tuple[Optional[str], Optional[str]], List[float]] = {}
        for task, dataset, mname, val in _iter_model_index(resp):
            s = _normalize_metric(mname, val)
            if s is None or math.isnan(s):
                continue
            per_group.setdefault((task, dataset), []).append(s)

        if not per_group:
            return 0.0

        group_scores = {k: sum(v) / len(v) for k, v in per_group.items()}
        overall = sum(group_scores.values()) / len(group_scores)

        breakdown = {
            "groups": [
                {"task": k[0], "dataset": k[1], "score": round(v, 4), "n_metrics": len(per_group[k])}
                for k, v in sorted(group_scores.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "n_groups": len(group_scores),
            "notes": "Heuristic normalization; higher-is-better metrics treated as fractions; WER/CER inverted; PPL uses 1/(1+log10(ppl)); loss/RMSE use 1/(1+value).",
        }
        
        return round(overall, 4)

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle, *args, **kwargs) -> float:
        #return self.evaluate(artifact_data.url)
        return 0.5


