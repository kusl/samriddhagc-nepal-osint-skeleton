/**
 * The corridor walked as a list: every named damage site in order of kilometre,
 * each opening the same-frame pre/post pair over its own ground.
 *
 * The comparator itself, and every caption it carries, now lives in
 * components/flood/DamageComparator — the tactical map opens the same pairs off
 * the points they depict, which is where a reader looking at geography wants
 * them. What stays here is the thing a map cannot do: the corridor as an
 * ordered rail, so a reader can step 0 km → 53 km and see the damage change
 * with distance. This widget is archived out of the flood preset and kept
 * registered; it is one visibility flip from returning.
 *
 * There is deliberately no free pan. Every frame on screen is a curated,
 * pre-verified evidentiary frame whose coverage, top raster, acquisition date
 * and cloud figure the backend has already computed; a freely panned frame would
 * carry a caption nobody verified.
 */
import { memo, useMemo, useState } from 'react';
import { ExternalLink, Image as ImageIcon } from 'lucide-react';

import { Widget } from '../Widget';
import { WidgetSkeleton, WidgetError } from './shared';
import {
  C,
  Comparator,
  Emsr927Note,
  LEVEL_NAME,
  NARROW_PX,
  PhaseDossier,
  SiteStatement,
  chipStyle,
  figure,
  label,
  provenanceLine,
  useBoxSize,
} from '../../flood/DamageComparator';
import {
  useDamageSites,
  orderedLevels,
  formatGroundWidth,
  type DamageSite,
  type DamageLevelKey,
} from '../../flood/damageSites';

export const FloodDamageExplorerWidget = memo(function FloodDamageExplorerWidget() {
  const { data, isLoading, error, refetch } = useDamageSites();
  const [rootRef, { w: rootW }] = useBoxSize<HTMLDivElement>();
  const narrow = rootW > 0 && rootW < NARROW_PX;

  // Rasuwagadhi first: the border post and the bridge stand in the pre frame and
  // the same ground is scoured to bedrock in the post — the most legible pair in
  // the collection, and km 0 of the corridor the rest of the desk maps.
  const [siteKey, setSiteKey] = useState('rasuwagadhi');
  const [levelKey, setLevelKey] = useState<DamageLevelKey>('site');

  const site: DamageSite | null = useMemo(() => {
    const sites = data?.sites ?? [];
    return sites.find((s) => s.key === siteKey) ?? sites[0] ?? null;
  }, [data, siteKey]);

  const levels = useMemo(() => orderedLevels(site?.levels ?? []), [site]);
  const level = useMemo(
    () => levels.find((l) => l.level === levelKey) ?? levels[levels.length - 1] ?? null,
    [levels, levelKey],
  );

  if (isLoading) {
    return (
      <Widget id="flood-damage-explorer" icon={<ImageIcon size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data || !site) {
    return (
      <Widget id="flood-damage-explorer" icon={<ImageIcon size={14} />}>
        <WidgetError message="Failed to load damage-site frames" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const postTop = level?.post.top ?? null;

  const rail = (
    <div style={{
      flexShrink: 0,
      display: 'flex',
      flexDirection: narrow ? 'row' : 'column',
      gap: narrow ? 4 : 1,
      width: narrow ? 'auto' : 152,
      padding: narrow ? '5px 12px' : '6px 8px',
      overflowX: narrow ? 'auto' : 'hidden',
      overflowY: narrow ? 'hidden' : 'auto',
      borderRight: narrow ? 'none' : `1px solid ${C.border}`,
      borderBottom: narrow ? `1px solid ${C.border}` : 'none',
    }}>
      {!narrow && (
        <div style={{ ...label, fontSize: 9, letterSpacing: '0.08em', padding: '0 4px 4px' }}>
          Corridor ↓
        </div>
      )}
      {data.sites.map((s) => {
        const active = s.key === site.key;
        return (
          <button
            key={s.key}
            type="button"
            onClick={() => setSiteKey(s.key)}
            title={s.finding ?? s.name}
            style={{
              display: 'flex',
              flexDirection: narrow ? 'row' : 'column',
              alignItems: narrow ? 'center' : 'flex-start',
              gap: narrow ? 5 : 1,
              padding: narrow ? '3px 7px' : '4px 6px',
              cursor: 'pointer',
              textAlign: 'left',
              whiteSpace: 'nowrap',
              border: narrow ? `1px solid ${C.border}` : 'none',
              borderLeft: narrow ? `1px solid ${C.border}` : `2px solid ${active ? C.info : 'transparent'}`,
              background: active ? C.elevated : 'transparent',
              color: active ? C.text : C.sub,
            }}
          >
            <span style={{ fontSize: 11, lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: narrow ? 140 : 134 }}>
              {s.name}
            </span>
            <span style={{ ...figure, fontSize: 9, letterSpacing: '0.06em', color: C.muted }}>
              {s.km_mark === null ? 'ORIGIN' : `KM ${s.km_mark}`}
              {s.levels.length === 0 ? ' · NO FRAME' : ''}
            </span>
          </button>
        );
      })}
    </div>
  );

  // A site with no renderable frame has no frame facts to list, and its finding
  // is already the whole of the statement panel — the column would be a border
  // around a repetition.
  const dossier = levels.length === 0 ? null : (
    <div style={{
      flexShrink: 0,
      width: narrow ? 'auto' : 208,
      display: 'flex',
      flexDirection: narrow ? 'row' : 'column',
      gap: narrow ? 16 : 8,
      padding: narrow ? '6px 12px' : '8px 10px',
      overflowY: narrow ? 'hidden' : 'auto',
      overflowX: narrow ? 'auto' : 'hidden',
      borderLeft: narrow ? 'none' : `1px solid ${C.border}`,
      borderTop: narrow ? `1px solid ${C.border}` : 'none',
      background: C.surface,
    }}>
      {site.finding && !narrow && (
        <div>
          <div style={{ fontSize: 11, lineHeight: 1.45, color: C.text }}>{site.finding}</div>
          {site.finding_source && (
            <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.45, marginTop: 2 }}>
              {site.finding_source}
            </div>
          )}
        </div>
      )}
      {level && (
        <>
          <PhaseDossier phase="PRE" frame={level.pre} compact={narrow} />
          <PhaseDossier phase="POST" frame={level.post} compact={narrow} />
        </>
      )}
      {site.key === 'syabrubesi' && !narrow && <Emsr927Note />}
    </div>
  );

  return (
    <Widget
      id="flood-damage-explorer"
      icon={<ImageIcon size={14} />}
      badge={`${data.sites.length} SITES`}
    >
      <div ref={rootRef} style={{ flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{
          flex: '1 1 auto',
          minHeight: 0,
          display: 'flex',
          flexDirection: narrow ? 'column' : 'row',
          // Stacked, the frame's floor plus the captions can outgrow a short
          // pane. It scrolls rather than letting the dossier paint over the
          // cloud caveat, which may never be the line that goes missing.
          overflowY: narrow ? 'auto' : 'hidden',
        }}>
          {rail}

          <div style={{
            flex: narrow ? '1 0 auto' : '1 1 auto',
            minWidth: 0,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              // Clear of the widget's own top resize band, which is 5px of
              // z-indexed handle across the first pixels of every widget body.
              padding: '7px 10px 4px',
              borderBottom: `1px solid ${C.border}`,
            }}>
              <span style={{ fontSize: 11, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {site.name}
              </span>
              {level && (
                <span style={{ ...figure, fontSize: 9, letterSpacing: '0.06em', color: C.muted, whiteSpace: 'nowrap' }}>
                  {formatGroundWidth(level.width_m)} ACROSS
                </span>
              )}
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 3, flexShrink: 0 }}>
                {levels.map((l) => (
                  <button
                    key={l.level}
                    type="button"
                    onClick={() => setLevelKey(l.level)}
                    title={`${formatGroundWidth(l.width_m)} across`}
                    style={{
                      padding: '2px 7px',
                      fontSize: 9,
                      fontWeight: 600,
                      fontFamily: C.mono,
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      border: `1px solid ${C.border}`,
                      background: l.level === level?.level ? C.elevated : 'transparent',
                      color: l.level === level?.level ? C.text : C.muted,
                    }}
                  >
                    {LEVEL_NAME[l.level]}
                  </button>
                ))}
              </div>
            </div>

            {level ? (
              <Comparator key={`${site.key}-${level.level}`} level={level} siteName={site.name} />
            ) : (
              <SiteStatement site={site} />
            )}

          </div>

          {dossier}
        </div>

        {/* Outside every scroll region and never truncated: CC BY-NC 4.0 makes
            this line the condition on which the pixels above may be shown. */}
        <div style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          flexWrap: 'wrap',
          padding: '6px 12px',
          borderTop: `1px solid ${C.border}`,
          background: C.surface,
          fontSize: 9,
          lineHeight: 1.5,
          color: C.muted,
        }}>
          <span style={{ flex: '1 1 300px', minWidth: 0 }}>
            Satellite imagery © 2026 Vantor (formerly Maxar), Open Data program · served via Esri
            Disaster Response Program ·{' '}
            <a
              href={data.license_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: C.info, textDecoration: 'none' }}
            >
              CC BY-NC 4.0
            </a>
          </span>
          {postTop && (
            <a href={postTop.item_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
              STAC item <ExternalLink size={9} />
            </a>
          )}
          {postTop?.visual && (
            <a href={postTop.visual} target="_blank" rel="noopener noreferrer" style={chipStyle}>
              COG .tif <ExternalLink size={9} />
            </a>
          )}
          <a href={data.service_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            Image service <ExternalLink size={9} />
          </a>
          <span style={{ ...figure, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', flexShrink: 0 }}>
            {provenanceLine(data)}
          </span>
        </div>
      </div>
    </Widget>
  );
});
