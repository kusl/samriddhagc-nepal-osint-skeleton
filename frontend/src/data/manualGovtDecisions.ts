export interface ManualGovtDecision {
  id: string
  title: string
  ministry: string
  office: string
  decision: string
  whyItMatters: string
  sourceName: string
  sourceUrl: string
  publishedAt: string
  evidenceNote: string
}

export const manualGovtDecisions: ManualGovtDecision[] = [
  {
    id: 'cabinet-karki-implementation',
    title: 'Cabinet moves to implement the Karki Commission report',
    ministry: 'Office of the Prime Minister and Council of Ministers',
    office: 'Cabinet / OPMCM',
    decision:
      'The first cabinet meeting of the Shah government decided to immediately implement the Gauri Bahadur Karki commission report on the September 2025 Gen Z violence, while separating security-agency recommendations for further study.',
    whyItMatters:
      'This is the new government’s first major accountability decision and changes the legal and political exposure of former political and administrative officials named in the report.',
    sourceName: 'The Rising Nepal',
    sourceUrl: 'https://risingnepaldaily.com/news/77845',
    publishedAt: '2026-03-27T12:41:45Z',
    evidenceNote:
      'The Rising Nepal reported that the first cabinet meeting decided to implement the report immediately, assigned Sashmit Pokharel as government spokesperson, and said a study committee would be formed for recommendations concerning security officials.',
  },
  {
    id: 'cabinet-karki-security-study',
    title: 'Government splits implementation path for civilian and security recommendations',
    ministry: 'Office of the Prime Minister and Council of Ministers',
    office: 'Cabinet / OPMCM',
    decision:
      'The government decided that recommendations involving security agencies would go through a study committee, while non-security recommendations would move directly into implementation channels.',
    whyItMatters:
      'This creates a visible two-track execution model: immediate movement on civilian accountability questions, but a slower review path for police and other security institutions.',
    sourceName: 'OnlineKhabar',
    sourceUrl: 'https://www.onlinekhabar.com/2026/03/1899370/decision-to-implement-karki-commission-report-against-whom-will-action-be-taken',
    publishedAt: '2026-03-27T15:25:38Z',
    evidenceNote:
      'OnlineKhabar reported spokesperson Sashmit Pokharel saying a committee would study the security side while other recommendations would be sent forward directly for implementation.',
  },
  {
    id: 'home-high-alert',
    title: 'Home administration places security forces on high alert after the Karki decision',
    ministry: 'Ministry of Home Affairs',
    office: 'Home Ministry',
    decision:
      'Following the cabinet decision on the Karki report, the home administration directed police and other security units into high-alert and standby posture, including Kathmandu Valley readiness measures.',
    whyItMatters:
      'This is the government’s first operational security response to anticipated backlash over Karki-report implementation and signals concern about immediate protest or retaliation risk.',
    sourceName: 'Khabarhub Nepali',
    sourceUrl: 'https://khabarhub.com/2026/27/947123/',
    publishedAt: '2026-03-27T16:46:41Z',
    evidenceNote:
      'Khabarhub reported that after the cabinet decided to carry the Karki report into implementation, the Home Ministry instructed security personnel to remain on high alert and Nepal Police relayed readiness instructions to valley units.',
  },
  {
    id: 'home-one-stop-service',
    title: 'Home Minister orders a one-stop public service model',
    ministry: 'Ministry of Home Affairs',
    office: 'Home Ministry',
    decision:
      'Home Minister Sudhan Gurung decided to conduct ministry work through a one-stop service system and instructed officials to reduce friction in public service delivery.',
    whyItMatters:
      'This is a concrete administrative reform measure rather than a speech headline: it defines how the ministry says it will process citizen-facing work and frames governance reform as operational, not rhetorical.',
    sourceName: 'My Republica',
    sourceUrl: 'https://myrepublica.nagariknetwork.com/news/home-minister-gurung-decides-to-implement-one-stop-service-system-22-88.html',
    publishedAt: '2026-03-27T12:51:07Z',
    evidenceNote:
      'My Republica reported that Gurung decided all official work would be carried out through a one-stop service system after assuming office at Singha Durbar.',
  },
  {
    id: 'finance-legal-reform',
    title: 'Finance Ministry starts repeal process for 15 laws and orders an economic reform roadmap',
    ministry: 'Ministry of Finance',
    office: 'Finance Ministry',
    decision:
      'Finance Minister Swarnim Wagle launched a legal and administrative reform package that includes starting the repeal process for roughly 15 outdated laws, moving to dissolve the Revenue Investigation Department, and ordering an economic legal reform roadmap.',
    whyItMatters:
      'This is one of the clearest policy-action bundles in the first day of the new government and provides a trackable reform benchmark beyond messaging.',
    sourceName: 'Nagarik News',
    sourceUrl: 'https://nagariknews.nagariknetwork.com/economy/finance-minister-wagle-launches-policy-reforms-process-of-repealing-15-acts-begins-39-43.html',
    publishedAt: '2026-03-27T15:07:10Z',
    evidenceNote:
      'Nagarik reported that Wagle made three early decisions on assuming office, including starting repeal of about 15 laws, moving against the Revenue Investigation Department, and ordering a wider economic legal reform roadmap.',
  },
  {
    id: 'infrastructure-stop-extensions',
    title: 'Infrastructure minister orders an end to routine deadline extensions',
    ministry: 'Ministry of Physical Infrastructure, Transport and Urban Development',
    office: 'Infrastructure Ministry',
    decision:
      'Minister Sunil Lamsal instructed staff to stop normalizing deadline extensions and to tighten anti-corruption discipline in project execution and ministry work.',
    whyItMatters:
      'For a ministry tied to procurement and project overruns, ending extension culture is a tangible governance decision with measurable downstream effects.',
    sourceName: 'Kantipur TV',
    sourceUrl: 'https://www.kantipurtv.com/news/2026/03/27/1774622160.html',
    publishedAt: '2026-03-27T15:26:31Z',
    evidenceNote:
      'Kantipur TV reported Lamsal’s instruction that work should proceed without deadline extensions and with stronger anti-corruption discipline.',
  },
  {
    id: 'pm-bureaucracy-speed',
    title: 'Prime Minister instructs ministers and secretaries to cut delay and work in favor of the public',
    ministry: 'Office of the Prime Minister and Council of Ministers',
    office: 'Prime Minister’s Office',
    decision:
      'After assuming office in Singha Durbar, Prime Minister Balendra Shah instructed ministers, secretaries, and staff that bureaucratic delay would not be tolerated and that government work must align with the public mandate.',
    whyItMatters:
      'This is a cross-government operating instruction from the prime minister and sets the tone for how ministries are expected to behave under the new coalition.',
    sourceName: 'OnlineKhabar',
    sourceUrl: 'https://www.onlinekhabar.com/2026/03/1899396/prime-minister-balens-instructions-to-employees-keep-the-spirit-of-the-government-there-will-be-no-letup',
    publishedAt: '2026-03-27T13:08:50Z',
    evidenceNote:
      'OnlineKhabar reported Shah telling officials that delays could not be justified by process excuses and that the government’s spirit needed to be reflected in day-to-day work.',
  },
  {
    id: 'govt-spokesperson-assigned',
    title: 'Government assigns Sashmit Pokharel as official spokesperson',
    ministry: 'Office of the Prime Minister and Council of Ministers',
    office: 'Cabinet / OPMCM',
    decision:
      'The cabinet assigned Education Minister Sashmit Pokharel to serve as government spokesperson.',
    whyItMatters:
      'This is a functional communications decision that affects how cabinet actions will be explained publicly and which ministry is speaking for the government line.',
    sourceName: 'The Rising Nepal',
    sourceUrl: 'https://risingnepaldaily.com/news/77845',
    publishedAt: '2026-03-27T12:41:45Z',
    evidenceNote:
      'The Rising Nepal reported that the cabinet designated Pokharel as the spokesperson immediately after the first cabinet meeting.',
  },
]
