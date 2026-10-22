import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanTrade } from './CatanTrade';
import * as api from '../services/api';
import type { CatanGameState, CatanState } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

type Trade = NonNullable<CatanGameState['trade']>;

const game = (
  phase: CatanGameState['phase'] = 'main',
  patch: Partial<CatanGameState> = {}
): CatanGameState => ({
  phase,
  current_player: 'rojo',
  turn: 3,
  setup_step: 'settlement',
  discards: {},
  victims: [],
  winner: null,
  hint: '',
  costs: {},
  trade: null,
  last_trade: null,
  ...patch,
});

const catan = (g: CatanGameState | null): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: [0, 0],
  payouts: {},
  buildings: [],
  players: ['rojo', 'azul', 'blanco'],
  board: null,
  game: g,
});

const offer = (patch: Partial<Trade> = {}): Trade => ({
  from: 'rojo',
  give: { wood: 2 },
  get: { ore: 1 },
  to: null,
  declined: [],
  ...patch,
});

describe('CatanTrade', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('renders nothing outside the main phase or without a game', () => {
    const { container, rerender } = render(<CatanTrade catan={catan(null)} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CatanTrade catan={catan(game('roll'))} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('builds an offer from the cards and sends it to everybody by default', async () => {
    render(<CatanTrade catan={catan(game())} />);
    expect(screen.getByRole('button', { name: 'Ofrecer' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Madera que das'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Mineral que pides'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ofrecer' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_TRADE_OFFER',
        JSON.stringify({ player: 'rojo', give: { wood: 2 }, get: { ore: 1 } })
      )
    );
  });

  it('can address the offer to one player', async () => {
    render(<CatanTrade catan={catan(game())} />);
    fireEvent.change(screen.getByLabelText('Trigo que das'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Oveja que pides'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'azul' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ofrecer' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_TRADE_OFFER',
        JSON.stringify({ player: 'rojo', give: { wheat: 1 }, get: { sheep: 3 }, to: 'azul' })
      )
    );
    expect(screen.queryByRole('option', { name: 'rojo' })).toBeNull(); // you do not trade with yourself
  });

  it('warns and blocks a trade of one resource for the same resource', () => {
    render(<CatanTrade catan={catan(game())} />);
    fireEvent.change(screen.getByLabelText('Madera que das'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Madera que pides'), { target: { value: '2' } });
    expect(screen.getByRole('button', { name: 'Ofrecer' })).toBeDisabled();
    expect(screen.getByText(/por el mismo recurso/)).toBeInTheDocument();
  });

  it('shows the open offer and lets each player accept or decline', async () => {
    render(<CatanTrade catan={catan(game('main', { trade: offer() }))} />);
    expect(screen.getByTestId('trade-offer')).toHaveTextContent('da 2 madera por 1 mineral');
    expect(screen.getByTestId('trade-offer')).toHaveTextContent('para cualquiera');
    expect(screen.queryByRole('button', { name: 'Ofrecer' })).toBeNull();

    fireEvent.click(screen.getByLabelText('Aceptar azul'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_TRADE_ACCEPT',
        JSON.stringify({ player: 'azul' })
      )
    );
    fireEvent.click(screen.getByLabelText('Rechazar blanco'));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_TRADE_DECLINE',
        JSON.stringify({ player: 'blanco' })
      )
    );
  });

  it('shows who declined and only the player an offer is meant for', () => {
    render(
      <CatanTrade
        catan={catan(game('main', { trade: offer({ to: 'azul', declined: ['azul'] }) }))}
      />
    );
    expect(screen.getByTestId('trade-offer')).toHaveTextContent('solo para azul');
    expect(screen.getByText('rechazó')).toBeInTheDocument();
    expect(screen.queryByLabelText('Aceptar blanco')).toBeNull();
    expect(screen.queryByLabelText('Aceptar azul')).toBeNull();
  });

  it('lets the proposer cancel the offer', async () => {
    render(<CatanTrade catan={catan(game('main', { trade: offer() }))} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar oferta' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_TRADE_CANCEL',
        JSON.stringify({ player: 'rojo' })
      )
    );
  });

  it('remembers the last exchange', () => {
    const last = { from: 'rojo', to: 'azul', give: { wood: 2 }, get: { ore: 1 } };
    render(<CatanTrade catan={catan(game('main', { last_trade: last }))} />);
    expect(screen.getByTestId('last-trade')).toHaveTextContent(
      'rojo dio 2 madera a azul por 1 mineral'
    );
  });

  it('shows the error when an action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanTrade catan={catan(game('main', { trade: offer() }))} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar oferta' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});
