import React, { useState } from 'react';
import { injectAction } from '../services/api';
import type { CatanState, CatanStatsMode } from '../types/system';

const RESOURCES: [string, string][] = [
  ['wood', 'Madera'],
  ['brick', 'Arcilla'],
  ['sheep', 'Oveja'],
  ['wheat', 'Trigo'],
  ['ore', 'Mineral'],
];

const PLAYER_COLORS: Record<string, string> = {
  rojo: '#dc2828',
  azul: '#1e78dc',
  blanco: '#f0f0f0',
  naranja: '#ff8c00',
};

interface CatanStatsProps {
  catan?: CatanState | null;
}

export const CatanStats: React.FC<CatanStatsProps> = ({ catan }) => {
  const [error, setError] = useState<string | null>(null);

  if (!catan || !catan.stats) return null;
  const stats = catan.stats;

  const send = async (action: string, payload: unknown) => {
    try {
      setError(null);
      await injectAction(action, JSON.stringify(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la acción');
    }
  };

  const setMode = (player: string, mode: CatanStatsMode) =>
    send('CATAN_STATS_MODE', { player, mode });

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Jugadores
      </h3>

      <div className="flex items-center gap-1 text-xs text-gray-600 mb-2">
        <span>Cantidad:</span>
        {[2, 3, 4].map((count) => (
          <button
            key={count}
            onClick={() => send('CATAN_PLAYERS', { count })}
            aria-pressed={catan.players.length === count}
            className={`px-2 py-0.5 border rounded ${
              catan.players.length === count ? 'border-blue-600 bg-blue-50 font-semibold' : ''
            }`}
          >
            {count}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1 text-xs text-gray-600 mb-3">
        <button
          onClick={() => setMode('all', 'simple')}
          className="px-2 py-0.5 border rounded hover:bg-gray-50"
        >
          Todos simple
        </button>
        <button
          onClick={() => setMode('all', 'resources')}
          className="px-2 py-0.5 border rounded hover:bg-gray-50"
        >
          Todos recursos
        </button>
      </div>

      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

      <div className="space-y-2">
        {catan.players.map((player) => {
          const s = stats[player];
          if (!s) return null;
          const showResources = s.mode === 'resources';
          return (
            <div
              key={player}
              data-testid={`stats-${player}`}
              className="rounded border border-gray-200 p-2 text-xs text-black"
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 font-semibold capitalize">
                  <span
                    className="inline-block w-3 h-3 rounded-sm border border-gray-700"
                    style={{ backgroundColor: PLAYER_COLORS[player] ?? '#999' }}
                  />
                  {player}
                </span>
                <span className="font-bold text-amber-600">{s.points} PV</span>
              </div>
              {s.has_longest_road && (
                <p data-testid={`longest-${player}`} className="mt-1 font-semibold text-amber-700">
                  Camino más largo ({s.longest_road} caminos) · +2 puntos
                </p>
              )}
              <p className="mt-1 text-gray-700">
                Casas {s.settlements} · Ciudades {s.cities} · Caminos {s.roads}
                {s.longest_road ? ` (línea de ${s.longest_road})` : ''} · Cartas {s.cards}
              </p>
              <button
                onClick={() => setMode(player, showResources ? 'simple' : 'resources')}
                aria-label={`Modo de ${player}`}
                className="mt-1 px-2 py-0.5 border rounded hover:bg-gray-50"
              >
                {showResources ? 'Modo: recursos' : 'Modo: simple'}
              </button>
              {showResources && (
                <ul className="mt-1 space-y-0.5">
                  {RESOURCES.map(([key, label]) => (
                    <li key={key} className="flex items-center justify-between">
                      <span>{label}</span>
                      <span className="flex items-center gap-1">
                        <button
                          aria-label={`Quitar ${label} a ${player}`}
                          onClick={() => send('CATAN_CARDS', { player, resource: key, amount: -1 })}
                          className="w-5 border rounded hover:bg-gray-50"
                        >
                          −
                        </button>
                        <span className="w-4 text-center">{s.hand[key] ?? 0}</span>
                        <button
                          aria-label={`Agregar ${label} a ${player}`}
                          onClick={() => send('CATAN_CARDS', { player, resource: key, amount: 1 })}
                          className="w-5 border rounded hover:bg-gray-50"
                        >
                          +
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
