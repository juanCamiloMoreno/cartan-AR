import React, { useState } from 'react';
import { injectAction } from '../services/api';
import type { CatanState } from '../types/system';

type Balance = 'random' | 'fair' | 'very_fair';

interface Rules {
  allow_adjacent_same_resource: boolean;
  allow_adjacent_red: boolean;
  allow_adjacent_low: boolean;
  allow_adjacent_same_number: boolean;
  shuffle_ports: boolean;
  balance: Balance;
}

const DEFAULT_RULES: Rules = {
  allow_adjacent_same_resource: true,
  allow_adjacent_red: false,
  allow_adjacent_low: true,
  allow_adjacent_same_number: true,
  shuffle_ports: true,
  balance: 'random',
};

const CHECKS: [keyof Omit<Rules, 'balance'>, string][] = [
  ['allow_adjacent_same_resource', 'Recursos iguales pueden ir pegados'],
  ['allow_adjacent_red', '6 y 8 pueden ir pegados'],
  ['allow_adjacent_low', '2 y 12 pueden ir pegados'],
  ['allow_adjacent_same_number', 'Números iguales pueden ir pegados'],
  ['shuffle_ports', 'Barajar los puertos'],
];

const BALANCE_LABELS: Record<Balance, string> = {
  random: 'Al azar',
  fair: 'Más o menos justo',
  very_fair: 'Muy justo',
};

const RESOURCE_LABELS: Record<string, string> = {
  wood: 'Madera',
  brick: 'Arcilla',
  sheep: 'Oveja',
  wheat: 'Trigo',
  ore: 'Mineral',
};

interface CatanGeneratorProps {
  catan?: CatanState | null;
}

export const CatanGenerator: React.FC<CatanGeneratorProps> = ({ catan }) => {
  const [rules, setRules] = useState<Rules>(DEFAULT_RULES);
  const [error, setError] = useState<string | null>(null);

  if (!catan || !catan.board) return null;
  const report = catan.generator;

  const generate = async () => {
    try {
      setError(null);
      await injectAction('CATAN_NEW_BOARD', JSON.stringify(rules));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo generar el tablero');
    }
  };

  return (
    <div data-testid="catan-generator">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Nuevo tablero
      </h3>

      <ul className="space-y-1 mb-2">
        {CHECKS.map(([key, label]) => (
          <li key={key}>
            <label className="flex items-center gap-2 text-xs text-black">
              <input
                type="checkbox"
                checked={rules[key]}
                onChange={(e) => setRules({ ...rules, [key]: e.target.checked })}
              />
              {label}
            </label>
          </li>
        ))}
      </ul>

      <label className="flex items-center gap-2 text-xs text-gray-600 mb-2">
        Equilibrio
        <select
          aria-label="Equilibrio"
          value={rules.balance}
          onChange={(e) => setRules({ ...rules, balance: e.target.value as Balance })}
          className="border rounded px-1 py-0.5 text-black"
        >
          {(Object.keys(BALANCE_LABELS) as Balance[]).map((level) => (
            <option key={level} value={level}>
              {BALANCE_LABELS[level]}
            </option>
          ))}
        </select>
      </label>

      <button
        onClick={generate}
        className="w-full px-3 py-2 text-sm font-bold bg-emerald-600 text-white rounded hover:bg-emerald-700"
      >
        Generar tablero
      </button>
      <p className="mt-1 text-[11px] text-gray-500">
        Cambia el mapa y empieza de cero (se pierden las piezas y las cartas).
      </p>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {report && report.metrics && (
        <div data-testid="generator-report" className="mt-2 text-xs text-black">
          {!report.satisfied && (
            <p className="text-amber-700">
              Las reglas eran demasiado estrictas: este es el mejor tablero que se encontró.
            </p>
          )}
          <p className="text-gray-600">
            {report.attempts} intentos · diferencia entre recursos {report.metrics.avg_spread} ·
            esquinas fuertes {report.metrics.strong_corners}
          </p>
          <ul className="text-gray-700">
            {Object.entries(report.metrics.resource_pips).map(([resource, pips]) => (
              <li key={resource}>
                {RESOURCE_LABELS[resource] ?? resource}: {pips} puntos
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
