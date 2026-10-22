import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanStats } from './CatanStats';
import * as api from '../services/api';
import type { CatanState, CatanPlayerStats } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

const base: CatanPlayerStats = {
  settlements: 2,
  cities: 1,
  roads: 3,
  cards: 5,
  points: 4,
  hand: { wood: 2, brick: 0, sheep: 1, wheat: 2, ore: 0 },
  mode: 'simple',
};

const make = (rojoMode: 'simple' | 'resources'): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: [0, 0],
  payouts: {},
  buildings: [],
  board: null,
  players: ['rojo', 'azul'],
  stats: {
    rojo: { ...base, mode: rojoMode },
    azul: { ...base, settlements: 0, cities: 0, roads: 0, cards: 0, points: 0 },
  },
});

describe('CatanStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('renders nothing without a game', () => {
    const { container } = render(<CatanStats catan={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows pieces, cards and points for each player', () => {
    render(<CatanStats catan={make('simple')} />);
    const rojo = screen.getByTestId('stats-rojo');
    expect(rojo).toHaveTextContent('Casas 2');
    expect(rojo).toHaveTextContent('Ciudades 1');
    expect(rojo).toHaveTextContent('Caminos 3');
    expect(rojo).toHaveTextContent('Cartas 5');
    expect(rojo).toHaveTextContent('4 PV');
  });

  it('hides the hand in simple mode and shows it in resources mode', () => {
    const { rerender } = render(<CatanStats catan={make('simple')} />);
    expect(screen.queryByLabelText('Agregar Madera a rojo')).toBeNull();
    rerender(<CatanStats catan={make('resources')} />);
    expect(screen.getByLabelText('Agregar Madera a rojo')).toBeInTheDocument();
  });

  it('toggles one player mode', async () => {
    render(<CatanStats catan={make('simple')} />);
    fireEvent.click(screen.getByRole('button', { name: 'Modo de rojo' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_STATS_MODE',
        JSON.stringify({ player: 'rojo', mode: 'resources' })
      )
    );
  });

  it('sets the mode of everybody', async () => {
    render(<CatanStats catan={make('simple')} />);
    fireEvent.click(screen.getByRole('button', { name: 'Todos recursos' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_STATS_MODE',
        JSON.stringify({ player: 'all', mode: 'resources' })
      )
    );
  });

  it('adds and removes cards', async () => {
    render(<CatanStats catan={make('resources')} />);
    fireEvent.click(screen.getByLabelText('Agregar Madera a rojo'));
    fireEvent.click(screen.getByLabelText('Quitar Trigo a rojo'));
    await waitFor(() => expect(api.injectAction).toHaveBeenCalledTimes(2));
    expect(api.injectAction).toHaveBeenCalledWith(
      'CATAN_CARDS',
      JSON.stringify({ player: 'rojo', resource: 'wood', amount: 1 })
    );
    expect(api.injectAction).toHaveBeenCalledWith(
      'CATAN_CARDS',
      JSON.stringify({ player: 'rojo', resource: 'wheat', amount: -1 })
    );
  });

  it('changes the number of players', async () => {
    render(<CatanStats catan={make('simple')} />);
    fireEvent.click(screen.getByRole('button', { name: '3' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith('CATAN_PLAYERS', JSON.stringify({ count: 3 }))
    );
  });

  it('shows the error when an action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanStats catan={make('simple')} />);
    fireEvent.click(screen.getByRole('button', { name: '4' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});

describe('CatanStats longest road', () => {
  it('shows the card and the line length of the holder only', () => {
    const state = make('simple');
    state.stats = {
      rojo: { ...state.stats!.rojo, has_longest_road: true, longest_road: 6, points: 6 },
      azul: { ...state.stats!.azul, has_longest_road: false, longest_road: 3 },
    };
    render(<CatanStats catan={state} />);
    expect(screen.getByTestId('longest-rojo')).toHaveTextContent('Camino más largo (6 caminos)');
    expect(screen.getByTestId('longest-rojo')).toHaveTextContent('+2 puntos');
    expect(screen.queryByTestId('longest-azul')).toBeNull();
    expect(screen.getByTestId('stats-azul')).toHaveTextContent('línea de 3');
  });
});
