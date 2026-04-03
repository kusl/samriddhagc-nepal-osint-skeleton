"""Official PR-elected House members for 2082.

Source:
- https://election.gov.np/admin/public//storage/HOR%202082/PR/Samanupatik_Elected.pdf

The PDF is a scan, so these rows were extracted with local Tesseract OCR and
manually cleaned against the official elected roster layout before being
checked into the app.
"""

from __future__ import annotations

import re

PR_ELECTED_SOURCE_URL = (
    "https://election.gov.np/admin/public//storage/HOR%202082/PR/Samanupatik_Elected.pdf"
)

_RAW_PR_ELECTED_MEMBERS_2082 = [
    {"election_order": 1, "closed_list_order": 1, "name_ne": "राम लामा", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 2, "closed_list_order": 2, "name_ne": "खुश्बु सरकार श्रेष्ठ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 3, "closed_list_order": 3, "name_ne": "मिङ्मा ग्याबु शेर्पा", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 4, "closed_list_order": 14, "name_ne": "बसुमाया तामाङ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 5, "closed_list_order": 15, "name_ne": "गंगा छन्त्याल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 6, "closed_list_order": 16, "name_ne": "सुम्निमा उदास", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 7, "closed_list_order": 17, "name_ne": "अनुष्का श्रेष्ठ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 8, "closed_list_order": 18, "name_ne": "ओजस्वी शेरचन", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 9, "closed_list_order": 19, "name_ne": "सिर्जना श्रेष्ठ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 10, "closed_list_order": 20, "name_ne": "रजनी श्रेष्ठ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 11, "closed_list_order": 21, "name_ne": "कुशुम महर्जन", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 12, "closed_list_order": 22, "name_ne": "भुमिका श्रेष्ठ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 13, "closed_list_order": 23, "name_ne": "प्रमिला कुलजु", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 14, "closed_list_order": 24, "name_ne": "सुजाता तामाङ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 15, "closed_list_order": 25, "name_ne": "कृपा महर्जन", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 16, "closed_list_order": 26, "name_ne": "एलिजा गुरुङ", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 17, "closed_list_order": 33, "name_ne": "रमेश प्रसाई", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 18, "closed_list_order": 48, "name_ne": "प्रतिभा रावल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 19, "closed_list_order": 49, "name_ne": "रचना खतिवडा खत्री", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 20, "closed_list_order": 50, "name_ne": "लिमा अधिकारी (आचार्य)", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 21, "closed_list_order": 51, "name_ne": "बिधुषी राणा", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 22, "closed_list_order": 52, "name_ne": "समीक्षा बास्कोटा", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 23, "closed_list_order": 53, "name_ne": "श्रद्धा कुँवर क्षेत्री", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 24, "closed_list_order": 54, "name_ne": "टीका संग्रोला", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 25, "closed_list_order": 55, "name_ne": "क्रान्तिशिखा घिताल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 26, "closed_list_order": 56, "name_ne": "आकृति अवस्थी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 27, "closed_list_order": 57, "name_ne": "सृष्टि भट्टराई", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 28, "closed_list_order": 58, "name_ne": "मञ्जु भुसाल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 29, "closed_list_order": 59, "name_ne": "प्रभा कार्की", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 30, "closed_list_order": 60, "name_ne": "शोभा खनाल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 31, "closed_list_order": 61, "name_ne": "रत्ना कुमारी थापा", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 32, "closed_list_order": 62, "name_ne": "ज्ञानु पौडेल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 33, "closed_list_order": 63, "name_ne": "प्रभा ढकाल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 34, "closed_list_order": 66, "name_ne": "प्रकाश चन्द्र दर्जी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 35, "closed_list_order": 73, "name_ne": "रीमा विश्वकर्मी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 36, "closed_list_order": 74, "name_ne": "अमृता बि.क.", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 37, "closed_list_order": 75, "name_ne": "सीता बादी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 38, "closed_list_order": 76, "name_ne": "स्मृति सेन्चुरी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 39, "closed_list_order": 77, "name_ne": "सुष्मा स्वर्णकार (डिम्पल)", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 40, "closed_list_order": 78, "name_ne": "तारा विश्वकर्मी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 41, "closed_list_order": 79, "name_ne": "खिमा बि.क.", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 42, "closed_list_order": 81, "name_ne": "सुरेन्द्र चौधरी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 43, "closed_list_order": 82, "name_ne": "प्रेम लाल चौधरी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 44, "closed_list_order": 84, "name_ne": "गीता चौधरी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 45, "closed_list_order": 87, "name_ne": "करिस्मा कठरिया", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 46, "closed_list_order": 88, "name_ne": "पुरुषोत्तम शुभप्रभात यादव", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 47, "closed_list_order": 89, "name_ne": "खगेन्द्र कर्ण", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 48, "closed_list_order": 95, "name_ne": "पूनम कुमारी अग्रवाल", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 49, "closed_list_order": 96, "name_ne": "निशा मेहता", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 50, "closed_list_order": 97, "name_ne": "ललिता कुमारी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 51, "closed_list_order": 98, "name_ne": "अंकिता ठाकुर", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 52, "closed_list_order": 99, "name_ne": "सरिता महतो", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 53, "closed_list_order": 100, "name_ne": "कामिनी कुमारी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 54, "closed_list_order": 101, "name_ne": "सुनिता कुमारी चौधरी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 55, "closed_list_order": 108, "name_ne": "समिना मिया", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 56, "closed_list_order": 109, "name_ne": "अफ्साना बानु", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 57, "closed_list_order": 110, "name_ne": "गजाला शमीम मिकरानी", "party": "राष्ट्रिय स्वतन्त्र पार्टी"},
    {"election_order": 58, "closed_list_order": 1, "name_ne": "भीष्मराज आङदेम्बे", "party": "नेपाली काँग्रेस"},
    {"election_order": 59, "closed_list_order": 16, "name_ne": "मदनकृष्ण श्रेष्ठ", "party": "नेपाली काँग्रेस"},
    {"election_order": 60, "closed_list_order": 17, "name_ne": "गीताकुमारी सेन्दाङ", "party": "नेपाली काँग्रेस"},
    {"election_order": 61, "closed_list_order": 18, "name_ne": "गंगालक्ष्मी अवाल", "party": "नेपाली काँग्रेस"},
    {"election_order": 62, "closed_list_order": 19, "name_ne": "गीता गुरुङ", "party": "नेपाली काँग्रेस"},
    {"election_order": 63, "closed_list_order": 20, "name_ne": "रेनुका काउचा", "party": "नेपाली काँग्रेस"},
    {"election_order": 64, "closed_list_order": 78, "name_ne": "अर्जुननरसिंह के.सी.", "party": "नेपाली काँग्रेस"},
    {"election_order": 65, "closed_list_order": 84, "name_ne": "काली बहादुर सहकारी", "party": "नेपाली काँग्रेस"},
    {"election_order": 66, "closed_list_order": 89, "name_ne": "सुशीला ढकाल आचार्य", "party": "नेपाली काँग्रेस"},
    {"election_order": 67, "closed_list_order": 90, "name_ne": "श्रीमती रुक्मिणी देवी कोइराला", "party": "नेपाली काँग्रेस"},
    {"election_order": 68, "closed_list_order": 91, "name_ne": "रीना उप्रेती", "party": "नेपाली काँग्रेस"},
    {"election_order": 69, "closed_list_order": 92, "name_ne": "सीता थपलिया", "party": "नेपाली काँग्रेस"},
    {"election_order": 70, "closed_list_order": 36, "name_ne": "प्रमिला कुमारी गच्छदार", "party": "नेपाली काँग्रेस"},
    {"election_order": 71, "closed_list_order": 70, "name_ne": "हरिता देवी कामी", "party": "नेपाली काँग्रेस"},
    {"election_order": 72, "closed_list_order": 71, "name_ne": "पवित्रा बि.क.", "party": "नेपाली काँग्रेस"},
    {"election_order": 73, "closed_list_order": 72, "name_ne": "मनमाया बि.क.", "party": "नेपाली काँग्रेस"},
    {"election_order": 74, "closed_list_order": 55, "name_ne": "चन्द्रमोहन यादव", "party": "नेपाली काँग्रेस"},
    {"election_order": 75, "closed_list_order": 53, "name_ne": "नीनु कुमारी कर्ण", "party": "नेपाली काँग्रेस"},
    {"election_order": 76, "closed_list_order": 54, "name_ne": "रेखा कुमारी यादव", "party": "नेपाली काँग्रेस"},
    {"election_order": 77, "closed_list_order": 42, "name_ne": "शाहजान खातुन", "party": "नेपाली काँग्रेस"},
    {"election_order": 78, "closed_list_order": 1, "name_ne": "भुमिका लिम्बु सुव्वा", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 79, "closed_list_order": 2, "name_ne": "गंगादेवी श्रेष्ठ", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 80, "closed_list_order": 17, "name_ne": "रामबहादुर थापा मगर", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 81, "closed_list_order": 18, "name_ne": "कुल भक्त शाक्य", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 82, "closed_list_order": 33, "name_ne": "पद्मा कुमारी अर्याल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 83, "closed_list_order": 34, "name_ne": "टुकाभद्रा हमाल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 84, "closed_list_order": 49, "name_ne": "एशुदा कुमारी बराल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 85, "closed_list_order": 50, "name_ne": "गुरु प्रसाद बराल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 86, "closed_list_order": 51, "name_ne": "पुष्पराज कडेल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 87, "closed_list_order": 70, "name_ne": "कृपाराम राना", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 88, "closed_list_order": 73, "name_ne": "विष्णुमाया बि.क.", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 89, "closed_list_order": 74, "name_ne": "नीता घतानी", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 90, "closed_list_order": 88, "name_ne": "रिगला यादव", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 91, "closed_list_order": 89, "name_ne": "यशोधा कुमारी", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 92, "closed_list_order": 97, "name_ne": "चन्देश्वर मण्डल", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 93, "closed_list_order": 106, "name_ne": "साजिदा खातुन सिद्दिकी", "party": "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"},
    {"election_order": 94, "closed_list_order": 1, "name_ne": "बलावती शर्मा", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 95, "closed_list_order": 18, "name_ne": "प्रमेश कुमार हमाल", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 96, "closed_list_order": 39, "name_ne": "प्रेम बहादुर वयक", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 97, "closed_list_order": 48, "name_ne": "भीमकुमारी बुढामगर", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 98, "closed_list_order": 51, "name_ne": "परशुराम तामाङ", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 99, "closed_list_order": 84, "name_ne": "पार्वती बि.क.", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 100, "closed_list_order": 92, "name_ne": "गणेश बहादुर विश्वकर्मा", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 101, "closed_list_order": 95, "name_ne": "जोग कुमार बरबरिया यादव", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 102, "closed_list_order": 104, "name_ne": "निराशा चौधरी (डगौरा)", "party": "नेपाली कम्युनिष्ट पार्टी"},
    {"election_order": 103, "closed_list_order": 17, "name_ne": "पूर्ण प्रसाद लिम्बु", "party": "श्रम संस्कृति पार्टी"},
    {"election_order": 104, "closed_list_order": 33, "name_ne": "अम्बिका देवी संग्रौला", "party": "श्रम संस्कृति पार्टी"},
    {"election_order": 105, "closed_list_order": 66, "name_ne": "राधिका रम्तेल", "party": "श्रम संस्कृति पार्टी"},
    {"election_order": 106, "closed_list_order": 105, "name_ne": "रुबी कुमारी", "party": "श्रम संस्कृति पार्टी"},
    {"election_order": 107, "closed_list_order": 17, "name_ne": "सरस्वती लामा", "party": "राष्ट्रिय प्रजातन्त्र पार्टी"},
    {"election_order": 108, "closed_list_order": 33, "name_ne": "भरत गिरी", "party": "राष्ट्रिय प्रजातन्त्र पार्टी"},
    {"election_order": 109, "closed_list_order": 49, "name_ne": "खुस्बु ओली", "party": "राष्ट्रिय प्रजातन्त्र पार्टी"},
    {"election_order": 110, "closed_list_order": 106, "name_ne": "ताहिर अली भाट", "party": "राष्ट्रिय प्रजातन्त्र पार्टी"},
]

PARTY_CODE_MAP = {
    "राष्ट्रिय स्वतन्त्र पार्टी": "RSP",
    "नेपाली काँग्रेस": "NC",
    "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)": "UML",
    "नेपाली कम्युनिष्ट पार्टी": "NCP",
    "श्रम संस्कृति पार्टी": "SSP",
    "राष्ट्रिय प्रजातन्त्र पार्टी": "RPP",
}

PARTY_ENGLISH_MAP = {
    "राष्ट्रिय स्वतन्त्र पार्टी": "Rastriya Swatantra Party",
    "नेपाली काँग्रेस": "Nepali Congress",
    "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)": "Communist Party of Nepal (Unified Marxist-Leninist)",
    "नेपाली कम्युनिष्ट पार्टी": "Nepali Communist Party",
    "श्रम संस्कृति पार्टी": "Shram Sanskriti Party",
    "राष्ट्रिय प्रजातन्त्र पार्टी": "Rastriya Prajatantra Party",
}

FULL_NAME_ROMAN_OVERRIDES = {
    "राम लामा": "Ram Lama",
    "एशुदा कुमारी बराल": "Eshuda Kumari Baral",
    "भीष्मराज आङदेम्बे": "Bhishmaraj Angdembe",
    "मदनकृष्ण श्रेष्ठ": "Madan Krishna Shrestha",
    "अर्जुननरसिंह के.सी.": "Arjun Narsingh K.C.",
    "कुल भक्त शाक्य": "Kul Bhakta Shakya",
    "कृपाराम राना": "Kriparam Rana",
    "गंगादेवी श्रेष्ठ": "Gangadevi Shrestha",
    "गुरु प्रसाद बराल": "Guru Prasad Baral",
    "चन्देश्वर मण्डल": "Chandeshwar Mandal",
    "टुकाभद्रा हमाल": "Tukabhadra Hamal",
    "नीता घतानी": "Nita Ghatani",
    "पद्मा कुमारी अर्याल": "Padma Kumari Aryal",
    "पुष्पराज कडेल": "Pushparaj Kadel",
    "भुमिका लिम्बु सुव्वा": "Bhumika Limbu Subba",
    "यशोधा कुमारी": "Yashodha Kumari",
    "रामबहादुर थापा मगर": "Rambahadur Thapa Magar",
    "रिगला यादव": "Rigala Yadav",
    "विष्णुमाया बि.क.": "Vishnumaya B.K.",
    "साजिदा खातुन सिद्दिकी": "Sajida Khatun Siddiqui",
    "श्रीमती रुक्मिणी देवी कोइराला": "Shrimati Rukmini Devi Koirala",
    "नीनु कुमारी कर्ण": "Ninu Kumari Karn",
    "भीमकुमारी बुढामगर": "Bhim Kumari Budhamagar",
    "अम्बिका देवी संग्रौला": "Ambika Devi Sangraula",
    "राधिका रम्तेल": "Radhika Ramtel",
    "खुस्बु ओली": "Khushbu Oli",
    "ताहिर अली भाट": "Tahir Ali Bhat",
}

WORD_ROMAN_OVERRIDES = {
    "राम": "Ram",
    "लामा": "Lama",
    "कुमारी": "Kumari",
    "बराल": "Baral",
    "कुल": "Kul",
    "भक्त": "Bhakta",
    "शाक्य": "Shakya",
    "कृपाराम": "Kriparam",
    "राना": "Rana",
    "गंगादेवी": "Gangadevi",
    "श्रेष्ठ": "Shrestha",
    "गुरु": "Guru",
    "प्रसाद": "Prasad",
    "चन्देश्वर": "Chandeshwar",
    "मण्डल": "Mandal",
    "टुकाभद्रा": "Tukabhadra",
    "हमाल": "Hamal",
    "नीता": "Nita",
    "घतानी": "Ghatani",
    "पद्मा": "Padma",
    "अर्याल": "Aryal",
    "पुष्पराज": "Pushparaj",
    "कडेल": "Kadel",
    "भुमिका": "Bhumika",
    "लिम्बु": "Limbu",
    "सुव्वा": "Subba",
    "यशोधा": "Yashodha",
    "रामबहादुर": "Rambahadur",
    "थापा": "Thapa",
    "मगर": "Magar",
    "रिगला": "Rigala",
    "यादव": "Yadav",
    "विष्णुमाया": "Vishnumaya",
    "बि": "B",
    "क": "K",
    "साजिदा": "Sajida",
    "खातुन": "Khatun",
    "सिद्दिकी": "Siddiqui",
    "अर्जुननरसिंह": "Arjunnarsingh",
    "के": "K",
    "सी": "C",
    "भीष्मराज": "Bhishmaraj",
    "आङदेम्बे": "Angdembe",
    "गीताकुमारी": "Geeta Kumari",
    "गंगा": "Ganga",
    "गंगाालक्ष्मी": "Gangalakshmi",
    "गीता": "Geeta",
    "गुरुङ": "Gurung",
    "रेनुका": "Renuka",
    "काउचा": "Kaucha",
    "काली": "Kali",
    "सुशीला": "Sushila",
    "रुक्मिणी": "Rukmini",
    "रीना": "Rina",
    "सीता": "Sita",
    "हरिता": "Harita",
    "पवित्रा": "Pabitra",
    "मनमाया": "Manmaya",
    "चन्द्रमोहन": "Chandramohan",
    "नीनु": "Ninu",
    "रेखा": "Rekha",
    "शाहजान": "Shahjan",
}

_INDEPENDENT_VOWELS = {
    "अ": "a",
    "आ": "a",
    "इ": "i",
    "ई": "i",
    "उ": "u",
    "ऊ": "u",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
}

_MATRA_MAP = {
    "ा": "a",
    "ि": "i",
    "ी": "i",
    "ु": "u",
    "ू": "u",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
}

_CONSONANT_MAP = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "ng",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "ny",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
}

_COMBINED_CONSONANTS = {
    "क्ष": "ksh",
    "त्र": "tr",
    "ज्ञ": "gy",
}

_SIGN_MAP = {
    "ं": "n",
    "ँ": "n",
    "ः": "h",
    "़": "",
}


def _simple_title(word: str) -> str:
    return word[:1].upper() + word[1:] if word else word


def _romanize_word_fallback(word: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(word):
        pair = word[index:index + 2]
        if pair in _COMBINED_CONSONANTS:
            base = _COMBINED_CONSONANTS[pair]
            index += 2
            if index < len(word) and word[index] == "्":
                pieces.append(base)
                index += 1
            elif index < len(word) and word[index] in _MATRA_MAP:
                pieces.append(base + _MATRA_MAP[word[index]])
                index += 1
            else:
                pieces.append(base + "a")
            continue

        char = word[index]
        if char in _INDEPENDENT_VOWELS:
            pieces.append(_INDEPENDENT_VOWELS[char])
            index += 1
            continue

        if char in _CONSONANT_MAP:
            base = _CONSONANT_MAP[char]
            index += 1
            if index < len(word) and word[index] == "्":
                pieces.append(base)
                index += 1
            elif index < len(word) and word[index] in _MATRA_MAP:
                pieces.append(base + _MATRA_MAP[word[index]])
                index += 1
            else:
                pieces.append(base + "a")
            continue

        if char in _SIGN_MAP:
            pieces.append(_SIGN_MAP[char])
            index += 1
            continue

        pieces.append(char)
        index += 1

    return _simple_title("".join(pieces))


def _romanize_nepali_name(name_ne: str) -> str:
    if name_ne in FULL_NAME_ROMAN_OVERRIDES:
        return FULL_NAME_ROMAN_OVERRIDES[name_ne]

    tokens = re.split(r"(\s+|[()./-])", name_ne)
    output: list[str] = []
    for token in tokens:
        if not token:
            continue
        if re.fullmatch(r"\s+|[()./-]", token):
            output.append(token)
            continue
        if token in WORD_ROMAN_OVERRIDES:
            output.append(WORD_ROMAN_OVERRIDES[token])
            continue
        output.append(_romanize_word_fallback(token))

    return re.sub(r"\s+", " ", "".join(output)).strip()


def _enrich_pr_member(row: dict) -> dict:
    return {
        **row,
        "name_roman": _romanize_nepali_name(row["name_ne"]),
        "party_code": PARTY_CODE_MAP.get(row["party"], row["party"]),
        "party_en": PARTY_ENGLISH_MAP.get(row["party"], row["party"]),
    }


PR_ELECTED_MEMBERS_2082 = [_enrich_pr_member(row) for row in _RAW_PR_ELECTED_MEMBERS_2082]
