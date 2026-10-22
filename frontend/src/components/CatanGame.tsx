import React, { useEffect, useState } from 'react';
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
  order: '¿Quién empieza?',
  setup: 'Preparación',
  reveal: 'Revelando el tablero',
  road_building: 'Caminos gratis',
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
  const [phased, setPhased] = useState(false);
  const [hiddenNotice, setHiddenNotice] = useState<number | null>(null);
  const [auto, setAuto] = useState(false);
  const [dice, setDice] = useState<Record<string, number>>({});
  const revealing = catan?.game?.phase === 'reveal';
  const noticeId = catan?.notice?.id ?? null;

  useEffect(() => {
    // A refused move stays on screen for a few seconds.
    if (noticeId === null) return;
    const timer = setTimeout(() => setHiddenNotice(noticeId), 6000);
    return () => clearTimeout(timer);
  }, [noticeId]);

  useEffect(() => {
    // Automatic reveal: one step every 1.2 seconds, one tile or token at a time.
    if (!auto || !revealing) return;
    const timer = setInterval(() => {
      injectAction('CATAN_REVEAL_NEXT').catch(() => undefined);
    }, 1200);
    return () => clearInterval(timer);
  }, [auto, revealing]);

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
  const rate = (current && catan.stats?.[current]?.rates?.[give]) || 4;

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
      {catan.notice && catan.notice.id !== hiddenNotice && (
        <p
          role="alert"
          data-testid="game-notice"
          className="mb-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700"
        >
          {catan.notice.text}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-1 text-xs text-gray-600 mb-2">
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={phased} onChange={(e) => setPhased(e.target.checked)} />
          Armar el tablero por fases
        </label>
        <span>Nueva partida:</span>
        {[2, 3, 4].map((players) => (
          <button
            key={players}
            aria-label={`Nueva partida de ${players}`}
            onClick={() => send('CATAN_NEW_GAME', { players, phased })}
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

      {game.phase === 'order' && (
        <div className="mb-2 space-y-2" data-testid="order-panel">
          {Object.entries(game.order_rolls ?? {}).length > 0 && (
            <p className="text-xs text-gray-700">
              Ya sacaron:{' '}
              {Object.entries(game.order_rolls ?? {})
                .map(([player, value]) => `${player} ${value}`)
                .join(', ')}
            </p>
          )}
          {(game.order_pending ?? []).map((player) => (
            <div key={player} className="flex flex-wrap items-center gap-1 text-xs text-black">
              <span className="font-semibold capitalize w-16">{player}</span>
              <button
                aria-label={`Tirar el dado de ${player}`}
                onClick={() => send('CATAN_ORDER_ROLL', { player })}
                className="px-2 py-0.5 border rounded hover:bg-gray-50"
              >
                Tirar dado
              </button>
              <input
                type="number"
                min={1}
                max={6}
                aria-label={`Dado de ${player}`}
                value={dice[player] ?? 1}
                onChange={(e) => setDice({ ...dice, [player]: Number(e.target.value) })}
                className="w-12 border rounded px-1 py-0.5"
              />
              <button
                aria-label={`Usar el dado de ${player}`}
                onClick={() => send('CATAN_ORDER_ROLL', { player, value: dice[player] ?? 1 })}
                className="px-2 py-0.5 border rounded hover:bg-gray-50"
              >
                Usar mi dado
              </button>
            </div>
          ))}
        </div>
      )}

      {game.phase === 'reveal' && (
        <div className="mb-2 space-y-2" data-testid="reveal-panel">
          <p className="text-xs text-gray-700">
            {game.reveal_done ?? 0} de {game.reveal_total ?? 0}
          </p>
          <div className="flex flex-wrap items-center gap-1 text-xs">
            <button
              onClick={() => send('CATAN_REVEAL_NEXT')}
              className="px-2 py-1 border rounded bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Revelar siguiente
            </button>
            <button
              onClick={() => send('CATAN_REVEAL_ALL')}
              className="px-2 py-1 border rounded hover:bg-gray-50"
            >
              Revelar todo
            </button>
            <label className="flex items-center gap-1 text-gray-700">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              Automático
            </label>
          </div>
        </div>
      )}

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
            <span data-testid="bank-rate">Banco {rate}:1</span>
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
