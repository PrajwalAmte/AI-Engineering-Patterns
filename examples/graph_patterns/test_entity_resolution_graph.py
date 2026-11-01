from graph_patterns.entity_resolution_graph import Record, normalize, resolve


def ids(resolution):
    return sorted(sorted(r.id for r in c) for c in resolution.clusters)


def test_normalisation_drops_legal_suffixes_and_punctuation():
    assert normalize("Acme, Inc.") == normalize("ACME Inc") == "acme"
    assert normalize("Smith & Sons Ltd") == "smith and sons"


def test_same_company_across_sources_is_merged():
    records = [
        Record("crm-1", "crm", "Acme Inc.", email_domain="acme.com"),
        Record("billing-9", "billing", "ACME Incorporated", email_domain="acme.com"),
        Record("support-4", "support", "Acme", city="Berlin"),
        Record("crm-2", "crm", "Globex Corporation", email_domain="globex.com"),
    ]
    assert ids(resolve(records)) == [["billing-9", "crm-1", "support-4"], ["crm-2"]]


def test_similar_names_with_conflicting_identifiers_stay_apart():
    records = [
        Record("a", "crm", "Delta Air", tax_id="11-111"),
        Record("b", "crm", "Delta Air", tax_id="22-222"),
    ]
    result = resolve(records)
    assert ids(result) == [["a"], ["b"]]


def test_a_bridge_record_cannot_chain_two_different_entities():
    records = [
        Record("x", "crm", "Apex Labs", email_domain="apexlabs.io"),
        Record("bridge", "support", "Apex"),  # vague: matches both
        Record("y", "crm", "Apex Dental", email_domain="apexdental.com"),
    ]
    result = resolve(records, threshold=0.3)
    assert not any({"x", "y"} <= set(c) for c in ids(result))
    assert result.rejected  # the blocked merge is recorded for review


def test_matching_tax_id_is_decisive():
    records = [Record("a", "s1", "Initech", tax_id="99-1"), Record("b", "s2", "Initech Holdings", tax_id="99-1")]
    assert ids(resolve(records)) == [["a", "b"]]
