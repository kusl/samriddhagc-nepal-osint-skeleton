#!/usr/bin/env python3
"""
Quick fix for notable politician biographies.
Updates specific candidates by matching their name patterns.
"""
import json
from pathlib import Path

# Direct fixes for notable politicians (match by name_en pattern)
FIXES = [
    {
        "match_pattern": "के.पी शर्मा ओली",  # KP Oli in Nepali
        "updates": {
            "name_en_roman": "Khadga Prasad Sharma Oli",
            "aliases": ["KP Oli", "K.P. Oli", "Oli", "केपी ओली", "K.P. Sharma Oli"],
            "biography": "Prime Minister 4 times: 2015-2016, 2018-2021, 2021, 2024-2025. Chairman of CPN-UML since 2014. His fourth term ended in September 2025 after Gen Z protests erupted following police crackdown on youth demonstrators, leading to his resignation. Previously spent 14 years in prison (1973-1987) for pro-democracy activities. Released controversial new map claiming Kalapani, Limpiyadhura, and Lipulekh from India in 2020.",
            "biography_source": "https://en.wikipedia.org/wiki/KP_Sharma_Oli",
            "is_notable": True
        }
    },
    {
        "match_pattern": "पुष्प कमल दाहाल",  # Prachanda
        "updates": {
            "name_en_roman": "Pushpa Kamal Dahal",
            "aliases": ["Prachanda", "प्रचण्ड", "Fierce One", "PM Prachanda"],
            "biography": "Prime Minister 3 times: 2008-2009, 2016-2017, 2022-2024. Former Maoist insurgent leader who led decade-long civil war (1996-2006) resulting in ~17,000 deaths. Key architect of 2006 Comprehensive Peace Accord that ended monarchy. His third term ended July 2024 after losing confidence vote. Currently Coordinator of Nepali Communist Party formed by merging 10 leftist parties.",
            "biography_source": "https://en.wikipedia.org/wiki/Pushpa_Kamal_Dahal",
            "is_notable": True
        }
    },
    {
        "match_pattern": "शेर बहादुर देउवा",  # Sher Bahadur Deuba
        "updates": {
            "name_en_roman": "Sher Bahadur Deuba",
            "aliases": ["SB Deuba", "Deuba", "शेर बहादुर"],
            "biography": "Prime Minister 5 times (record): 1995-97, 2001-02, 2004-05, 2017-18, 2021-22. Twice dismissed by King Gyanendra (2002, 2005). Signed controversial Mahakali Treaty with India (1996). As NC President, lost party leadership to Gagan Thapa in 2026. Imprisoned 10 years under Panchayat system. Successfully conducted all three tiers of elections in 2017.",
            "biography_source": "https://en.wikipedia.org/wiki/Sher_Bahadur_Deuba",
            "is_notable": True
        }
    },
    {
        "match_pattern": "रवि लामिछाने",  # Rabi Lamichhane
        "updates": {
            "name_en_roman": "Rabi Lamichhane",
            "aliases": ["Rabi", "RSP President", "रवि"],
            "biography": "Deputy PM & Home Minister 2x: 2022-2023, 2024. Founded Rastriya Swatantra Party in June 2022, becoming 4th largest party in first election. Former investigative journalist, TV host of 'Sidha Kura Janata Sanga'. Arrested April 2025 in cooperative fraud scandal involving billions of rupees. Released during Gen Z prison breaks September 2025. Guinness World Record holder for longest talk show (62 hours).",
            "biography_source": "https://en.wikipedia.org/wiki/Rabi_Lamichhane",
            "is_notable": True
        }
    },
    {
        "match_pattern": "गगन कुमार थापा",  # Gagan Thapa
        "updates": {
            "name_en_roman": "Gagan Kumar Thapa",
            "aliases": ["Gagan Thapa", "गगन थापा", "NC President"],
            "biography": "Health Minister 2016-2017. Elected NC President in January 2026, defeating old guard. Three-time MP from Kathmandu-4. WEF Young Global Leader. Declared Prisoner of Conscience by Amnesty International (2005) after imprisonment during King Gyanendra's direct rule. Led generational change in Nepal's oldest democratic party. PM candidate for 2026 elections.",
            "biography_source": "https://en.wikipedia.org/wiki/Gagan_Thapa",
            "is_notable": True
        }
    },
    {
        "match_pattern": "माधव कुमार नेपाल",  # Madhav Kumar Nepal
        "updates": {
            "name_en_roman": "Madhav Kumar Nepal",
            "aliases": ["Madhav Nepal", "MK Nepal", "माधव नेपाल"],
            "biography": "Prime Minister 2009-2011 (never won direct election). CPN-UML General Secretary for 15 years. Key negotiator of 12-point peace accord that ended Maoist insurgency. Split from UML in 2021 citing KP Oli's 'arrogance and monopoly'. Charged in Patanjali land scam (June 2025). Currently Co-coordinator of merged Nepali Communist Party.",
            "biography_source": "https://en.wikipedia.org/wiki/Madhav_Kumar_Nepal",
            "is_notable": True
        }
    },
    {
        "match_pattern": "कमल थापा",  # Kamal Thapa
        "updates": {
            "name_en_roman": "Kamal Thapa",
            "aliases": ["KT", "कमल", "RPP Leader"],
            "biography": "Deputy PM 3 times: 2015-16, 2017, 2017-18. Home Minister during King Gyanendra's controversial direct rule (2006). Held 12+ ministerial portfolios including Foreign Minister. Served as ANFA President. Lost RPP chairmanship to Lingden in 2021, formed RPP-Nepal, reunified December 2025. Advocates Hindu state and constitutional monarchy.",
            "biography_source": "https://en.wikipedia.org/wiki/Kamal_Thapa",
            "is_notable": True
        }
    },
    {
        "match_pattern": "स्वर्णिम वाग्ले",  # Swarnim Wagle
        "updates": {
            "name_en_roman": "Swarnim Wagle",
            "aliases": ["Dr. Swarnim Wagle", "स्वर्णिम", "Economist"],
            "biography": "Vice-Chairman of National Planning Commission (2014-2018). PhD in Economics from University of Hawaii. RSP co-founder and ideologue. Previously worked at World Bank. Known for advocating economic liberalization, anti-corruption reforms, and evidence-based policymaking. Key voice for good governance in Nepal.",
            "biography_source": "https://en.wikipedia.org/wiki/Swarnim_Wagle",
            "is_notable": True
        }
    },
    {
        "match_pattern": "रेणु दाहाल",  # Renu Dahal
        "updates": {
            "name_en_roman": "Renu Dahal",
            "aliases": ["रेणु", "Prachanda's daughter"],
            "biography": "Mayor of Bharatpur Metropolitan City 2017-2022. Daughter of 3x PM Pushpa Kamal Dahal (Prachanda). Senior leader of Nepali Communist Party. Known for urban development initiatives in Bharatpur including road expansion and waste management. Active in women's political empowerment.",
            "biography_source": None,
            "is_notable": True
        }
    },
    {
        "match_pattern": "उपेन्द्र यादव",  # Upendra Yadav
        "updates": {
            "name_en_roman": "Upendra Yadav",
            "aliases": ["Upendra", "JSP Chairman", "Madheshi leader"],
            "biography": "Deputy PM 2x: 2018-19, 2024. Foreign Minister 2x: 2008-09, 2011. Pioneer of Madheshi movement who burned copies of 2007 Interim Constitution. Founded Madheshi Jana Adhikar Forum. Under investigation for 2007 Gaur massacre (27 deaths). Known for frequent party mergers/splits. Lost 2022 election to CK Raut.",
            "biography_source": "https://en.wikipedia.org/wiki/Upendra_Yadav",
            "is_notable": True
        }
    },
    {
        "match_pattern": "राजेन्द्र लिङ्देन",  # Rajendra Lingden
        "updates": {
            "name_en_roman": "Rajendra Prasad Lingden",
            "aliases": ["Lingden", "राजेन्द्र", "RPP Chairman"],
            "biography": "RPP Chairman since 2021, defeating Kamal Thapa with backing from former King Gyanendra. Brief Deputy PM stint 2022-2023. Strong advocate for Hindu state restoration and constitutional monarchy. Led RPP reunification December 2025. Party failed to win any seats in December 2024 by-elections.",
            "biography_source": "https://en.wikipedia.org/wiki/Rajendra_Lingden",
            "is_notable": True
        }
    },
    {
        "match_pattern": "विष्णु प्रसाद पौडेल",  # Bishnu Poudel
        "updates": {
            "name_en_roman": "Bishnu Prasad Paudel",
            "aliases": ["Bishnu Poudel", "विष्णु पौडेल", "UML Vice Chair"],
            "biography": "Finance Minister 3 times. Also served as Home Minister (2021), Defence Minister (2011). CPN-UML Vice Chairman. Five-time parliamentarian from Rupandehi. Key figure in failed UML-Maoist merger (2018). Served as Finance Minister during Gen Z protests until August 2025. Started career as primary school teacher.",
            "biography_source": "https://en.wikipedia.org/wiki/Bishnu_Prasad_Paudel",
            "is_notable": True
        }
    },
    {
        "match_pattern": "बालेन्द्र शाह",  # Balen Shah (if running)
        "updates": {
            "name_en_roman": "Balendra Shah",
            "aliases": ["Balen Shah", "Balen", "Mayor Balen", "बालेन"],
            "biography": "Balendra 'Balen' Shah is RSP's PM candidate for 2026 elections. Former Mayor of Kathmandu (2022-2026) - first independent mayor. Rose to fame as hip-hop artist before politics. Civil engineer by profession. Symbolizes Gen Z political aspirations. Challenging KP Oli directly in Jhapa-5.",
            "biography_source": "https://en.wikipedia.org/wiki/Balen_Shah",
            "is_notable": True
        }
    },
    {
        "match_pattern": "हर्क सम्पाङ",  # Harka Sampang
        "updates": {
            "name_en_roman": "Harka Raj Rai",
            "aliases": ["Harka Sampang", "Harka", "हर्क", "Dharan Mayor"],
            "biography": "Harka Sampang is founder and Chairman of Shram Sanskriti Party (Labor Culture Party) formed November 2025. Former Mayor of Dharan (2022-2026) - first independent mayor. Former migrant worker in Afghanistan. Led 'Gift a Tree' campaign. Promotes 'Harkabad' philosophy of labor dignity.",
            "biography_source": "https://en.wikipedia.org/wiki/Harka_Sampang",
            "is_notable": True
        }
    },
    {
        "match_pattern": "प्रकाश शरण महत",  # Prakash Mahat
        "updates": {
            "name_en_roman": "Prakash Sharan Mahat",
            "aliases": ["Dr. Mahat", "प्रकाश महत", "NC Economist"],
            "biography": "Dr. Prakash Sharan Mahat is a senior Nepali Congress leader and economist. Served as Foreign Minister and Finance Minister multiple times. PhD in Economics. Key architect of NC's economic policies.",
            "biography_source": None,
            "is_notable": True
        }
    },
]


def main():
    script_dir = Path(__file__).parent.resolve()
    data_path = script_dir / "../../frontend/public/data/election-results-2082.json"

    print(f"Loading {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for constituency in data.get("results", []):
        for candidate in constituency.get("candidates", []):
            name_en = candidate.get("name_en", "")
            name_ne = candidate.get("name_ne", "")

            for fix in FIXES:
                pattern = fix["match_pattern"]
                if pattern in name_en or pattern in name_ne:
                    for key, value in fix["updates"].items():
                        if key == "aliases":
                            # Merge aliases
                            existing = set(candidate.get("aliases", []))
                            existing.update(value)
                            candidate["aliases"] = list(existing)
                        else:
                            candidate[key] = value
                    updated += 1
                    print(f"  Updated: {fix['updates']['name_en_roman']}")
                    break

    # Save
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {updated} notable politicians")


if __name__ == "__main__":
    main()
