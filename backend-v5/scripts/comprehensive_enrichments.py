#!/usr/bin/env python3
"""
Comprehensive Candidate Enrichments for Nepal 2082 (2026) Elections
Compiled from multiple research agents across 7 major parties.

Sources used:
- Kathmandu Post (kathmandupost.com)
- My Republica (myrepublica.nagariknetwork.com)
- Himalayan Times (thehimalayantimes.com)
- Setopati (en.setopati.com)
- Onlinekhabar (english.onlinekhabar.com)
- Wikipedia
- Official government/party websites
"""
import json
from pathlib import Path

# ============ CPN-UML ENRICHMENTS ============
UML_ENRICHMENTS = [
    {
        "match_ne": "इश्वर पोखरेल",
        "name_en_roman": "Ishwar Pokharel",
        "aliases": ["Ishwor Pokhrel", "Ishwar Pokhrel"],
        "biography": "Deputy PM & Defence Minister (2018-2021). Senior Vice-President of CPN-UML. Founding Central Committee member of CPN (ML) in 1980. Two-time General Secretary of CPN-UML (2009-2018). Key architect of peace process and Maoist combatant integration.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/uml-senior-vice-chair-pokharel-made-acting-party-chairman",
        "is_notable": True
    },
    {
        "match_ne": "प्रदिप कुमार ज्ञवाली",
        "name_en_roman": "Pradeep Kumar Gyawali",
        "aliases": ["Pradip Kumar Gyawali", "Pradeep Gyawali"],
        "biography": "Foreign Minister (2018-2021). CPN-UML Standing Committee member and spokesperson. Key government negotiator with Maoist rebels during peace process. Multiple-term MP from Gulmi since 1999. Published poet and author.",
        "biography_source": "https://kathmandupost.com/politics/2021/04/18/in-the-cpn-uml-oli-has-found-a-new-spin-doctor-pradeep-gyawali",
        "is_notable": True
    },
    {
        "match_ne": "शंकर पोख्रेल",
        "name_en_roman": "Shankar Pokhrel",
        "aliases": ["Shankar Pokharel"],
        "biography": "General Secretary of CPN-UML. Former Chief Minister of Lumbini Province (2018, 2021). Former President of ANNFSU. Minister for Information and Communications. Lost Dang-2 by 196 votes in 2022.",
        "biography_source": "https://en.setopati.com/political/159955",
        "is_notable": True
    },
    {
        "match_ne": "देव राज घिमिरे",
        "name_en_roman": "Dev Raj Ghimire",
        "aliases": ["Devraj Ghimire"],
        "biography": "Speaker of House of Representatives (Jan 2023 - Jan 2026). Joined Communist Party following Jhapa rebellion in 1974. National Assembly member (1999-2003). UML Province-1 in-charge. MP from Jhapa-2.",
        "biography_source": "https://kathmandupost.com/national/2023/01/19/uml-s-dev-raj-ghimire-elected-house-speaker",
        "is_notable": True
    },
    {
        "match_ne": "राजन भट्टराई",
        "name_en_roman": "Rajan Bhattarai",
        "aliases": ["Dr. Rajan Bhattarai"],
        "biography": "CPN-UML Standing Committee member. Foreign Affairs Advisor to PM KP Oli (twice) and PM Madhav Nepal. PhD from JNU, Master's from University of London (Chevening). Member of Nepal-India Eminent Persons' Group. Chairs Asia-Europe Political Forum since 2022.",
        "biography_source": "https://kathmandupost.com/politics/2024/07/19/nepal-can-t-backtrack-on-bri-says-uml-leader",
        "is_notable": True
    },
    {
        "match_ne": "भानु भक्त ढकाल",
        "name_en_roman": "Bhanu Bhakta Dhakal",
        "aliases": ["Bhanubhakta Dhakal"],
        "biography": "Minister for Health, Culture/Tourism, and Law/Justice. Member of 2nd CA from Terhathum. Convener of UML Mass Organizations. Former ANNFSU Secretary General. Controversy: Alleged embezzlement in COVID medical equipment procurement.",
        "biography_source": "https://en.setopati.com/political/127162",
        "is_notable": True
    },
    {
        "match_ne": "पृथ्‍वी सुव्वा गुरुङ",
        "name_en_roman": "Prithvi Subba Gurung",
        "aliases": ["Prithvi Subba Gurung"],
        "biography": "CPN-UML Vice-President. Former Chief Minister of Gandaki Province (2018-2021). Current Minister of ICT. Former Minister of Culture/Tourism. Won Lamjung 2022 defeating Maoist General Secretary.",
        "biography_source": "https://en.wikipedia.org/wiki/Prithvi_Subba_Gurung",
        "is_notable": True
    },
    {
        "match_ne": "भगवती न्यौपाने",
        "name_en_roman": "Bhagwati Neupane",
        "aliases": ["Bhagawati Neupane"],
        "biography": "Current Minister of Federal Affairs (July 2025). UML Central Committee member. Chief Whip of UML in National Assembly. Resigned NA seat Jan 2026 to contest HoR from Tanahun-1.",
        "biography_source": "https://kathmandupost.com/national/2025/07/15/uml-leader-bhagwati-neupane-appointed-as-minister-for-federal-affairs-and-general-administration",
        "is_notable": True
    },
    {
        "match_ne": "अर्जुन कुमार कार्की",
        "name_en_roman": "Arjun Kumar Karki",
        "aliases": ["Arjun Karki", "Dr. Arjun Kumar Karki"],
        "biography": "Ambassador of Nepal to USA (2015-2021). President of Rural Reconstruction Nepal since 1989. International coordinator of LDC Watch since 2004. Justice and Peace Award recipient (2011).",
        "biography_source": "https://en.wikipedia.org/wiki/Arjun_Karki",
        "is_notable": True
    },
    {
        "match_ne": "गणेश सिंह ठगुन्ना",
        "name_en_roman": "Ganesh Singh Thagunna",
        "aliases": ["Ganesh Thaguna"],
        "biography": "Minister of Federal Affairs. Multiple-term MP from Darchula (2013, 2017). Darchula District Secretary for UML three times. Deputy In-charge of Sudurpaschim Pradesh Committee.",
        "biography_source": "https://en.wikipedia.org/wiki/Ganesh_Singh_Thagunna",
        "is_notable": True
    },
    {
        "match_ne": "घनश्याम खतीवडा",
        "name_en_roman": "Ghanashyam Khatiwada",
        "aliases": ["Ghanashyam Khatewada"],
        "biography": "CPN-UML Koshi Province Chairman. Elected to House of Representatives from Morang-1 in 2017. Prominent figure in UML eastern Nepal politics.",
        "biography_source": "https://en.setopati.com/political/161855",
        "is_notable": True
    },
    {
        "match_ne": "पार्वत गुरुङ",
        "name_en_roman": "Parvat Gurung",
        "aliases": ["Parbat Gurung"],
        "biography": "Former Minister of Communication and IT and Minister of Women, Children and Senior Citizens under PM Oli. Elected from Dolakha in 2017 and 2013 CA.",
        "biography_source": "https://en.wikipedia.org/wiki/Parbat_Gurung",
        "is_notable": True
    },
    {
        "match_ne": "राजेन्द्र कुमार राई",
        "name_en_roman": "Rajendra Kumar Rai",
        "aliases": ["Rajendra Rai"],
        "biography": "Cabinet Minister. Current MP from Dhankuta-1 (won 2017, 2022). UML Dhankuta Chairman (2009-2018). UML swept Dhankuta in 2022 - Rai defeated Sunil Bahadur Thapa by 1,397 votes.",
        "biography_source": "https://myrepublica.nagariknetwork.com/index.php/news/rajendra-rai-of-uml-wins-in-dhankuta",
        "is_notable": True
    },
    {
        "match_ne": "दावा दोर्जे लामा",
        "name_en_roman": "Dawa Dorje Lama",
        "aliases": ["Dawa Lama"],
        "biography": "Minister of Land Management, Agriculture and Cooperatives in Bagmati Province. Provincial Assembly member from Chitwan-1 'Ka'. Vice Chairman of UML Bagmati Provincial Committee. Close to PM Oli.",
        "biography_source": "https://kathmandupost.com/national/2018/02/28/province-3-cabinet-expanded-four-new-ministers-sworn-in",
        "is_notable": True
    },
    {
        "match_ne": "नारायण प्रसाद आचार्य",
        "name_en_roman": "Narayan Prasad Acharya",
        "aliases": ["Narayan Acharya"],
        "biography": "MP from Palpa-1 (2022, 31,103 votes). Defeated NC's Gyan Bahadur Gaha. Unanimously elected CPN-UML Palpa District Chairman at party's 8th district convention.",
        "biography_source": "https://en.wikipedia.org/wiki/Narayan_Prasad_Acharya",
        "is_notable": True
    },
    {
        "match_ne": "खिम लाल भट्टराई",
        "name_en_roman": "Khim Lal Bhattarai",
        "aliases": ["Khimlal Bhattarai"],
        "biography": "Former UML Chief Whip (until Mar 2022), then Parliamentary Party Leader in National Assembly. Resigned NA seat to contest Rupandehi-5 in 2022 but candidacy invalidated due to nomination conflict.",
        "biography_source": "https://thehimalayantimes.com/kathmandu/uml-loses-na-seat",
        "is_notable": True
    },
    {
        "match_ne": "अशोक कुमार ब्याञ्जु श्रेष्ठ",
        "name_en_roman": "Ashok Kumar Byanju Shrestha",
        "aliases": ["Ashok Byanju"],
        "biography": "Mayor of Dhulikhel Municipality (2022, 8,351 votes). Represented Dhulikhel in UCLG ASPAC meetings. Led Dhulikhel to become WeGO member (2018).",
        "biography_source": "https://dhulikhelmun.gov.np/en/content/ashok-kumar-byanjushrestha",
        "is_notable": True
    },
    {
        "match_ne": "मिलन गुरुङ्ग",
        "name_en_roman": "Milan Gurung",
        "aliases": ["Chakre Milan", "Milan Chakre"],
        "biography": "Notorious underworld figure turned politician, known as 'Chakre Milan'. Son of former Gorkha Army soldier from Siranchowk. Rose through sand mining commissions in Maharajgunj. UML candidate for Gorkha-2 contesting seat previously held by Prachanda. Multiple criminal cases including gang-related activities. Arrested multiple times including Aug 2024 in Maharajgunj.",
        "biography_source": "https://english.onlinekhabar.com/milan-chakres-double-life.html",
        "is_notable": True
    },
]

# ============ NEPALI CONGRESS ENRICHMENTS ============
NC_ENRICHMENTS = [
    {
        "match_ne": "विमलेन्द्र निधि",
        "name_en_roman": "Bimalendra Nidhi",
        "aliases": ["Vimalendra Nidhi", "Bimal Nidhi"],
        "biography": "NC Vice President. Deputy PM twice (under PM Dahal). Home Minister. Minister for Education, General Administration, Physical Infrastructure. Son of late NC General Secretary Mahendra Narayan Nidhi. Former NSU president. 7 years imprisoned for democracy movements.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/will-nepali-congress-make-bimalendra-nidhi-its-president",
        "is_notable": True
    },
    {
        "match_ne": "विजय कुमार गच्‍छदार",
        "name_en_roman": "Bijay Kumar Gachhadar",
        "aliases": ["Vijay Kumar Gachhadar", "BK Gachhadar"],
        "biography": "NC Vice President. Deputy PM 5 times under 5 different PMs. Led Nepal Loktantrik Forum before merging with NC (2017). Minister for Water Resources. Controversy: Lalita Niwas land scandal - released on Rs 10 lakh bail.",
        "biography_source": "https://thehimalayantimes.com/nepal/bijay-kumar-gachhadar-named-nepali-congress-vice-president-flouting-party-statute/",
        "is_notable": True
    },
    {
        "match_ne": "मिनेन्द्र प्रसाद रिजाल",
        "name_en_roman": "Minendra Prasad Rijal",
        "aliases": ["Minendra Rijal", "Dr. Minendra Rijal"],
        "biography": "Former Defence Minister (Oct 2022). Minister for Information (under PM Koirala). MP from Morang-2 (late PM GP Koirala's constituency). Key architect of Nepal's mixed electoral system. Educated at NYU Stern, Amrit Science College.",
        "biography_source": "https://www.c-r.org/who-we-are/people/minendra-rijal",
        "is_notable": True
    },
    {
        "match_ne": "महेन्द्र यादव",
        "name_en_roman": "Mahendra Yadav",
        "aliases": ["Mahendra Prasad Yadav"],
        "biography": "NC Deputy General Secretary. Former Minister of Water Supply (2017). President of Nepal Tarun Dal (2007). Member of both CAs. Lost Dhanusha-4 by only 124 votes in 2022 to CPN-UML.",
        "biography_source": "https://en.wikipedia.org/wiki/Mahendra_Yadav_(Nepali_politician)",
        "is_notable": True
    },
    {
        "match_ne": "फरमुल्लाह मंसुर",
        "name_en_roman": "Farmullah Mansoor",
        "aliases": ["Farmullah Mansur"],
        "biography": "NC Joint General Secretary (Muslim category). MP from Bara-3. Former Labour Minister. Close ally of GP Koirala and Sushil Koirala. Elected joint gen sec defeating Sheikh Wakil (2,776 vs 1,871).",
        "biography_source": "https://en.wikipedia.org/wiki/Farmullah_Mansoor",
        "is_notable": True
    },
    {
        "match_ne": "महालक्ष्मी उपाध्याय(डिना)",
        "name_en_roman": "Mahalakshmi Upadhyay (Dina)",
        "aliases": ["Mahalaxmi Upadhyay Dina", "Dina Upadhyaya"],
        "biography": "NC Joint General Secretary (women). Former State Minister. CA member (2008, 2013). Lost to RPP by 2,382 votes in Makwanpur-1 in 2022. Vocal defender of constitution.",
        "biography_source": "https://kathmandupost.com/national/2017/11/28/old-foes-back-in-race-after-23-years",
        "is_notable": True
    },
    {
        "match_ne": "नैन सिंह महर",
        "name_en_roman": "Nain Singh Mahar",
        "aliases": ["Nain Simh Mahar"],
        "biography": "Former NSU President (2016). From Dadeldhura (PM Deuba's home district). Founding president of FNJ Dadeldhura. Author of 'Nepali Congress and Its Sister Organizations'. Received NC ticket for Dadeldhura replacing Deuba's traditional seat.",
        "biography_source": "https://kathmandupost.com/valley/2016/08/18/nain-singh-mahar-wins-nsu-presidential-election",
        "is_notable": True
    },
    {
        "match_ne": "योगेन्द्र चौधरी",
        "name_en_roman": "Yogendra Chaudhary",
        "aliases": ["Yogendr Chaudhary"],
        "biography": "NC Central Joint General Secretary (Tharu category). Tharuhat movement leader. Advocated for Tharu language as official. Nominated from Dang-1 for 2026. Tharus comprise 34% of Dang's population.",
        "biography_source": "https://kathmandupost.com/politics/2022/11/17/minister-chaudhary-faces-tough-challenge-in-dang-1",
        "is_notable": True
    },
    {
        "match_ne": "गुरु राज घिमिरे",
        "name_en_roman": "Guru Raj Ghimire",
        "aliases": ["Gururaj Ghimire"],
        "biography": "Newly elected NC General Secretary (2025) under Gagan Thapa's leadership. Vocal critic of undemocratic practices within party, describing arbitrary schedule changes as 'authoritarian'. Represents NC's reformist wing that fought for internal party democracy.",
        "biography_source": "https://khojsamachar.com/gururaj-ghimire-nepali-congress-authoritarian-practices/",
        "is_notable": True
    },
    {
        "match_ne": "अर्जुन प्रसाद जोशी",
        "name_en_roman": "Arjun Prasad Joshi",
        "aliases": ["Arjun Joshi"],
        "biography": "Veteran NC politician from Parbat. Won Parvat-1 in 2008 CA (13,258 votes). Elected to House of Representatives in 1999. Nominated to NC Central Committee by PM Deuba, later elected as open category central member.",
        "biography_source": "https://en.wikipedia.org/wiki/Arjun_Prasad_Joshi",
        "is_notable": True
    },
    {
        "match_ne": "गोविन्द भट्टराई",
        "name_en_roman": "Govind Bhattarai",
        "aliases": ["Govinda Bhattarai"],
        "biography": "NC politician from Tanahun. Former NSU President and Nepal Tarun Dal Vice President. Lost Tanahun-1 by-election (2023) to RSP's Dr. Swarnim Wagle by 14,388 votes despite ruling coalition backing.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/nc-decides-to-nominate-govinda-bhattarai-in-tanahu-1/",
        "is_notable": True
    },
    {
        "match_ne": "तिलक बहादुर रानाभाट",
        "name_en_roman": "Tilak Bahadur Ranabhat",
        "aliases": ["Tilak Ranabhat"],
        "biography": "NC Central Committee member (open category) from Kaski. Elected at party's special convention under Gagan Thapa leadership. NC candidate for Kaski-1 in 2026 elections.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/15/here-is-the-list-of-newly-elected-office-bearers-central-committee-members-of-nepali-congress",
        "is_notable": True
    },
]

# ============ RSP ENRICHMENTS ============
RSP_ENRICHMENTS = [
    {
        "match_ne": "पुकार बम",
        "name_en_roman": "Pukar Bam",
        "aliases": ["Pukar Bom"],
        "biography": "RSP negotiation team chief. Founding member of Bibeksheel Nepali Party. Led 'Enough is Enough' campaign with 11-day hunger strike. Active in earthquake reconstruction and COVID relief. Edward S. Mason Fellow at Harvard (2025).",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/pukar-bam-accepted-as-edward-s-mason-fellow-at-harvard-university-89-56.html",
        "is_notable": True
    },
    {
        "match_ne": "सागर ढकाल",
        "name_en_roman": "Sagar Dhakal",
        "aliases": [],
        "biography": "Challenged PM Deuba in Dadeldhura-1 (2022) as independent, got 13,042 votes vs Deuba's 25,534. Questioned Deuba on BBC Nepali about accountability. RSP Secretariat member. Plans rematch in 2026.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/16/sagar-dhakal-plans-rematch-against-sher-bahadur-deuba-in-dadeldhura",
        "is_notable": True
    },
    {
        "match_ne": "रन्‍जु न्‍यौपाने",
        "name_en_roman": "Ranju Darshana",
        "aliases": ["Ranju Darshana Neupane", "Ranju Nyaupane"],
        "biography": "Youth activist. Ran for Kathmandu Mayor at 21 (2017) - 3rd place with 23,439 votes. Former general secretary of Bibeksheel Sajha. Founded 'Monday for Mental Health'. Earthquake rescue activist (2015).",
        "biography_source": "https://en.m.wikipedia.org/wiki/Ranju_Darshana",
        "is_notable": True
    },
    {
        "match_ne": "डा. लेखजंग थापा",
        "name_en_roman": "Dr. Lekh Jung Thapa",
        "aliases": ["Lekhjung Thapa"],
        "biography": "Senior neurologist. Founding president of Nepal Stroke Association. Heads neurology dept at National Neuro Center. Developed national stroke protocol. Trained thousands of health workers through 'Stroke Master Class'. Won RSP primary with highest votes.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/rsp-to-field-dr-lekh-jung-thapa-in-rupandehi-3-by-election-38-50.html",
        "is_notable": True
    },
    {
        "match_ne": "इन्दिरा राना मगर",
        "name_en_roman": "Indira Rana Magar",
        "aliases": ["Indira Ranamagar"],
        "biography": "Deputy Speaker (Jan 2023 - Dec 2025). Founded Prisoners' Assistance Nepal (2000). Runs children's homes in Kathmandu, Sankhu, Jhapa. BBC 100 Most Influential Women (2017). Ashok Fellow. Queen Silvia World Children's Honorary Award (2014).",
        "biography_source": "https://en.wikipedia.org/wiki/Indira_Ranamagar",
        "is_notable": True
    },
    {
        "match_ne": "कविन्द्र बुर्लाकोटी",
        "name_en_roman": "Kabindra Burlakoti",
        "aliases": ["Kavindra Burlakoti"],
        "biography": "RSP General Secretary (June 2025). Former Deputy General Secretary. Promoted after founding gen sec Mukul Dhakal expelled (Aug 2024). Heads party integration subcommittee following mergers with Balen Shah's team.",
        "biography_source": "https://kathmandupost.com/national/2025/06/21/rastriya-swatantra-party-appoints-jha-as-spokesperson-burlakoti-as-general-secretary",
        "is_notable": True
    },
    {
        "match_ne": "खगेन्द्र सुनार",
        "name_en_roman": "Khagendra Sunar",
        "aliases": [],
        "biography": "Dalit rights activist from Banke-3. Rose to prominence after 2020 Rukum West killings. Coordinator of Dalit Campaign. Protested at Maitighar in chains. Controversy: Ministerial nomination withdrawn due to legal cases.",
        "biography_source": "https://kathmandupost.com/politics/2025/10/26/prime-minister-drops-khagendra-sunar-s-ministerial-nomination-due-to-controversy",
        "is_notable": True
    },
    {
        "match_ne": "मिङमा शेर्पा",
        "name_en_roman": "Mingma Sherpa",
        "aliases": [],
        "biography": "World-renowned mountaineer. First Nepali/South Asian to climb all 14 eight-thousanders on first attempt (2011). Guinness Record with brother Chhang Dawa. Chairman of Seven Summit Treks. Quit NC to join RSP.",
        "biography_source": "https://thehimalayantimes.com/nepal/mountaineer-tourism-entrepreneur-mingma-sherpa-resigns-from-nepali-congress",
        "is_notable": True
    },
    {
        "match_ne": "निशा डाँगी",
        "name_en_roman": "Nisha Dangi",
        "aliases": [],
        "biography": "Among Nepal's youngest MPs (born 1997). Entered parliament Dec 2022 via PR at age 25. RSP Parliamentary Party Whip (May 2023). Liaison MP for Jhapa, Morang, Ilam, Salyan. Symbol of youth empowerment.",
        "biography_source": "https://en.wikipedia.org/wiki/Nisha_Dangi",
        "is_notable": True
    },
    {
        "match_ne": "के पी खनाल",
        "name_en_roman": "K.P. Khanal",
        "aliases": ["KP Khanal"],
        "biography": "'Nepal's Youngest Social Activist' (born 2000). Started 'Bal Bahas' radio program at 13. Founding chairperson of Maina Devi Foundation. National Youth Lead Award (2019). Active in Gen Z movement.",
        "biography_source": "https://en.wikipedia.org/wiki/KP_Khanal",
        "is_notable": True
    },
    {
        "match_ne": "सस्मित पोखरेल",
        "name_en_roman": "Sasmit Pokharel",
        "aliases": ["Sasmita Pokharel"],
        "biography": "Close aide of Mayor Balen Shah. Associate expert at City Planning Commission. Law student at Kathmandu University. RSP secretariat member and joint spokesperson from Balen's team. Contesting Kathmandu-5.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/mayor-balens-close-aide-sasmit-pokharel-likely-to-contest-from-kathmandu-5-61-42.html",
        "is_notable": True
    },
    {
        "match_ne": "सुनिल के.सी.",
        "name_en_roman": "Sunil K.C.",
        "aliases": ["Sunil KC"],
        "biography": "Founder of AIDIA (Asian Institute of Diplomacy). President of NICCI. FNCCI Executive Committee member. Started career as radio presenter at 13. Won Bagmati provincial seat from Kathmandu-2 (A) in 2022 as RPP candidate.",
        "biography_source": "https://www.aidiaasia.org/speaker/1/bio",
        "is_notable": True
    },
    {
        "match_ne": "मनिष झा",
        "name_en_roman": "Manish Jha",
        "aliases": [],
        "biography": "RSP Spokesperson (appointed June 2025). MP since 2022 via PR from Madheshi category. Based in Janakpur/Kathmandu. Handles party communications. Running for Dhanusha-3.",
        "biography_source": "https://en.wikipedia.org/wiki/Manish_Jha_(politician)",
        "is_notable": True
    },
    {
        "match_ne": "भुप देव शाह",
        "name_en_roman": "Bhupadev Shah",
        "aliases": ["Bhupdev Shah", "Bhoop Dev Shah"],
        "biography": "Chief personal secretary to Mayor Balen Shah for three years. Previously personal secretary to late Ujwal Thapa (Bibeksheel Nepali founder). RSP secretariat member and co-general secretary. Contesting Achham-2.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/mayor-balens-chief-personal-secretary-bhoop-dev-shah-to-contest-from-achham-91-64.html",
        "is_notable": True
    },
    {
        "match_ne": "बिनिता कठायत",
        "name_en_roman": "Binita Kathayat",
        "aliases": [],
        "biography": "Current MP via PR (2022). From Jumla district. Former Galaxy 4K Television staff. Invited as RSP Khas Arya representative from rural areas. Known for campaigning in snow, visiting remote households. Running for Jumla-1.",
        "biography_source": "https://en.wikipedia.org/wiki/Binita_Kathayat",
        "is_notable": True
    },
    {
        "match_ne": "सुलभ खरेल",
        "name_en_roman": "Sulabh Kharel",
        "aliases": ["Sulav Kharel"],
        "biography": "Lawyer specializing in criminal defense and constitutional litigation. LL.M. from Michigan Law School. Presidential award for arguments challenging PM's House dissolution. Close to RSP President Lamichhane. Running for Rupandehi-2.",
        "biography_source": "https://kathmandupost.com/province-no-5/2025/08/07/nine-vie-for-rastriya-swatantra-party-candidacy-in-rupandehi-3-by-election",
        "is_notable": True
    },
    {
        "match_ne": "सुधन गुरुङ",
        "name_en_roman": "Sudan Gurung",
        "aliases": ["Sudhan Gurung"],
        "biography": "Founder of Hami Nepal NGO. Emerged as face of 2025 Gen Z uprising that toppled PM Prachanda's government. Created 'Youths Against Corruption' Discord channel coordinating protests. Negotiated with President and Army Chief, helped install Sushila Karki as interim PM. Facilitated RSP-Balen Shah merger talks. Plans Nepal Janasewa Party with Gen-Z martyr family members.",
        "biography_source": "https://en.wikipedia.org/wiki/Sudan_Gurung",
        "is_notable": True
    },
]

# ============ NCP/MAOIST ENRICHMENTS ============
MAOIST_ENRICHMENTS = [
    {
        "match_ne": "भीम बहादुर रावल",
        "name_en_roman": "Bhim Bahadur Rawal",
        "aliases": ["Bhim Rawal", "Dr. Bhim Bahadur Rawal"],
        "biography": "Deputy PM & Defence Minister (First Oli cabinet). Home Minister (Madhav Nepal cabinet). Minister for Commerce/Tourism (1994-95, 1998-99). Lawyer. Expelled from CPN-UML (2024), now with NCP. UN Cambodian elections panel member.",
        "biography_source": "https://en.wikipedia.org/wiki/Bhim_Bahadur_Rawal",
        "is_notable": True
    },
    {
        "match_ne": "ओनसरी घर्ती मगर",
        "name_en_roman": "Onsari Gharti Magar",
        "aliases": [],
        "biography": "First female Speaker of Nepal's Parliament (Oct 2015) - youngest ever. Former Maoist guerrilla who fought in decade-long insurgency. Participated in Holeri police post attack (1996). Deputy Speaker. Minister of Youth/Sports. Married to Barsha Man Pun.",
        "biography_source": "https://en.wikipedia.org/wiki/Onsari_Gharti_Magar",
        "is_notable": True
    },
    {
        "match_ne": "देव प्रसाद गुरुङ",
        "name_en_roman": "Dev Prasad Gurung",
        "aliases": ["Dev Gurung"],
        "biography": "General Secretary of CPN-Maoist Centre (Aug 2022). Key figure in peace negotiations. Minister for Local Development (2007 x2), Law/Justice (2008). Won Manang in 2008 CA. Former Chief Whip.",
        "biography_source": "https://en.wikipedia.org/wiki/Dev_Gurung",
        "is_notable": True
    },
    {
        "match_ne": "पम्फा भुसाल",
        "name_en_roman": "Pampha Bhusal",
        "aliases": [],
        "biography": "Second woman to lead a political party in Nepal. Only female member of 19-member Maoist central committee during insurgency (1996). Minister of Energy (2021). Won Lalitpur-3 in 2008 CA landslide. CPN-MC Assistant General Secretary.",
        "biography_source": "https://en.wikipedia.org/wiki/Pampha_Bhusal",
        "is_notable": True
    },
    {
        "match_ne": "जनार्दन शर्मा",
        "name_en_roman": "Janardan Sharma",
        "aliases": ["Prabhakar"],
        "biography": "Former Finance and Home Minister. One of four PLA deputy commanders. Ended 18-hour loadshedding as Energy Minister. Four-time MP from Rukum West-1. Controversy: Tax rate controversy as Finance Minister. Split from Prachanda (2025) forming 'Progressive Campaign Nepal'.",
        "biography_source": "https://en.wikipedia.org/wiki/Janardan_Sharma",
        "is_notable": True
    },
    {
        "match_ne": "कृष्ण बहादुर महारा",
        "name_en_roman": "Krishna Bahadur Mahara",
        "aliases": [],
        "biography": "Former Speaker (2018). CPN-MC Vice-Chair. Close Prachanda associate during civil war. Deputy PM and Finance Minister. Controversy: Arrested Mar 2024 and Oct 2025 for gold smuggling with Chinese nationals - facing organized crime charges.",
        "biography_source": "https://www.occrp.org/en/news/nepals-former-speaker-charged-with-gold-smuggling-organized-crime",
        "is_notable": True
    },
    {
        "match_ne": "शक्ति बहादुर बस्नेत",
        "name_en_roman": "Shakti Bahadur Basnet",
        "aliases": ["Suresh Singh"],
        "biography": "CPN-MC Deputy General Secretary. Joined Maoist movement 1990. Central Committee member (1998). Minister of Health, Home, Forests, Energy. As Home Minister, initiated 'Police My Friend' campaign. Won Jajarkot-1 (2017) with 32,281 votes.",
        "biography_source": "https://en.wikipedia.org/wiki/Shakti_Bahadur_Basnet",
        "is_notable": True
    },
    {
        "match_ne": "धर्माशिला चापागाई",
        "name_en_roman": "Dharmashila Chapagain",
        "aliases": [],
        "biography": "CPN-MC central member. Won Jhapa-4 in 2008 CA (19,289 votes). State Minister for Health (2011). National judo player. Overcame family opposition for education, worked fields at night before SLC exams. Women's empowerment advocate.",
        "biography_source": "https://en.wikipedia.org/wiki/Dharmashila_Chapagain",
        "is_notable": True
    },
    {
        "match_ne": "नारायण काजी श्रेष्‍ठ",
        "name_en_roman": "Narayan Kaji Shrestha",
        "aliases": ["Prakash"],
        "biography": "Senior Vice-Chairman and Parliamentary Party Leader of CPN (Maoist Centre). Deputy PM and Home Minister (Aug 2011), then Deputy PM and Foreign Minister (Sep 2011). As Home Minister (2023-2024), initiated investigations into Bhutanese refugee scam, Lalita Niwas land grab, and gold smuggling. Underground for 18 years until 2008. Former mathematics lecturer.",
        "biography_source": "https://en.wikipedia.org/wiki/Narayan_Kaji_Shrestha",
        "is_notable": True
    },
    {
        "match_ne": "पुष्प कमल दाहाल प्रचण्ड",
        "name_en_roman": "Pushpa Kamal Dahal",
        "aliases": ["Prachanda", "Pushpa Kamal Dahal Prachanda"],
        "biography": "Chairman of CPN (Maoist-Centre). Prime Minister three times: 2008-09, 2016-17, Dec 2022-July 2024. Led Maoist insurgency launched Feb 13, 1996 that ended 239-year monarchy and killed ~17,000. By 2005 rebels controlled 80% of Nepal. Gave up armed revolt 2006, joined peace process. CPN (Maoist) won 220 seats in 2008 elections.",
        "biography_source": "https://en.wikipedia.org/wiki/Pushpa_Kamal_Dahal",
        "is_notable": True
    },
    {
        "match_ne": "बर्षमान पुन",
        "name_en_roman": "Barshaman Pun",
        "aliases": ["Ananta"],
        "biography": "CPN-MC Deputy General Secretary and MP. One of four PLA deputy commanders. Commanded Holeri police station attack (Feb 13, 1996) that started civil war. Former Minister for Energy, Finance, Peace and Reconstruction. Married to Onsari Gharti Magar (former Speaker).",
        "biography_source": "https://en.wikipedia.org/wiki/Barsaman_Pun",
        "is_notable": True
    },
    {
        "match_ne": "रेणु दाहाल",
        "name_en_roman": "Renu Dahal",
        "aliases": [],
        "biography": "Second daughter of Prachanda. First lady Mayor of Bharatpur (2017, 2022). Resigned Jan 2026 to contest Chitwan-3 on NCP ticket. Joined CPN-MC 1994. Politburo member. General Secretary of All Nepal Women's Association (Revolutionary). Her brother Prakash died of cardiac arrest in 2017.",
        "biography_source": "https://en.wikipedia.org/wiki/Renu_Dahal",
        "is_notable": True
    },
    {
        "match_ne": "टोप बहादुर रायमाझी",
        "name_en_roman": "Top Bahadur Rayamajhi",
        "aliases": [],
        "biography": "Former Deputy PM and Energy Minister (First Oli cabinet). Four consecutive wins from Arghakhanchi. Defected to CPN-UML (Mar 2021). Controversy: Arrest warrant (May 2023) for Bhutanese refugee scam - arrested after 11 days absconding. Suspended from UML Secretary position.",
        "biography_source": "https://en.wikipedia.org/wiki/Top_Bahadur_Rayamajhi",
        "is_notable": True
    },
    {
        "match_ne": "राम कुमारी झाक्री",
        "name_en_roman": "Ram Kumari Jhakri",
        "aliases": [],
        "biography": "First woman president of ANNFSU (UML student wing, 2008). Central figure of 2006 democracy protests. Former Minister of Urban Development. In 2021, helped form CPN (Unified Socialist). Recently announced return to CPN-UML. Controversy: Arrested for comparing President Bhandari with queens.",
        "biography_source": "https://en.wikipedia.org/wiki/Ram_Kumari_Jhakri",
        "is_notable": True
    },
    {
        "match_ne": "लेख राज भट्ट",
        "name_en_roman": "Lekh Raj Bhatta",
        "aliases": ["Lekhraj Bhatta", "Lekh Raj Bhatt"],
        "biography": "CPN-UML Secretary (formerly CPN-MC). Won Kailali-5 in 2008 and 2013 CA. Minister for Labour/Transport (First Dahal cabinet), Industry/Commerce (Second Oli cabinet). Defected to UML (2021), lost parliamentary membership but reappointed minister.",
        "biography_source": "https://en.wikipedia.org/wiki/Lekh_Raj_Bhatta",
        "is_notable": True
    },
    {
        "match_ne": "गौरी शंकर चौधरी",
        "name_en_roman": "Gauri Shankar Chaudhary",
        "aliases": [],
        "biography": "CPN-UML member. Former Agriculture Minister, Labour Minister under PM Oli. MP from Kailali-3. Disqualified from parliament after switching from CPN-MC to UML - among four ministers disqualified for party-switching.",
        "biography_source": "https://en.wikipedia.org/wiki/Gauri_Shankar_Chaudhary",
        "is_notable": True
    },
    # New NCP/Maoist enrichments from research agent
    {
        "match_ne": "बीना मगर",
        "name_en_roman": "Bina Magar",
        "aliases": ["Bina Dahal"],
        "biography": "Federal parliamentarian from CPN (Maoist Centre) representing Kanchanpur-1. Daughter-in-law of party chairman Pushpa Kamal Dahal 'Prachanda'. First elected to parliament in 2074 BS. Member of the 125-member Politburo, one of four family members of Prachanda in party leadership positions.",
        "biography_source": "https://www.setopati.com/election/Parliamentary/287936",
        "is_notable": True
    },
    {
        "match_ne": "गिरिराज  मणी  पोखरेल",
        "name_en_roman": "Giriraj Mani Pokhrel",
        "aliases": ["Girirajmani Pokharel"],
        "biography": "Born Falgun 24, 2015 BS in Kharpa, Khotang. SLC 2030 BS, Bachelor's and Master's in Commerce from Mahendra Morang Adarsh Campus, Biratnagar. Former journalist turned politician. Health Minister twice, Education Minister once. Deputy General Secretary of CPN-MC. Two-time MP from Mahottari.",
        "biography_source": "https://ne.wikipedia.org/wiki/गिरीराजमणि_पोखरेल",
        "is_notable": True
    },
    {
        "match_ne": "लेखनाथ न्यौपाने",
        "name_en_roman": "Lekhnath Neupane",
        "aliases": [],
        "biography": "Born Chaitra 28, 2030 BS in Harmī-9, Gorkha. Master's in Education from TU Kirtipur. ANNFSU (Revolutionary) chairman 2060-2067. Joined CPN (Maoist) in 2049 BS. Rejoined Maoist Centre in 2074 with Badal faction. Known as studious and combative leader. Politburo member.",
        "biography_source": "https://ne.wikipedia.org/wiki/लेखनाथ_न्यौपाने",
        "is_notable": True
    },
    {
        "match_ne": "मातृका प्रसाद यादव",
        "name_en_roman": "Matrika Prasad Yadav",
        "aliases": ["Matrika Yadav"],
        "biography": "Born 1958 in Dhanusha. I.Ed from Tribhuvan University. Joined CPN (Fourth Convention) in 2034 BS, twice ANNFSU chairman at Siraha Campus. Joined Prachanda's Unity Centre 2050/51. CA member 2064 via PR. Former Industry, Commerce and Supply Minister. Won Dhanusha-1 with 26,414 votes.",
        "biography_source": "https://ne.wikipedia.org/wiki/मातृकाप्रसाद_यादव",
        "is_notable": True
    },
    {
        "match_ne": "त्रिलोचन भट्ट",
        "name_en_roman": "Trilochan Bhatt",
        "aliases": [],
        "biography": "Born Jestha 7, 2026 BS in Phaledi, Doti. Left school after class 8 due to poverty, worked as watchman at Japanese company in Mumbai. Started politics 2047 BS. Doti district secretary 2062, chairman since 2071. Politburo member. Chief Minister of Sudurpashchim Province from Falgun 3, 2074.",
        "biography_source": "https://ne.wikipedia.org/wiki/त्रिलोचन_भट्ट",
        "is_notable": True
    },
    {
        "match_ne": "विशाल खड्का",
        "name_en_roman": "Bishal Khadka",
        "aliases": [],
        "biography": "CPN-MC leader, Forest and Environment Minister of Bagmati Province. Full-time Maoist since 2054 BS during People's War, faced 18 cases at age 16. Won Dolakha-1(ka) in 2074 with 28,350 votes. Former personal secretary and bodyguard commander for Prachanda. Central committee and Politburo member.",
        "biography_source": "https://nepalmuhar.com/2022/08/23/politics/10076/",
        "is_notable": True
    },
    {
        "match_ne": "सुदर्शन वराल",
        "name_en_roman": "Sudarshan Baral",
        "aliases": ["Sudarshan Boral"],
        "biography": "CPN-MC Lumbini Province chairman. Unanimously elected at first provincial convention in Bhalubang, Dang (Mangsir 2078). Former Social Development Minister under Shankar Pokharel's Lumbini Province government. Close to Maoist leader Barshaman Pun.",
        "biography_source": "https://ekantipur.com/pradesh-5/2021/12/16/163963898305833450.html",
        "is_notable": True
    },
    {
        "match_ne": "राम चन्द्र झा",
        "name_en_roman": "Ramchandra Jha",
        "aliases": [],
        "biography": "Former minister who joined CPN (Maoist) from UML. Became alternate central member at UML's 6th convention, Janakpur in-charge, central member at 7th, Politburo member after 8th convention. Former Local Development Minister. Later joined Baburam's Naya Shakti, returned to MC, then left for CPN (Unified Socialist).",
        "biography_source": "https://www.ratopati.com/story/206182/2021/11/10/ramchandra-jha",
        "is_notable": True
    },
    {
        "match_ne": "युवराज दुलाल",
        "name_en_roman": "Yuvraj Dulal",
        "aliases": ["Sharad", "Commander Sharad"],
        "biography": "Born Falgun 7, 2039 BS in Sindhupalchok. Nom de guerre 'Sharad'. Skilled PLA commander during People's War. Personal secretary and bodyguard commander for Prachanda. Commanded Thankot Front in Kathmandu. Won Sindhupalchok-2(ka) with 19,696 votes. Social Development Minister of Province 3. Politburo member.",
        "biography_source": "https://www.abcnepal.tv/posts/13770",
        "is_notable": True
    },
    {
        "match_ne": "गोपाल शर्मा",
        "name_en_roman": "Gopal Sharma",
        "aliases": [],
        "biography": "CPN-MC Chief Whip of Karnali Province Assembly. Represents Rukum West. Former Finance Minister under CM Mahendra Bahadur Shahi's Karnali Province government. Member of 125-member Politburo.",
        "biography_source": "https://www.setopati.com/politics/281182",
        "is_notable": True
    },
    {
        "match_ne": "बृजेश कुमार गुप्‍त",
        "name_en_roman": "Brijesh Kumar Gupta",
        "aliases": [],
        "biography": "Won Constituent Assembly from Kapilvastu-3 in 2008 and 2013 representing People's Progressive Party. Born in Thulo Bargadawa village (now Kapilvastu Municipality-5). Now contesting from CPN (Maoist Centre).",
        "biography_source": "https://en.wikipedia.org/wiki/Brijesh_Kumar_Gupta",
        "is_notable": True
    },
]

# ============ JSP ENRICHMENTS ============
JSP_ENRICHMENTS = [
    {
        "match_ne": "हृदयेश त्रिपाठी",
        "name_en_roman": "Hridayesh Tripathi",
        "aliases": ["Hridayesh Tripathy"],
        "biography": "Veteran Madheshi leader. Three-time MP from Sarlahi. Former Minister of Health and Law. Co-founded TMLP with Mahantha Thakur during 2007 Madhesh movement. Split from NC during Madhesh agitation.",
        "biography_source": "https://en.wikipedia.org/wiki/Hridayesh_Tripathi",
        "is_notable": True
    },
    {
        "match_ne": "राज किशोर यादव",
        "name_en_roman": "Raj Kishor Yadav",
        "aliases": ["Rajkishor Yadav"],
        "biography": "JSP Vice President. Former Industry Minister - shortest ministerial tenure in Nepal's history at just 12 days due to government collapse (2022). Former Deputy Speaker of House of Representatives.",
        "biography_source": "https://kathmandupost.com/politics/2024/08/26/janata-samajbadi-party-nepal-picks-office-bearers",
        "is_notable": True
    },
    {
        "match_ne": "दीपक कार्की",
        "name_en_roman": "Dipak Karki",
        "aliases": ["Deepak Karki"],
        "biography": "Current MP from Dhanusha-1. State Minister for Forests and Health under PM Prachanda. Resigned alongside Upendra Yadav when JSP quit government (May 2024).",
        "biography_source": "https://en.wikipedia.org/wiki/Dipak_Karki_(Dhanusha_politician)",
        "is_notable": True
    },
    {
        "match_ne": "नवलकिशोर साह सुडी",
        "name_en_roman": "Nawal Kishore Sah Sudi",
        "aliases": ["Nawal Kishor Sah Sundi"],
        "biography": "Current Minister for Women, Children and Senior Citizens (July 2024). Born Sep 27, 1947. Active in politics since 1990. MP from Saptari-1. Former Minister for Forestry/Environment and Social Development in Madhesh Province.",
        "biography_source": "https://en.wikipedia.org/wiki/Nawal_Kishor_Sah",
        "is_notable": True
    },
    {
        "match_ne": "लालबाबु राउत",
        "name_en_roman": "Lalbabu Raut",
        "aliases": ["Mohammad Lalbabu Raut"],
        "biography": "First Chief Minister of Madhesh Province - only provincial CM to serve full 5-year term (2018-2023). JSP General Secretary. Former teacher at Thakur-ram Multiple Campus. Controversy: CIAA cases on Swachatta Abhiyan, Janaki Mandir.",
        "biography_source": "https://en.wikipedia.org/wiki/Lalbabu_Raut",
        "is_notable": True
    },
    {
        "match_ne": "रामअशिष राय यादव",
        "name_en_roman": "Ram Ashish Yadav",
        "aliases": ["Ramashish Ray Yadav"],
        "biography": "Speaker of Madhesh Provincial Assembly (elected Dec 2025 with 72 of 96 votes). Former JSP-N Chief Whip. Provincial Assembly member from Dhanusha. JSP candidate for Rautahat-2.",
        "biography_source": "https://kathmandupost.com/national/2025/12/21/ram-ashish-yadav-elected-speaker-of-madhesh-province-assembly",
        "is_notable": True
    },
    {
        "match_ne": "बिरेन्द्र प्रसाद महतो",
        "name_en_roman": "Birendra Prasad Mahato",
        "aliases": ["Dr. Birendra Prasad Mahato"],
        "biography": "MP from Siraha-4 (2022, 24,102 votes). Former Minister for Forests and Environment. Member of 2nd CA from MJAF party list. Born July 5, 1969, Siraha.",
        "biography_source": "https://en.wikipedia.org/wiki/Birendra_Prasad_Mahato",
        "is_notable": True
    },
    {
        "match_ne": "सुरेन्‍द्र कुमार यादव",
        "name_en_roman": "Surendra Kumar Yadav",
        "aliases": ["Dr. Surendra Kumar Yadav"],
        "biography": "Former MP from Mahottari-4 (2017, 18,353 votes). Former State Minister for Health. Controversy: Allegedly abducted from Janakpur (2020) over PM Oli's ordinances - police refused to register case.",
        "biography_source": "https://kathmandupost.com/national/2020/04/27/nepal-police-s-refusal-to-register-surendra-yadav-abduction-case-raises-questions-about-its-neutrality",
        "is_notable": True
    },
    {
        "match_ne": "अशोक कुमार यादव",
        "name_en_roman": "Ashok Kumar Yadav",
        "aliases": ["Ashok Yadav"],
        "biography": "JSP Madhesh Province Chair. Provincial Assembly member from Sarlahi. Controversy: Arrest warrant (2025) for vandalism and threatening police; currently absconding, suspected fled to India.",
        "biography_source": "https://myrepublica.nagariknetwork.com/news/special-police-team-deployed-to-arrest-jsp-leader-ashok-yadav-likely-hiding-63-28.html",
        "is_notable": True
    },
    {
        "match_ne": "रामेश्‍वर राय यादव",
        "name_en_roman": "Rameshwar Raya Yadav",
        "aliases": ["Rameshwor Raya Yadav"],
        "biography": "Former Minister of Labour, Employment and Social Security. Former CPN-MC central committee member who switched to JSP. Welcomed into JSP by Upendra Yadav. Has contested from Sarlahi since 2008.",
        "biography_source": "https://en.wikipedia.org/wiki/Rameshwar_Raya_Yadav",
        "is_notable": True
    },
    {
        "match_ne": "गोविन्द चौधरी",
        "name_en_roman": "Govinda Chaudhary",
        "aliases": ["Govind Chaudhary"],
        "biography": "JSP Vice-Chairman from Rautahat. Appointed by Chairman Upendra Yadav in Aug 2024. JSP candidate for Rautahat constituency in 2026 elections.",
        "biography_source": "https://kathmandupost.com/politics/2024/08/26/janata-samajbadi-party-nepal-picks-office-bearers",
        "is_notable": True
    },
    {
        "match_ne": "शिवलाल थापा मगर",
        "name_en_roman": "Shivalal Thapa Magar",
        "aliases": ["Shiva Lal Thapa Magar"],
        "biography": "JSP Vice-Chairman. In-charge of Gandaki Province Committee. Presided over reconstitution of Gandaki Provincial Committee in Pokhara. Was among 23 candidates for five vice chairman positions.",
        "biography_source": "https://kathmandupost.com/politics/2024/08/26/janata-samajbadi-party-nepal-picks-office-bearers",
        "is_notable": True
    },
    {
        "match_ne": "बिद्युत बज्राचार्य",
        "name_en_roman": "Bidyut Bajracharya",
        "aliases": [],
        "biography": "JSP Vice-Chairman. Advocate for LGBTQIA+ inclusion - stated JSP has always provided opportunities for LGBTQIA+ people. Part of JSP Nepal secretariat. Appointed by Chairman Upendra Yadav Aug 2024.",
        "biography_source": "https://kathmandupost.com/politics/2024/08/26/janata-samajbadi-party-nepal-picks-office-bearers",
        "is_notable": True
    },
    {
        "match_ne": "उमेश कुमार यादव",
        "name_en_roman": "Umesh Kumar Yadav",
        "aliases": ["Umesh Prasad Yadav"],
        "biography": "Former Minister of Irrigation under PM Prachanda. Recently joined JSP from CPN-MC (Jan 2026). Won Saptari-3 in 2013 CA. JSP candidate for Saptari-2 in 2026 after Upendra Yadav moved to Saptari-3.",
        "biography_source": "https://kathmandupost.com/national/2026/01/06/umesh-yadav-joins-jsp-n",
        "is_notable": True
    },
]

# ============ RPP ENRICHMENTS ============
RPP_ENRICHMENTS = [
    {
        "match_ne": "रविन्द्र मिश्र",
        "name_en_roman": "Rabindra Mishra",
        "aliases": ["Ravindra Mishra"],
        "biography": "RPP Senior Vice-chairman. Former BBC Nepali editor-in-chief. Founded Sajha Party. President of Bibeksheel Sajha (2017-2022). Joined RPP Sep 2022. Founder of Help Nepal Network (14 countries). 'Nation above Notion' advocate for Hindu state/monarchy.",
        "biography_source": "https://en.wikipedia.org/wiki/Rabindra_Mishra",
        "is_notable": True
    },
    {
        "match_ne": "बिक्रम पान्डे",
        "name_en_roman": "Bikram Pandey",
        "aliases": ["Bikram Pandey Chitwan"],
        "biography": "RPP Vice President. Construction contractor. CA member (2013) from Chitwan-5. Won Chitwan-3 (2022, 35,055 votes). Controversy: CIAA filed Rs 8.5 billion Sikta Irrigation Project corruption case (Dec 2018).",
        "biography_source": "https://en.wikipedia.org/wiki/Bikram_Pandey",
        "is_notable": True
    },
    {
        "match_ne": "हेम जङग गुरुङ",
        "name_en_roman": "Hem Jung Gurung",
        "aliases": ["Hem Jang Gurung"],
        "biography": "RPP Vice-Chairman. Part of Chairman Lingden's faction alongside Vice-Chairmen Roshan Karki, Dhruba Bahadur Pradhan, and Buddhiman Tamang. Contesting Kaski-2.",
        "biography_source": "https://english.nepalnews.com/s/feature/perpetually-divided-royalists/",
        "is_notable": True
    },
    {
        "match_ne": "गौरब बोहरा",
        "name_en_roman": "Gaurab Bohara",
        "aliases": ["Gaurav Bohara"],
        "biography": "Son of late RPP leader Deepak Bohara who represented Rupandehi-3 in HoR. Father served in National Panchayat and held multiple ministerial positions. Became active in politics after father's death (Apr 1, 2025). RPP aspirant for Rupandehi-3 by-election.",
        "biography_source": "https://en.himalpress.com/deepak-bohara-rupandehis-trusted-leader-from-panchayat-to-republic/",
        "is_notable": True
    },
]

# ============ SHRAM SANSKRITI ENRICHMENTS ============
SHRAM_ENRICHMENTS = [
    {
        "match_ne": "समिर तामाङ्ग",
        "name_en_roman": "Samir Tamang",
        "aliases": ["Samir Tamangg"],
        "biography": "Shram Sanskriti Party Joint General Secretary and central member. Contesting high-profile Jhapa-5 against KP Oli (UML) and Balen Shah (RSP). Harka Sampang stated 'Samir Tamang is enough to defeat Oli and Balendra.'",
        "biography_source": "https://ekantipur.com/politics/2026/01/17/en/samir-tamang-candidate-of-shram-sanskriti-party-in-jhapa-5-says-hark-we-will-defeat-both-oli-and-balen-37-15.html",
        "is_notable": True
    },
    {
        "match_ne": "उद्धव कुमार राई",
        "name_en_roman": "Uddhav Kumar Rai",
        "aliases": ["Uddhaw Kumar Rae"],
        "biography": "Shram Sanskriti candidate for Okhaldhunga. Personally received ticket from Harka Sampang in Dharan - breaking traditional pattern of Kathmandu-centralized party operations.",
        "biography_source": "https://kathmandupost.com/politics/2026/01/18/dharan-rallies-to-harka-sampang-s-beat-as-rivals-stay-quiet",
        "is_notable": True
    },
    {
        "match_ne": "विनोद नेम्बाङ्ग लिम्बु",
        "name_en_roman": "Binod Nembang Limbu",
        "aliases": ["Vinod Nembang Limbu"],
        "biography": "Shram Sanskriti candidate for Ilam-1, historically a stronghold of former PM Jhalanath Khanal. Competing against 12 candidates from various parties.",
        "biography_source": "https://risingnepaldaily.com/news/75023",
        "is_notable": True
    },
    {
        "match_ne": "त्रिभुवन खंग",
        "name_en_roman": "Tribhuvan Khang",
        "aliases": ["Tribhuwan Khmg"],
        "biography": "Shram Sanskriti candidate for Saptari-2, a highly contested seat previously fought between Janamat President Dr. CK Raut and JSP Chair Upendra Yadav.",
        "biography_source": "https://thehimalayantimes.com/nepal/saptari-2-looks-for-new-representative-as-former-comrades-clash",
        "is_notable": True
    },
]


def main():
    """Apply all enrichments to election data."""
    script_dir = Path(__file__).parent.resolve()
    data_path = script_dir / "../../frontend/public/data/election-results-2082.json"

    print(f"Loading {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Combine all enrichments
    all_enrichments = (
        UML_ENRICHMENTS +
        NC_ENRICHMENTS +
        RSP_ENRICHMENTS +
        MAOIST_ENRICHMENTS +
        JSP_ENRICHMENTS +
        RPP_ENRICHMENTS +
        SHRAM_ENRICHMENTS
    )

    # Create lookup by Nepali name
    enrichment_lookup = {}
    for e in all_enrichments:
        match_ne = e.get("match_ne", "")
        if match_ne:
            enrichment_lookup[match_ne] = e

    print(f"Total enrichments available: {len(enrichment_lookup)}")

    # Apply enrichments
    updated = 0
    for constituency in data.get("results", []):
        for candidate in constituency.get("candidates", []):
            name_ne = candidate.get("name_ne", "") or candidate.get("name_en", "")

            if name_ne in enrichment_lookup:
                enrichment = enrichment_lookup[name_ne]

                # Update fields
                if enrichment.get("name_en_roman"):
                    candidate["name_en_roman"] = enrichment["name_en_roman"]

                # Merge aliases
                existing_aliases = set(candidate.get("aliases", []))
                new_aliases = enrichment.get("aliases", [])
                existing_aliases.update(new_aliases)
                candidate["aliases"] = list(existing_aliases)

                if enrichment.get("biography"):
                    candidate["biography"] = enrichment["biography"]

                if enrichment.get("biography_source"):
                    candidate["biography_source"] = enrichment["biography_source"]

                if enrichment.get("is_notable") is not None:
                    candidate["is_notable"] = enrichment["is_notable"]

                updated += 1
                print(f"  Updated: {enrichment['name_en_roman']}")

    # Save
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {updated} candidates with detailed biographies")


if __name__ == "__main__":
    main()
