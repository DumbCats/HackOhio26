"""Deterministic BM25 search over the approved explanation corpus (app/rag/corpus.json).

Pure Python, no embeddings. The corpus is tiny (about 50 passages), so a classic
BM25 over title + text + tags with a light stemmer and a customer-phrasing
synonym map is plenty, fully deterministic, and explainable in Q&A.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parent / "corpus.json"

K1 = 1.5
B = 0.75
TITLE_WEIGHT = 2   # title tokens counted twice
TAG_WEIGHT = 2     # tag tokens counted twice
MIN_SCORE = 2.5    # below this the best hit is treated as "nothing fits"
RELATIVE_CUTOFF = 0.35  # drop hits scoring under 35 in 100 of the best hit

STOPWORDS = frozenset("""
a about above after again all am an and any are as at be because been before being below
between both but by can could did do does doing during each few for from further had
has have having he her here hers him his how i if in into is it its itself just me
my myself no nor not now of on once only or other our ours over own she should
so some such than that the their them then there these they this those through to too under
until up very was we were what when where which while who whom why will with would you your
yours yourself please hi hello hey thanks thank ok okay im i'm us also get got go going know
tell say said mean means really still yet ever even like want need does doesn't don't dont
""".split())

# Customer phrasing -> extra query words that appear in the right passages' tags.
# Keys are matched as whole phrases on the lowercased query (word boundaries).
SYNONYMS: dict[str, str] = {
    # restoration / timing
    "eta": "restoration estimate range when back",
    "when back": "restoration estimate range",
    "when will": "restoration estimate range when back",
    "how long": "restoration estimate range hours",
    "come back": "restoration back estimate",
    "coming back": "restoration back estimate",
    "turn on": "restoration back",
    "fixed": "restoration repair back",
    "lights back": "restoration back restored",
    "power back": "restoration back restored",
    "back on": "restoration back restored",
    "how many hours": "restoration estimate range hours",
    # risk
    "chance": "risk band",
    "likely": "risk band",
    "odds": "risk band percent",
    "risk": "band",
    "band": "risk band",
    "my band": "risk band meaning",
    "high risk": "band high risk factors",
    "lose power": "risk band",
    "losing power": "risk band",
    "percent": "risk percent",
    "percentage": "risk percent",
    # confidence
    "sure": "confidence",
    "how sure": "confidence",
    "accurate": "confidence accuracy",
    "accuracy": "confidence accurate",
    "trust": "confidence",
    "reliable": "confidence",
    "believe": "confidence trust",
    "certain": "confidence",
    # can't predict / fallback
    "can't predict": "fallback reliably",
    "cant predict": "fallback reliably",
    "cannot predict": "fallback reliably",
    "predict": "fallback reliably",
    "no band": "fallback",
    "no estimate": "fallback",
    # step restoration
    "neighbor": "neighbor step steps",
    "neighbour": "neighbor step steps",
    "next door": "neighbor step",
    "across the street": "neighbor step street",
    "before me": "neighbor step first",
    "logged": "log",
    "do you log": "log",
    "they have power": "neighbor step",
    # estimate changed
    "changed": "estimate change update",
    "keeps changing": "estimate change update",
    "went up": "estimate change update longer",
    "pushed back": "estimate change update later",
    "longer now": "estimate change update longer",
    # privacy
    "my data": "privacy data",
    "private": "privacy",
    "personal": "privacy",
    "my address": "privacy address",
    "store": "stored needs privacy",
    "save": "stored needs privacy",
    "keep my": "stored needs privacy",
    "sell": "privacy data",
    "share my": "privacy share",
    "medical info": "needs stored privacy",
    "medical information": "needs stored privacy",
    # real vs simulated
    "fake": "simulated real",
    "real": "real simulated",
    "is this live": "live simulated real",
    "made up": "simulated real",
    "demo": "simulated demo",
    # crews
    "crew": "crews",
    "trucks": "crews",
    "linemen": "crews",
    "lineman": "crews",
    "workers": "crews",
    "fixing": "crews repair",
    "how often": "accurate accuracy check",
    # labels
    "label": "label chip source",
    "badge": "label chip source",
    "tag": "label chip source",
    "our estimate": "label chip source",
    "simulated utility feed": "label chip source",
    "utility confirmed": "label chip source",
    "safety guidance": "label chip source",
    "what is simulated": "real simulated",
    "how many crews": "crews pool",
    "power is out": "outage know",
    "power out": "outage",
    "lights out": "outage",
    # data sources
    "where does": "source data",
    "data come": "data source",
    "data from": "data source",
    # weather
    "weather": "weather forecast",
    "forecast": "weather forecast",
    # improvement
    "better": "improve",
    "limitation": "improve missing",
    "limitations": "improve missing",
    # official
    "official": "official outage page utility",
    "aep website": "official outage page",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def stem(word: str) -> str:
    """Light suffix stemmer: enough to fold neighbors/neighbor, changed/change."""
    w = word.replace("'", "")
    if len(w) <= 3 or w.isdigit():
        return w
    for suf, rep in (("ies", "y"), ("ing", ""), ("ied", "y"), ("ed", ""), ("ly", ""),
                     ("es", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: len(w) - len(suf)] + rep
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    out = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        s = stem(tok)
        if s and s not in STOPWORDS:
            out.append(s)
    return out


def expand_query(query: str) -> str:
    q = " " + re.sub(r"\s+", " ", query.lower()) + " "
    extra = []
    for phrase in sorted(SYNONYMS):  # sorted -> deterministic
        if re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", q):
            extra.append(SYNONYMS[phrase])
    return query + " " + " ".join(extra)


@lru_cache(maxsize=1)
def load_corpus() -> tuple[dict, ...]:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return tuple(data["passages"])


@lru_cache(maxsize=1)
def _index():
    passages = load_corpus()
    docs = []
    for p in passages:
        toks = (tokenize(p["title"]) * TITLE_WEIGHT + tokenize(p["text"])
                + tokenize(" ".join(p.get("tags", []))) * TAG_WEIGHT)
        docs.append(Counter(toks))
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    lengths = [sum(d.values()) for d in docs]
    avgdl = sum(lengths) / max(n, 1)
    return passages, docs, idf, lengths, avgdl


def score_all(query: str) -> list[tuple[float, int]]:
    passages, docs, idf, lengths, avgdl = _index()
    q_terms = Counter(tokenize(expand_query(query)))
    scores = []
    for i, d in enumerate(docs):
        s = 0.0
        for term, qtf in q_terms.items():
            tf = d.get(term)
            if not tf:
                continue
            denom = tf + K1 * (1 - B + B * lengths[i] / avgdl)
            # query term repeats (from synonyms) count, but with diminishing weight
            s += idf[term] * tf * (K1 + 1) / denom * (1 + math.log(qtf))
        scores.append((round(s, 6), i))
    # sort by score desc, then corpus order -> fully deterministic
    scores.sort(key=lambda x: (-x[0], x[1]))
    return scores


def search(query: str, k: int = 3) -> list[dict]:
    """Top-k passages ({id, title, text, score}); [] when nothing fits."""
    if not query or not query.strip():
        return []
    k = max(1, min(int(k), 10))
    passages = load_corpus()
    ranked = score_all(query)
    if not ranked or ranked[0][0] < MIN_SCORE:
        return []
    best = ranked[0][0]
    out = []
    for s, i in ranked[:k]:
        if s < MIN_SCORE or s < best * RELATIVE_CUTOFF:
            break
        p = passages[i]
        out.append({"id": p["id"], "title": p["title"], "text": p["text"], "score": s})
    return out
