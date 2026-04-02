from collections import Counter

from app.data.pr_elected_members_2082 import PR_ELECTED_MEMBERS_2082


def test_pr_member_count_and_party_split():
    assert len(PR_ELECTED_MEMBERS_2082) == 110

    counts = Counter(row["party"] for row in PR_ELECTED_MEMBERS_2082)
    assert counts == {
        "राष्ट्रिय स्वतन्त्र पार्टी": 57,
        "नेपाली काँग्रेस": 20,
        "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)": 16,
        "नेपाली कम्युनिष्ट पार्टी": 9,
        "श्रम संस्कृति पार्टी": 4,
        "राष्ट्रिय प्रजातन्त्र पार्टी": 4,
    }
