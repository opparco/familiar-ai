"""
SentenceTransformer 埋め込みモデル比較デモ
  - intfloat/multilingual-e5-small
  - cl-nagoya/ruri-v3-30m
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# モデル定義
# ──────────────────────────────────────────────

class MultilingualE5Model:

    MODEL_NAME = "intfloat/multilingual-e5-small"

    def __init__(self) -> None:
        self._model: Any = None

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading %s ...", self.MODEL_NAME)
            t0 = time.perf_counter()
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Loaded in %.2f s", time.perf_counter() - t0)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        self._load()
        prefixed = [f"passage: {t}" for t in texts]
        return self._model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        self._load()
        prefixed = [f"query: {t}" for t in texts]
        return self._model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)


class RuriV3Model:

    MODEL_NAME = "cl-nagoya/ruri-v3-30m"

    def __init__(self) -> None:
        self._model: Any = None

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading %s ...", self.MODEL_NAME)
            t0 = time.perf_counter()
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Loaded in %.2f s", time.perf_counter() - t0)

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        self._load()
        prefixed = [f"検索文書: {t}" for t in texts]
        return self._model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        self._load()
        prefixed = [f"検索クエリ: {t}" for t in texts]
        return self._model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)


# ──────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def run_retrieval_demo(model_name: str, encode_docs, encode_queries) -> None:
    """クエリと文書のマッチングデモ。"""

    documents = [
        "東京は日本の首都であり、世界最大の都市圏のひとつです。",
        "機械学習はデータからパターンを学習するAIの一分野です。",
        "日本の伝統料理には寿司、天ぷら、ラーメンなどがあります。",
        "気候変動は地球温暖化や異常気象を引き起こしています。",
        "Python は科学計算や機械学習で広く使われるプログラミング言語です。",
        "富士山は日本で最も高い山で、標高3776メートルです。",
        "自然言語処理（NLP）はテキストデータを扱うAI技術です。",
    ]

    queries = [
        "日本の首都はどこ？",
        "ディープラーニングとは何か",
        "富士山の高さ",
        "日本食について教えて",
    ]

    print(f"\n{'='*60}")
    print(f"  モデル: {model_name}")
    print(f"{'='*60}")

    doc_embeddings = encode_docs(documents)
    query_embeddings = encode_queries(queries)

    for q, q_emb in zip(queries, query_embeddings):
        scores = [(cosine_similarity(q_emb, d_emb), doc) for d_emb, doc in zip(doc_embeddings, documents)]
        scores.sort(reverse=True)
        print(f"\nクエリ: 「{q}」")
        for rank, (score, doc) in enumerate(scores[:3], 1):
            print(f"  {rank}位 [{score:.4f}] {doc}")


def run_sts_demo(model_name: str, encode_queries) -> None:
    """文ペアの意味的類似度デモ (STS)。"""

    pairs = [
        ("猫が窓の外を見ている", "ネコが窓から外を眺めています"),  # 高類似
        ("今日は晴れています", "明日は雨が降るでしょう"),  # 低類似
        ("機械学習モデルを訓練する", "AIを学習させる"),  # 中高類似
        ("東京タワーは赤い", "スカイツリーは東京にある"),  # 低..中類似
        ("彼女はピアノを弾くのが好きだ", "彼女はピアノを演奏することを楽しんでいる"),  # 高類似
    ]

    print(f"\n{'='*60}")
    print(f"  STS デモ: {model_name}")
    print(f"{'='*60}")

    sents_a = [p[0] for p in pairs]
    sents_b = [p[1] for p in pairs]

    emb_a = encode_queries(sents_a)
    emb_b = encode_queries(sents_b)

    for (a, b), ea, eb in zip(pairs, emb_a, emb_b):
        score = cosine_similarity(ea, eb)
        print(f"  [{score:.4f}] 「{a}」 .. 「{b}」")


def run_multilingual_demo(model_name: str, encode_queries) -> None:
    """多言語テキストの類似度デモ。"""
    sentences = [
        "東京は日本の首都です",
        "Tokyo is the capital of Japan",
        "東京は大きな都市です",
        "Paris is the capital of France",
        "パリはフランスの首都です",
    ]

    print(f"\n{'='*60}")
    print(f"  多言語デモ: {model_name}")
    print(f"{'='*60}")

    embeddings = encode_queries(sentences)
    n = len(sentences)

    # 類似度行列を表示
    sims = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            sims[i][j] = cosine_similarity(embeddings[i], embeddings[j])

    header = "      " + "  ".join(f"  [{i}]" for i in range(n))
    print(header)
    for i, row in enumerate(sims):
        row_str = "  ".join(f"{v:.3f}" for v in row)
        print(f"  [{i}] {row_str}")
    print()
    for i, s in enumerate(sentences):
        print(f"  [{i}] {s}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

def main() -> None:
    e5 = MultilingualE5Model()
    ruri = RuriV3Model()

    models = [
        (e5.MODEL_NAME, e5.encode_documents, e5.encode_queries),
        (ruri.MODEL_NAME, ruri.encode_documents, ruri.encode_queries),
    ]

    for name, enc_docs, enc_queries in models:
        run_retrieval_demo(name, enc_docs, enc_queries)

    for name, _, enc_queries in models:
        run_sts_demo(name, enc_queries)

    for name, _, enc_queries in models:
        run_multilingual_demo(name, enc_queries)


if __name__ == "__main__":
    main()
