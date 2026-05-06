import math
import jieba
from typing import List, Tuple


class Bm25Service:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: List[str] = []
        self._tokenized_docs: List[List[str]] = []
        self._doc_len: List[int] = []
        self._avgdl: float = 0
        self._idf: dict = {}
        self._doc_freqs: List[dict] = []
        self._corpus_size: int = 0

    def rebuild_index(self, documents: List[str]):
        self._documents = documents
        self._corpus_size = len(documents)
        if self._corpus_size == 0:
            return

        self._tokenized_docs = []
        self._doc_len = []
        for doc in documents:
            tokens = [w for w in jieba.cut(doc) if len(w) >= 2]
            self._tokenized_docs.append(tokens)
            self._doc_len.append(len(tokens))

        total_len = sum(self._doc_len)
        self._avgdl = total_len / self._corpus_size if self._corpus_size > 0 else 0

        df = {}
        for tokens in self._tokenized_docs:
            seen = set(tokens)
            for word in seen:
                df[word] = df.get(word, 0) + 1

        self._idf = {}
        for word, freq in df.items():
            self._idf[word] = math.log((self._corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

        self._doc_freqs = []
        for tokens in self._tokenized_docs:
            freq = {}
            for word in tokens:
                freq[word] = freq.get(word, 0) + 1
            self._doc_freqs.append(freq)

    def search(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        if self._corpus_size == 0:
            return []

        query_tokens = [w for w in jieba.cut(query) if len(w) >= 2]
        if not query_tokens:
            return []

        scores = []
        for i in range(self._corpus_size):
            score = self._score(query_tokens, i)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _score(self, query_tokens: List[str], doc_idx: int) -> float:
        score = 0.0
        doc_len = self._doc_len[doc_idx]
        doc_freq = self._doc_freqs[doc_idx]

        for word in query_tokens:
            if word not in self._idf:
                continue
            idf = self._idf[word]
            tf = doc_freq.get(word, 0)
            if tf == 0:
                continue

            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avgdl)
            score += idf * numerator / denominator

        return score
