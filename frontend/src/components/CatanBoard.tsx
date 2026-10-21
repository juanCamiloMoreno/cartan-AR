import React, { useState } from 'react';
import { injectAction } from '../services/api';
import type { CatanState } from '../types/system';

const RESOURCE_COLORS: Record<string, string> = {
  wood: '#2e7d32',
  sheep: '#9ccc65',
  wheat: '#fbc02d',
  brick: '#c2572b',
  ore: '#78909c',
  desert: '#e6d3a3',
};

const PLAYER_COLORS: Record<string, string> = {
  rojo: '#dc2828',
  azul: '#1e78dc',
  blanco: '#f0f0f0',
  naranja: '#ff8c00',
};

type Mode = 'build' | 'remove' | 'robber';

const MODE_HINTS: Record<Mode, string> = {
  build: 'Toca una esquina: pone una casa. Si ya hay una casa tuya, la sube a ciudad.',
  remove: 'Toca una casa o ciudad para quitarla.',
  robber: 'Toca un hexágono para mover al ladrón.',
};

interface CatanBoardProps {
  catan?: CatanState | null;
}

export const CatanBoard: React.FC<CatanBoardProps> = ({ catan }) => {
  const [player, setPlayer] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('build');
  const [error, setError] = useState<string | null>(null);

  const board = catan?.board;
  if (!catan || !board) {
    return (
      <p className="text-sm italic text-gray-500">
        No hay un tablero de Catan cargado. Genera uno con scripts/generate_catan_board.py y cárgalo
        desde la biblioteca de mapas.
      </p>
    );
  }

  const activePlayer = player ?? catan.players[0];
  const buildingAt = new Map(catan.buildings.map((b) => [JSON.stringify(b.vertex), b]));
  const producing = new Set(catan.producing.map((t) => `${t.q},${t.r}`));
  const robberTile = board.tiles.find((t) => t.q === catan.robber[0] && t.r === catan.robber[1]);

  const send = async (action: string, payload: unknown) => {
    try {
      setError(null);
      await injectAction(action, JSON.stringify(payload));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar la acción');
    }
  };

  const onVertex = (id: [number, number][]) => {
    if (mode === 'build') send('CATAN_BUILD', { player: activePlayer, vertex: id });
    if (mode === 'remove') send('CATAN_REMOVE', { vertex: id });
  };

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="flex flex-wrap items-center gap-2">
        {catan.players.map((name) => (
          <button
            key={name}
            onClick={() => setPlayer(name)}
            aria-pressed={activePlayer === name}
            className={`flex items-center gap-2 px-3 py-1 rounded border text-sm capitalize ${
              activePlayer === name ? 'border-blue-600 bg-blue-50 font-semibold' : 'border-gray-300'
            }`}
          >
            <span
              className="inline-block w-3 h-3 rounded-sm border border-gray-700"
              style={{ backgroundColor: PLAYER_COLORS[name] ?? '#999' }}
            />
            {name}
          </button>
        ))}
        <span className="mx-2 text-gray-300">|</span>
        {(
          [
            ['build', 'Construir'],
            ['remove', 'Quitar'],
            ['robber', 'Ladrón'],
          ] as [Mode, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setMode(value)}
            aria-pressed={mode === value}
            className={`px-3 py-1 rounded border text-sm ${
              mode === value ? 'border-amber-600 bg-amber-50 font-semibold' : 'border-gray-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-600">{MODE_HINTS[mode]}</p>
      {error && <p className="text-xs text-red-600">{error}</p>}

      <svg
        viewBox={`0 0 ${board.width} ${board.height}`}
        className="flex-1 min-h-0 max-h-full w-full"
        role="img"
        aria-label="Tablero de Catan"
      >
        <rect width={board.width} height={board.height} fill="#1e88e5" rx={12} />
        {board.tiles.map((tile) => {
          const key = `${tile.q},${tile.r}`;
          return (
            <g
              key={key}
              data-testid={`tile-${key}`}
              onClick={() => mode === 'robber' && send('CATAN_ROBBER', { tile: [tile.q, tile.r] })}
              style={{ cursor: mode === 'robber' ? 'pointer' : 'default' }}
            >
              <polygon
                points={tile.corners.map((c) => c.join(',')).join(' ')}
                fill={RESOURCE_COLORS[tile.resource] ?? '#ccc'}
                stroke={producing.has(key) ? '#ffd700' : '#f5f5f5'}
                strokeWidth={producing.has(key) ? 7 : 3}
              />
              {tile.number !== null && (
                <>
                  <circle cx={tile.x} cy={tile.y} r={21} fill="#fff8e1" stroke="#212121" />
                  <text
                    x={tile.x}
                    y={tile.y + 7}
                    textAnchor="middle"
                    fontSize={20}
                    fontWeight="bold"
                    fill={tile.number === 6 || tile.number === 8 ? '#c62828' : '#212121'}
                  >
                    {tile.number}
                  </text>
                </>
              )}
            </g>
          );
        })}

        {robberTile && (
          <circle
            data-testid="robber"
            cx={robberTile.x}
            cy={robberTile.y}
            r={12}
            fill="#1e1e1e"
            stroke="#fff"
            strokeWidth={2}
            pointerEvents="none"
          />
        )}

        {board.vertices.map((vertex, index) => {
          const building = buildingAt.get(JSON.stringify(vertex.id));
          const size = building?.kind === 'city' ? 13 : 9;
          return (
            <g
              key={index}
              data-testid={`vertex-${index}`}
              data-building={building ? `${building.player}:${building.kind}` : ''}
              onClick={() => onVertex(vertex.id)}
              style={{ cursor: mode === 'robber' ? 'default' : 'pointer' }}
            >
              {building ? (
                <rect
                  x={vertex.x - size}
                  y={vertex.y - size}
                  width={size * 2}
                  height={size * 2}
                  fill={PLAYER_COLORS[building.player] ?? '#999'}
                  stroke="#141414"
                  strokeWidth={2}
                />
              ) : (
                <circle
                  cx={vertex.x}
                  cy={vertex.y}
                  r={7}
                  fill="#ffffff"
                  fillOpacity={mode === 'robber' ? 0 : 0.35}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
