import React, { useState } from 'react';
import { injectAction } from '../services/api';
import type { CatanState } from '../types/system';

const RESOURCES: [string, string][] = [
  ['wood', 'Madera'],
  ['brick', 'Arcilla'],
  ['sheep', 'Oveja'],
  ['wheat', 'Trigo'],
  ['ore', 'Mineral'],
];

const PHASE_LABELS: Record<string, string> = {
  free: 'Modo libre',
  setup: 'Preparación',
  roll: 'Tirar dados',
  discard: 'Descartar',
  robber: 'Ladrón',
  steal: 'Robar',
  main: 'Turno',
  finished: 'Terminó',
};

const COST_LABELS: Record<string, string> = {
  road: 'Camino',
  settlement: 'Casa',
  city: 'Ciudad',
};

interface CatanGameProps {
  catan?: CatanState | null;
}

export const CatanGame: React.FC<CatanGameProps> = ({ catan }) => {
  const [error, setError] = useState<string | null>(null);
  const [give, setGive] = useState('wood');
  const [get, setGet] = useState('ore');
  const [discards, setDiscards] = useState<Record<string, Record<string, number>>>({});

  const game = catan?.game;
  if (!catan || !game) return null;

  const send = async (action: string, payload?: unknown) => {
    try {
      setError(null);
      await injectAction(action, payload === undefined ? undefined : JSON.stringify(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la acción');
    }
  };

  const inGame = game.phase !== 'free';
  const current = game.current_player;

  const setDiscard = (player: string, resource: string, value: number) =>
    setDiscards((prev) => ({
      ...prev,
      [player]: { ...(prev[player] ?? {}), [resource]: Math.max(0, value) },
    }));

  return (
    <div data-testid="catan-game">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Partida</h3>

      <div className="rounded border border-gray-200 p-2 text-xs text-black mb-2">
        <p className="font-semibold" data-testid="game-phase">
          {PHASE_LABELS[game.phase] ?? game.phase}
          {inGame && game.turn > 0 ? ` · turno ${game.turn}` : ''}
        </p>
        <p data-testid="game-hint" className="text-gray-700">
          {game.hint}
        </p>
      </div>

      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

      <div className="flex flex-wrap items-center gap-1 text-xs text-gray-600 mb-2">
        <span>Nueva partida:</span>
        {[2, 3, 4].map((players) => (
          <button
            key={players}
            aria-label={`Nueva partida de ${players}`}
            onClick={() => send('CATAN_NEW_GAME', { players })}
            className="px-2 py-0.5 border rounded hover:bg-gray-50"
          >
            {players}
          </button>
        ))}
        {inGame && (
          <button
            onClick={() => send('CATAN_FREE_PLAY')}
            className="px-2 py-0.5 border rounded hover:bg-gray-50"
          >
            Modo libre
          </button>
        )}
      </div>

      {game.phase === 'roll' && (
        <button
          onClick={() => send('CATAN_ROLL')}
          className="w-full mb-2 px-3 py-2 text-sm font-bold bg-amber-500 text-white rounded hover:bg-amber-600"
        >
          Tirar dados ({current})
        </button>
      )}

      {game.phase === 'main' && (
        <div className="mb-2 space-y-2">
          <button
            onClick={() => send('CATAN_END_TURN')}
            className="w-full px-3 py-2 text-sm font-bold bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Terminar turno
          </button>
          <div className="flex flex-wrap items-center gap-1 text-xs text-gray-600">
            <span>Banco 4:1</span>
            <select
              aria-label="Dar"
              value={give}
              onChange={(e) => setGive(e.target.value)}
              className="border rounded px-1 py-0.5 text-black"
            >
              {RESOURCES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <span>→</span>
            <select
              aria-label="Recibir"
              value={get}
              onChange={(e) => setGet(e.target.value)}
              className="border rounded px-1 py-0.5 text-black"
            >
              {RESOURCES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <button
              onClick={() => send('CATAN_BANK', { player: current, give, get })}
              className="px-2 py-0.5 border rounded hover:bg-gray-50"
            >
              Cambiar
            </button>
          </div>
        </div>
      )}

      {game.phase === 'discard' && (
        <div className="mb-2 space-y-2">
          {Object.entries(game.discards).map(([player, needed]) => {
            const chosen = discards[player] ?? {};
            const total = Object.values(chosen).reduce((a, b) => a + b, 0);
            return (
              <div key={player} data-testid={`discard-${player}`} className="text-xs text-black">
                <p className="font-semibold capitalize">
                  {player}: descarta {needed} ({total}/{needed})
                </p>
                <div className="flex flex-wrap gap-1">
                  {RESOURCES.map(([key, label]) => (
                    <input
                      key={key}
                      type="number"
                      min={0}
                      aria-label={`${label} de ${player}`}
                      value={chosen[key] ?? 0}
                      onChange={(e) => setDiscard(player, key, Number(e.target.value))}
                      className="w-12 border rounded px-1 py-0.5"
                    />
                  ))}
                </div>
                <button
                  onClick={() => send('CATAN_DISCARD', { player, cards: chosen })}
                  className="mt-1 px-2 py-0.5 border rounded hover:bg-gray-50"
                >
                  Descartar
                </button>
              </div>
            );
          })}
        </div>
      )}

      {game.phase === 'steal' && (
        <div className="mb-2 flex flex-wrap items-center gap-1 text-xs text-gray-600">
          <span>Robar a:</span>
          {game.victims.map((victim) => (
            <button
              key={victim}
              onClick={() => send('CATAN_STEAL', { victim })}
              className="px-2 py-0.5 border rounded capitalize hover:bg-gray-50"
            >
              {victim}
            </button>
          ))}
        </div>
      )}

      {game.phase === 'robber' && (
        <p className="mb-2 text-xs text-red-700">
          Elige "Ladrón" en el tablero y toca el hexágono donde quedará.
        </p>
      )}

      {game.phase === 'finished' && game.winner && (
        <p className="mb-2 text-sm font-bold text-green-700" data-testid="game-winner">
          ¡{game.winner} ganó!
        </p>
      )}

      {inGame && (
        <p className="text-[11px] text-gray-500">
          Costos:{' '}
          {Object.entries(game.costs)
            .map(
              ([kind, cost]) =>
                `${COST_LABELS[kind] ?? kind} ${Object.entries(cost)
                  .map(([res, n]) => `${n} ${RESOURCES.find(([k]) => k === res)?.[1] ?? res}`)
                  .join(' + ')}`
            )
            .join(' · ')}
        </p>
      )}
    </div>
  );
};
