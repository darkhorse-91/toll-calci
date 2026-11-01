import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { PointItem, RouteItem } from './QuoteCard';

interface MapProps {
  route: RouteItem | null;
  hoveredPoint: PointItem | null;
}

export const Map: React.FC<MapProps> = ({ route }) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    // Standard free OpenStreetMap tile style
    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [78.9629, 22.5937], // Center of India
      zoom: 4.5,
    });

    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // Update route and markers when route changes
  useEffect(() => {
    if (!map.current || !route) return;

    // Clear existing markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    const mapInstance = map.current;

    const updateRouteLayer = () => {
      // Add or update GeoJSON route line
      const geojson: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'LineString',
              coordinates: route.geometry.coordinates,
            },
          },
        ],
      };

      if (mapInstance.getSource('route-line')) {
        (mapInstance.getSource('route-line') as maplibregl.GeoJSONSource).setData(geojson);
      } else {
        mapInstance.addSource('route-line', {
          type: 'geojson',
          data: geojson,
        });

        mapInstance.addLayer({
          id: 'route-line-casing',
          type: 'line',
          source: 'route-line',
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: {
            'line-color': '#1E2124',
            'line-width': 7,
          },
        });

        mapInstance.addLayer({
          id: 'route-line-core',
          type: 'line',
          source: 'route-line',
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: {
            'line-color': '#0B6B3A',
            'line-width': 4,
          },
        });
      }

      // Add coin markers for each toll point
      route.points.forEach((pt) => {
        if (!pt.lat || !pt.lng) return;

        const el = document.createElement('div');
        el.className = `coin-marker ${pt.pass_applied ? 'coin-covered' : 'coin-charged'}`;
        el.innerHTML = pt.pass_applied ? '✓' : '₹';
        el.title = `${pt.name}: ${pt.pass_applied ? '₹0 (Pass)' : `₹${pt.amount_inr}`}`;

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([pt.lng, pt.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 25 }).setHTML(`
              <b>${pt.name}</b><br/>
              <span>${pt.operator} ${pt.road ? `· ${pt.road}` : ''}</span><br/>
              <b>${pt.pass_applied ? '₹0 (Pass covered)' : `₹${pt.amount_inr}`}</b>
            `)
          )
          .addTo(mapInstance);

        markersRef.current.push(marker);
      });

      // Fit bounds to route
      if (route.geometry.coordinates.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        route.geometry.coordinates.forEach((coord) => {
          bounds.extend([coord[0], coord[1]]);
        });
        mapInstance.fitBounds(bounds, { padding: 40, maxZoom: 14 });
      }
    };

    if (mapInstance.isStyleLoaded()) {
      updateRouteLayer();
    } else {
      mapInstance.once('load', updateRouteLayer);
    }
  }, [route]);

  return (
    <div className="card" style={{ padding: '0.5rem' }}>
      <div ref={mapContainer} className="map-canvas-container" />
      <div style={{ padding: '0.4rem 0.5rem', fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'right' }}>
        © OpenStreetMap contributors · National Toll Plazas
      </div>
    </div>
  );
};
