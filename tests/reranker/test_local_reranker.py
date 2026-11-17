"""Local encoder precision tests, plus an optional real-model smoke test."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from zotero_arxiv_daily.reranker.local import LocalReranker


@pytest.mark.parametrize(
    ("device_type", "expected_dtype"),
    [("cpu", torch.float32), ("cuda", torch.bfloat16), ("mps", torch.bfloat16)],
)
def test_encoder_precision_preserves_accelerator_defaults(config, monkeypatch, device_type, expected_dtype):
    """Exercise real tensor conversion without loading model weights or requiring a GPU."""
    class TinyEncoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(
                [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=torch.bfloat16
            ))
            self.device = SimpleNamespace(type=device_type)
            self.encoding_dtypes = []

        @property
        def dtype(self):
            return self.weight.dtype

        def encode(self, texts, **kwargs):
            self.encoding_dtypes.append(self.dtype)
            indices = [{"hello": 0, "world": 1, "ping": 2}[text] for text in texts]
            return self.weight[indices].detach().float().numpy()

        def similarity(self, candidates, corpus):
            return torch.from_numpy(candidates @ corpus.T)

    encoder = TinyEncoder()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(
        SentenceTransformer=lambda *args, **kwargs: encoder
    ))
    config.executor.debug = True
    scores = LocalReranker(config).get_similarity_score(["hello", "world"], ["ping"])

    assert encoder.encoding_dtypes == [expected_dtype, expected_dtype]
    np.testing.assert_allclose(scores, [[0.5], [0.5]])


@pytest.mark.slow
def test_local_reranker(config):
    reranker = LocalReranker(config)
    score = reranker.get_similarity_score(["hello", "world"], ["ping"])
    assert score.shape == (2, 1)
