import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanBoard } from './CatanBoard';
import * as api from '../services/api';
import type { CatanState } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

const corners = [
  [10, 0],
  [20, 5],
  [20, 15],
  [10, 20],
  [0, 15],
  [0, 5],
];

const catan: CatanState = {
  dice: null,
  total: null,
  producing: [{ q: 0, r: 0, resource: 'wood', number: 6 }],
  robber: [1, 0],
  payouts: {},
  players: ['rojo', 'azul'],
  buildings: [
    {
      vertex: [
        [0, 0],
        [0, 1],
        [1, 0],
      ],
      player: 'azul',
      kind: 'city',
    },
  ],
  board: {
    width: 300,
    height: 200,
    size: 70,
    tiles: [
      { q: 0, r: 0, resource: 'wood', number: 6, x: 100, y: 100, corners },
      { q: 1, r: 0, resource: 'desert', number: null, x: 200, y: 100, corners },
    ],
    vertices: [
      {
        id: [
          [0, 0],
          [0, 1],
          [1, 0],
        ],
        x: 150,
        y: 60,
      },
      {
        id: [
          [-1, 0],
          [-1, 1],
          [0, 0],
        ],
        x: 50,
        y: 60,
      },
    ],
  },
};

const withEdges: CatanState = {
  ...catan,
  roads: [
    {
      edge: [
        [0, 0],
        [1, 0],
      ],
      player: 'azul',
    },
  ],
  board: {
    ...catan.board!,
    edges: [
      {
        id: [
          [0, 0],
          [1, 0],
        ],
        x1: 0,
        y1: 0,
        x2: 10,
        y2: 0,
      },
      {
        id: [
          [0, 0],
          [0, 1],
        ],
        x1: 0,
        y1: 0,
        x2: 0,
        y2: 10,
      },
    ],
  },
};

describe('CatanBoard roads', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('draws existing roads in their owner color without road mode', () => {
    render(<CatanBoard catan={withEdges} />);
    expect(screen.getByTestId('edge-0')).toHaveAttribute('data-road', 'azul');
    expect(screen.queryByTestId('edge-1')).toBeNull();
  });

  it('builds a road for the selected player in road mode', async () => {
    render(<CatanBoard catan={withEdges} />);
    fireEvent.click(screen.getByRole('button', { name: 'Camino' }));
    fireEvent.click(screen.getByTestId('edge-1'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_ROAD',
        JSON.stringify({
          player: 'rojo',
          edge: [
            [0, 0],
            [0, 1],
          ],
        })
      )
    );
  });
});

describe('CatanBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('explains how to get a board when there is none', () => {
    render(<CatanBoard catan={null} />);
    expect(screen.getByText(/No hay un tablero de Catan/)).toBeInTheDocument();
  });

  it('shows buildings and the robber', () => {
    render(<CatanBoard catan={catan} />);
    expect(screen.getByTestId('vertex-0')).toHaveAttribute('data-building', 'azul:city');
    expect(screen.getByTestId('vertex-1')).toHaveAttribute('data-building', '');
    expect(screen.getByTestId('robber')).toBeInTheDocument();
  });

  it('builds for the first player by default', async () => {
    render(<CatanBoard catan={catan} />);
    fireEvent.click(screen.getByTestId('vertex-1'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_BUILD',
        JSON.stringify({
          player: 'rojo',
          vertex: [
            [-1, 0],
            [-1, 1],
            [0, 0],
          ],
        })
      )
    );
  });

  it('builds for the selected player', async () => {
    render(<CatanBoard catan={catan} />);
    fireEvent.click(screen.getByRole('button', { name: /azul/ }));
    fireEvent.click(screen.getByTestId('vertex-1'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_BUILD',
        JSON.stringify({
          player: 'azul',
          vertex: [
            [-1, 0],
            [-1, 1],
            [0, 0],
          ],
        })
      )
    );
  });

  it('removes a building in remove mode', async () => {
    render(<CatanBoard catan={catan} />);
    fireEvent.click(screen.getByRole('button', { name: 'Quitar' }));
    fireEvent.click(screen.getByTestId('vertex-0'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_REMOVE',
        JSON.stringify({
          vertex: [
            [0, 0],
            [0, 1],
            [1, 0],
          ],
        })
      )
    );
  });

  it('moves the robber only in robber mode', async () => {
    render(<CatanBoard catan={catan} />);
    fireEvent.click(screen.getByTestId('tile-0,0'));
    expect(api.injectAction).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Ladrón' }));
    fireEvent.click(screen.getByTestId('tile-0,0'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_ROBBER',
        JSON.stringify({ tile: [0, 0] })
      )
    );

    // Vertices do nothing while moving the robber.
    vi.mocked(api.injectAction).mockClear();
    fireEvent.click(screen.getByTestId('vertex-1'));
    expect(api.injectAction).not.toHaveBeenCalled();
  });

  it('shows an error if the action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanBoard catan={catan} />);
    fireEvent.click(screen.getByTestId('vertex-1'));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});
