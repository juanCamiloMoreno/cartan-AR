import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HandDebugPanel } from './HandDebugPanel';
import type { HandDebug } from '../types/system';

const hand = (gesture: string, fingers: Partial<Record<string, boolean>>): HandDebug => ({
  label: 'Right',
  gesture,
  fingers: { Thumb: false, Index: false, Middle: false, Ring: false, Pinky: false, ...fingers },
  landmarks: Array.from({ length: 21 }, (_, i) => [i / 21, 0.5] as [number, number]),
});

describe('HandDebugPanel', () => {
  it('says when no hand is visible', () => {
    render(<HandDebugPanel hands={[]} />);
    expect(screen.getByText('No se ve ninguna mano.')).toBeInTheDocument();
  });

  it('handles a missing list', () => {
    render(<HandDebugPanel hands={undefined} />);
    expect(screen.getByText('No se ve ninguna mano.')).toBeInTheDocument();
  });

  it('names the gesture and what it does', () => {
    render(<HandDebugPanel hands={[hand('ROCK', { Index: true, Pinky: true })]} />);
    expect(screen.getByTestId('gesture-0')).toHaveTextContent('Rock');
    expect(screen.getByText(/tira los dados/)).toBeInTheDocument();
  });

  it('marks which fingers the camera sees extended', () => {
    render(<HandDebugPanel hands={[hand('GUN', { Thumb: true, Index: true })]} />);
    expect(screen.getByTestId('finger-0-Thumb').className).toContain('green');
    expect(screen.getByTestId('finger-0-Index').className).toContain('green');
    expect(screen.getByTestId('finger-0-Pinky').className).not.toContain('green');
  });

  it('draws the skeleton with a different color for curled fingers', () => {
    const { container } = render(<HandDebugPanel hands={[hand('POINTING', { Index: true })]} />);
    const index = container.querySelector('line[data-finger="Index"]');
    const ring = container.querySelector('line[data-finger="Ring"]');
    expect(index).toHaveAttribute('data-extended', 'true');
    expect(ring).toHaveAttribute('data-extended', 'false');
    expect(index?.getAttribute('stroke')).not.toBe(ring?.getAttribute('stroke'));
    expect(container.querySelectorAll('circle')).toHaveLength(21);
  });

  it('shows one block per hand', () => {
    render(
      <HandDebugPanel
        hands={[hand('CLOSED_FIST', {}), hand('VICTORY', { Index: true, Middle: true })]}
      />
    );
    expect(screen.getByTestId('gesture-0')).toHaveTextContent('Puño');
    expect(screen.getByTestId('gesture-1')).toHaveTextContent('Paz');
  });

  it('shows an unknown gesture as received', () => {
    render(<HandDebugPanel hands={[hand('MYSTERY', {})]} />);
    expect(screen.getByTestId('gesture-0')).toHaveTextContent('MYSTERY');
  });
});
