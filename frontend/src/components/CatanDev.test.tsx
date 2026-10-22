import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanDev } from './CatanDev';
import { CatanStats } from './CatanStats';
import * as api from '../services/api';
import type { CatanGameState, CatanPlayerStats, CatanState } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

type Dev = NonNullable<CatanGameState['dev']>;

const dev = (patch: Partial<Dev> = {}): Dev => ({
  deck_left: 20,
  hand: {},
  bought: [],
  played: false,
  free_roads: 0,
  ...patch,
});

const game = (
  phase: CatanGameState['phase'] = 'main',
  devPatch: Partial<Dev> = {}
): CatanGameState => ({
  phase,
  current_player: 'rojo',
  turn: 4,
  setup_step: 'settlement',
  discards: {},
  victims: [],
  winner: null,
  hint: '',
  costs: {},
  dev: dev(devPatch),
});

const catan = (g: CatanGameState | null): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: [0, 0],
  payouts: {},
  buildings: [],
  players: ['rojo', 'azul'],
  board: null,
  game: g,
});

describe('CatanDev', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('renders nothing without a game or while the board is being prepared', () => {
    const { container, rerender } = render(<CatanDev catan={catan(null)} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CatanDev catan={catan(game('setup'))} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the deck and buys a card in the main phase only', async () => {
    const { rerender } = render(<CatanDev catan={catan(game('main'))} />);
    expect(screen.getByTestId('deck-left')).toHaveTextContent('Quedan 20 en el mazo');
    fireEvent.click(screen.getByRole('button', { name: 'Comprar carta' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DEV_BUY',
        JSON.stringify({ player: 'rojo' })
      )
    );
    rerender(<CatanDev catan={catan(game('roll'))} />);
    expect(screen.getByRole('button', { name: 'Comprar carta' })).toBeDisabled();
    rerender(<CatanDev catan={catan(game('main', { deck_left: 0 }))} />);
    expect(screen.getByRole('button', { name: 'Comprar carta' })).toBeDisabled();
  });

  it('lists the cards of the player in turn with what each one does', () => {
    render(<CatanDev catan={catan(game('main', { hand: { knight: 2, victory_point: 1 } }))} />);
    expect(screen.getByTestId('dev-knight')).toHaveTextContent('Caballero × 2');
    expect(screen.getByTestId('dev-knight')).toHaveTextContent('Tres caballeros');
    expect(screen.getByTestId('dev-victory_point')).toHaveTextContent('no se juega');
    expect(screen.queryByLabelText('Jugar Punto de victoria')).toBeNull();
  });

  it('plays a knight', async () => {
    render(<CatanDev catan={catan(game('main', { hand: { knight: 1 } }))} />);
    fireEvent.click(screen.getByLabelText('Jugar Caballero'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DEV_PLAY',
        JSON.stringify({ player: 'rojo', card: 'knight' })
      )
    );
  });

  it('plays year of plenty with the two chosen resources', async () => {
    render(<CatanDev catan={catan(game('main', { hand: { year_of_plenty: 1 } }))} />);
    fireEvent.change(screen.getByLabelText('Primer recurso'), { target: { value: 'brick' } });
    fireEvent.change(screen.getByLabelText('Segundo recurso'), { target: { value: 'sheep' } });
    fireEvent.click(screen.getByLabelText('Jugar Año de abundancia'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DEV_PLAY',
        JSON.stringify({ player: 'rojo', card: 'year_of_plenty', resources: ['brick', 'sheep'] })
      )
    );
  });

  it('plays monopoly on the chosen resource', async () => {
    render(<CatanDev catan={catan(game('main', { hand: { monopoly: 1 } }))} />);
    fireEvent.change(screen.getByLabelText('Recurso del monopolio'), { target: { value: 'ore' } });
    fireEvent.click(screen.getByLabelText('Jugar Monopolio'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DEV_PLAY',
        JSON.stringify({ player: 'rojo', card: 'monopoly', resource: 'ore' })
      )
    );
  });

  it('blocks a card bought this turn and any second card in the same turn', () => {
    const { rerender } = render(
      <CatanDev catan={catan(game('main', { hand: { knight: 1 }, bought: ['knight'] }))} />
    );
    expect(screen.getByTestId('dev-knight')).toHaveTextContent('1 nueva');
    expect(screen.getByLabelText('Jugar Caballero')).toBeDisabled();
    rerender(<CatanDev catan={catan(game('main', { hand: { knight: 2 }, bought: ['knight'] }))} />);
    expect(screen.getByLabelText('Jugar Caballero')).toBeEnabled(); // one was bought earlier
    rerender(<CatanDev catan={catan(game('main', { hand: { knight: 1 }, played: true }))} />);
    expect(screen.getByLabelText('Jugar Caballero')).toBeDisabled();
  });

  it('can play a card before rolling but not while the robber moves', () => {
    const { rerender } = render(<CatanDev catan={catan(game('roll', { hand: { knight: 1 } }))} />);
    expect(screen.getByLabelText('Jugar Caballero')).toBeEnabled();
    rerender(<CatanDev catan={catan(game('robber', { hand: { knight: 1 } }))} />);
    expect(screen.getByLabelText('Jugar Caballero')).toBeDisabled();
  });

  it('shows the free roads that are left and lets you stop', async () => {
    render(<CatanDev catan={catan(game('road_building', { free_roads: 2 }))} />);
    expect(screen.getByTestId('free-roads')).toHaveTextContent('que quedan: 2');
    fireEvent.click(screen.getByRole('button', { name: 'Terminar caminos' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_DEV_SKIP',
        JSON.stringify({ player: 'rojo' })
      )
    );
  });

  it('says when there are no cards and shows the error when an action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanDev catan={catan(game('main'))} />);
    expect(screen.getByText('No tiene cartas de desarrollo.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Comprar carta' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});

describe('CatanStats with the army and the development cards', () => {
  const stats = (patch: Partial<CatanPlayerStats>): CatanPlayerStats => ({
    settlements: 2,
    cities: 0,
    roads: 2,
    cards: 3,
    points: 2,
    hand: {},
    mode: 'simple',
    ...patch,
  });

  it('shows the army card, the knights and how many development cards each one holds', () => {
    const state = catan(null);
    state.stats = {
      rojo: stats({ has_largest_army: true, knights: 3, dev_cards: 2, points: 4 }),
      azul: stats({ knights: 1 }),
    };
    render(<CatanStats catan={state} />);
    expect(screen.getByTestId('army-rojo')).toHaveTextContent('Ejército más grande (3 caballeros)');
    expect(screen.queryByTestId('army-azul')).toBeNull();
    expect(screen.getByTestId('stats-rojo')).toHaveTextContent('Desarrollo 2');
    expect(screen.getByTestId('stats-azul')).toHaveTextContent('Caballeros 1');
  });
});
