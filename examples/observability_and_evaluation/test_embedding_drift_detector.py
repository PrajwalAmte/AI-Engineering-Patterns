from common.fakes import embed
from observability_and_evaluation.embedding_drift_detector import DriftDetector

DOCS = [
    "how to reset your password from the login page",
    "update billing card and download invoices",
    "export your data as csv from settings",
    "invite teammates and manage workspace roles",
]
BASELINE_QUERIES = [
    "reset password login",
    "download invoice billing",
    "export csv settings data",
    "invite teammates workspace",
] * 15
NEW_TOPIC = ["does the api support webhooks for payment events", "webhook retry policy for api events"] * 30


def make():
    detector = DriftDetector(embed=embed, index=[embed(d) for d in DOCS], min_samples=40)
    detector.fit_baseline(BASELINE_QUERIES)
    return detector


def test_stays_quiet_on_familiar_traffic():
    detector = make()
    for q in BASELINE_QUERIES:
        detector.observe(q)
    report = detector.report()
    assert report.alerts == []
    assert report.centroid_shift < 0.01


def test_alerts_when_users_ask_about_things_the_index_does_not_cover():
    detector = make()
    for q in NEW_TOPIC:
        detector.observe(q)
    report = detector.report()
    assert report.alignment_drop > 0.10
    assert any("alignment" in a for a in report.alerts)
    assert any("centroid" in a for a in report.alerts)


def test_no_verdict_until_enough_samples():
    detector = make()
    for q in NEW_TOPIC[:10]:
        detector.observe(q)
    assert detector.report() is None
