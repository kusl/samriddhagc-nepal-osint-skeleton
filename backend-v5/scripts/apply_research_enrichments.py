#!/usr/bin/env python3
"""
Apply biographical enrichments from research agents to election-results-2082.json
"""

import json
import re
from pathlib import Path

# Biographical enrichments from research agents
ENRICHMENTS = [
    # ========== CPN-UML (a2bdd88) ==========
    {
        "match_ne": "शेरधन राई",
        "name_en_roman": "Sherdhan Rai",
        "biography": "Born 2027 BS Falgun 11 in Tiding, Amchok Rural Municipality-3, Bhojpur. Parents: Jagirman Rai and Ramrimaya Rai. Holds MA in Sociology. Started political career in 2042 BS during school days, went underground during 1990 People's Movement with codename 'Nichhak'. Served as UML Bhojpur District Chairman for four consecutive terms (2054-2070). Elected youngest MP at age 25 in 2056 BS. Minister of Information and Communication Technology and Government Spokesperson in 2072 BS. First Chief Minister of Koshi Province on 2074 Falgun 2. Elected as CPN-UML Secretary in the 11th National Convention.",
        "biography_source": "https://ne.wikipedia.org/wiki/शेरधन_राई",
        "is_notable": True
    },
    {
        "match_ne": "उमाशंकर अरगरिया",
        "name_en_roman": "Umashankar Argariya",
        "biography": "Served as Minister of Culture, Tourism and Civil Aviation from June 4-22, 2021 (18 days before Supreme Court removal). Won from Dhanusha-2 in 2017 elections. Originally from Nepali Congress, joined Madheshi Janadhikar Forum Nepal in 2008 under Upendra Yadav. Later joined Loktantrik Samajwadi Party and then CPN-UML after being welcomed by KP Sharma Oli.",
        "biography_source": "https://en.wikipedia.org/wiki/Umashankar_Argariya",
        "is_notable": True
    },
    {
        "match_ne": "मनोज कुमार सिंह",
        "name_en_roman": "Manoj Kumar Singh",
        "biography": "Elected as member of the Madhesh Provincial Assembly from CPN-UML. Elected from Siraha-3 'A' constituency as a first-time provincial assembly member in 2079 elections. Among the new faces elected to the Madhesh Provincial Assembly.",
        "biography_source": "https://en.wikipedia.org/wiki/Manoj_Kumar_Singh_(Nepalese_politician)",
        "is_notable": True
    },
    {
        "match_ne": "हरीकृष्ण श्रेष्ठ",
        "name_en_roman": "Harikrishna Shrestha",
        "biography": "CPN-UML leader from Myagdi district who served two terms as UML District Chairman. Secretariat member of UML Gandaki Province Committee. Elected as Arthunge VDC Chairman in 2053 BS local elections. Unanimously nominated as UML candidate for House of Representatives from Myagdi constituency in 2079 elections. Known for calm and polite demeanor, played important role in strengthening party organization.",
        "biography_source": "https://www.kathmandupati.com/news/myagdi-amale/246096/",
        "is_notable": True
    },
    {
        "match_ne": "मनोज जंग थापा",
        "name_en_roman": "Manoj Jung Thapa",
        "biography": "CPN-UML Central Committee member and candidate from Sindhuli Federal Constituency No. 2. Engineer by profession. Central In-charge of the Intellectual Council that provides guidance to UML-led governments. Member of Debate Note Committee in UML's Constitution Convention. Named in the 301-member Central Committee proposed by KP Sharma Oli in the 10th National Convention.",
        "biography_source": "https://sindhulisaugat.com/2022/10/09/120039/",
        "is_notable": True
    },
    {
        "match_ne": "विनोद प्रसाद ढकाल",
        "name_en_roman": "Binod Prasad Dhakal",
        "biography": "Prominent CPN-UML leader from Morang district. Party's direct candidate from Morang-4 constituency. Despite central chairman KP Sharma Oli's intervention in Morang's 10th convention, the rebel panel led by Binod Dhakal achieved comprehensive victory. Contested for UML Secretary position in the 11th National Convention receiving 684 votes. Active in party politics at provincial level in Koshi Province.",
        "biography_source": "https://www.makalukhabar.com/2025/12/99977551375/",
        "is_notable": True
    },
    {
        "match_ne": "शेर बहादुर तामाङग",
        "name_en_roman": "Sher Bahadur Tamang",
        "biography": "Former Minister and CPN (NCP) leader who joined KP Sharma Oli-led Nepal Communist Party. Wife Ushakala Rai is Provincial Assembly member from Province No. 1. Previously Law Minister but resigned after controversy over certain statements. Nominated as UML coalition candidate from Sindhupalchok-2 for House of Representatives elections.",
        "biography_source": "https://cpnuml.org/info/1210587",
        "is_notable": True
    },
    {
        "match_ne": "कुलमणि देवकोटा",
        "name_en_roman": "Kulmani Devkota",
        "biography": "CPN-UML Surkhet District Chairman closely associated with Yamlal Kandel. Unanimously nominated as UML candidate for House of Representatives from Surkhet Constituency No. 2 in January 2026. Selected as open category delegate from Karnali Province for UML's 10th National Convention. Prominent district-level leader based in Surkhet.",
        "biography_source": "https://www.ratopati.com/story/534589/",
        "is_notable": True
    },
    {
        "match_ne": "लिलामणी गौतम",
        "name_en_roman": "Lilamani Gautam",
        "biography": "Young CPN-UML leader from Lumbini Province elected as Central Committee member from the Youth Cluster (under 40 years) in the party's 11th National Convention. UML reserved seats for youth cluster in party statute for this convention.",
        "biography_source": "https://www.ratopati.com/story/531148/",
        "is_notable": True
    },
    {
        "match_ne": "जगदिश प्रसाद कुसियैत",
        "name_en_roman": "Jagdish Prasad Kusiyait",
        "biography": "CPN-UML leader unanimously nominated as party's candidate from Sunsari Constituency No. 4 for Falgun 21 House of Representatives elections. Name forwarded as single nomination from constituency, indicating strong party support.",
        "biography_source": "https://www.ratopati.com/story/534899/",
        "is_notable": False
    },
    {
        "match_ne": "रामजी साह सोनार",
        "name_en_roman": "Ramji Sah Sonar",
        "biography": "CPN-UML candidate from Rautahat district. Party's Central Committee meeting decided to nominate him from Rautahat Constituency No. 4 for Falgun 21 House of Representatives elections. Part of UML's full slate of candidates in Madhesh Province.",
        "biography_source": "https://www.ratopati.com/story/537963/",
        "is_notable": False
    },

    # ========== Nepali Congress (a8cbfff) ==========
    {
        "match_ne": "गोरख बहादुर विष्ट",
        "name_en_roman": "Gorakh Bahadur Bishta (Ananda)",
        "biography": "Nepali Congress candidate from Kailali constituency no. 4 for House of Representatives. Has 36 years of political experience and extensive national and international connections. Committed to development in Kailali-4 with strong support from Congress regional leadership including regional president Basanta Rokaya.",
        "biography_source": "https://nepalsamaya.com/detail/140850",
        "is_notable": True
    },
    {
        "match_ne": "प्रबल थापा क्षेत्री",
        "name_en_roman": "Prabal Thapa Chhetri",
        "biography": "Nepali Congress candidate from Kathmandu-1, replacing veteran leader Prakashman Singh. Mahasamiti member of Nepali Congress from Kathmandu-1. Son-in-law of former CIAA Chief Commissioner Lokman Singh Karki and nephew of Rastriya Prajatantra Party leader Kamal Thapa. Close to party president Gagan Thapa.",
        "biography_source": "https://nepalkhabar.com/politics/263321-2026-1-20-15-55-16",
        "is_notable": True
    },
    {
        "match_ne": "मधु प्रसाद आचार्य",
        "name_en_roman": "Madhu Prasad Acharya",
        "biography": "Central committee member of Nepali Congress. Active young leader vocal about making Nepali Congress a people's party. Participated in special general convention supporting Gagan Thapa's faction. Met with government officials including Home Minister along with other Congress youth leaders.",
        "biography_source": "https://shilapatra.com/detail/175177",
        "is_notable": True
    },
    {
        "match_ne": "सुदन कुमार वली",
        "name_en_roman": "Dr. Sudan Kumar Wali",
        "biography": "33-year-old economist with PhD in Economics from University of International Business and Economics, Beijing. Former member of Lumbini Province Planning Commission. Nepali Congress fielded him from Rolpa to challenge traditional Maoist stronghold, representing new generation of policy-focused leadership.",
        "biography_source": "https://www.lumbinisanchar.com/archives/131944",
        "is_notable": True
    },
    {
        "match_ne": "चुन्‍न प्रसाद शर्मा",
        "name_en_roman": "Chunna Prasad Sharma Paudel",
        "biography": "Mahasamiti member of Nepali Congress and candidate from Rupandehi constituency no. 2. Age 60 with citizenship from Baglung. Father: Pashupati Sharma, Wife: Uma Devi Sharma. Pledged to revitalize Butwal's economic, social and development aspects if elected.",
        "biography_source": "https://lumbinipati.com/archives/60895",
        "is_notable": True
    },

    # ========== CPN-Maoist Centre (a9b8cc8) ==========
    {
        "match_ne": "यशोदा गुरुङ",
        "name_en_roman": "Yashoda Gurung Subedi",
        "biography": "CPN (Maoist Centre) politician and Member of Parliament. Central committee member since 8th National Convention in 2022. Selected as Politburo member among 125-member body formed by Chairman Prachanda. Well-connected female leader repeatedly nominated through proportional representation.",
        "biography_source": "https://www.ratopati.com/tag/12457",
        "is_notable": True
    },
    {
        "match_ne": "शिव कुमार मंडल",
        "name_en_roman": "Shiv Kumar Mandal (Kewat)",
        "biography": "CPN (Maoist Centre) politician included in party's 125-member Politburo at rank 49. Chairman Pushpa Kamal Dahal Prachanda proposed his name during Central Committee meeting at Pragya Pratishthan. Madhesi leader representing the party.",
        "biography_source": "https://www.onlinekhabar.com/2022/07/1154107",
        "is_notable": True
    },
    {
        "match_ne": "जयप्रकाश थारु",
        "name_en_roman": "Jayprakash Tharu",
        "biography": "CPN (Maoist Centre) leader elected as Mayor (Pradhan) of Khadag Municipality in Saptari District in 2022 local elections. Defeated incumbent mayor Hemayu Hak of Janata Samajbadi Party with 5,882 votes against 5,067 votes. Victory marked Maoist Centre's first mayoral win in Saptari district.",
        "biography_source": "https://ekantipur.com/local-elections-2022/2022/05/19/165297975285841847.html",
        "is_notable": True
    },
    {
        "match_ne": "घनश्‍याम यादव",
        "name_en_roman": "Ghanshyam Yadav Ahir",
        "biography": "CPN (Maoist Centre) central committee member. Nominated from Madhesi male quota during party's 8th National Convention. Also listed under disability category (Apanga) representation in central committee.",
        "biography_source": "https://www.nayabishwo.com/2022/01/02/101766",
        "is_notable": True
    },

    # ========== RSP (a8ae62f) ==========
    {
        "match_ne": "तौफिक अहमद खान",
        "name_en_roman": "Taufiq Ahmed Khan",
        "biography": "RSP candidate from Rupandehi-5 constituency. Experienced strategic consultant, environmental engineer, and policy expert. Active for past 15 years in governance, sustainable development, and international diplomatic relations. Part of Mayor Balen Shah's quota of candidates.",
        "biography_source": "https://hindi.pardaphash.com/election-activity-intensifies-in-rupandehi-5-with-young-face-taufiq-ahmed-khan-in-the-news/",
        "is_notable": True
    },
    {
        "match_ne": "गणेश पौडेल",
        "name_en_roman": "Ganesh Poudel",
        "biography": "Also known as Khadkaraj Poudel. Contested from Rupandehi-2 in 2079 election as RSP candidate, securing 25,782 votes but losing to UML's Bishnu Poudel by 1,366 votes. Joined RSP through Balen Shah's entry, now central member. RSP candidate from Kaski-1 for 2082 elections, dedicated candidacy to Gen-Z movement martyrs and injured.",
        "biography_source": "https://www.ratopati.com/story/538307/ganesh-poudel-to-contest-from-rsp-in-kaski-1",
        "is_notable": True
    },
    {
        "match_ne": "सीताराम साह",
        "name_en_roman": "Sitaram Sah",
        "biography": "RSP candidate from Saptari-4 constituency for 2082 Pratinidhi Sabha elections. Part of RSP's 164 candidates fielded across Nepal for Falgun 21 election.",
        "biography_source": "https://www.setopati.com/politics/380341",
        "is_notable": False
    },
    {
        "match_ne": "राजन गौतम",
        "name_en_roman": "Rajan Gautam",
        "biography": "Gandaki Province President of RSP. Member of candidate selection committee under coordination of Joint General Secretary Bipin Acharya. Member of election-focused task force. Applied for proportional candidacy from Gandaki Province.",
        "biography_source": "https://www.ratopati.com/story/524961/",
        "is_notable": True
    },
    {
        "match_ne": "लखन कुमार थापा",
        "name_en_roman": "Lakhan Kumar Thapa",
        "biography": "Elected as Rukum East District President of RSP at district convention. Leads 13-member new district working committee. Under his leadership, party decided to strengthen organization across district and expand membership while intensifying political activities.",
        "biography_source": "https://tikhosanchar.com/?p=9469",
        "is_notable": True
    },
    {
        "match_ne": "कृष्ण हरी बुढाथोकी",
        "name_en_roman": "Dr. Krishna Hari Budhathoki",
        "biography": "Selected as RSP candidate from Ramechhap constituency for Pratinidhi Sabha elections. Finalized during late-night party meeting along with candidates for Okhaldhunga, Syangja-1, Bajura, and Baglung-2.",
        "biography_source": "https://www.makalukhabar.com/2026/01/99977560436/",
        "is_notable": True
    },
    {
        "match_ne": "अचुत्तम लामिछाने",
        "name_en_roman": "Achuttam Lamichhane",
        "biography": "Bagmati Province President of RSP. Ex-officio member of election-focused task force formed by party's central committee. Task force formed at RSP central committee meeting at Banasthali central office to focus on political studies, election strategy, and media studies.",
        "biography_source": "https://www.ratopati.com/story/524958/",
        "is_notable": True
    },
    {
        "match_ne": "नरेन्द्र कुमार गुप्ता",
        "name_en_roman": "Narendra Kumar Gupta",
        "biography": "RSP candidate from Nawalparasi-2 constituency. Among 164 candidates fielded by RSP for upcoming Pratinidhi Sabha elections.",
        "biography_source": "https://www.setopati.com/politics/380341",
        "is_notable": False
    },
    {
        "match_ne": "रामजी यादव",
        "name_en_roman": "Ramji Yadav",
        "biography": "RSP candidate from Saptari-2 constituency for 2082 elections. One of candidates fielded in Saptari district along with Pushpa Chaudhary (Saptari-1), Umakant Chaudhary (Saptari-3), and Sitaram Sah (Saptari-4).",
        "biography_source": "https://www.setopati.com/politics/380341",
        "is_notable": False
    },
    {
        "match_ne": "पुष्पा कुमारी चौधरी",
        "name_en_roman": "Pushpa Kumari Chaudhary",
        "biography": "RSP candidate from Saptari-1 constituency. Part of party's slate of candidates for 2082 Pratinidhi Sabha elections in Saptari district.",
        "biography_source": "https://www.setopati.com/politics/380341",
        "is_notable": False
    },
    {
        "match_ne": "बिश्वराज पोखरेल",
        "name_en_roman": "Bishwaraj Pokhrel",
        "biography": "Selected as RSP candidate from Okhaldhunga constituency for Pratinidhi Sabha elections. Finalized during late-night party meeting.",
        "biography_source": "https://www.makalukhabar.com/2026/01/99977560436/",
        "is_notable": False
    },

    # ========== JSP (ae442db) ==========
    {
        "match_ne": "योगेन्द्र राय यादव",
        "name_en_roman": "Yogendra Rae Yadav",
        "biography": "Nepali politician and former member of Madhesh Provincial Assembly from JSP Nepal. Elected from Rautahat 1(Kha) constituency. Also assigned party mobilization responsibility in Rautahat for Swatantra Vidyarthi Union (SwiViYu) elections.",
        "biography_source": "https://en.wikipedia.org/wiki/Yogendra_Rae_Yadav",
        "is_notable": True
    },
    {
        "match_ne": "दीपक गुरुङ्ग",
        "name_en_roman": "Deepak Gurung",
        "biography": "JSP Nepal leader recommended as candidate for Rupandehi constituency no. 2 for House of Representatives elections on Falgun 21.",
        "biography_source": "https://www.ratopati.com/story/535143/",
        "is_notable": False
    },
    {
        "match_ne": "सबिता यादव",
        "name_en_roman": "Sabita Yadav",
        "biography": "JSP Nepal leader assigned party mobilization responsibility in Sunsari district. Worked alongside Dineshkumar Mehta and Tajub Limbu in Sunsari for Swatantra Vidyarthi Union (SwiViYu) elections.",
        "biography_source": "https://www.nepalpress.com/2025/03/07/568608/",
        "is_notable": False
    },
    {
        "match_ne": "अशेश्वर यादव",
        "name_en_roman": "Asheshwar Yadav",
        "biography": "JSP Nepal Central Executive Committee member. Selected to central executive committee in party's post-convention work distribution.",
        "biography_source": "https://www.setopati.com/politics/337574",
        "is_notable": False
    },
]


def normalize_name(name: str) -> str:
    """Normalize name for matching by removing extra spaces and common variations."""
    # Remove parenthetical content for matching
    name = re.sub(r'\s*\([^)]*\)', '', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name.strip()


def apply_enrichments(election_data: dict, enrichments: list) -> tuple[dict, int]:
    """Apply biographical enrichments to election data."""
    # Create lookup by normalized Nepali name
    enrichment_map = {}
    for e in enrichments:
        key = normalize_name(e["match_ne"])
        enrichment_map[key] = e

    updated_count = 0

    for constituency in election_data.get("results", []):
        for candidate in constituency.get("candidates", []):
            # Try to match by Nepali name
            name_ne = candidate.get("name_ne", "")
            normalized = normalize_name(name_ne)

            if normalized in enrichment_map:
                enrichment = enrichment_map[normalized]

                # Only update if we have better information
                current_bio = candidate.get("biography", "")
                new_bio = enrichment["biography"]

                # Check if current bio is just a placeholder
                is_placeholder = (
                    "Detailed biographical information not available" in current_bio or
                    "No detailed biographical information was found" in current_bio or
                    len(current_bio) < 100
                )

                if is_placeholder or len(new_bio) > len(current_bio):
                    candidate["biography"] = new_bio
                    candidate["biography_source"] = enrichment["biography_source"]
                    candidate["is_notable"] = enrichment["is_notable"]

                    # Update romanized name if provided
                    if enrichment.get("name_en_roman"):
                        candidate["name_en_roman"] = enrichment["name_en_roman"]

                    updated_count += 1
                    print(f"  ✓ Updated: {name_ne} ({candidate.get('party', 'Unknown')})")

    return election_data, updated_count


def main():
    # Paths
    input_path = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/frontend/public/data/election-results-2082.json")
    output_path = input_path  # Overwrite in place

    print(f"Loading election data from: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        election_data = json.load(f)

    total_candidates = sum(
        len(c.get("candidates", []))
        for c in election_data.get("results", [])
    )
    print(f"Total candidates in dataset: {total_candidates}")
    print(f"Enrichments to apply: {len(ENRICHMENTS)}")
    print("\nApplying enrichments...")

    updated_data, updated_count = apply_enrichments(election_data, ENRICHMENTS)

    print(f"\n✓ Updated {updated_count} candidates with biographical enrichments")

    # Save updated data
    print(f"\nSaving to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)

    print("Done!")

    # Also save enrichments as standalone JSON for reference
    enrichments_path = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/backend-v5/scripts/enrichments/research_biographies.json")
    enrichments_path.parent.mkdir(exist_ok=True)

    with open(enrichments_path, 'w', encoding='utf-8') as f:
        json.dump(ENRICHMENTS, f, ensure_ascii=False, indent=2)

    print(f"Enrichments also saved to: {enrichments_path}")


if __name__ == "__main__":
    main()
