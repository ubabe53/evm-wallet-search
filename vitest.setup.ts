import "@testing-library/jest-dom/vitest";

// Cytoscape renders to canvas in the browser. jsdom does not implement canvas,
// so tests provide the minimal drawing surface needed for component smoke tests.
HTMLCanvasElement.prototype.getContext = (() => ({
  canvas: document.createElement("canvas"),
  clearRect: () => undefined,
  fillRect: () => undefined,
  save: () => undefined,
  restore: () => undefined,
  translate: () => undefined,
  scale: () => undefined,
  beginPath: () => undefined,
  closePath: () => undefined,
  moveTo: () => undefined,
  lineTo: () => undefined,
  arc: () => undefined,
  fill: () => undefined,
  stroke: () => undefined,
  measureText: () => ({ width: 24 }),
  setTransform: () => undefined,
  resetTransform: () => undefined,
})) as unknown as HTMLCanvasElement["getContext"];

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
