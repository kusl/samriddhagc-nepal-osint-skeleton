#!/usr/bin/env python3
"""
Comprehensive Candidate Enrichment for Major Parties

Creates detailed, unbiased biographies with multiple sources.
Includes both achievements and controversies for transparency.
"""
import json
from pathlib import Path

# Comprehensive politician data with multiple sources
POLITICIANS = [
    # ============ RSP - Rastriya Swatantra Party ============
    {
        "match_ne": "वालेन्द्र शाह",  # WRONG transliteration - fixing it
        "name_en_roman": "Balendra Shah",
        "aliases": ["Balen Shah", "Balen", "Mayor Balen", "Rapper Mayor", "बालेन शाह"],
        "biography": "RSP PM Candidate for 2026. Mayor of Kathmandu 2022-2026 (first independent mayor elected). Civil engineer and former hip-hop artist. Resigned January 2026 to contest against KP Oli in Jhapa-5. Key achievements: Ended Kathmandu's waste management crisis, improved traffic control. Controversies: Displayed Greater Nepal map causing India tensions (2023), banned Indian films (overturned by Supreme Court), criticized for heavy-handed squatter resettlement. Time Magazine Top 100 Emerging Leaders 2023. Symbol of Gen Z political aspirations.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/18/mayor-balen-resigns-to-contest-march-5-elections",
        "is_notable": True
    },
    {
        "match_ne": "रवि लामिछाने",
        "name_en_roman": "Rabi Lamichhane",
        "aliases": ["Rabi", "RSP President", "रवि"],
        "biography": "RSP Founder & President. Deputy PM & Home Minister 2x (2022-23, 2024). Former investigative journalist, TV host of 'Sidha Kura Janata Sanga'. Founded RSP June 2022 - became 4th largest party in first election. Achievements: Guinness World Record for 62-hour talk show, led party to 21 seats in debut. Controversies: Arrested April 2025 in Rs 860 million cooperative fraud scandal, released on Rs 27.48 million bail December 2025. Citizenship controversy - acquired US citizenship 2007, did not properly renounce.",
        "biography_source": "https://kathmandupost.com/national/2025/12/19/rabi-lamichhane-gets-bail-eligible-for-march-polls-says-legal-expert",
        "is_notable": True
    },
    {
        "match_ne": "स्वर्णिम वाग्ले",
        "name_en_roman": "Swarnim Wagle",
        "aliases": ["Dr. Swarnim Wagle", "स्वर्णिम", "Economist Wagle"],
        "biography": "RSP Vice-Chair. PhD economist from Australian National University. Vice-Chair of National Planning Commission 2017-18. Chief Economic Advisor, UNDP Asia-Pacific (36 countries) during COVID. Won Tanahun-1 by-election 2023 with 55% votes, 15,000 margin. Achievements: Key role in post-2015 earthquake reconstruction, co-edited 'The Great Upheaval' (Cambridge Press). Left Nepali Congress March 2023 citing 'constant humiliation' by the Deubas.",
        "biography_source": "https://kathmandupost.com/politics/2023/03/31/economist-wagle-quits-congress-after-constant-humiliation-by-the-deubas",
        "is_notable": True
    },

    # ============ CPN-UML ============
    {
        "match_ne": "के.पी शर्मा ओली",
        "name_en_roman": "Khadga Prasad Sharma Oli",
        "aliases": ["KP Oli", "K.P. Oli", "Oli", "केपी ओली"],
        "biography": "Prime Minister 4 times (2015-16, 2018-21, 2021, 2024-25). CPN-UML Chairman since 2014. Spent 14 years in prison (1973-87) for pro-democracy activism. Achievements: Led UML to historic 2017 victory, released new map claiming Kalapani from India (2020). Major controversy: Fourth term ended September 2025 after Gen Z protests erupted following police crackdown on youth demonstrators killing several. Social media ban during protests drew international criticism. Currently PM candidate for 2026.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/18/uml-declares-oli-as-its-pm-candidate",
        "is_notable": True
    },
    {
        "match_ne": "विष्णु प्रसाद पौडेल",
        "name_en_roman": "Bishnu Prasad Paudel",
        "aliases": ["Bishnu Poudel", "विष्णु पौडेल", "BP Paudel"],
        "biography": "CPN-UML Vice Chairman. Finance Minister 3x, also Home Minister (2021), Defence Minister (2011). Five-time MP from Rupandehi-2. Achievements: Defeated former PM Baburam Bhattarai in 2013, key economic policy architect. Started as primary school teacher at 18, escaped Bhairahawa Jail during Panchayat era. Served as Finance Minister until Gen Z protests forced government resignation August 2025.",
        "biography_source": "https://en.wikipedia.org/wiki/Bishnu_Prasad_Paudel",
        "is_notable": True
    },
    {
        "match_ne": "प्रदीप कुमार ज्ञवाली",
        "name_en_roman": "Pradeep Kumar Gyawali",
        "aliases": ["Pradeep Gyawali", "प्रदीप ज्ञवाली"],
        "biography": "Former Foreign Minister (2018-21). CPN-UML Deputy General Secretary. Represented Nepal at 74th UNGA. Key negotiator in peace process with Maoist rebels. Elected from Gulmi-1 with 7,000+ vote margin in 2017. Political career spanning since 1970s student movements.",
        "biography_source": "https://www.weforum.org/people/pradeep-kumar-gyawali/",
        "is_notable": True
    },
    {
        "match_ne": "महेश बस्नेत",
        "name_en_roman": "Mahesh Basnet",
        "aliases": ["महेश", "Mahesh Bhaktapur"],
        "biography": "CPN-UML Secretary. Former MP from Bhaktapur. Key Oli ally - provided shelter to Oli in Gundu, Bhaktapur during Gen Z protests September 2025. Lost Bhaktapur-2 seat in 2022 election. Controversy: Threatened journalist Tekman Shakya (September 2025) - condemned by media groups.",
        "biography_source": "https://english.nepalnews.com/s/feature/cpn-uml-11the-general-convention-conservatives-with-oli-reformists-with-pokharel/",
        "is_notable": True
    },

    # ============ NEPALI CONGRESS ============
    {
        "match_ne": "शेर बहादुर देउवा",
        "name_en_roman": "Sher Bahadur Deuba",
        "aliases": ["SB Deuba", "Deuba", "शेर बहादुर"],
        "biography": "Prime Minister 5 times (record): 1995-97, 2001-02, 2004-05, 2017-18, 2021-22. NC President 2016-2026. Achievements: Conducted all three tiers of elections in 2017, continuous MP from Dadeldhura for 34 years since 1991. Controversies: Twice dismissed by King Gyanendra (2002, 2005), signed controversial Mahakali Treaty with India (1996). Lost party presidency to Gagan Thapa in disputed January 2026 convention - filed Supreme Court challenge.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/15/gagan-thapa-s-long-political-journey-to-party-leadership",
        "is_notable": True
    },
    {
        "match_ne": "गगन कुमार थापा",
        "name_en_roman": "Gagan Kumar Thapa",
        "aliases": ["Gagan Thapa", "गगन थापा", "NC President"],
        "biography": "NC President (elected January 2026) & PM Candidate. Health Minister 2016-17. Three-time MP from Kathmandu-4, now contesting Sarlahi-4. Achievements: WEF Young Global Leader, led generational transition in Nepal's oldest party. Declared Prisoner of Conscience by Amnesty International 2005 after imprisonment during King Gyanendra's direct rule. Controversy: Elected president in special convention boycotted by Deuba faction, briefly expelled before Election Commission recognition.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/15/gagan-thapa-s-long-political-journey-to-party-leadership",
        "is_notable": True
    },
    {
        "match_ne": "प्रकाश शरण महत",
        "name_en_roman": "Prakash Sharan Mahat",
        "aliases": ["Dr. Mahat", "PS Mahat", "प्रकाश महत"],
        "biography": "NC Senior Leader & Spokesperson. Foreign Minister 2016, Finance Minister 2023-24. PhD Economics from Southern Illinois University. Member of Constitution Drafting Committee. Brother of Ram Sharan Mahat (former Finance Minister). Author of 'Nepali Congress and Nation Building'. Controversy: Finance Minister tenure ended amid fiscal management criticism in 2024.",
        "biography_source": "https://en.wikipedia.org/wiki/Prakash_Sharan_Mahat",
        "is_notable": True
    },
    {
        "match_ne": "शशाङ्क कोइराला",
        "name_en_roman": "Shashanka Koirala",
        "aliases": ["Shekhar Koirala", "Dr. Shashanka Koirala", "शेखर कोइराला"],
        "biography": "NC Senior Leader. Son of former PM B.P. Koirala. Renowned ophthalmologist. NC General Secretary 2016-22. Only Koirala family member elected through FPTP in 2008. Won three consecutive elections from Nawalparasi-1. Boycotted 2026 special convention that elected Gagan Thapa. Runner-up for party presidency against Deuba in 2021.",
        "biography_source": "https://en.wikipedia.org/wiki/Shashanka_Koirala",
        "is_notable": True
    },

    # ============ NCP / MAOIST CENTRE ============
    {
        "match_ne": "पुष्प कमल दाहाल",
        "name_en_roman": "Pushpa Kamal Dahal",
        "aliases": ["Prachanda", "प्रचण्ड", "Fierce One"],
        "biography": "Prime Minister 3 times (2008-09, 2016-17, 2022-24). Nepali Communist Party Coordinator. Led Maoist insurgency 1996-2006 resulting in ~17,000 deaths. Achievements: Key architect of 2006 Comprehensive Peace Accord ending monarchy, first Maoist leader to become PM. Controversies: Third term ended July 2024 after losing confidence vote, criticized for political instability and frequent coalition changes. Currently contesting from Rukum East.",
        "biography_source": "https://kathmandupost.com/politics/2024/07/12/pushpa-kamal-dahal-loses-vote-of-confidence",
        "is_notable": True
    },
    {
        "match_ne": "माधव कुमार नेपाल",
        "name_en_roman": "Madhav Kumar Nepal",
        "aliases": ["Madhav Nepal", "MK Nepal", "माधव नेपाल"],
        "biography": "Prime Minister 2009-2011 (never won direct election). NCP Co-coordinator. CPN-UML General Secretary for 15 years. Achievements: Key negotiator of 12-point peace accord ending Maoist insurgency. Controversies: Resigned as PM after failing to extend peace process deadline, split from CPN-UML 2021 citing Oli's 'arrogance', charged in Patanjali land scam June 2025. Contesting Rautahat-1 for 6th time.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/madhav-nepal-charged-in-patanjali-land-scam/",
        "is_notable": True
    },
    {
        "match_ne": "नारायण काजी श्रेष्ठ",
        "name_en_roman": "Narayan Kaji Shrestha",
        "aliases": ["Prakash", "NK Shrestha", "नारायण काजी"],
        "biography": "Deputy PM 3 times (2008-09, 2016-17, 2022-present). NCP Vice-Chair. Instrumental in 12-point Understanding (2006) that brought Maoists and seven parties together. Former mathematics lecturer. Did not join armed rebellion in 1996, maintaining peaceful political activities. Key bridge between underground Maoist movement and mainstream politics.",
        "biography_source": "https://en.wikipedia.org/wiki/Narayan_Kaji_Shrestha",
        "is_notable": True
    },
    {
        "match_ne": "रेणु दाहाल",
        "name_en_roman": "Renu Dahal",
        "aliases": ["रेणु", "Prachanda's daughter"],
        "biography": "Mayor of Bharatpur Metropolitan City 2017-present (two terms). Daughter of 3x PM Prachanda. NCP Politburo member. Achievements: Won 2022 election by margin of 12,499 votes, established independent political career. Controversies: 2017 victory controversial - ballot papers reportedly torn, required re-election in ward 19, won by only 203 votes. Allegations of nepotism due to family connection.",
        "biography_source": "https://en.wikipedia.org/wiki/Renu_Dahal",
        "is_notable": True
    },
    {
        "match_ne": "बर्षमान पुन",
        "name_en_roman": "Barsaman Pun",
        "aliases": ["Ananta", "Barsha Man Pun"],
        "biography": "NCP Senior Leader. Former Energy & Finance Minister. Deputy Commander of People's Liberation Army during insurgency. Commanded historic Holeri police station attack (Feb 13, 1996) - first attack of civil war. Married to Onsari Gharti Magar (first female Speaker). Presented proposals at 2025 National Unity Convention leading to NCP formation.",
        "biography_source": "https://en.wikipedia.org/wiki/Barsaman_Pun",
        "is_notable": True
    },

    # ============ RPP ============
    {
        "match_ne": "राजेन्द्र प्रसाद लिङ्देन",
        "name_en_roman": "Rajendra Prasad Lingden",
        "aliases": ["Rajendra Lingden", "Lingden", "राजेन्द्र लिङ्देन"],
        "biography": "RPP Chairman since December 2021. Deputy PM January-February 2023 (resigned after 40 days). Achievements: Led RPP to significant gains in 2022 - increased seats from 1 to 14, secured 7% vote share. Defeated Kamal Thapa for chairmanship. Controversies: Internal rebellion by Bikram Pandey and Dhawal Rana factions, RPP failed to win any seats in December 2025 by-elections. Advocates Hindu state and monarchy restoration. Contesting Jhapa-3.",
        "biography_source": "https://kathmandupost.com/politics/2023/08/06/how-serious-is-the-rastriya-prajatantra-party-about-promoting-youth-leaders-and-meritocracy",
        "is_notable": True
    },
    {
        "match_ne": "कमल थापा",
        "name_en_roman": "Kamal Thapa",
        "aliases": ["KT", "कमल", "RPP-Nepal Chairman"],
        "biography": "Deputy PM 3 times (2015-16, 2017, 2017-18). Foreign Minister 3 times. Home Minister during King Gyanendra's controversial direct rule (2005-06) - human rights groups called for sanctions. Held 12+ ministerial portfolios since 1988. Former national footballer, ANFA President 1978-87. Lost RPP chairmanship to Lingden 2021, formed RPP-Nepal, reunified December 2025. Detained June 2025 during pro-monarchy demonstration. Contesting Kathmandu-5.",
        "biography_source": "https://raprapanepal.org/?p=864&lang=en",
        "is_notable": True
    },

    # ============ OTHER NOTABLE ============
    {
        "match_ne": "उपेन्द्र यादव",
        "name_en_roman": "Upendra Yadav",
        "aliases": ["Upendra", "JSP Chairman", "उपेन्द्र यादव"],
        "biography": "JSP Chairman. Deputy PM 2x (2018-19, 2024), Foreign Minister 2x (2008-09, 2011). Pioneer of Madheshi movement - burned copies of 2007 Interim Constitution. Founded Madheshi Jana Adhikar Forum. Controversy: Under investigation for 2007 Gaur massacre (27 deaths). Known for frequent party mergers/splits. Lost 2022 election to CK Raut in Saptari-2.",
        "biography_source": "https://en.wikipedia.org/wiki/Upendra_Yadav",
        "is_notable": True
    },
    {
        "match_ne": "हर्क राज राई",  # Actual name in data
        "name_en_roman": "Harka Raj Rai",
        "aliases": ["Harka Sampang", "Harka", "हर्क", "Dharan Mayor", "हर्क सम्पाङ"],
        "biography": "Founder & Chairman of Shram Sanskriti Party (November 2025). Mayor of Dharan 2022-2026 (first independent mayor). Former migrant worker in Afghanistan. Achievements: Led 'Gift a Tree' campaign planting 100,000+ saplings, established soap factory and turmeric plant in Dharan. Promotes 'Harkabad' philosophy - labor dignity and self-reliance. Considered for interim PM alongside Balen and Sushila Karki during Gen Z protests. Contesting Sunsari-1.",
        "biography_source": "https://en.wikipedia.org/wiki/Harka_Sampang",
        "is_notable": True
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
            name_ne = candidate.get("name_ne", "") or candidate.get("name_en", "")

            for politician in POLITICIANS:
                pattern = politician["match_ne"]
                if pattern in name_ne:
                    # Update all fields
                    candidate["name_en_roman"] = politician["name_en_roman"]

                    # Merge aliases
                    existing = set(candidate.get("aliases", []))
                    existing.update(politician["aliases"])
                    candidate["aliases"] = list(existing)

                    candidate["biography"] = politician["biography"]
                    candidate["biography_source"] = politician["biography_source"]
                    candidate["is_notable"] = politician["is_notable"]

                    updated += 1
                    print(f"  Updated: {politician['name_en_roman']}")
                    break

    # Save
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {updated} candidates with detailed biographies")


if __name__ == "__main__":
    main()
