/**
 * Hook for fetching government announcements for map display.
 * Places announcements based on the issuing office:
 * - DAO (District Administration Office) announcements are placed at the district centroid
 * - Central ministries/commissions default to Singha Durbar, Kathmandu
 */

import { useQuery } from '@tanstack/react-query';
import { getAnnouncementSummary } from '../api/announcements';
import type { Announcement } from '../types/announcement';
import { DISTRICTS, normalizeDistrictName } from '../data/districts';
import { formatBsToAd } from '../lib/nepaliDate';

export interface MapAnnouncement {
  id: string;
  title: string;
  source: string;
  source_name: string;
  category: string;
  date_bs: string | null;
  date_ad: string | null;
  url: string;
  is_read: boolean;
  is_important: boolean;
  has_attachments: boolean;
  /** Stable timestamp used for sorting and relative time fallbacks */
  timestamp: string;
  /** User-facing date label for official announcement metadata */
  time_label: string;
  /** True when the item has no official date and is only recent because it was fetched recently */
  is_fetched_only: boolean;
  /** Best-effort district name for filtering/labeling */
  district: string;
  location_confidence: 'district' | 'province_capital' | 'central' | 'unknown';
  // GeoJSON coordinates for marker placement: [lng, lat]
  coordinates: [number, number];
}

// Singha Durbar coordinates (Prime Minister's Office & key ministries)
const SINGHA_DURBAR_COORDS: [number, number] = [85.3206, 27.6989];

const DISTRICT_BY_NORMALIZED = new Map(
  DISTRICTS.map(d => [normalizeDistrictName(d.name), d] as const)
);

const NEPALI_DISTRICT_ALIASES: Record<string, string> = {
  'ताप्लेजुङ': 'Taplejung',
  'पाँचथर': 'Panchthar',
  'इलाम': 'Ilam',
  'झापा': 'Jhapa',
  'मोरङ': 'Morang',
  'सुनसरी': 'Sunsari',
  'धनकुटा': 'Dhankuta',
  'तेह्रथुम': 'Terhathum',
  'संखुवासभा': 'Sankhuwasabha',
  'भोजपुर': 'Bhojpur',
  'सोलुखुम्बु': 'Solukhumbu',
  'ओखलढुङ्गा': 'Okhaldhunga',
  'खोटाङ': 'Khotang',
  'उदयपुर': 'Udayapur',
  'सप्तरी': 'Saptari',
  'सिराहा': 'Siraha',
  'धनुषा': 'Dhanusha',
  'महोत्तरी': 'Mahottari',
  'सर्लाही': 'Sarlahi',
  'रौतहट': 'Rautahat',
  'बारा': 'Bara',
  'पर्सा': 'Parsa',
  'डोलखा': 'Dolakha',
  'सिन्धुपाल्चोक': 'Sindhupalchok',
  'सिन्धुपालचोक': 'Sindhupalchok',
  'रसुवा': 'Rasuwa',
  'धादिङ': 'Dhading',
  'नुवाकोट': 'Nuwakot',
  'काठमाडौं': 'Kathmandu',
  'काठमाण्डौ': 'Kathmandu',
  'काठमाण्डू': 'Kathmandu',
  'भक्तपुर': 'Bhaktapur',
  'ललितपुर': 'Lalitpur',
  'काभ्रे': 'Kavrepalanchok',
  'कावरे': 'Kavrepalanchok',
  'काभ्रेपलान्चोक': 'Kavrepalanchok',
  'रामेछाप': 'Ramechhap',
  'सिन्धुली': 'Sindhuli',
  'मकवानपुर': 'Makwanpur',
  'चितवन': 'Chitwan',
  'गोरखा': 'Gorkha',
  'लमजुङ': 'Lamjung',
  'तनहुँ': 'Tanahu',
  'कास्की': 'Kaski',
  'मनाङ': 'Manang',
  'मुस्ताङ': 'Mustang',
  'म्याग्दी': 'Myagdi',
  'पर्वत': 'Parbat',
  'बागलुङ': 'Baglung',
  'स्याङ्जा': 'Syangja',
  'नवलपुर': 'Nawalparasi East',
  'नवलपरासी': 'Nawalparasi West',
  'रुपन्देही': 'Rupandehi',
  'कपिलवस्तु': 'Kapilvastu',
  'अर्घाखाँची': 'Arghakhanchi',
  'अर्घाखांची': 'Arghakhanchi',
  'गुल्मी': 'Gulmi',
  'पाल्पा': 'Palpa',
  'दाङ': 'Dang',
  'प्युठान': 'Pyuthan',
  'रोल्पा': 'Rolpa',
  'रुकुम पूर्व': 'Rukum East',
  'रुकुम पश्चिम': 'Rukum West',
  'बाँके': 'Banke',
  'बर्दिया': 'Bardiya',
  'डोल्पा': 'Dolpa',
  'मुगु': 'Mugu',
  'हुम्ला': 'Humla',
  'जुम्ला': 'Jumla',
  'कालिकोट': 'Kalikot',
  'दैलेख': 'Dailekh',
  'जाजरकोट': 'Jajarkot',
  'सल्यान': 'Salyan',
  'सुर्खेत': 'Surkhet',
  'बाजुरा': 'Bajura',
  'बझाङ': 'Bajhang',
  'अछाम': 'Achham',
  'डोटी': 'Doti',
  'कैलाली': 'Kailali',
  'कञ्चनपुर': 'Kanchanpur',
  'दडेलधुरा': 'Dadeldhura',
  'बैतडी': 'Baitadi',
  'दार्चुला': 'Darchula',
};

function districtToCoordinates(districtName: string): [number, number] | null {
  const info = DISTRICT_BY_NORMALIZED.get(normalizeDistrictName(districtName));
  if (!info) return null;
  // GeoJSON style: [lng, lat]
  return [info.lng, info.lat];
}

function findDistrictInText(value: string | null | undefined): string | null {
  if (!value) return null;
  const text = value.trim();
  if (!text) return null;

  const lowered = text.toLowerCase();
  for (const district of DISTRICTS) {
    const englishPattern = new RegExp(`\\b${normalizeDistrictName(district.name).replace(/\s+/g, '\\s+')}\\b`, 'i');
    if (englishPattern.test(lowered)) {
      return district.name;
    }
  }

  for (const [alias, district] of Object.entries(NEPALI_DISTRICT_ALIASES)) {
    if (text.includes(alias)) {
      return district;
    }
  }

  return null;
}

// Provincial source domains → province capital district
const PROVINCE_CAPITALS: Record<string, string> = {
  'koshi': 'Morang',
  'madhesh': 'Parsa',
  'bagmati': 'Kathmandu',
  'gandaki': 'Kaski',
  'lumbini': 'Rupandehi',
  'karnali': 'Surkhet',
  'sudurpashchim': 'Kailali',
};

function normalizeAnnouncementText(value: string | null | undefined): string {
  if (!value) return '';
  return value
    .replace(/[०१२३४५६७८९]/g, (digit) => String('०१२३४५६७८९'.indexOf(digit)))
    .replace(/[–—]/g, '-')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function isGenericAnnouncementTitle(announcement: Announcement): boolean {
  const title = normalizeAnnouncementText(announcement.title);
  const sourceName = normalizeAnnouncementText(announcement.source_name);

  if (!title) return true;
  if (sourceName && title === sourceName) return true;

  const genericExact = new Set([
    'notice',
    'notices',
    'सूचना',
    'सूचना। सूचना।। सूचना।।।',
    'प्रेस विज्ञप्ति',
    'विज्ञप्ति',
    'नेपाल सरकारको पोर्टल',
    'कोशी प्रदेश सरकारको पोर्टल',
    'राष्ट्रिय योजना आयोग',
    'लोक सेवा आयोग',
    'राष्ट्रिय परिचयपत्र तथा पञ्‍जीकरण विभाग',
    'श्रम संसार प्रणाली',
  ].map(normalizeAnnouncementText));

  if (genericExact.has(title)) return true;

  const lowSignalPatterns = [
    /को पोर्टल$/,
    / प्रणाली$/,
    / विभाग$/,
    / मन्त्रालय$/,
    / आयोग$/,
    / कार्यालय$/,
    / कृषि बजार/,
  ];

  return title.length <= 40 && lowSignalPatterns.some(pattern => pattern.test(title));
}

function isCentralSource(announcement: Announcement): boolean {
  const source = normalizeAnnouncementText(announcement.source);
  const sourceName = normalizeAnnouncementText(announcement.source_name);
  const title = normalizeAnnouncementText(announcement.title);

  if (source.includes('opmcm') || source.includes('moha') || source.includes('mofa') || source.includes('election.gov.np')) {
    return true;
  }

  const centralMarkers = ['मन्त्रालय', 'राष्ट्रिय', 'संघीय', 'आयोग', 'विभाग', 'नेपाल सरकार'];
  return centralMarkers.some(marker =>
    announcement.source_name.includes(marker) || announcement.title.includes(marker)
  ) && !findDistrictInText(title) && !findDistrictInText(sourceName);
}

function inferAnnouncementPlacement(announcement: Announcement): {
  district: string;
  coordinates: [number, number];
  confidence: 'district' | 'province_capital' | 'central' | 'unknown';
} | null {
  // DAO sources are stored as "DAO <District>"
  const m = announcement.source_name.match(/^DAO\s+(.+)$/i);
  if (m?.[1]) {
    const district = m[1].trim();
    const coordinates = districtToCoordinates(district);
    if (coordinates) return { district, coordinates, confidence: 'district' };
  }

  // Fallback: some DAO sources are encoded in the source domain (dao{district}.moha.gov.np)
  const src = (announcement.source || '').toLowerCase();
  const m2 = src.match(/^dao([a-z]+)\.moha\.gov\.np$/);
  if (m2?.[1]) {
    const key = m2[1];
    for (const d of DISTRICTS) {
      const normalized = normalizeDistrictName(d.name).replace(/\s+/g, '');
      if (normalized === key) {
        return { district: d.name, coordinates: [d.lng, d.lat], confidence: 'district' };
      }
    }
  }

  // Provincial government sources → map to province capital
  const srcName = announcement.source_name.toLowerCase();
  for (const [province, capital] of Object.entries(PROVINCE_CAPITALS)) {
    if (srcName.includes(province) || src.includes(province)) {
      const coordinates = districtToCoordinates(capital);
      if (coordinates) return { district: capital, coordinates, confidence: 'province_capital' };
    }
  }

  // District offices often carry the district only in the title or office label
  const titleDistrict = findDistrictInText(announcement.title);
  if (titleDistrict) {
    const coordinates = districtToCoordinates(titleDistrict);
    if (coordinates) return { district: titleDistrict, coordinates, confidence: 'district' };
  }

  const sourceNameDistrict = findDistrictInText(announcement.source_name);
  if (sourceNameDistrict) {
    const coordinates = districtToCoordinates(sourceNameDistrict);
    if (coordinates) return { district: sourceNameDistrict, coordinates, confidence: 'district' };
  }

  const sourceDistrict = findDistrictInText(announcement.source);
  if (sourceDistrict) {
    const coordinates = districtToCoordinates(sourceDistrict);
    if (coordinates) return { district: sourceDistrict, coordinates, confidence: 'district' };
  }

  if (isCentralSource(announcement)) {
    return { district: 'Kathmandu', coordinates: SINGHA_DURBAR_COORDS, confidence: 'central' };
  }

  return null;
}

function formatAdDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) {
    return dateStr;
  }

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) {
    return 'Recent';
  }

  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60000);

  if (minutes < 1) return 'Now';
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}

function getAnnouncementTimestamp(announcement: Announcement): string {
  return (
    announcement.date_ad ??
    announcement.published_at ??
    announcement.fetched_at ??
    announcement.created_at
  );
}

function isFetchedOnlyAnnouncement(announcement: Announcement): boolean {
  return !announcement.date_ad && !announcement.date_bs && !announcement.published_at;
}

function getAnnouncementTimeLabel(announcement: Announcement): string {
  if (announcement.date_ad) {
    return formatAdDate(announcement.date_ad);
  }

  if (announcement.date_bs) {
    return formatBsToAd(announcement.date_bs);
  }

  if (announcement.published_at) {
    return formatRelativeTime(announcement.published_at);
  }

  if (announcement.fetched_at) {
    return `Fetched ${formatAdDate(announcement.fetched_at)}`;
  }

  return `Added ${formatAdDate(announcement.created_at)}`;
}

/**
 * Transform announcement to map-ready format
 */
function getMapAnnouncementPriority(announcement: MapAnnouncement): number {
  let score = 0;
  if (!announcement.is_fetched_only) score += 100;
  if (announcement.location_confidence === 'district') score += 35;
  else if (announcement.location_confidence === 'province_capital') score += 25;
  else if (announcement.location_confidence === 'central') score += 5;
  return score;
}

function toMapAnnouncement(announcement: Announcement): MapAnnouncement | null {
  const placement = inferAnnouncementPlacement(announcement);
  const isFetchedOnly = isFetchedOnlyAnnouncement(announcement);
  const isGeneric = isGenericAnnouncementTitle(announcement);

  // Do not place weak fetched-only source/portal labels on the map.
  if (!placement && isFetchedOnly) return null;
  if (isGeneric && isFetchedOnly) return null;
  if (!placement && isGeneric) return null;

  return {
    id: announcement.id,
    title: announcement.title,
    source: announcement.source,
    source_name: announcement.source_name,
    category: announcement.category,
    date_bs: announcement.date_bs,
    date_ad: announcement.date_ad,
    url: announcement.url,
    is_read: announcement.is_read,
    is_important: announcement.is_important,
    has_attachments: announcement.has_attachments,
    timestamp: getAnnouncementTimestamp(announcement),
    time_label: getAnnouncementTimeLabel(announcement),
    is_fetched_only: isFetchedOnly,
    district: placement?.district || 'Nepal',
    location_confidence: placement?.confidence || 'unknown',
    coordinates: placement?.coordinates || SINGHA_DURBAR_COORDS,
  };
}

/**
 * Hook to fetch announcements for map display
 */
export function useMapAnnouncements(hours: number = 168) {
  const query = useQuery({
    queryKey: ['map-announcements', hours],
    queryFn: async () => {
      const summary = await getAnnouncementSummary(100, hours);
      return summary.latest
        .map(toMapAnnouncement)
        .filter((item): item is MapAnnouncement => Boolean(item))
        .sort((a, b) => {
          const priorityDiff = getMapAnnouncementPriority(b) - getMapAnnouncementPriority(a);
          if (priorityDiff !== 0) return priorityDiff;
          return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
        })
        .slice(0, 20);
    },
    refetchInterval: 5 * 60 * 1000, // 5 minutes
    staleTime: 2 * 60 * 1000, // 2 minutes
  });

  return {
    announcements: query.data || [],
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}
