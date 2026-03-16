#!/usr/bin/env python3
"""
Comprehensive test suite for the enhanced ML/NLP system.

Tests:
1. NepaliPreprocessor - Unicode normalization, tokenization, language detection
2. NepaliTransliterator - Bidirectional transliteration
3. HybridNER - Entity extraction (rule-based only, no heavy models)
4. TextEmbedder - Embedding generation (using MiniLM for speed)
5. SemanticSeverityDetector - Severity classification
6. PriorityBandit - Priority prediction with v2 features
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test data - real Nepal news samples (English and Nepali)
TEST_STORIES = [
    {
        "id": 1,
        "title": "Multiple killed in bus accident in Sindhupalchok",
        "content": "A bus carrying passengers fell into Sunkoshi river in Sindhupalchok district today, killing at least 15 people. Police and army rescue teams have been deployed.",
        "expected_severity": "critical",
        "expected_category": "disaster",
        "language": "english",
    },
    {
        "id": 2,
        "title": "PM Pushpa Kamal Dahal meets Indian PM Modi in Delhi",
        "content": "Prime Minister Pushpa Kamal Dahal held bilateral talks with Indian Prime Minister Narendra Modi in New Delhi. Both leaders discussed trade, connectivity and border issues.",
        "expected_severity": "medium",
        "expected_category": "political",
        "language": "english",
    },
    {
        "id": 3,
        "title": "काठमाडौंमा प्रदर्शनले यातायात अवरुद्ध",
        "content": "विद्यार्थी संगठनहरूले काठमाडौंको माइतीघर मण्डलामा प्रदर्शन गरे। प्रदर्शनकारीहरूले सरकारको नयाँ शिक्षा नीतिको विरोध गरे।",
        "expected_severity": "medium",
        "expected_category": "social",
        "language": "nepali",
    },
    {
        "id": 4,
        "title": "भूकम्पमा ठूलो क्षति, धेरैको मृत्यु",
        "content": "गोरखा जिल्लामा ७.८ म्याग्निच्युडको भूकम्प गयो। भूकम्पमा कम्तीमा ५० जनाको मृत्यु भएको छ भने सयौं घाइते भएका छन्।",
        "expected_severity": "critical",
        "expected_category": "disaster",
        "language": "nepali",
    },
    {
        "id": 5,
        "title": "Nepal Rastra Bank announces new monetary policy",
        "content": "The central bank has announced its monetary policy for the fiscal year. Interest rates on loans will be reduced to boost economic growth.",
        "expected_severity": "medium",
        "expected_category": "economic",
        "language": "english",
    },
    {
        "id": 6,
        "title": "Police arrest suspects in Kathmandu murder case",
        "content": "Nepal Police arrested three suspects in connection with a murder in Balaju. The suspects were allegedly involved in a gang-related killing.",
        "expected_severity": "high",
        "expected_category": "security",
        "language": "english",
    },
    {
        "id": 7,
        "title": "दशैंको रौनक, देशभर उल्लास",
        "content": "नेपालभर दशैं पर्वको रौनक छाएको छ। विजया दशमीको दिन देशभरका मन्दिरहरूमा टीका लगाउनेको भीड लागेको छ।",
        "expected_severity": "low",
        "expected_category": "social",
        "language": "nepali",
    },
    {
        "id": 8,
        "title": "Explosion in Biratnagar injures several",
        "content": "A bomb explosion near a marketplace in Biratnagar has injured at least 8 people. Police suspect this may be linked to extortion threats from criminal groups.",
        "expected_severity": "high",
        "expected_category": "security",
        "language": "english",
    },
]


def print_header(title: str):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, passed: bool, details: str = ""):
    """Print a test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
    if details:
        for line in details.split("\n"):
            print(f"         {line}")


def test_nepali_preprocessor():
    """Test the NepaliPreprocessor class."""
    print_header("Testing NepaliPreprocessor")

    from app.services.nlp.nepali_preprocessor import NepaliPreprocessor

    preprocessor = NepaliPreprocessor()
    passed = 0
    total = 0

    # Test 1: Unicode normalization
    total += 1
    test_text = "काठमाडौं   मा    प्रदर्शन"
    normalized = preprocessor.normalize(test_text)
    if "  " not in normalized and normalized.strip() == normalized:
        print_result("Unicode normalization", True, f"'{test_text}' → '{normalized}'")
        passed += 1
    else:
        print_result("Unicode normalization", False)

    # Test 2: Tokenization
    total += 1
    test_text = "PM Dahal visited Pokhara काठमाडौं"
    tokens = preprocessor.tokenize(test_text)
    expected_tokens = ["PM", "Dahal", "visited", "Pokhara", "काठमाडौं"]
    if tokens == expected_tokens:
        print_result("Tokenization", True, f"Tokens: {tokens}")
        passed += 1
    else:
        print_result("Tokenization", False, f"Expected: {expected_tokens}, Got: {tokens}")

    # Test 3: Language detection (Nepali)
    total += 1
    nepali_text = "काठमाडौंमा प्रदर्शन भयो"
    is_nepali = preprocessor.is_nepali(nepali_text)
    if is_nepali:
        print_result("Nepali detection", True, f"'{nepali_text}' detected as Nepali")
        passed += 1
    else:
        print_result("Nepali detection", False)

    # Test 4: Language detection (English)
    total += 1
    english_text = "Prime Minister visited Kathmandu today"
    is_nepali = preprocessor.is_nepali(english_text)
    if not is_nepali:
        print_result("English detection", True, f"'{english_text}' detected as English")
        passed += 1
    else:
        print_result("English detection", False)

    # Test 5: Stopword removal
    total += 1
    tokens = ["यो", "प्रधानमन्त्री", "को", "भेट", "हो"]
    filtered = preprocessor.remove_stopwords(tokens)
    if "को" not in filtered and "हो" not in filtered and "प्रधानमन्त्री" in filtered:
        print_result("Stopword removal", True, f"Filtered: {filtered}")
        passed += 1
    else:
        print_result("Stopword removal", False, f"Got: {filtered}")

    # Test 6: Devanagari digit conversion
    total += 1
    test_text = "भूकम्प ७.८ म्याग्निच्युड"
    normalized = preprocessor.normalize(test_text)
    if "7.8" in normalized:
        print_result("Digit conversion", True, f"'{test_text}' → '{normalized}'")
        passed += 1
    else:
        print_result("Digit conversion", False, f"Got: '{normalized}'")

    print(f"\n  Results: {passed}/{total} tests passed")
    return passed == total


def test_nepali_transliterator():
    """Test the NepaliTransliterator class."""
    print_header("Testing NepaliTransliterator")

    from app.services.nlp.nepali_preprocessor import NepaliTransliterator

    transliterator = NepaliTransliterator()
    passed = 0
    total = 0

    # Test 1: Roman to Devanagari (dictionary)
    total += 1
    roman = "kathmandu"
    devanagari = transliterator.to_devanagari(roman)
    if devanagari == "काठमाडौं":
        print_result("Roman→Devanagari (dict)", True, f"'{roman}' → '{devanagari}'")
        passed += 1
    else:
        print_result("Roman→Devanagari (dict)", False, f"Expected: काठमाडौं, Got: {devanagari}")

    # Test 2: Common surnames
    total += 1
    roman = "Dahal"
    devanagari = transliterator.to_devanagari(roman.lower())
    if devanagari == "दाहाल":
        print_result("Surname transliteration", True, f"'{roman}' → '{devanagari}'")
        passed += 1
    else:
        print_result("Surname transliteration", False, f"Got: {devanagari}")

    # Test 3: Get all forms
    total += 1
    name = "pokhara"
    forms = transliterator.get_all_forms(name)
    if "पोखरा" in forms and "pokhara" in forms:
        print_result("Get all forms", True, f"Forms for '{name}': {forms[:4]}...")
        passed += 1
    else:
        print_result("Get all forms", False, f"Got: {forms}")

    print(f"\n  Results: {passed}/{total} tests passed")
    return passed == total


def test_hybrid_ner():
    """Test the HybridNER class (rule-based only)."""
    print_header("Testing HybridNER (Rule-Based)")

    from app.services.nlp.hybrid_ner import HybridNER

    ner = HybridNER()
    passed = 0
    total = 0

    # Test 1: Extract politicians
    total += 1
    text = "PM Pushpa Kamal Dahal met with KP Sharma Oli yesterday in Kathmandu."
    entities = ner._extract_rule_based_entities(text)
    politicians = [e for e in entities if e["type"] == "PERSON"]
    if len(politicians) >= 2:
        names = [p["text"] for p in politicians]
        print_result("Politician extraction", True, f"Found: {names}")
        passed += 1
    else:
        print_result("Politician extraction", False, f"Found: {politicians}")

    # Test 2: Extract districts
    total += 1
    text = "The earthquake affected Sindhupalchok, Dolakha, and Gorkha districts."
    entities = ner._extract_rule_based_entities(text)
    locations = [e for e in entities if e["type"] == "LOCATION"]
    if len(locations) >= 3:
        locs = [l["text"] for l in locations]
        print_result("District extraction", True, f"Found: {locs}")
        passed += 1
    else:
        print_result("District extraction", False, f"Found: {locations}")

    # Test 3: Extract Nepali entities
    total += 1
    text = "प्रधानमन्त्री पुष्पकमल दाहालले काठमाडौंमा भाषण गरे"
    entities = ner._extract_rule_based_entities(text)
    if len(entities) >= 1:
        print_result("Nepali entity extraction", True, f"Found: {[e['text'] for e in entities]}")
        passed += 1
    else:
        print_result("Nepali entity extraction", False)

    # Test 4: Extract organizations
    total += 1
    text = "Nepal Rastra Bank announced new policy. The Election Commission will hold meetings."
    entities = ner._extract_rule_based_entities(text)
    orgs = [e for e in entities if e["type"] == "ORGANIZATION"]
    if len(orgs) >= 1:
        print_result("Organization extraction", True, f"Found: {[o['text'] for o in orgs]}")
        passed += 1
    else:
        print_result("Organization extraction", False)

    # Test 5: Full hybrid extraction (including transformer if available)
    total += 1
    text = "Minister Narayan Kaji Shrestha visited Pokhara to inspect flood damage."
    try:
        entities = ner.extract_entities(text)
        # Even if transformer fails, rule-based should work
        if len(entities) >= 1:
            print_result("Hybrid extraction", True, f"Found {len(entities)} entities")
            passed += 1
        else:
            print_result("Hybrid extraction", False, "No entities found")
    except Exception as e:
        print_result("Hybrid extraction", False, f"Error: {e}")

    print(f"\n  Results: {passed}/{total} tests passed")
    return passed == total


def test_text_embedder():
    """Test the MultilingualTextEmbedder (using MiniLM for speed)."""
    print_header("Testing MultilingualTextEmbedder")

    from app.services.embeddings.text_embedder import get_embedder, get_multilingual_embedder

    passed = 0
    total = 0

    # Use MiniLM for faster testing
    print("  Loading MiniLM embedder (for faster testing)...")
    start = time.time()
    embedder = get_embedder(model_key="minilm")

    # Test 1: Basic embedding
    total += 1
    text = "Nepal earthquake kills hundreds"
    embedding = embedder.embed_text(text)
    if len(embedding) == 384 and embedding[0] != 0.0:
        print_result("Basic embedding", True, f"Dim: {len(embedding)}, First 3: {embedding[:3]}")
        passed += 1
    else:
        print_result("Basic embedding", False, f"Dim: {len(embedding)}")

    # Test 2: Empty text handling
    total += 1
    embedding = embedder.embed_text("")
    if len(embedding) == 384 and all(v == 0.0 for v in embedding):
        print_result("Empty text handling", True, "Returns zero vector")
        passed += 1
    else:
        print_result("Empty text handling", False)

    # Test 3: Nepali text embedding
    total += 1
    nepali_text = "काठमाडौंमा भूकम्प"
    embedding = embedder.embed_text(nepali_text, preprocess=True)
    if len(embedding) == 384 and embedding[0] != 0.0:
        print_result("Nepali embedding", True, f"Successfully embedded Nepali text")
        passed += 1
    else:
        print_result("Nepali embedding", False)

    # Test 4: Batch embedding
    total += 1
    texts = ["Earthquake in Nepal", "Flood in India", "Election results"]
    embeddings = embedder.embed_texts(texts)
    if len(embeddings) == 3 and len(embeddings[0]) == 384:
        print_result("Batch embedding", True, f"Embedded {len(texts)} texts")
        passed += 1
    else:
        print_result("Batch embedding", False)

    # Test 5: Similarity computation
    total += 1
    text1 = "Earthquake kills many in Nepal"
    text2 = "Nepal disaster death toll rises"
    text3 = "Football match in Kathmandu"

    emb1 = embedder.embed_text(text1)
    emb2 = embedder.embed_text(text2)
    emb3 = embedder.embed_text(text3)

    sim_similar = embedder.compute_similarity(emb1, emb2)
    sim_different = embedder.compute_similarity(emb1, emb3)

    if sim_similar > sim_different:
        print_result("Similarity ordering", True,
                    f"Similar: {sim_similar:.3f}, Different: {sim_different:.3f}")
        passed += 1
    else:
        print_result("Similarity ordering", False,
                    f"Expected similar > different, got {sim_similar:.3f} vs {sim_different:.3f}")

    elapsed = time.time() - start
    print(f"\n  Results: {passed}/{total} tests passed (in {elapsed:.2f}s)")
    return passed == total


def test_semantic_severity():
    """Test the SemanticSeverityDetector."""
    print_header("Testing SemanticSeverityDetector")

    # Patch to use MiniLM for faster testing
    import app.ml.features.semantic_severity as severity_module
    from app.services.embeddings.text_embedder import get_embedder

    passed = 0
    total = 0

    print("  Initializing severity detector...")
    start = time.time()

    # Create detector
    detector = severity_module.SemanticSeverityDetector(
        temperature=0.2,
        min_confidence=0.25,
    )
    # Force use of minilm for testing
    detector._embedder = get_embedder(model_key="minilm")

    # Test cases with expected severity
    test_cases = [
        ("Bomb explosion kills 20 people in market", "critical"),
        ("Major earthquake devastates city, hundreds dead", "critical"),
        ("विस्फोटमा धेरैको मृत्यु भएको छ", "critical"),
        ("Police arrest suspects in murder case", "high"),
        ("Flood displaces thousands of families", "high"),
        ("Government announces new policy reforms", "medium"),
        ("प्रदर्शनले यातायात अवरुद्ध", "medium"),
        ("Festival celebrations across Nepal", "low"),
        ("Local sports team wins championship", "low"),
    ]

    correct = 0
    for text, expected in test_cases:
        total += 1
        severity, confidence, probs = detector.detect_severity(text)

        # Check if top-2 includes expected
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        top2 = [s[0] for s in sorted_probs[:2]]

        if severity == expected or expected in top2:
            print_result(f"Severity: {text[:40]}...", True,
                        f"Predicted: {severity} ({confidence:.2f}), Expected: {expected}")
            passed += 1
            correct += 1
        else:
            print_result(f"Severity: {text[:40]}...", False,
                        f"Predicted: {severity}, Expected: {expected}\n"
                        f"Probs: {dict(sorted_probs)}")

    # Test batch detection
    total += 1
    texts = [t[0] for t in test_cases[:3]]
    results = detector.detect_severity_batch(texts)
    if len(results) == 3:
        print_result("Batch detection", True, f"Processed {len(texts)} texts")
        passed += 1
    else:
        print_result("Batch detection", False)

    # Test severity score
    total += 1
    high_sev_text = "Bomb kills dozens of people"
    low_sev_text = "Festival brings joy to community"
    high_score = detector.get_severity_score(high_sev_text)
    low_score = detector.get_severity_score(low_sev_text)
    if high_score > low_score:
        print_result("Severity score ordering", True,
                    f"High: {high_score:.3f}, Low: {low_score:.3f}")
        passed += 1
    else:
        print_result("Severity score ordering", False)

    elapsed = time.time() - start
    print(f"\n  Results: {passed}/{total} tests passed (in {elapsed:.2f}s)")
    print(f"  Accuracy: {correct}/{len(test_cases)} severity classifications correct")
    return passed >= total * 0.7  # 70% pass rate acceptable


def test_priority_bandit():
    """Test the PriorityBandit with v2 features."""
    print_header("Testing PriorityBandit (v2 Features)")

    from app.ml.models.priority_bandit import PriorityBandit, get_priority_bandit

    passed = 0
    total = 0

    # Test 1: Feature extraction v1 (legacy)
    total += 1
    bandit = PriorityBandit(input_dim=14)
    features_v1 = bandit.extract_context_features(
        category="security",
        severity_keywords=["killed", "explosion"],
        source_confidence=0.8,
        entity_count=3,
        hour_of_day=14,
        day_of_week=2,
        is_weekend=False,
    )
    if len(features_v1) == 14:
        print_result("V1 feature extraction", True, f"Dim: {len(features_v1)}")
        passed += 1
    else:
        print_result("V1 feature extraction", False, f"Dim: {len(features_v1)}")

    # Test 2: Feature extraction v2
    total += 1
    bandit_v2 = PriorityBandit(input_dim=32)

    # Create mock entities
    mock_entities = [
        {"text": "Pushpa Kamal Dahal", "type": "PERSON", "source": "rule_based"},
        {"text": "Kathmandu", "type": "LOCATION", "source": "rule_based"},
        {"text": "Nepal Rastra Bank", "type": "ORGANIZATION", "source": "transformer"},
    ]

    features_v2 = bandit_v2.extract_context_features_v2(
        text="PM Dahal announced new economic policy at Nepal Rastra Bank headquarters",
        category="economic",
        source_confidence=0.9,
        entities=mock_entities,
        published_at=datetime.now(),
        embedder=None,  # Will lazy-load
        severity_detector=None,  # Will lazy-load
    )

    if len(features_v2) == 32:
        print_result("V2 feature extraction", True, f"Dim: {len(features_v2)}")
        passed += 1
    else:
        print_result("V2 feature extraction", False, f"Dim: {len(features_v2)}")

    # Test 3: Rule-based prediction (v2)
    total += 1
    prediction = bandit_v2._rule_based_predict(features_v2)
    if prediction.priority in ["critical", "high", "medium", "low"]:
        print_result("V2 rule-based prediction", True,
                    f"Priority: {prediction.priority} ({prediction.confidence:.2f})")
        passed += 1
    else:
        print_result("V2 rule-based prediction", False)

    # Test 4: Feature names
    total += 1
    names_v2 = bandit_v2.get_feature_names("v2")
    if len(names_v2) == 32:
        print_result("Feature names", True, f"32 feature names defined")
        passed += 1
    else:
        print_result("Feature names", False, f"Got {len(names_v2)} names")

    # Test 5: High-level predict_from_story API
    total += 1
    try:
        prediction = bandit_v2.predict_from_story(
            text="Earthquake kills 50 in Gorkha district",
            category="disaster",
            source_confidence=0.85,
            entities=[{"text": "Gorkha", "type": "LOCATION", "source": "rule_based"}],
            published_at=datetime.now(),
        )
        if prediction.priority in ["critical", "high"]:
            print_result("predict_from_story API", True,
                        f"Priority: {prediction.priority} (correct for disaster)")
            passed += 1
        else:
            print_result("predict_from_story API", False,
                        f"Expected critical/high for disaster, got {prediction.priority}")
    except Exception as e:
        print_result("predict_from_story API", False, f"Error: {e}")

    print(f"\n  Results: {passed}/{total} tests passed")
    return passed == total


def test_end_to_end():
    """Test the full pipeline with sample stories."""
    print_header("End-to-End Pipeline Test")

    from app.services.nlp.nepali_preprocessor import get_preprocessor
    from app.services.nlp.hybrid_ner import get_hybrid_ner
    from app.services.embeddings.text_embedder import get_embedder
    from app.ml.features.semantic_severity import SemanticSeverityDetector
    from app.ml.models.priority_bandit import PriorityBandit

    # Initialize components
    preprocessor = get_preprocessor()
    ner = get_hybrid_ner()
    embedder = get_embedder(model_key="minilm")

    severity_detector = SemanticSeverityDetector()
    severity_detector._embedder = embedder  # Use minilm for speed

    bandit = PriorityBandit(input_dim=32)

    print("\n  Processing sample stories...\n")

    results = []
    for story in TEST_STORIES[:4]:  # Test first 4 stories
        text = f"{story['title']} {story['content']}"

        # 1. Preprocessing
        normalized = preprocessor.normalize(text)
        is_nepali = preprocessor.is_nepali(text)

        # 2. NER
        entities = ner._extract_rule_based_entities(text)

        # 3. Severity
        severity, sev_conf, _ = severity_detector.detect_severity(text)

        # 4. Priority prediction
        features = bandit.extract_context_features_v2(
            text=text,
            category=story.get("expected_category"),
            source_confidence=0.8,
            entities=entities,
            published_at=datetime.now(),
            severity_detector=severity_detector,
        )
        prediction = bandit._rule_based_predict(features)

        # Check results
        severity_match = severity == story["expected_severity"] or \
                        (severity in ["critical", "high"] and story["expected_severity"] in ["critical", "high"])

        result = {
            "id": story["id"],
            "title": story["title"][:50],
            "language": "Nepali" if is_nepali else "English",
            "entities_found": len(entities),
            "predicted_severity": severity,
            "expected_severity": story["expected_severity"],
            "severity_match": severity_match,
            "priority": prediction.priority,
        }
        results.append(result)

        print(f"  Story {story['id']}: {story['title'][:40]}...")
        print(f"    Language: {result['language']}")
        print(f"    Entities: {len(entities)} found")
        print(f"    Severity: {severity} (expected: {story['expected_severity']}) {'✅' if severity_match else '❌'}")
        print(f"    Priority: {prediction.priority}\n")

    # Summary
    correct = sum(1 for r in results if r["severity_match"])
    print(f"  Overall severity accuracy: {correct}/{len(results)} ({100*correct/len(results):.0f}%)")

    return correct >= len(results) * 0.5  # 50% accuracy acceptable for rule-based


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  NEPAL OSINT v5 - Smart ML/NLP System Tests")
    print("=" * 60)

    start_time = time.time()

    results = {}

    # Run tests
    results["NepaliPreprocessor"] = test_nepali_preprocessor()
    results["NepaliTransliterator"] = test_nepali_transliterator()
    results["HybridNER"] = test_hybrid_ner()
    results["TextEmbedder"] = test_text_embedder()
    results["SemanticSeverity"] = test_semantic_severity()
    results["PriorityBandit"] = test_priority_bandit()
    results["End-to-End"] = test_end_to_end()

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"  {status}: {name}")

    elapsed = time.time() - start_time
    print(f"\n  Total: {passed}/{total} test suites passed")
    print(f"  Time: {elapsed:.2f}s")

    if passed == total:
        print("\n  🎉 All tests passed! The ML/NLP system is working correctly.")
    else:
        print(f"\n  ⚠️  {total - passed} test suite(s) failed. Review output above.")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
