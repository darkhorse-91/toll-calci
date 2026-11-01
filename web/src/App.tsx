import React, { useState, useEffect } from 'react';
import { Form, FormState } from './components/Form';
import { QuoteCard, RouteItem, PointItem } from './components/QuoteCard';
import { Map } from './components/Map';
import strings from './strings.en.json';

export const App: React.FC = () => {
  // Read query params for shareable URLs
  const params = new URLSearchParams(window.location.search);
  const initialForm: FormState = {
    fromText: params.get('from_name') || '',
    fromLocation:
      params.get('from_lat') && params.get('from_lng')
        ? {
            id: 'param',
            name: params.get('from_name') || '',
            lat: parseFloat(params.get('from_lat')!),
            lng: parseFloat(params.get('from_lng')!),
          }
        : null,
    toText: params.get('to_name') || '',
    toLocation:
      params.get('to_lat') && params.get('to_lng')
        ? {
            id: 'param',
            name: params.get('to_name') || '',
            lat: parseFloat(params.get('to_lat')!),
            lng: parseFloat(params.get('to_lng')!),
          }
        : null,
    vehicleClass: params.get('vehicle') || 'CAR_JEEP_VAN',
    commercial: params.get('commercial') === 'true',
    journey: (params.get('journey') as 'ONE_WAY' | 'RETURN_24H') || 'ONE_WAY',
    passActive: params.get('pass') === 'true',
    tripsLeft: params.get('trips_left') || '',
    travelDate: params.get('date') || '',
  };

  const [formState, setFormState] = useState<FormState>(initialForm);
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState<number>(0);
  const [ratesAsOf, setRatesAsOf] = useState<string>('2026-04-01');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<PointItem | null>(null);

  const fetchQuote = async (state: FormState) => {
    if (!state.fromLocation || !state.toLocation) return;

    setIsLoading(true);
    setErrorMsg(null);

    // Update URL query parameters for shareability
    const urlParams = new URLSearchParams({
      from_name: state.fromLocation.name,
      from_lat: String(state.fromLocation.lat),
      from_lng: String(state.fromLocation.lng),
      to_name: state.toLocation.name,
      to_lat: String(state.toLocation.lat),
      to_lng: String(state.toLocation.lng),
      vehicle: state.vehicleClass,
      commercial: String(state.commercial),
      journey: state.journey,
      pass: String(state.passActive),
    });
    if (state.tripsLeft) urlParams.set('trips_left', state.tripsLeft);
    if (state.travelDate) urlParams.set('date', state.travelDate);
    window.history.replaceState(null, '', `?${urlParams.toString()}`);

    try {
      const payload = {
        from: { lat: state.fromLocation.lat, lng: state.fromLocation.lng },
        to: { lat: state.toLocation.lat, lng: state.toLocation.lng },
        vehicle_class: state.vehicleClass,
        commercial: state.commercial,
        journey: state.journey,
        travel_date: state.travelDate || undefined,
        annual_pass: {
          active: state.passActive,
          trips_left: state.tripsLeft ? parseInt(state.tripsLeft, 10) : undefined,
        },
      };

      const res = await fetch('/v1/quote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const code = errData?.error?.code;
        if (code === 'NO_ROUTE') {
          setErrorMsg(strings.errors.noRoute);
        } else if (code === 'UPSTREAM_UNAVAILABLE') {
          setErrorMsg(strings.errors.upstreamUnavailable);
        } else {
          setErrorMsg(errData?.error?.message || strings.errors.generic);
        }
        setRoutes([]);
        return;
      }

      const data = await res.json();
      setRatesAsOf(data.rates_as_of);
      setRoutes(data.routes || []);
      setSelectedRouteIndex(0);
    } catch (e: any) {
      setErrorMsg(strings.errors.generic);
    } finally {
      setIsLoading(false);
    }
  };

  // If initial URL has start and destination, automatically trigger calculation
  useEffect(() => {
    if (initialForm.fromLocation && initialForm.toLocation) {
      fetchQuote(initialForm);
    }
  }, []);

  const currentRoute = routes.length > 0 ? routes[selectedRouteIndex] : null;

  return (
    <div>
      {/* Hero with highway milestone */}
      <header className="hero">
        <div className="hero-inner">
          <div>
            <h1>{strings.app.title}</h1>
            <p>{strings.app.subtitle}</p>
          </div>
          <figure className="stone" aria-label="National highway milestone">
            <div className="cap">NH</div>
            <div className="body">
              <div style={{ fontWeight: 800, fontSize: '0.9rem' }}>TOLL CALC</div>
              <div className="km">₹0</div>
            </div>
          </figure>
        </div>
      </header>

      {/* Main Container */}
      <main className="app-container">
        {/* Left Column: Form & Quote Card */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <Form
            initialState={formState}
            onSubmit={(st) => {
              setFormState(st);
              fetchQuote(st);
            }}
            isLoading={isLoading}
          />

          {errorMsg && (
            <div
              className="card"
              style={{
                background: 'rgba(179, 38, 30, 0.1)',
                border: '1px solid var(--red)',
                color: 'var(--red)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span>{errorMsg}</span>
              <button
                onClick={() => fetchQuote(formState)}
                style={{
                  background: 'var(--red)',
                  color: '#fff',
                  border: 'none',
                  padding: '0.4rem 0.8rem',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                {strings.errors.retry}
              </button>
            </div>
          )}

          {/* Route Variant Tabs */}
          {routes.length > 1 && (
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {routes.map((r, idx) => (
                <button
                  key={idx}
                  className={`chip ${selectedRouteIndex === idx ? 'active' : ''}`}
                  onClick={() => setSelectedRouteIndex(idx)}
                >
                  {r.label === 'USUAL'
                    ? strings.quote.routeUsual
                    : r.label === 'LOWEST_TOLL'
                    ? strings.quote.routeLowest
                    : strings.quote.routeFree}
                </button>
              ))}
            </div>
          )}

          {/* Render Quote Card */}
          {currentRoute && (
            <QuoteCard
              route={currentRoute}
              fromName={formState.fromText}
              toName={formState.toText}
              vehicleLabel={strings.vehicles[formState.vehicleClass as keyof typeof strings.vehicles] || formState.vehicleClass}
              isCommercial={formState.commercial}
              journeyType={formState.journey}
              passActive={formState.passActive}
              ratesAsOf={ratesAsOf}
              onPointHover={setHoveredPoint}
            />
          )}
        </div>

        {/* Right Column: Interactive Map */}
        <div>
          <Map route={currentRoute} hoveredPoint={hoveredPoint} />
        </div>
      </main>
    </div>
  );
};
