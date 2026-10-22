import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { CatanGame } from './CatanGame';
import { CatanBoard } from './CatanBoard';
import * as api from '../services/api';
import type { CatanGameState, CatanState } from '../types/system';

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

const game = (patch: Partial<CatanGameState> = {}): CatanGameState => ({
  phase: 'order',
  current_player: 'rojo',
  turn: 0,
  setup_step: 'settlement',
  discards: {},
  victims: [],
  winner: null,
  hint: '',
  costs: {},
  phased: true,
  hidden: true,
  order: [],
  order_rolls: {},
  order_pending: ['rojo', 'azul'],
  reveal_done: 0,
  reveal_total: 37,
  ...patch,
});

const catan = (g: CatanGameState, hidden = true): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: hidden ? null : [0, 0],
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
        resource: hidden ? 'hidden' : 'wood',
        number: hidden ? null : 6,
        x: 100,
        y: 100,
        corners,
      },
    ],
    vertices: [],
  },
});

describe('phased game panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts a phased game only when the box is ticked', async () => {
    render(<CatanGame catan={catan(game({ phase: 'free', hidden: false }))} />);
    fireEvent.click(screen.getByLabelText('Nueva partida de 3'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_NEW_GAME',
        JSON.stringify({ players: 3, phased: false })
      )
    );
    fireEvent.click(screen.getByLabelText('Armar el tablero por fases'));
    fireEvent.click(screen.getByLabelText('Nueva partida de 4'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_NEW_GAME',
        JSON.stringify({ players: 4, phased: true })
      )
    );
  });

  it('lets each pending player roll for the first turn, with the app or their own die', async () => {
    render(
      <CatanGame
        catan={catan(game({ order_rolls: { rojo: 4 }, order_pending: ['azul', 'blanco'] }))}
      />
    );
    expect(screen.getByTestId('game-phase')).toHaveTextContent('¿Quién empieza?');
    expect(screen.getByTestId('order-panel')).toHaveTextContent('rojo 4');
    expect(screen.queryByLabelText('Tirar el dado de rojo')).toBeNull();

    fireEvent.click(screen.getByLabelText('Tirar el dado de azul'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_ORDER_ROLL',
        JSON.stringify({ player: 'azul' })
      )
    );

    fireEvent.change(screen.getByLabelText('Dado de blanco'), { target: { value: '5' } });
    fireEvent.click(screen.getByLabelText('Usar el dado de blanco'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_ORDER_ROLL',
        JSON.stringify({ player: 'blanco', value: 5 })
      )
    );
  });

  it('shows the reveal progress and reveals by hand', async () => {
    render(<CatanGame catan={catan(game({ phase: 'reveal', reveal_done: 5 }))} />);
    expect(screen.getByTestId('reveal-panel')).toHaveTextContent('5 de 37');
    fireEvent.click(screen.getByRole('button', { name: 'Revelar siguiente' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith('CATAN_REVEAL_NEXT', undefined)
    );
    fireEvent.click(screen.getByRole('button', { name: 'Revelar todo' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith('CATAN_REVEAL_ALL', undefined)
    );
  });

  it('reveals one step every 1.2 seconds in automatic mode and stops when unticked', async () => {
    vi.useFakeTimers();
    render(<CatanGame catan={catan(game({ phase: 'reveal' }))} />);
    fireEvent.click(screen.getByLabelText('Automático'));
    expect(api.injectAction).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3700);
    });
    expect(api.injectAction).toHaveBeenCalledTimes(3);
    expect(api.injectAction).toHaveBeenCalledWith('CATAN_REVEAL_NEXT');

    fireEvent.click(screen.getByLabelText('Automático'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.injectAction).toHaveBeenCalledTimes(3);
  });

  it('stops the automatic reveal when the reveal is over', async () => {
    vi.useFakeTimers();
    const { rerender } = render(<CatanGame catan={catan(game({ phase: 'reveal' }))} />);
    fireEvent.click(screen.getByLabelText('Automático'));
    rerender(<CatanGame catan={catan(game({ phase: 'roll', hidden: false }), false)} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.injectAction).not.toHaveBeenCalled();
  });
});

describe('hidden board on the dashboard', () => {
  it('draws hidden tiles as empty plates without numbers or robber', () => {
    render(<CatanBoard catan={catan(game({ phase: 'setup' }))} />);
    const polygon = screen.getByTestId('tile-0,0').querySelector('polygon');
    expect(polygon).toHaveAttribute('fill', '#cfd8dc');
    expect(screen.getByTestId('tile-0,0').querySelector('circle')).toBeNull();
    expect(screen.queryByTestId('robber')).toBeNull();
  });

  it('shows the colors, the numbers and the robber once revealed', () => {
    render(<CatanBoard catan={catan(game({ phase: 'roll', hidden: false }), false)} />);
    const tile = screen.getByTestId('tile-0,0');
    expect(tile.querySelector('polygon')).toHaveAttribute('fill', '#2e7d32');
    expect(tile).toHaveTextContent('6');
    expect(screen.getByTestId('robber')).toBeInTheDocument();
  });
});

describe('refused moves', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows why a move was refused and hides it after a few seconds', async () => {
    vi.useFakeTimers();
    const state = {
      ...catan(game({ phase: 'main', hidden: false }), false),
      notice: { id: 11, text: "It is rojo's turn" },
    };
    render(<CatanGame catan={state} />);
    expect(screen.getByTestId('game-notice')).toHaveTextContent("rojo's turn");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6100);
    });
    expect(screen.queryByTestId('game-notice')).toBeNull();
  });

  it('shows a new message even after an old one was hidden', async () => {
    vi.useFakeTimers();
    const base = catan(game({ phase: 'main', hidden: false }), false);
    const { rerender } = render(
      <CatanGame catan={{ ...base, notice: { id: 1, text: 'first' } }} />
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6100);
    });
    expect(screen.queryByTestId('game-notice')).toBeNull();
    rerender(<CatanGame catan={{ ...base, notice: { id: 2, text: 'second' } }} />);
    expect(screen.getByTestId('game-notice')).toHaveTextContent('second');
  });

  it('shows nothing when there is no notice', () => {
    render(<CatanGame catan={catan(game({ phase: 'main', hidden: false }), false)} />);
    expect(screen.queryByTestId('game-notice')).toBeNull();
  });
});
