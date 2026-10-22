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

const NAMES: Record<string, string> = Object.fromEntries(
  RESOURCES.map(([key, name]) => [key, name.toLowerCase()])
);

type Cards = Record<string, number>;

const describe = (cards: Cards) =>
  Object.entries(cards)
    .filter(([, n]) => n > 0)
    .map(([key, n]) => `${n} ${NAMES[key] ?? key}`)
    .join(' + ');

interface CatanTradeProps {
  catan?: CatanState | null;
}

export const CatanTrade: React.FC<CatanTradeProps> = ({ catan }) => {
  const [error, setError] = useState<string | null>(null);
  const [give, setGive] = useState<Cards>({});
  const [get, setGet] = useState<Cards>({});
  const [to, setTo] = useState('');

  const game = catan?.game;
  if (!catan || !game || game.phase !== 'main' || !game.current_player) return null;

  const player = game.current_player;
  const others = catan.players.filter((p) => p !== player);
  const trade = game.trade;

  const send = async (action: string, payload: unknown) => {
    try {
      setError(null);
      await injectAction(action, JSON.stringify(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la acción');
    }
  };

  const total = (cards: Cards) => Object.values(cards).reduce((a, b) => a + b, 0);
  const overlap = Object.keys(give).some((k) => (give[k] ?? 0) > 0 && (get[k] ?? 0) > 0);
  const canOffer = total(give) > 0 && total(get) > 0 && !overlap;

  const setCount = (cards: Cards, set: (c: Cards) => void, key: string, value: number) =>
    set({ ...cards, [key]: Math.max(0, Number.isFinite(value) ? value : 0) });

  const row = (label: string, cards: Cards, set: (c: Cards) => void, suffix: string) => (
    <div className="flex flex-wrap items-center gap-1 text-xs text-gray-700">
      <span className="w-12 font-semibold">{label}</span>
      {RESOURCES.map(([key, name]) => (
        <label key={key} className="flex flex-col items-center">
          <span className="text-[10px] text-gray-500">{name}</span>
          <input
            type="number"
            min={0}
            aria-label={`${name} que ${suffix}`}
            value={cards[key] ?? 0}
            onChange={(e) => setCount(cards, set, key, Number(e.target.value))}
            className="w-11 border rounded px-1 py-0.5 text-black"
          />
        </label>
      ))}
    </div>
  );

  return (
    <div data-testid="catan-trade">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Comercio entre jugadores
      </h3>

      {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

      {trade ? (
        <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-black space-y-2">
          <p data-testid="trade-offer">
            <span className="font-semibold capitalize">{trade.from}</span> da {describe(trade.give)}{' '}
            por {describe(trade.get)}
            {trade.to ? ` (solo para ${trade.to})` : ' (para cualquiera)'}.
          </p>
          <div className="flex flex-wrap gap-2">
            {others
              .filter((p) => !trade.to || trade.to === p)
              .map((p) => (
                <span key={p} className="flex items-center gap-1">
                  <span className="capitalize">{p}:</span>
                  {trade.declined.includes(p) ? (
                    <span className="text-gray-500">rechazó</span>
                  ) : (
                    <>
                      <button
                        aria-label={`Aceptar ${p}`}
                        onClick={() => send('CATAN_TRADE_ACCEPT', { player: p })}
                        className="px-2 py-0.5 border rounded bg-emerald-600 text-white hover:bg-emerald-700"
                      >
                        Acepta
                      </button>
                      <button
                        aria-label={`Rechazar ${p}`}
                        onClick={() => send('CATAN_TRADE_DECLINE', { player: p })}
                        className="px-2 py-0.5 border rounded hover:bg-gray-50"
                      >
                        Rechaza
                      </button>
                    </>
                  )}
                </span>
              ))}
          </div>
          <button
            onClick={() => send('CATAN_TRADE_CANCEL', { player: trade.from })}
            className="px-2 py-0.5 border rounded hover:bg-gray-50"
          >
            Cancelar oferta
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-gray-600">
            Oferta de <span className="font-semibold capitalize">{player}</span>:
          </p>
          {row('Das', give, setGive, 'das')}
          {row('Pides', get, setGet, 'pides')}
          <div className="flex items-center gap-2 text-xs text-gray-700">
            <label className="flex items-center gap-1">
              Para
              <select
                aria-label="Para"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className="border rounded px-1 py-0.5 text-black"
              >
                <option value="">Cualquiera</option>
                {others.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <button
              disabled={!canOffer}
              onClick={() =>
                send('CATAN_TRADE_OFFER', {
                  player,
                  give: Object.fromEntries(Object.entries(give).filter(([, n]) => n > 0)),
                  get: Object.fromEntries(Object.entries(get).filter(([, n]) => n > 0)),
                  ...(to ? { to } : {}),
                })
              }
              className="px-2 py-1 border rounded bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Ofrecer
            </button>
          </div>
          {overlap && (
            <p className="text-[11px] text-red-600">
              No se puede cambiar un recurso por el mismo recurso.
            </p>
          )}
        </div>
      )}

      {game.last_trade && (
        <p data-testid="last-trade" className="mt-2 text-[11px] text-gray-600">
          Último intercambio: <span className="capitalize">{game.last_trade.from}</span> dio{' '}
          {describe(game.last_trade.give)} a{' '}
          <span className="capitalize">{game.last_trade.to}</span> por{' '}
          {describe(game.last_trade.get)}.
        </p>
      )}
    </div>
  );
};
