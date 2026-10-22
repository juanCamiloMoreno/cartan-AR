import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanGame } from './CatanGame';
import { CatanBoard } from './CatanBoard';
import * as api from '../services/api';
import type { CatanGameState, CatanState } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

const costs = {
  road: { wood: 1, brick: 1 },
  settlement: { wood: 1, brick: 1, sheep: 1, wheat: 1 },
  city: { wheat: 2, ore: 3 },
};

const game = (patch: Partial<CatanGameState> = {}): CatanGameState => ({
  phase: 'main',
  current_player: 'rojo',
  turn: 3,
  setup_step: 'settlement',
  discards: {},
  victims: [],
  winner: null,
  hint: 'Turno de rojo: construye, comercia o termina el turno.',
  costs,
  ...patch,
});

const catan = (g: CatanGameState): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: [0, 0],
  payouts: {},
  buildings: [],
  players: ['rojo', 'azul'],
  game: g,
  board: {
    width: 300,
    height: 200,
    size: 70,
    tiles: [
      {
        q: 0,
        r: 0,
        resource: 'wood',
        number: 6,
        x: 100,
        y: 100,
        corners: [
          [10, 0],
          [20, 5],
          [20, 15],
          [10, 20],
          [0, 15],
          [0, 5],
        ],
      },
    ],
    vertices: [],
    edges: [],
  },
});

describe('CatanGame', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('renders nothing without a game state', () => {
    const { container } = render(<CatanGame catan={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the phase, the turn and the hint', () => {
    render(<CatanGame catan={catan(game())} />);
    expect(screen.getByTestId('game-phase')).toHaveTextContent('Turno · turno 3');
    expect(screen.getByTestId('game-hint')).toHaveTextContent('Turno de rojo');
  });

  it('starts a game with the chosen number of players', async () => {
    render(<CatanGame catan={catan(game({ phase: 'free', turn: 0, hint: 'Modo libre' }))} />);
    fireEvent.click(screen.getByLabelText('Nueva partida de 3'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_NEW_GAME',
        JSON.stringify({ players: 3, phased: false })
      )
    );
    expect(screen.queryByRole('button', { name: 'Terminar turno' })).toBeNull();
  });

  it('can leave the game for the free mode', async () => {
    render(<CatanGame catan={catan(game())} />);
    fireEvent.click(screen.getByRole('button', { name: 'Modo libre' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith('CATAN_FREE_PLAY', undefined)
    );
  });

  it('rolls the dice only in the roll phase', async () => {
    const { rerender } = render(<CatanGame catan={catan(game({ phase: 'roll' }))} />);
    fireEvent.click(screen.getByRole('button', { name: /Tirar dados \(rojo\)/ }));
    await waitFor(() => expect(api.injectAction).toHaveBeenCalledWith('CATAN_ROLL', undefined));
    rerender(<CatanGame catan={catan(game({ phase: 'main' }))} />);
    expect(screen.queryByRole('button', { name: /Tirar dados/ })).toBeNull();
  });

  it('ends the turn and trades with the bank in the main phase', async () => {
    render(<CatanGame catan={catan(game())} />);
    fireEvent.click(screen.getByRole('button', { name: 'Terminar turno' }));
    await waitFor(() => expect(api.injectAction).toHaveBeenCalledWith('CATAN_END_TURN', undefined));

    fireEvent.change(screen.getByLabelText('Dar'), { target: { value: 'brick' } });
    fireEvent.change(screen.getByLabelText('Recibir'), { target: { value: 'wheat' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cambiar' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_BANK',
        JSON.stringify({ player: 'rojo', give: 'brick', get: 'wheat' })
      )
    );
  });

  it('collects the cards to discard after a 7', async () => {
    render(<CatanGame catan={catan(game({ phase: 'discard', discards: { azul: 4 } }))} />);
    expect(screen.getByTestId('discard-azul')).toHaveTextContent('descarta 4 (0/4)');
    fireEvent.change(screen.getByLabelText('Madera de azul'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Mineral de azul'), { target: { value: '1' } });
    expect(screen.getByTestId('discard-azul')).toHaveTextContent('(4/4)');
    fireEvent.click(screen.getByRole('button', { name: 'Descartar' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DISCARD',
        JSON.stringify({ player: 'azul', cards: { wood: 3, ore: 1 } })
      )
    );
  });

  it('lets the current player choose who to rob', async () => {
    render(<CatanGame catan={catan(game({ phase: 'steal', victims: ['azul'] }))} />);
    fireEvent.click(screen.getByRole('button', { name: 'azul' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_STEAL',
        JSON.stringify({ victim: 'azul' })
      )
    );
  });

  it('tells how to place the robber and announces the winner', () => {
    const { rerender } = render(<CatanGame catan={catan(game({ phase: 'robber' }))} />);
    expect(screen.getByText(/toca el hexágono/)).toBeInTheDocument();
    rerender(<CatanGame catan={catan(game({ phase: 'finished', winner: 'azul' }))} />);
    expect(screen.getByTestId('game-winner')).toHaveTextContent('azul ganó');
  });

  it('lists the building costs during a game', () => {
    render(<CatanGame catan={catan(game())} />);
    expect(screen.getByText(/Ciudad 2 Trigo \+ 3 Mineral/)).toBeInTheDocument();
  });

  it('shows the error when an action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanGame catan={catan(game())} />);
    fireEvent.click(screen.getByRole('button', { name: 'Terminar turno' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});

describe('CatanBoard during a game', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('switches to the robber mode by itself and moves the robber on a tile click', async () => {
    render(<CatanBoard catan={catan(game({ phase: 'robber' }))} />);
    fireEvent.click(screen.getByTestId('tile-0,0'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_ROBBER',
        JSON.stringify({ tile: [0, 0] })
      )
    );
  });

  it('does not offer to remove pieces during a game but does in free mode', () => {
    const { rerender } = render(<CatanBoard catan={catan(game())} />);
    expect(screen.queryByRole('button', { name: 'Quitar' })).toBeNull();
    rerender(<CatanBoard catan={catan(game({ phase: 'free' }))} />);
    expect(screen.getByRole('button', { name: 'Quitar' })).toBeInTheDocument();
  });

  it('follows the setup step: settlement first, then the road', () => {
    const { rerender } = render(
      <CatanBoard catan={catan(game({ phase: 'setup', setup_step: 'settlement' }))} />
    );
    expect(screen.getByRole('button', { name: 'Construir' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    rerender(<CatanBoard catan={catan(game({ phase: 'setup', setup_step: 'road' }))} />);
    expect(screen.getByRole('button', { name: 'Camino' })).toHaveAttribute('aria-pressed', 'true');
  });
});
