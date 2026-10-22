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

const CARD_LABELS: Record<string, string> = {
  knight: 'Caballero',
  victory_point: 'Punto de victoria',
  road_building: 'Construcción de caminos',
  year_of_plenty: 'Año de abundancia',
  monopoly: 'Monopolio',
};

const CARD_HELP: Record<string, string> = {
  knight: 'Mueve al ladrón y roba una carta. Tres caballeros dan el Ejército más grande.',
  victory_point: 'Vale 1 punto, no se juega: cuenta al final.',
  road_building: 'Pones 2 caminos gratis.',
  year_of_plenty: 'Tomas 2 recursos del banco.',
  monopoly: 'Todos te dan sus cartas de un recurso.',
};

const PLAYABLE_PHASES = ['roll', 'main'];

interface CatanDevProps {
  catan?: CatanState | null;
}

export const CatanDev: React.FC<CatanDevProps> = ({ catan }) => {
  const [error, setError] = useState<string | null>(null);
  const [plenty, setPlenty] = useState<[string, string]>(['wood', 'ore']);
  const [monopoly, setMonopoly] = useState('wheat');

  const game = catan?.game;
  const dev = game?.dev;
  if (!catan || !game || !dev) return null;
  const visible = ['roll', 'main', 'road_building', 'robber', 'steal', 'discard'].includes(
    game.phase
  );
  if (!visible || !game.current_player) return null;

  const player = game.current_player;
  const send = async (action: string, payload?: unknown) => {
    try {
      setError(null);
      await injectAction(action, payload === undefined ? undefined : JSON.stringify(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la acción');
    }
  };

  const cards = Object.entries(dev.hand).filter(([, n]) => n > 0);
  const canPlay = PLAYABLE_PHASES.includes(game.phase) && !dev.played;
  const boughtNow = (card: string) => dev.bought.filter((c) => c === card).length;

  const resourceSelect = (label: string, value: string, onChange: (v: string) => void) => (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="border rounded px-1 py-0.5 text-black"
    >
      {RESOURCES.map(([key, name]) => (
        <option key={key} value={key}>
          {name}
        </option>
      ))}
    </select>
  );

  return (
    <div data-testid="catan-dev">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Cartas de desarrollo de <span className="capitalize">{player}</span>
      </h3>

      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

      <div className="mb-2 flex items-center gap-2 text-xs text-gray-600">
        <button
          onClick={() => send('CATAN_DEV_BUY', { player })}
          disabled={game.phase !== 'main' || dev.deck_left === 0}
          className="px-2 py-1 border rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Comprar carta
        </button>
        <span data-testid="deck-left">Quedan {dev.deck_left} en el mazo</span>
      </div>
      <p className="mb-2 text-[11px] text-gray-500">Cuesta 1 oveja, 1 trigo y 1 mineral.</p>

      {game.phase === 'road_building' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-black" data-testid="free-roads">
          <span>Caminos gratis que quedan: {dev.free_roads}</span>
          <button
            onClick={() => send('CATAN_DEV_SKIP', { player })}
            className="px-2 py-0.5 border rounded hover:bg-gray-50"
          >
            Terminar caminos
          </button>
        </div>
      )}

      {cards.length === 0 ? (
        <p className="text-xs italic text-gray-400">No tiene cartas de desarrollo.</p>
      ) : (
        <ul className="space-y-2">
          {cards.map(([card, count]) => {
            const fresh = boughtNow(card);
            const ready = count - fresh > 0;
            const playable = card !== 'victory_point';
            return (
              <li
                key={card}
                data-testid={`dev-${card}`}
                className="rounded border border-gray-200 p-2 text-xs text-black"
              >
                <p className="font-semibold">
                  {CARD_LABELS[card] ?? card} × {count}
                  {fresh > 0 && <span className="ml-1 text-amber-700">({fresh} nueva)</span>}
                </p>
                <p className="text-gray-500">{CARD_HELP[card]}</p>
                {playable && (
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    {card === 'year_of_plenty' && (
                      <>
                        {resourceSelect('Primer recurso', plenty[0], (v) =>
                          setPlenty([v, plenty[1]])
                        )}
                        {resourceSelect('Segundo recurso', plenty[1], (v) =>
                          setPlenty([plenty[0], v])
                        )}
                      </>
                    )}
                    {card === 'monopoly' &&
                      resourceSelect('Recurso del monopolio', monopoly, setMonopoly)}
                    <button
                      aria-label={`Jugar ${CARD_LABELS[card]}`}
                      disabled={!canPlay || !ready}
                      title={
                        !ready
                          ? 'Se compró en este turno'
                          : dev.played
                            ? 'Ya se jugó una carta este turno'
                            : undefined
                      }
                      onClick={() =>
                        send('CATAN_DEV_PLAY', {
                          player,
                          card,
                          ...(card === 'year_of_plenty' ? { resources: plenty } : {}),
                          ...(card === 'monopoly' ? { resource: monopoly } : {}),
                        })
                      }
                      className="px-2 py-0.5 border rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Jugar
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
