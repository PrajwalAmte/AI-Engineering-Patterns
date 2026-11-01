from common.fakes import embed
from retrieval_and_memory.hybrid_search import BM25, HybridIndex, rrf

DOCS = [
    "Error E-4012 means the payment token expired. Ask the customer to re-enter their card.",
    "Resolving login failures: reset the password, then clear the SSO session.",
    "Our office is closed on public holidays.",
    "Error E-4013 means the card was declined by the issuing bank.",
]

SYNONYMS = {"authentication": "login", "sign": "login", "problems": "failures", "issues": "failures"}


def synonym_embed(text):
    """Stands in for a real embedding model: knows that 'authentication issues' ~ 'login failures'."""
    words = [SYNONYMS.get(w, w) for w in text.lower().replace("?", "").split()]
    return embed(" ".join(words))


def test_bm25_ranks_exact_identifier_first():
    scores = BM25(DOCS).scores("what does E-4012 mean")
    assert max(range(len(DOCS)), key=lambda i: scores[i]) == 0


def test_rrf_rewards_documents_both_retrievers_agree_on():
    fused = rrf([[1, 2, 3], [2, 1, 4]])
    assert fused[1] == fused[2] > fused[3] > 0
    assert fused[4] > 0


def test_identifier_query_is_served_by_the_sparse_side():
    hits = HybridIndex(DOCS, synonym_embed).search("E-4012", k=2)
    assert hits[0].doc_id == 0
    assert hits[0].sparse_rank == 1


def test_paraphrase_query_is_served_by_the_dense_side():
    hits = HybridIndex(DOCS, synonym_embed).search("authentication issues", k=1)
    assert hits[0].doc_id == 1
    assert hits[0].sparse_rank is None
    assert hits[0].dense_rank == 1
