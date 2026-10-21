import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CatanPanel } from './CatanPanel';
import * as api from '../services/api';
import type { CatanState } from '../types/system';

vi.mock('../services/api', () => ({
  injectAction: vi.fn(),
}));

const roll: CatanState = {
  buildings: [],
  players: ['rojo'],
  board: null,
  dice: [3, 3],
  total: 6,
  producing: [{ q: 0, r: 0, resource: 'wood', number: 6 }],
  robber: [0, 0],
  payouts: { ana: { wood: 1 } },
};

describe('CatanPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.injectAction).mockResolvedValue({});
  });

  it('shows a hint before the first roll', () => {
    render(<CatanPanel catan={null} />);
    expect(screen.getByText('Aún no se ha tirado.')).toBeInTheDocument();
  });

  it('rolls the dice from the button', async () => {
    render(<CatanPanel catan={null} />);
    fireEvent.click(screen.getByRole('button', { name: 'Tirar dados' }));
    await waitFor(() => expect(api.injectAction).toHaveBeenCalledWith('CATAN_ROLL', undefined));
  });

  it('sends physical dice entered by the player', async () => {
    render(<CatanPanel catan={null} />);
    fireEvent.change(screen.getByLabelText('Dado 1'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Dado 2'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Usar mis dados' }));
    await waitFor(() => expect(api.injectAction).toHaveBeenCalledWith('CATAN_ROLL', '4,2'));
  });

  it('shows the result and who receives resources', () => {
    render(<CatanPanel catan={roll} />);
    expect(screen.getByText('Salió 6 (3 + 3)')).toBeInTheDocument();
    expect(screen.getAllByText('Madera').length).toBeGreaterThan(0);
    expect(screen.getByText('ana: 1 Madera')).toBeInTheDocument();
  });

  it('warns about the robber on a 7', () => {
    render(<CatanPanel catan={{ ...roll, dice: [3, 4], total: 7, producing: [], payouts: {} }} />);
    expect(screen.getByText('¡Ladrón! Nadie produce.')).toBeInTheDocument();
  });

  it('shows an error if the request fails', async () => {
    vi.mocked(api.injectAction).mockRejectedValue(new Error('boom'));
    render(<CatanPanel catan={null} />);
    fireEvent.click(screen.getByRole('button', { name: 'Tirar dados' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});
