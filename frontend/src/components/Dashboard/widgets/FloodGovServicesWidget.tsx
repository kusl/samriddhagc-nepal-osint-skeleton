/**
 * The desk's action surface: the government's own response portals.
 *
 * Every other widget answers "what happened". This one answers "what do I do
 * now" — where a family registers a rescue request, checks the list of people
 * pulled out of Rasuwa, finds blood, or sends money. Rendered through the
 * MILSPEC grammar as a fixed-column register rather than a stack of large
 * links: on a page of tables, a column of 14px anchors reads as an
 * advertisement, and the row still opens the portal.
 *
 * Rows are links to the agencies, never mirrors of them. The backend probes each
 * portal and passes `reachable` through; `reachable === null` means our own probe
 * could not run, which is not the same claim as a portal being down and is never
 * rendered as one. Attachments arrive as a count because nepal.gov.np publishes
 * no URL for them — a guessed file path would be a fabricated source.
 *
 * Titles are largely Nepali and are rendered verbatim. No translation is
 * invented here; the agency tag and the domain are the English-legible identity
 * of every row.
 */
import { memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, LifeBuoy } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
  LABEL_XS,
  MS,
  Note,
  Row,
  Scroll,
  Section,
  SourceLine,
  Status,
  TableHead,
  TableRow,
  dtgDay,
  type Tone,
} from '../../flood/milspec';

const TITLE = 'RESPONSE PORTALS';

type FetchState = 'live' | 'cache' | 'fallback';

interface GovNotice {
  id: string;
  titleEn: string | null;
  titleNe: string | null;
  contentEn: string | null;
  contentNe: string | null;
  priority: number | null;
  issuingAgency: string | null;
  sourceUrl: string | null;
  publishedAt: string | null;
  /** Empty in every notice today; the field is carried in case it ever fills. */
  emergencyContacts: unknown[];
  /** null = our probe could not run. Never rendered as "down". */
  reachable: boolean | null;
  link_status: number | null;
}

interface GovUpdate {
  id: string;
  title: string;
  createdAt: string | null;
  author: { name: string | null; department: string | null } | null;
  /** A count, not objects: the portal publishes no attachment URL. */
  attachments: number;
  tags: string[];
}

interface GovServices {
  portal_url: string;
  source?: { notices: FetchState; updates: FetchState };
  fetched_at: string | null;
  snapshot_verified_on: string | null;
  notices: GovNotice[];
  updates: GovUpdate[];
}

const GOV_REFRESH = 15 * 60 * 1000;

/**
 * Declared inline because the shared flood client is owned by another agent this
 * run; the queryKey sits under the same 'flood' root so it invalidates with the
 * rest of the desk. The endpoint holds its own 15-minute cache, so a shorter
 * interval here would only add traffic.
 */
function useGovServices() {
  return useQuery<GovServices>({
    queryKey: ['flood', 'gov-services'] as const,
    queryFn: async () => (await apiClient.get('/flood/gov-services')).data,
    staleTime: GOV_REFRESH,
    refetchInterval: GOV_REFRESH,
  });
}

/**
 * The portal stamps these in UTC to the millisecond — a server insert time, not
 * a hand-typed local one — so the calendar day is resolved on the Kathmandu
 * clock before `dtgDay` stamps it. Slicing the raw UTC string instead would put
 * anything published after 18:15 NPT on the previous day.
 *
 * Local because milspec has no zone-aware day resolver; it returns a plain ISO
 * day so the DTG itself is still milspec's.
 */
const nptDay = (iso: string | null): string | null => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  // en-CA yields YYYY-MM-DD, which is exactly what dtgDay slices.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kathmandu',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
};

/** "https://freehealth.mohp.gov.np/blood-bank" → "freehealth.mohp.gov.np". */
const domainOf = (url: string | null): string | null => {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return url.replace(/^https?:\/\//, '').split('/')[0] || null;
  }
};

/**
 * The portal's own priority field, ascending. Its semantics are undocumented
 * upstream, so the word says only where the portal ranked the row — it is not a
 * judgement this desk made, and an absent field stays absent.
 */
function Priority({ priority }: { priority: number | null }) {
  if (priority == null) return <Status tone="muted">—</Status>;
  const t: Tone = priority === 1 ? 'high' : priority === 2 ? 'medium' : 'muted';
  return <Status tone={t}>P{priority}</Status>;
}

/** Devanagari needs the language tag for correct shaping. Rendered verbatim. */
function PortalTitle({ notice }: { notice: GovNotice }) {
  const en = notice.titleEn;
  const ne = notice.titleNe;
  return (
    <>
      {en ? <span style={{ color: MS.text }}>{en}</span> : null}
      {!en && ne ? (
        <span lang="ne" style={{ color: MS.text }}>
          {ne}
        </span>
      ) : null}
      {/* A portal that answered a probe with an error is flagged; a probe that
          could not run says nothing, because our own egress being down would
          otherwise steer a family away from a live service. */}
      {notice.reachable === false && (
        <span style={{ marginLeft: 8 }}>
          <Status tone="medium">
            NOT RESPONDING{notice.link_status ? ` · HTTP ${notice.link_status}` : ''}
          </Status>
        </span>
      )}
    </>
  );
}

function PortalLink({ url, label }: { url: string | null; label: string | null }) {
  if (!url) return <span style={{ color: MS.disabled }}>—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={label ?? url}
      style={{
        color: MS.info,
        textDecoration: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        whiteSpace: 'nowrap',
      }}
    >
      OPEN <ExternalLink size={9} />
    </a>
  );
}

export const FloodGovServicesWidget = memo(function FloodGovServicesWidget() {
  const { data, isLoading, error, refetch } = useGovServices();

  if (isLoading) {
    return (
      <Widget id="flood-gov-services" title={TITLE} icon={<LifeBuoy size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-gov-services" title={TITLE} icon={<LifeBuoy size={14} />}>
        <WidgetError message="Failed to reach the government services record" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const notices = data.notices ?? [];
  const updates = data.updates ?? [];

  if (notices.length === 0 && updates.length === 0) {
    return (
      <Widget id="flood-gov-services" title={TITLE} icon={<LifeBuoy size={14} />}>
        <WidgetEmpty message="nepal.gov.np is publishing no response services for this event" />
      </Widget>
    );
  }

  const stale = data.source?.notices !== 'live' || data.source?.updates !== 'live';
  const fallback = data.source?.notices === 'fallback' || data.source?.updates === 'fallback';
  const fetchedDay = nptDay(data.fetched_at);

  return (
    <Widget
      id="flood-gov-services"
      title={TITLE}
      icon={<LifeBuoy size={14} />}
      badge={`${notices.length} PORTALS`}
      badgeVariant={fallback ? 'high' : 'default'}
    >
      <Body>
        <Scroll>
          <TableHead
            cols={[
              { label: 'AGENCY', width: '14%' },
              { label: 'PORTAL' },
              { label: 'PRIORITY', width: '10%' },
              { label: 'CONTACT', width: '18%' },
              { label: 'LINK', width: '8%', align: 'right' },
            ]}
          />
          {notices.map((notice) => {
            const domain = domainOf(notice.sourceUrl);
            // Carried through as unknown: the field is empty in every notice
            // today, so its element shape is unverified and only strings are
            // safe to print.
            const contacts = (notice.emergencyContacts ?? []).filter(
              (c): c is string => typeof c === 'string',
            );

            return (
              <TableRow
                key={notice.id}
                cells={[
                  {
                    width: '14%',
                    node: (
                      <span style={{ ...LABEL_XS, color: MS.info }}>{notice.issuingAgency ?? '—'}</span>
                    ),
                  },
                  {
                    node: (
                      <>
                        <PortalTitle notice={notice} />
                        {domain && (
                          <span style={{ ...LABEL_XS, marginLeft: 8, textTransform: 'none', letterSpacing: 0 }}>
                            {domain}
                          </span>
                        )}
                      </>
                    ),
                  },
                  { width: '10%', node: <Priority priority={notice.priority} /> },
                  {
                    width: '18%',
                    node: contacts.length > 0 ? contacts.join(' · ') : '—',
                    tone: contacts.length > 0 ? 'text' : 'muted',
                  },
                  {
                    width: '8%',
                    align: 'right',
                    node: <PortalLink url={notice.sourceUrl} label={domain} />,
                  },
                ]}
              />
            );
          })}

          {updates.length > 0 && (
            <>
              <Section title="GOVERNMENT STATEMENTS" meta={`${updates.length}`} />
              {updates.map((update) => (
                <Row
                  key={update.id}
                  label={
                    <span lang="ne" style={{ color: MS.text }}>
                      {update.title}
                    </span>
                  }
                  sub={
                    <>
                      {dtgDay(nptDay(update.createdAt))}
                      {update.author?.department ? ` · ${update.author.department}` : ''}
                      {/* Stated as a count with no link: the portal publishes no
                          URL for these files, and a constructed path would be a
                          source we invented. */}
                      {update.attachments > 0
                        ? ` · ${update.attachments} FILE${update.attachments === 1 ? '' : 'S'} AT SOURCE`
                        : ''}
                    </>
                  }
                  right={<PortalLink url={data.portal_url} label={domainOf(data.portal_url)} />}
                />
              ))}
            </>
          )}

          <Note>
            {fallback ? (
              <>
                nepal.gov.np unreachable — showing the hand-verified snapshot of{' '}
                {data.snapshot_verified_on ? dtgDay(data.snapshot_verified_on) : 'the last successful fetch'}.
                Each portal link was confirmed reachable independently of the portal that lists them.
              </>
            ) : (
              <>
                Rows in the portal&rsquo;s own priority order; titles are passed through untranslated.
              </>
            )}
          </Note>
        </Scroll>

        <SourceLine
          source="nepal.gov.np"
          asOf={fetchedDay ? dtgDay(fetchedDay) : null}
          url={data.portal_url}
          right={
            <Status tone={fallback ? 'medium' : stale ? 'muted' : 'low'}>
              {fallback ? 'SNAPSHOT' : stale ? 'CACHED' : 'LIVE'}
            </Status>
          }
        />
      </Body>
    </Widget>
  );
});
