import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanGenerator } from './CatanGenerator';
import { CatanBoard } from './CatanBoard';
import { CatanGame } from './CatanGame';
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

const catan = (patch: Partial<CatanState> = {}): CatanState => ({
  dice: null,
  total: null,
  producing: [],
  robber: [0, 0],
  payouts: {},
  buildings: [],
  players: ['rojo', 'azul'],
  board: {
    width: 300,
    height: 200,
    size: 70,
    tiles: [{ q: 0, r: 0, resource: 'wood', number: 6, x: 100, y: 100, corners }],
    vertices: [],
    ports: [
      {
        id: [
          [0, 0],
          [0, -1],
        ],
        kind: 'any',
        x1: 90,
        y1: 20,
        x2: 110,
        y2: 20,
        x: 100,
        y: 5,
      },
      {
        id: [
          [0, 0],
          [1, -1],
        ],
        kind: 'ore',
        x1: 120,
        y1: 30,
        x2: 130,
        y2: 50,
        x: 150,
        y: 30,
      },
    ],
  },
  ...patch,
});

describe('CatanGenerator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('renders nothing without a board', () => {
    const { container } = render(<CatanGenerator catan={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('starts with the official rules: 6 and 8 apart, the rest allowed', () => {
    render(<CatanGenerator catan={catan()} />);
    expect(screen.getByLabelText('6 y 8 pueden ir pegados')).not.toBeChecked();
    expect(screen.getByLabelText('Recursos iguales pueden ir pegados')).toBeChecked();
    expect(screen.getByLabelText('2 y 12 pueden ir pegados')).toBeChecked();
    expect(screen.getByLabelText('Números iguales pueden ir pegados')).toBeChecked();
    expect(screen.getByLabelText('Barajar los puertos')).toBeChecked();
    expect(screen.getByLabelText('Equilibrio')).toHaveValue('random');
  });

  it('sends the checklist and the balance level', async () => {
    render(<CatanGenerator catan={catan()} />);
    fireEvent.click(screen.getByLabelText('Recursos iguales pueden ir pegados'));
    fireEvent.click(screen.getByLabelText('2 y 12 pueden ir pegados'));
    fireEvent.click(screen.getByLabelText('6 y 8 pueden ir pegados'));
    fireEvent.change(screen.getByLabelText('Equilibrio'), { target: { value: 'very_fair' } });
    fireEvent.click(screen.getByRole('button', { name: 'Generar tablero' }));
    await waitFor(() =>
      expect(api.injectAction).toHaveBeenCalledWith(
        'CATAN_NEW_BOARD',
        JSON.stringify({
          allow_adjacent_same_resource: false,
          allow_adjacent_red: true,
          allow_adjacent_low: false,
          allow_adjacent_same_number: true,
          shuffle_ports: true,
          balance: 'very_fair',
        })
      )
    );
  });

  it('shows the report of the last board', () => {
    render(
      <CatanGenerator
        catan={catan({
          generator: {
            attempts: 120,
            satisfied: true,
            metrics: {
              resource_pips: { wood: 15, ore: 11 },
              resource_avg: { wood: 3.75, ore: 3.67 },
              avg_spread: 0.08,
              total_spread: 4,
              best_corner: 12,
              strong_corners: 2,
            },
          },
        })}
      />
    );
    const report = screen.getByTestId('generator-report');
    expect(report).toHaveTextContent('120 intentos');
    expect(report).toHaveTextContent('Madera: 15 puntos');
    expect(report).not.toHaveTextContent('demasiado estrictas');
  });

  it('warns when the rules could not all be met', () => {
    render(
      <CatanGenerator
        catan={catan({
          generator: {
            attempts: 6000,
            satisfied: false,
            metrics: {
              resource_pips: { wood: 15 },
              resource_avg: { wood: 3.75 },
              avg_spread: 2,
              total_spread: 9,
              best_corner: 13,
              strong_corners: 4,
            },
          },
        })}
      />
    );
    expect(screen.getByTestId('generator-report')).toHaveTextContent('demasiado estrictas');
  });

  it('shows the error when the action fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanGenerator catan={catan()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generar tablero' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});

describe('harbors on the board and in the bank trade', () => {
  it('draws every harbor with its ratio', () => {
    render(<CatanBoard catan={catan()} />);
    expect(screen.getByTestId('port-0')).toHaveTextContent('3:1');
    expect(screen.getByTestId('port-1')).toHaveTextContent('2:1');
    expect(screen.getByTestId('port-1')).toHaveAttribute('data-kind', 'ore');
  });

  it('shows the bank rate of the player in turn for the resource they give', () => {
    const state = catan({
      game: {
        phase: 'main',
        current_player: 'rojo',
        turn: 2,
        setup_step: 'settlement',
        discards: {},
        victims: [],
        winner: null,
        hint: '',
        costs: {},
      },
      stats: {
        rojo: {
          settlements: 1,
          cities: 0,
          roads: 0,
          cards: 0,
          points: 1,
          hand: {},
          rates: { wood: 2, brick: 3, sheep: 4, wheat: 4, ore: 4 },
          mode: 'simple',
        },
      },
    });
    render(<CatanGame catan={state} />);
    expect(screen.getByTestId('bank-rate')).toHaveTextContent('Banco 2:1');
    fireEvent.change(screen.getByLabelText('Dar'), { target: { value: 'ore' } });
    expect(screen.getByTestId('bank-rate')).toHaveTextContent('Banco 4:1');
  });
});
