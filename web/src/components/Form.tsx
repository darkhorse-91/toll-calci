import React, { useState, useRef } from 'react';
import strings from '../strings.en.json';

export interface LocationItem {
  id: string;
  name: string;
  detail?: string;
  lat: number;
  lng: number;
}

export interface FormState {
  fromText: string;
  fromLocation: LocationItem | null;
  toText: string;
  toLocation: LocationItem | null;
  vehicleClass: string;
  commercial: boolean;
  journey: 'ONE_WAY' | 'RETURN_24H';
  passActive: boolean;
  tripsLeft: string;
  travelDate: string;
}

interface FormProps {
  initialState: FormState;
  onSubmit: (state: FormState) => void;
  isLoading: boolean;
}

export const Form: React.FC<FormProps> = ({ initialState, onSubmit, isLoading }) => {
  const [form, setForm] = useState<FormState>(initialState);
  const [showDatePicker, setShowDatePicker] = useState(Boolean(initialState.travelDate));

  // Autocomplete states
  const [fromSuggestions, setFromSuggestions] = useState<LocationItem[]>([]);
  const [toSuggestions, setToSuggestions] = useState<LocationItem[]>([]);
  const [activeField, setActiveField] = useState<'from' | 'to' | null>(null);

  const debounceTimer = useRef<NodeJS.Timeout | null>(null);

  const searchPlaces = async (query: string, field: 'from' | 'to') => {
    if (query.trim().length < 2) {
      if (field === 'from') setFromSuggestions([]);
      else setToSuggestions([]);
      return;
    }
    try {
      const res = await fetch(`/v1/places?q=${encodeURIComponent(query)}&limit=5`);
      if (res.ok) {
        const data = await res.json();
        if (field === 'from') setFromSuggestions(data);
        else setToSuggestions(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleTextChange = (field: 'from' | 'to', val: string) => {
    if (field === 'from') {
      setForm((prev) => ({ ...prev, fromText: val, fromLocation: null }));
    } else {
      setForm((prev) => ({ ...prev, toText: val, toLocation: null }));
    }
    setActiveField(field);

    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      searchPlaces(val, field);
    }, 250);
  };

  const selectLocation = (field: 'from' | 'to', loc: LocationItem) => {
    if (field === 'from') {
      setForm((prev) => ({ ...prev, fromText: loc.name, fromLocation: loc }));
      setFromSuggestions([]);
    } else {
      setForm((prev) => ({ ...prev, toText: loc.name, toLocation: loc }));
      setToSuggestions([]);
    }
    setActiveField(null);
  };

  const swapLocations = () => {
    setForm((prev) => ({
      ...prev,
      fromText: prev.toText,
      fromLocation: prev.toLocation,
      toText: prev.fromText,
      toLocation: prev.fromLocation,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.fromLocation || !form.toLocation) {
      alert('Please select both starting location and destination from the search suggestions.');
      return;
    }
    onSubmit(form);
  };

  const vehicleKeys: (keyof typeof strings.vehicles)[] = [
    'CAR_JEEP_VAN',
    'LCV',
    'BUS_TRUCK_2AXLE',
    'AXLE_3',
    'AXLE_4_6',
    'AXLE_7_PLUS',
  ];

  return (
    <form className="card" onSubmit={handleSubmit}>
      {/* From field */}
      <div className="form-group" style={{ position: 'relative' }}>
        <label htmlFor="from-input">{strings.form.fromLabel}</label>
        <input
          id="from-input"
          className="input-text"
          type="text"
          value={form.fromText}
          placeholder="e.g. Lucknow, Hazratganj"
          autoComplete="off"
          onChange={(e) => handleTextChange('from', e.target.value)}
          onFocus={() => setActiveField('from')}
        />
        {activeField === 'from' && fromSuggestions.length > 0 && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderRadius: '4px',
              zIndex: 100,
              boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
            }}
          >
            {fromSuggestions.map((item) => (
              <div
                key={item.id}
                style={{ padding: '0.6rem 0.8rem', cursor: 'pointer', borderBottom: '1px solid var(--line)' }}
                onClick={() => selectLocation('from', item)}
              >
                <b>{item.name}</b>
                {item.detail && <small style={{ display: 'block', color: 'var(--muted)' }}>{item.detail}</small>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Swap button */}
      <div style={{ textAlign: 'center', margin: '-0.4rem 0 0.6rem' }}>
        <button
          type="button"
          onClick={swapLocations}
          style={{
            background: 'none',
            border: '1px dashed var(--line)',
            borderRadius: '4px',
            padding: '0.2rem 0.6rem',
            cursor: 'pointer',
            fontSize: '0.8rem',
            color: 'var(--muted)',
          }}
        >
          ⇅ {strings.form.swap}
        </button>
      </div>

      {/* To field */}
      <div className="form-group" style={{ position: 'relative' }}>
        <label htmlFor="to-input">{strings.form.toLabel}</label>
        <input
          id="to-input"
          className="input-text"
          type="text"
          value={form.toText}
          placeholder="e.g. Agra, Tajganj"
          autoComplete="off"
          onChange={(e) => handleTextChange('to', e.target.value)}
          onFocus={() => setActiveField('to')}
        />
        {activeField === 'to' && toSuggestions.length > 0 && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderRadius: '4px',
              zIndex: 100,
              boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
            }}
          >
            {toSuggestions.map((item) => (
              <div
                key={item.id}
                style={{ padding: '0.6rem 0.8rem', cursor: 'pointer', borderBottom: '1px solid var(--line)' }}
                onClick={() => selectLocation('to', item)}
              >
                <b>{item.name}</b>
                {item.detail && <small style={{ display: 'block', color: 'var(--muted)' }}>{item.detail}</small>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Vehicle class chips */}
      <div className="form-group">
        <label>{strings.form.vehicleLabel}</label>
        <div className="chip-grid">
          {vehicleKeys.map((vKey) => (
            <button
              key={vKey}
              type="button"
              className={`chip ${form.vehicleClass === vKey ? 'active' : ''}`}
              onClick={() => setForm((prev) => ({ ...prev, vehicleClass: vKey }))}
            >
              {strings.vehicles[vKey]}
            </button>
          ))}
        </div>
      </div>

      {/* Private / Commercial (CAR_JEEP_VAN only) */}
      {form.vehicleClass === 'CAR_JEEP_VAN' && (
        <div className="form-group">
          <label>{strings.form.usageLabel}</label>
          <div className="toggle-group">
            <button
              type="button"
              className={`toggle-btn ${!form.commercial ? 'active' : ''}`}
              onClick={() => setForm((prev) => ({ ...prev, commercial: false }))}
            >
              {strings.form.private}
            </button>
            <button
              type="button"
              className={`toggle-btn ${form.commercial ? 'active' : ''}`}
              onClick={() => setForm((prev) => ({ ...prev, commercial: true }))}
            >
              {strings.form.commercial}
            </button>
          </div>
        </div>
      )}

      {/* Trip Journey */}
      <div className="form-group">
        <label>{strings.form.journeyLabel}</label>
        <div className="toggle-group">
          <button
            type="button"
            className={`toggle-btn ${form.journey === 'ONE_WAY' ? 'active' : ''}`}
            onClick={() => setForm((prev) => ({ ...prev, journey: 'ONE_WAY' }))}
          >
            {strings.form.oneWay}
          </button>
          <button
            type="button"
            className={`toggle-btn ${form.journey === 'RETURN_24H' ? 'active' : ''}`}
            onClick={() => setForm((prev) => ({ ...prev, journey: 'RETURN_24H' }))}
          >
            {strings.form.return24h}
          </button>
        </div>
      </div>

      {/* Annual Pass Toggle */}
      <div className="form-group">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.passActive}
            onChange={(e) => setForm((prev) => ({ ...prev, passActive: e.target.checked }))}
          />
          {strings.form.passToggle}
        </label>
        {form.passActive && (
          <div style={{ marginTop: '0.5rem' }}>
            <input
              type="number"
              className="input-text"
              placeholder={strings.form.tripsLeftLabel}
              min="0"
              max="200"
              value={form.tripsLeft}
              onChange={(e) => setForm((prev) => ({ ...prev, tripsLeft: e.target.value }))}
            />
          </div>
        )}
      </div>

      {/* Travelling Later */}
      <div className="form-group">
        <span
          onClick={() => setShowDatePicker((prev) => !prev)}
          style={{ fontSize: '0.85rem', color: 'var(--sign)', cursor: 'pointer', textDecoration: 'underline' }}
        >
          {showDatePicker ? '▲ Travelling today' : `▼ ${strings.form.travelLaterToggle}`}
        </span>
        {showDatePicker && (
          <div style={{ marginTop: '0.4rem' }}>
            <input
              type="date"
              className="input-text"
              value={form.travelDate}
              onChange={(e) => setForm((prev) => ({ ...prev, travelDate: e.target.value }))}
            />
          </div>
        )}
      </div>

      {/* Submit Button */}
      <button type="submit" className="btn-primary" disabled={isLoading}>
        {isLoading ? strings.form.loading : strings.form.submit}
      </button>
    </form>
  );
};
