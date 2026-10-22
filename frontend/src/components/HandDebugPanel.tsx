import React from 'react';
import type { HandDebug } from '../types/system';

// MediaPipe hand skeleton: landmark index pairs, grouped by finger.
const FINGER_BONES: Record<string, [number, number][]> = {
  Thumb: [
    [1, 2],
    [2, 3],
    [3, 4],
  ],
  Index: [
    [5, 6],
    [6, 7],
    [7, 8],
  ],
  Middle: [
    [9, 10],
    [10, 11],
    [11, 12],
  ],
  Ring: [
    [13, 14],
    [14, 15],
    [15, 16],
  ],
  Pinky: [
    [17, 18],
    [18, 19],
    [19, 20],
  ],
};
const PALM_BONES: [number, number][] = [
  [0, 1],
  [0, 5],
  [5, 9],
  [9, 13],
  [13, 17],
  [0, 17],
];

const FINGER_LABELS: Record<string, string> = {
  Thumb: 'Pulgar',
  Index: 'Índice',
  Middle: 'Medio',
  Ring: 'Anular',
  Pinky: 'Meñique',
};

const GESTURE_LABELS: Record<string, string> = {
  OPEN_PALM: 'Palma abierta',
  CLOSED_FIST: 'Puño',
  GUN: 'Pistola',
  POINTING: 'Señalar',
  VICTORY: 'Paz',
  ROCK: 'Rock',
  SHAKA: 'Shaka',
  UNKNOWN: 'No reconocido',
  NONE: 'Ninguno',
};

const GESTURE_USES: Record<string, string> = {
  OPEN_PALM: 'selecciona (puertas, menú)',
  CLOSED_FIST: 'mueve el mapa',
  GUN: 'sin uso por ahora',
  POINTING: 'mantener 1 s sobre un panel cambia su modo',
  VICTORY: 'mantener 2 s: paso 1 del menú',
  ROCK: 'mantener 1 s: tira los dados',
  SHAKA: 'paso 2 del menú',
};

const EXTENDED = '#16a34a';
const CURLED = '#9ca3af';

interface HandDebugPanelProps {
  hands?: HandDebug[] | null;
}

export const HandDebugPanel: React.FC<HandDebugPanelProps> = ({ hands }) => {
  const list = hands ?? [];

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        Depuración de manos
      </h3>
      {list.length === 0 ? (
        <p className="text-xs italic text-gray-400">No se ve ninguna mano.</p>
      ) : (
        <div className="space-y-3">
          {list.map((hand, index) => (
            <div key={index} data-testid={`hand-${index}`} className="text-xs text-black">
              <svg
                viewBox="0 0 1 1"
                className="w-full max-w-[220px] bg-gray-900 rounded"
                role="img"
                aria-label={`Esqueleto de la mano ${hand.label}`}
              >
                {PALM_BONES.map(([a, b]) => (
                  <line
                    key={`${a}-${b}`}
                    x1={hand.landmarks[a][0]}
                    y1={hand.landmarks[a][1]}
                    x2={hand.landmarks[b][0]}
                    y2={hand.landmarks[b][1]}
                    stroke="#d1d5db"
                    strokeWidth={0.012}
                  />
                ))}
                {Object.entries(FINGER_BONES).map(([finger, bones]) =>
                  bones.map(([a, b]) => (
                    <line
                      key={`${finger}-${a}-${b}`}
                      data-finger={finger}
                      data-extended={hand.fingers[finger] ? 'true' : 'false'}
                      x1={hand.landmarks[a][0]}
                      y1={hand.landmarks[a][1]}
                      x2={hand.landmarks[b][0]}
                      y2={hand.landmarks[b][1]}
                      stroke={hand.fingers[finger] ? EXTENDED : CURLED}
                      strokeWidth={0.02}
                      strokeLinecap="round"
                    />
                  ))
                )}
                {hand.landmarks.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={y} r={0.012} fill="#fff" />
                ))}
              </svg>
              <p className="mt-1">
                <span className="font-semibold">
                  Mano {hand.label === 'Left' ? 'izquierda' : 'derecha'}:
                </span>{' '}
                <span data-testid={`gesture-${index}`} className="font-bold text-blue-700">
                  {GESTURE_LABELS[hand.gesture] ?? hand.gesture}
                </span>
              </p>
              {GESTURE_USES[hand.gesture] && (
                <p className="text-gray-500">{GESTURE_USES[hand.gesture]}</p>
              )}
              <ul className="mt-1 flex flex-wrap gap-1">
                {Object.keys(FINGER_LABELS).map((finger) => (
                  <li
                    key={finger}
                    data-testid={`finger-${index}-${finger}`}
                    className={`px-1.5 py-0.5 rounded border ${
                      hand.fingers[finger]
                        ? 'border-green-600 bg-green-50 text-green-800'
                        : 'border-gray-300 text-gray-400'
                    }`}
                  >
                    {FINGER_LABELS[finger]}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
