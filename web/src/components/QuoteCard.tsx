import React from 'react';
import strings from '../strings.en.json';

export interface PointItem {
  id: number;
  name: string;
  kind: 'PLAZA' | 'CLOSED_SECTION';
  operator: string;
  road?: string;
  lat?: number;
  lng?: number;
  entry?: string;
  exit?: string;
  amount_without_pass_inr?: number;
  amount_inr?: number;
  pass_applied: boolean;
  trips_used: number;
  reason?: 'NOT_ELIGIBLE' | 'STATE_ROAD' | 'TRIPS_USED_UP' | 'RATE_MISSING' | null;
}

export interface RouteItem {
  label: 'USUAL' | 'LOWEST_TOLL' | 'TOLL_FREE';
  distance_km: number;
  est_duration_min: number;
  geometry: {
    type: string;
    coordinates: number[][];
  };
  toll_with_pass_inr: number | null;
  toll_without_pass_inr: number | null;
  complete: boolean;
  pass: {
    eligible: boolean;
    points_covered: number;
    points_total: number;
    trips_used: number;
    trips_left_after: number | null;
    break_even_journeys: number | null;
  };
  points: PointItem[];
  insights: {
    key: string;
    text: string;
    period: string;
    source: string;
  }[];
}

interface QuoteCardProps {
  route: RouteItem;
  fromName: string;
  toName: string;
  vehicleLabel: string;
  isCommercial: boolean;
  journeyType: string;
  passActive: boolean;
  ratesAsOf: string;
  onPointHover?: (point: PointItem | null) => void;
}

export const QuoteCard: React.FC<QuoteCardProps> = ({
  route,
  fromName,
  toName,
  vehicleLabel,
  isCommercial,
  journeyType,
  passActive,
  ratesAsOf,
  onPointHover,
}) => {
  const metaLine = [
    vehicleLabel,
    vehicleLabel.includes('Car') ? (isCommercial ? 'commercial' : 'private') : null,
    journeyType === 'ONE_WAY' ? 'one way' : 'return within 24h',
    passActive ? 'annual pass active' : 'no pass',
  ]
    .filter(Boolean)
    .join(' · ');

  // Pass box narrative logic
  const renderPassBox = () => {
    if (passActive) {
      if (!route.pass.eligible) {
        return <p>{strings.quote.notEligible}</p>;
      }

      // Check if any state roads were uncovered
      const stateRoadPoints = route.points.filter((p) => p.reason === 'STATE_ROAD');
      const tripsUsedUpPoints = route.points.filter((p) => p.reason === 'TRIPS_USED_UP');

      return (
        <>
          <p>
            <b>
              {route.pass.trips_left_after !== null
                ? strings.quote.passCovered
                    .replace('{covered}', String(route.pass.points_covered))
                    .replace('{total}', String(route.pass.points_total))
                    .replace('{used}', String(route.pass.trips_used))
                    .replace('{left}', String(route.pass.trips_left_after))
                : strings.quote.passCoveredAssumed
                    .replace('{covered}', String(route.pass.points_covered))
                    .replace('{total}', String(route.pass.points_total))
                    .replace('{used}', String(route.pass.trips_used))}
            </b>
          </p>
          {stateRoadPoints.length > 0 && (
            <p>
              {strings.quote.stateRoadNotCovered
                .replace('{point}', stateRoadPoints[0].name)
                .replace('{amount}', String(stateRoadPoints[0].amount_inr || 0))}
            </p>
          )}
          {tripsUsedUpPoints.length > 0 && (
            <p>
              {strings.quote.tripsRunOut.replace('{point}', tripsUsedUpPoints[0].name)}
            </p>
          )}
        </>
      );
    } else {
      // User has no pass
      if (route.pass.eligible && route.pass.break_even_journeys) {
        return (
          <p>
            {strings.quote.noPassSavings
              .replace('{withPass}', String(route.toll_with_pass_inr || 0))
              .replace('{withoutPass}', String(route.toll_without_pass_inr || 0))
              .replace('{breakEven}', String(route.pass.break_even_journeys))}
          </p>
        );
      } else if (route.pass.eligible) {
        return <p>{strings.quote.noPassZeroSavings}</p>;
      } else {
        return <p>{strings.quote.notEligible}</p>;
      }
    }
  };

  return (
    <div className="quote-card">
      {/* Route bar */}
      <div className="quote-bar">
        <b>
          {fromName} → {toName}
        </b>
        <span>{metaLine}</span>
      </div>

      {/* Incomplete Rate Banner */}
      {!route.complete && (
        <div style={{ background: 'var(--red)', color: '#fff', padding: '0.6rem 1rem', fontSize: '0.88rem' }}>
          {strings.quote.rateMissingBanner.replace(
            '{count}',
            String(route.points.filter((p) => p.reason === 'RATE_MISSING').length)
          )}
        </div>
      )}

      {/* Total amount */}
      <div className="quote-total">
        <div>
          <small>{strings.quote.youPay}</small>
          <div className="amt">
            ₹{passActive ? (route.toll_with_pass_inr !== null ? route.toll_with_pass_inr : '—') : (route.toll_without_pass_inr !== null ? route.toll_without_pass_inr : '—')}
          </div>
        </div>
        {passActive && route.toll_without_pass_inr !== null && (
          <div style={{ textAlign: 'right' }}>
            <small>{strings.quote.withoutPass}</small>
            <div style={{ fontSize: '1.25rem', fontWeight: 800 }}>₹{route.toll_without_pass_inr}</div>
          </div>
        )}
      </div>

      {/* Annual Pass Summary Box */}
      <div className="quote-pass-box">{renderPassBox()}</div>

      {/* Points list in travel order */}
      <ul className="quote-points">
        {route.points.map((pt) => {
          let tagClass = 'tag';
          let tagText = '';

          if (pt.pass_applied) {
            tagClass += ' tag-pass';
            tagText = 'Pass';
          } else if (pt.reason === 'STATE_ROAD') {
            tagClass += ' tag-state';
            tagText = 'State Road';
          } else if (pt.reason === 'RATE_MISSING') {
            tagClass += ' tag-missing';
            tagText = 'Rate missing';
          }

          const displayAmt =
            pt.amount_inr !== null ? (
              <span>
                ₹{pt.amount_inr} {tagText && <span className={tagClass}>{tagText}</span>}
              </span>
            ) : (
              <span style={{ color: 'var(--red)' }}>{strings.quote.rateNotAvailable}</span>
            );

          return (
            <li
              key={pt.id}
              onMouseEnter={() => onPointHover && onPointHover(pt)}
              onMouseLeave={() => onPointHover && onPointHover(null)}
            >
              <div>
                <b>{pt.name}</b>
                <span style={{ display: 'block', fontSize: '0.8rem', color: 'var(--muted)' }}>
                  {pt.operator} {pt.road ? `· ${pt.road}` : ''} {pt.entry && pt.exit ? `(${pt.entry} → ${pt.exit})` : ''}
                </span>
              </div>
              <div>{displayAmt}</div>
            </li>
          );
        })}
      </ul>

      {/* Route Insights facts */}
      {route.insights.length > 0 && (
        <div className="quote-facts">
          <p>
            <b>{strings.quote.aboutRoad}</b>
          </p>
          {route.insights.map((ins) => (
            <p key={ins.key}>{ins.text}</p>
          ))}
          <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '0.5rem' }}>
            FASTag data from IHMCL monthly reports, FY 2025–26.
          </p>
        </div>
      )}

      {/* Footer Notice */}
      <div className="quote-footer">
        {strings.quote.footerNotice.replace('{date}', ratesAsOf)}
      </div>
    </div>
  );
};
