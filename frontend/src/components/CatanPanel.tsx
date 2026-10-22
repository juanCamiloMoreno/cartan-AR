import React, { useState } from 'react';
import { injectAction } from '../services/api';
import type { CatanState } from '../types/system';

const RESOURCE_LABELS: Record<string, string> = {
  wood: 'Madera',
  sheep: 'Oveja',
  wheat: 'Trigo',
  brick: 'Arcilla',
  ore: 'Mineral',
};

interface CatanPanelProps {
  catan?: CatanState | null;
}

export const CatanPanel: React.FC<CatanPanelProps> = ({ catan }) => {
  const [die1, setDie1] = useState(1);
  const [die2, setDie2] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const send = async (payload?: string) => {
    try {
      setError(null);
      await injectAction('CATAN_ROLL', payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo tirar los dados');
    }
  };

  const gameActive = !!catan?.game && catan.game.phase !== 'free';
  const canRoll = !gameActive || catan?.game?.phase === 'roll';

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Catan</h3>
      <button
        disabled={!canRoll}
        onClick={() => send()}
        className="w-full px-3 py-2 text-sm font-bold bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Tirar dados
      </button>

      <div className="mt-2 flex items-center gap-1 text-xs text-gray-600">
        <input
          aria-label="Dado 1"
          type="number"
          min={1}
          max={6}
          value={die1}
          onChange={(e) => setDie1(Number(e.target.value))}
          className="w-10 border rounded px-1 py-0.5 text-black"
        />
        <input
          aria-label="Dado 2"
          type="number"
          min={1}
          max={6}
          value={die2}
          onChange={(e) => setDie2(Number(e.target.value))}
          className="w-10 border rounded px-1 py-0.5 text-black"
        />
        <button
          onClick={() => send(`${die1},${die2}`)}
          className="px-2 py-0.5 border rounded hover:bg-gray-50"
        >
          Usar mis dados
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {catan && catan.total !== null && catan.dice ? (
        <div className="mt-3 text-sm text-black" data-testid="catan-result">
          <p className="font-medium">
            Salió {catan.total} ({catan.dice[0]} + {catan.dice[1]})
          </p>
          {catan.total === 7 ? (
            <p className="text-xs text-red-600">¡Ladrón! Nadie produce.</p>
          ) : catan.producing.length === 0 ? (
            <p className="text-xs text-gray-500">Ningún hexágono produce.</p>
          ) : (
            <ul className="text-xs text-gray-700 list-disc pl-4">
              {catan.producing.map((t) => (
                <li key={`${t.q},${t.r}`}>{RESOURCE_LABELS[t.resource] ?? t.resource}</li>
              ))}
            </ul>
          )}
          {Object.entries(catan.payouts ?? {}).map(([player, gains]) => (
            <p key={player} className="text-xs text-gray-700">
              {player}:{' '}
              {Object.entries(gains)
                .map(([res, n]) => `${n} ${RESOURCE_LABELS[res] ?? res}`)
                .join(', ')}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs italic text-gray-400">Aún no se ha tirado.</p>
      )}
    </div>
  );
};
